"""Assembles one session from options and runs it on a worker thread.

Shared by the CLI (main.py) and the web UI (web.py), so a session started
from the browser and one started from the terminal are wired identically.
"""
import logging
import random
import threading
from dataclasses import asdict, dataclass

import anthropic
import httpx

from . import elevenlabs
from .body.moves import ReachyMiniBody, SimBody
from .body.voice import MacVoice, SimVoice
from .brain.activities import ACTIVITIES, style_prompt, switch_every_for
from .brain.persona_show import PersonaShow
from .brain.personas import normalize_cast
from .brain.user_model import UserModel
from .brain.writer import ClaudeWriter, TemplateWriter
from .clock import Clock
from .config import Config
from .events import EventBus
from .perception.heart import HeartAnalyzer, SimHeartSource
from .perception.pulse_sensor import ArduinoPulseSource, SimulatedArduino
from .perception.speech import ConsoleListener, ScriptedListener, WebListener
from .perception.text import TextAnalyzer, TextEmotion
from .personality import MODE_PERSONALITIES, default_selection, load_profile
from .session import Session
from .session_log import SessionLog
from .signals import SignalHub


logger = logging.getLogger(__name__)


@dataclass
class SessionOptions:
    participant: str = "P00"
    profile: str = "beating_in_sync"
    no_tease: bool = False          # pre-interview answer: would rather not be teased
    language_hint: str = "en"       # language Reachy starts in (before introductions)
    llm: bool = True                # Claude writes the lines; False = offline templates
    heart: str = "sim"              # sim | arduino | arduino-sim (real beat pipeline, synthetic IR)
    camera: bool = True             # face emotion + attention (needs the vision extra)
    conversation: str = "realtime"  # realtime (ElevenLabs agent, fluid) | scripted (Director + templates/Claude)
    listener: str = "elevenlabs"    # elevenlabs (mic + typed) | web (typed) | console | mic (whisper) | scenario
    scenario: str | None = None
    voice: str = "elevenlabs"       # elevenlabs (Reachy's speaker) | mac (macOS `say`) | sim (text only)
    time_scale: float = 1.0
    heart_port: str | None = None   # Arduino serial port; None = auto-detect
    pulse_mode: str | None = None   # wake | one | two; None = Config.pulse_mode
    personas: list[str] | None = None   # cast / persona moves for this session; None = the profile's default
    switch_every: int | None = None     # Off-Brand: exchanges per persona; None = profile default
    heart_wake: bool = True             # Reachy sleeps (and snores) until a heartbeat arrives
    music: bool | None = None           # stage 5 dance; None = profile default
    motion_intensity: float = 1.0       # how big Reachy's gestures are (0.3 subtle - 1.3 dramatic)
    motion_speed: float = 1.0           # how fast they play (0.5 slow - 1.5 fast)
    voice_id: str | None = None         # ElevenLabs voice; None = default (Callum)
    tone: str = "playful"               # warm | playful | bold
    chattiness: str = "normal"          # brief | normal | chatty
    duration: str | None = None         # quick | standard | long -> sets switch_every
    activities: list[str] | None = None # brain/activities.py keys


class SessionRunner:
    """Owns at most one running session. The robot connection outlives sessions."""

    def __init__(self, bus: EventBus, cfg: Config, robot=None):
        self.bus, self.cfg, self.robot = bus, cfg, robot
        self.session: Session | None = None
        self.web_listener: WebListener | None = None
        self.thread: threading.Thread | None = None
        self.pulse: ArduinoPulseSource | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, opts: SessionOptions) -> None:
        if self.running:
            raise RuntimeError("a session is already running")
        session, listener, analyzer = self.build(opts)
        self.session = session

        def run() -> None:
            self.bus.emit("session", status="running", **asdict(opts))
            try:
                session.run(listener, analyzer)
            except Exception:
                logger.exception("Session crashed")
                self.bus.emit("error", message="Session crashed, see server log.")
            finally:
                if self.pulse is not None:
                    self.pulse.stop()
                if session.sim_heart is not None:
                    session.sim_heart.stop()
                self.bus.emit("session", status="ended", log=session.log.path, **asdict(opts))
                session.log.close()

        self.thread = threading.Thread(target=run, daemon=True, name="session")
        self.thread.start()

    def build(self, opts: SessionOptions):
        cfg = Config(**{**asdict(self.cfg), "time_scale": opts.time_scale})
        clock = Clock(cfg.time_scale)
        hub = SignalHub()
        rng = random.Random(cfg.seed)
        log = SessionLog(cfg.sessions_dir, opts.participant, self.bus)
        heart = HeartAnalyzer(cfg, hub, clock, log)
        sim_heart = None
        mode = opts.pulse_mode or cfg.pulse_mode
        if opts.heart == "arduino":
            self.pulse = ArduinoPulseSource(heart, hub, log, clock, opts.heart_port or cfg.heart_port, mode,
                                            finger_min=cfg.finger_min)
        else:
            # The simulated heart reacts to Reachy's modes; in arduino-sim it feeds synthetic IR
            # through the real beat detector instead of reporting BPM directly.
            sim_heart = SimHeartSource(heart, clock, cfg.seed, push=opts.heart == "sim")
            sim_heart.start()
            self.pulse = None
            if opts.heart == "arduino-sim":
                fake = SimulatedArduino(sim_heart.current_bpm, sim_heart.fingers)
                self.pulse = ArduinoPulseSource(heart, hub, log, clock, None, mode, simulated=fake,
                                                finger_min=cfg.finger_min)
        if self.pulse is not None:
            self.pulse.start()
        if opts.camera:
            from .perception.face import FacePerception

            FacePerception(cfg, hub, session_log=log).start()

        profile = load_profile(opts.profile)
        selection = opts.personas if opts.personas is not None else default_selection(profile)
        show, flirty = None, True
        acts = [a for a in (opts.activities or []) if a in ACTIVITIES]
        if profile.kind == "personas":
            n = len(normalize_cast(selection, opts.no_tease))
            every = opts.switch_every or switch_every_for(opts.duration, n) or profile.switch_every
            show = PersonaShow(selection, every, rng, opts.no_tease)
            show.activities = [a for a in acts if a != "music_dance"]
            show.style = style_prompt(opts.tone, opts.chattiness, acts)
            log.event("cast", 0.0, cast=show.cast, switch_every=show.switch_every)
        else:
            # Facilitator's pick of persona moves for stage 4 (Flirty + the provocations).
            profile.provocations = [k for k in selection if k in MODE_PERSONALITIES and k != "flirty"]
            flirty = "flirty" in selection
        templates = TemplateWriter(rng)
        writer = templates
        if opts.llm:
            try:
                writer = ClaudeWriter(cfg, templates, profile)
                writer.notify = lambda message: self.bus.emit("error", message=message)
            except anthropic.AnthropicError as e:
                logger.warning("Claude client unavailable (%s); using offline templates.", e)
        if self.robot is not None and not self.robot_ok():
            try:                       # the daemon restarted since we connected: reconnect once
                self.connect_robot()
            except Exception as e:     # still unreachable: the session runs, Reachy just won't move
                logger.error("Reachy unreachable: %s", e)
                self.bus.emit("error", message="Reachy isn't reachable: the session runs without movement. "
                                               "Turn the robot on in Reachy Mini Control.")
        body = ReachyMiniBody(self.robot, cfg.use_emotion_library, rng) if self.robot is not None else SimBody(clock)
        body.intensity = max(0.3, min(1.3, float(opts.motion_intensity)))
        body.speed = max(0.5, min(1.5, float(opts.motion_speed)))
        has_el = elevenlabs.api_key() is not None
        if (opts.voice == "elevenlabs" or opts.listener == "elevenlabs") and not has_el:
            self.bus.emit("error", message="No ELEVENLABS_API_KEY in .env: using the macOS voice and typed input.")
        if opts.voice == "elevenlabs" and has_el:
            voice = elevenlabs.ElevenLabsVoice(clock, voice_id=opts.voice_id)
        elif opts.voice in ("mac", "elevenlabs"):
            voice = MacVoice(clock)
        else:
            voice = SimVoice(clock)
        user = UserModel(language=opts.language_hint, no_tease=opts.no_tease)
        agent_id = None
        if opts.conversation == "realtime" and has_el and opts.listener not in ("scenario", "console", "web"):
            try:
                from .realtime import ensure_agent

                agent_id = ensure_agent(profile, voice_id=opts.voice_id)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                logger.error("Could not set up the live agent (%s); using the scripted conversation.", e)
                self.bus.emit("error", message=f"Live conversation unavailable ({e}); using scripted mode.")
        session = Session(cfg, clock, hub, heart, body, voice, writer, log, user, profile, sim_heart, rng,
                          realtime_agent=agent_id, show=show, heart_wake=opts.heart_wake,
                          music=("music_dance" in acts) if opts.activities is not None else
                          (profile.music if opts.music is None else opts.music), flirty=flirty)

        if opts.listener == "scenario":
            listener = ScriptedListener(opts.scenario, session.on_command, clock)
        elif opts.listener == "console":
            listener = ConsoleListener(session.on_command, clock, opts.language_hint)
        elif opts.listener == "elevenlabs" and has_el:
            listener = self.web_listener = elevenlabs.ElevenLabsListener(clock)
        elif opts.listener == "mic":
            from .perception.speech import WhisperListener

            listener = WhisperListener(session.on_command, clock, cfg.whisper_model)
        else:
            listener = self.web_listener = WebListener(clock)
        return session, listener, TextAnalyzer(TextEmotion(cfg.ter_model_dir))

    def command(self, cmd: str) -> None:
        if self.session is None:
            raise RuntimeError("no session")
        self.session.on_command(cmd)

    def participant_says(self, text: str, language: str | None) -> None:
        if self.web_listener is None or not self.running:
            raise RuntimeError("no session listening for typed input")
        self.web_listener.push(text, language)

    def robot_ok(self) -> bool:
        """True if the robot link still answers (the daemon may have restarted since we connected)."""
        if self.robot is None:
            return False
        try:
            self.robot.get_current_joint_positions()
            return True
        except Exception:  # SDK raises ConnectionError / TimeoutError / RuntimeError when the daemon is gone
            return False

    def connect_robot(self, robot_name: str | None = None) -> None:
        """(Re)connect to Reachy, e.g. after the daemon was restarted. No session may be running."""
        if self.running:
            raise RuntimeError("stop the session first")
        from reachy_mini import ReachyMini

        old, self.robot, self._preview_body = self.robot, None, None
        if old is not None:
            try:
                old.client.disconnect()
            except Exception as e:  # stale link: nothing to clean up
                logger.debug("old robot link: %s", e)
        self.robot = ReachyMini(media_backend="no_media", **({"robot_name": robot_name} if robot_name else {}))
        logger.info("Connected to Reachy Mini")

    def wait_preview(self) -> None:
        """Block until a test gesture (e.g. the setup nod) has finished playing."""
        body = getattr(self, "_preview_body", None)
        if body is not None:
            body.wait()

    def preview_gesture(self, name: str, intensity: float = 1.0, speed: float = 1.0) -> None:
        """Try a gesture from the persona catalog (on the running session's body, or a spare one)."""
        from .body.gestures import GESTURES
        from .body.moves import styled

        seq = styled(GESTURES[name], max(0.3, min(1.3, intensity)), max(0.5, min(1.5, speed)))
        if self.session is not None and self.running:
            self.session.body.play(seq)
            return
        if self.robot is None:
            raise RuntimeError("Reachy isn't connected: press Connect Reachy on the Check setup page")
        if getattr(self, "_preview_body", None) is None:
            self._preview_body = ReachyMiniBody(self.robot, use_emotion_library=False)
        self._preview_body.play(seq)

    def wait(self) -> None:
        if self.thread:
            self.thread.join()
