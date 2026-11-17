"""Assembles one session from options and runs it on a worker thread.

Shared by the CLI (main.py) and the web UI (web.py), so a session started
from the browser and one started from the terminal are wired identically.
"""
import logging
import random
import threading
from dataclasses import asdict, dataclass

import anthropic

from .body.moves import ReachyMiniBody, SimBody
from .body.voice import MacVoice, SimVoice
from .brain.user_model import UserModel
from .brain.writer import ClaudeWriter, TemplateWriter
from .clock import Clock
from .config import Config
from .events import EventBus
from .perception.heart import HeartAnalyzer, SimHeartSource
from .perception.pulse_sensor import ArduinoPulseSource, SimulatedArduino
from .perception.speech import ConsoleListener, ScriptedListener, WebListener
from .perception.text import TextAnalyzer, TextEmotion
from .personality import load_profile
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
    camera: bool = False            # face emotion + attention (needs the vision extra)
    listener: str = "web"           # web | console | mic | scenario
    scenario: str | None = None
    voice: str = "sim"              # sim (text only) | mac (macOS `say`)
    time_scale: float = 1.0
    heart_port: str | None = None   # Arduino serial port; None = auto-detect
    pulse_mode: str | None = None   # wake | one | two; None = Config.pulse_mode


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

            FacePerception(cfg, hub).start()

        profile = load_profile(opts.profile)
        templates = TemplateWriter(rng)
        writer = templates
        if opts.llm:
            try:
                writer = ClaudeWriter(cfg, templates, profile)
                writer.notify = lambda message: self.bus.emit("error", message=message)
            except anthropic.AnthropicError as e:
                logger.warning("Claude client unavailable (%s); using offline templates.", e)
        body = ReachyMiniBody(self.robot, cfg.use_emotion_library, rng) if self.robot is not None else SimBody(clock)
        voice = MacVoice(clock) if opts.voice == "mac" else SimVoice(clock)
        user = UserModel(language=opts.language_hint, no_tease=opts.no_tease)
        session = Session(cfg, clock, hub, heart, body, voice, writer, log, user, profile, sim_heart, rng)

        if opts.listener == "scenario":
            listener = ScriptedListener(opts.scenario, session.on_command, clock)
        elif opts.listener == "console":
            listener = ConsoleListener(session.on_command, clock, opts.language_hint)
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

    def wait(self) -> None:
        if self.thread:
            self.thread.join()
