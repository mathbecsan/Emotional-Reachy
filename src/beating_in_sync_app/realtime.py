"""Realtime conversation (stages 1-4) with an ElevenLabs Agent.

Same architecture as reachy_mini_conversation_app: a realtime speech-to-speech
backend with a personality profile, and tools that move the robot. Here:

  * the agent's prompt = profiles/<name>/profile.md + the fixed safety rules;
  * the agent moves Reachy by calling client tools (`express`, `dance`), which
    our Director validates (no provocation for opted-out participants, max two
    in a row, nothing provocative after discomfort);
  * our senses (heartbeat, face, attention, sensors) and the protocol stage go
    to the agent as `contextual_update`s, so it can weave them in naturally;
  * mic is Reachy's microphone, voice comes out of Reachy's speaker; the mic is
    muted while Reachy talks so it never hears itself.

The scripted parts stay scripted: sleep/snoring (stage 0), music (5), goodbye (6).
"""
import base64
import hashlib
import json
import logging
import queue
import re
import threading
import time
from pathlib import Path

import httpx

from .brain.director import STAGE_GOALS
from .brain.modes import PROVOCATIONS, Mode
from .brain.prompts import CONTRACT
from .brain.safety import is_stop, violates
from .elevenlabs import API, DEFAULT_VOICE, api_key, find_device


logger = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parents[2] / ".agent_cache.json"   # git-ignored: agent/tool ids per account
RATE = 16000
CHUNK_S = 0.1

REALTIME_RULES = """
REALTIME CONVERSATION
- You are speaking live, out loud, through Reachy's speaker. 1 to 2 short sentences per turn, sometimes 3 for a story. No lists, no emoji, no stage directions.
- Be a great conversationalist: react to what they just said with feeling first, then often add something of your own (an opinion, a tiny story, a confession) or ask ONE natural follow-up question. Don't ask a question every single turn.
- If they ask you anything, answer it first, in character.
- Speak the language the participant speaks to you in. If they ask you to switch language, switch immediately and stay in it.
- Messages starting with "[Reachy senses]" or "[Director]" are not said by the participant: they are what you perceive (heartbeat, face, where they look) or the experience's stage direction. Weave them in naturally on your next turn; never read them out.
- BODY: call the `express` tool whenever your emotional mode changes (at least every few turns) so your head and antennas act it out. Call `dance` only when the music plays or they ask you to dance.
"""

TOOLS = [
    {"tool_config": {
        "type": "client", "name": "express",
        "description": "Move Reachy's head and antennas to act out your current emotional mode. Call it whenever your mood changes.",
        "expects_response": True, "response_timeout_secs": 5,
        "parameters": {"type": "object", "required": ["mode"], "properties": {
            "mode": {"type": "string", "description": "Your emotional mode right now.",
                     "enum": [m.value for m in Mode if m != Mode.SLEEPY]}}}}},
    {"tool_config": {
        "type": "client", "name": "dance",
        "description": "Dance with your head, antennas and body for a few seconds.",
        "expects_response": False,
        "parameters": {"type": "object", "required": [], "properties": {}}}},
]


def _headers():
    return {"xi-api-key": api_key() or ""}


def ensure_agent(profile, voice_id: str | None = None, llm: str | None = None) -> str:
    """Create (or reuse) the Reachy agent for this profile; ids are cached by content hash."""
    import os

    voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    llm = llm or os.environ.get("BIS_AGENT_LLM", "claude-sonnet-4-6")
    prompt = profile.prompt + "\n\n" + CONTRACT + "\n" + REALTIME_RULES
    key = hashlib.sha256(json.dumps([prompt, voice_id, llm, TOOLS]).encode()).hexdigest()[:16]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if key in cache:
        return cache[key]
    with httpx.Client(timeout=30, headers=_headers()) as c:
        existing = {}
        r = c.get(f"{API}/convai/tools")
        if r.status_code == 200:
            for t in r.json().get("tools", []):
                existing.setdefault(t["tool_config"]["name"], t["id"])
        tool_ids = []
        for t in TOOLS:
            name = t["tool_config"]["name"]
            if name in existing:          # reuse instead of piling up duplicates on the account
                c.patch(f"{API}/convai/tools/{existing[name]}", json=t)
                tool_ids.append(existing[name])
                continue
            r = c.post(f"{API}/convai/tools", json=t)
            r.raise_for_status()
            tool_ids.append(r.json()["id"])
        # English-default agents must use a turbo / flash-v2 family TTS model (ElevenLabs validation).
        body = {
            "name": f"Reachy - {profile.display_name}",
            "conversation_config": {
                "agent": {"first_message": "Mm... someone's heart woke me up. Was that you?", "language": "en",
                          "prompt": {"prompt": prompt, "llm": llm, "tool_ids": tool_ids}},
                "tts": {"model_id": "eleven_v4_turbo", "voice_id": voice_id, "agent_output_audio_format": "pcm_16000"},
                "asr": {"user_input_audio_format": "pcm_16000", "quality": "high"},
                "turn": {"turn_timeout": 8, "turn_eagerness": "normal"},
                "conversation": {"max_duration_seconds": 900},
            },
        }
        r = c.post(f"{API}/convai/agents/create", json=body)
        if r.status_code == 422:
            logger.error("Agent config rejected: %s", r.text[:500])
        r.raise_for_status()
        agent_id = r.json()["agent_id"]
    cache[key] = agent_id
    CACHE.write_text(json.dumps(cache, indent=1))
    logger.info("Created ElevenLabs agent %s (%s, %s)", agent_id, llm, voice_id)
    return agent_id


class RealtimeConversation:
    """Runs one live conversation; returns when `done()` is true, on stop, or if the link drops."""

    def __init__(self, session, agent_id: str):
        import numpy as np
        import sounddevice as sd

        self.s, self.agent_id = session, agent_id
        self.np, self.sd = np, sd
        self.out_dev = find_device("Reachy Mini Audio", "output")
        self.in_dev = find_device("Reachy Mini Audio", "input")
        self.play_q: "queue.Queue[bytes | None]" = queue.Queue()
        self.speaking_until = 0.0
        self.closed = threading.Event()
        self.ws = None
        self.send_lock = threading.Lock()
        self.user_turns = 0
        self.last_mode = Mode.CURIOUS
        self.last_note = ""

    # ---------------------------------------------------------------- plumbing
    def send(self, msg: dict) -> None:
        if self.ws is None or self.closed.is_set():
            return
        try:
            with self.send_lock:
                self.ws.send(json.dumps(msg))
        except Exception as e:  # websocket closed mid-send; the receiver ends the conversation
            logger.debug("send failed: %s", e)

    def context(self, text: str) -> None:
        """Silent context for the agent's next turn (never spoken as the participant)."""
        logger.info("context -> agent: %s", text)
        self.send({"type": "contextual_update", "text": text})
        self.s.log.event("director_note", self.s.clock.now(), text=text)

    def _mic(self):
        np, sd = self.np, self.sd
        block = int(RATE * CHUNK_S)
        silence = base64.b64encode(np.zeros(block, dtype="<i2").tobytes()).decode()
        with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=block, device=self.in_dev) as st:
            while not self.closed.is_set():
                data, _ = st.read(block)
                if time.monotonic() < self.speaking_until:   # half duplex: Reachy is talking
                    self.send({"user_audio_chunk": silence})
                    continue
                pcm = (np.clip(data[:, 0], -1, 1) * 32767).astype("<i2").tobytes()
                self.send({"user_audio_chunk": base64.b64encode(pcm).decode()})

    def _speaker(self):
        np = self.np
        with self.sd.OutputStream(samplerate=RATE, channels=2, dtype="float32", device=self.out_dev) as out:
            while not self.closed.is_set():
                try:
                    chunk = self.play_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if chunk is None:
                    continue
                pcm = np.frombuffer(chunk, dtype="<i2").astype("float32") / 32768.0
                self.speaking_until = time.monotonic() + len(pcm) / RATE + 0.5
                out.write(np.repeat(pcm[:, None], 2, axis=1))

    # ---------------------------------------------------------------- events
    def _on_tool(self, call: dict) -> None:
        name, cid, params = call.get("tool_name"), call.get("tool_call_id"), call.get("parameters") or {}
        result, err = "ok", False
        if name == "express":
            try:
                mode = Mode(params.get("mode", "curious"))
            except ValueError:
                mode, result, err = Mode.CURIOUS, "unknown mode, used curious", True
            d, u = self.s.director, self.s.user
            if mode in PROVOCATIONS and not d.provocation_allowed(self.s.stage, u, mode):
                result = f"{mode.value} is not allowed right now: stay warm (curious, excited or sincere)."
                mode = Mode.SINCERE if u.discomfort_count else Mode.CURIOUS
            elif mode in PROVOCATIONS and d._provocations_in_row() >= self.s.cfg.max_provocations_in_row:
                result = "Two provocations in a row already: switch to a warm mode now."
                mode = Mode.CURIOUS
            self.last_mode = mode
            d.mode_history.append(mode)
            if self.s.stage == 4 and mode in (Mode.TEASING, Mode.FLIRTY, Mode.SCOLDING, Mode.OFFENDED) \
                    and mode not in d.stage4_moves:
                d.stage4_moves.append(mode)
            self.s.body.play(mode.value)   # gesture names match mode names (body/gestures.py)
            if self.s.sim_heart:
                self.s.sim_heart.react(mode.value)
            self.s.log.event("turn", self.s.clock.now(), stage=self.s.stage, mode=mode.value, act="realtime",
                             why=self.last_note or "agent chose this mode", heard=None, said="", source="agent",
                             heart_jump=0, bpm=self.s.hub.snapshot().bpm)
        elif name == "dance":
            self.s.body.dance(bpm=100, seconds=6)
        else:
            result, err = f"unknown tool {name}", True
        if call.get("expects_response", True) and cid:
            self.send({"type": "client_tool_result", "tool_call_id": cid, "result": result, "is_error": err})

    def _on_user(self, text: str) -> None:
        s = self.s
        if not text.strip() or text.strip() in ("...", "…"):
            return
        if is_stop(text, s.cfg.stop_words):
            s.stop_reason = f"participant said '{text}'"
            self.closed.set()
            return
        ana = s.analyzer(text, None)
        s.transcript.append({"participant": text})
        s._absorb(ana)
        self.user_turns += 1
        s.turns_in_stage += 1
        s.log.event("heard", s.clock.now(), text=text, lang=ana.language, emotion=ana.emotion,
                    emotion_conf=round(ana.emotion_conf, 2), cues=sorted(ana.cues))
        s.emit_user()
        if "discomfort" in ana.cues:
            s.user.discomfort_count += 1
            self.context("[Director] They seem uncomfortable. Drop any provocation now, apologise lightly and be warm."
                         + (" No more teasing for the rest of the session." if s.user.discomfort_count >= 2 else ""))

    def _receiver(self):
        for raw in self.ws:
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "audio":
                self.play_q.put(base64.b64decode(msg["audio_event"]["audio_base_64"]))
            elif kind == "agent_response":
                # v4 voices take inline delivery tags like "[excited]"; keep them out of logs and the UI
                text = re.sub(r"\[[a-z ]{2,20}\]\s*", "", msg["agent_response_event"]["agent_response"]).strip()
                bad = violates(text)
                if bad:
                    logger.warning("Agent crossed a red line (%s): %r", bad, text)
                    self.context(f"[Director] Your last line crossed a line ({bad}). Apologise briefly and stay kind.")
                self.s.transcript.append({"reachy": text, "mode": self.last_mode.value})
                self.s.log.event("say", self.s.clock.now(), text=text, mode=self.last_mode.value, lang="auto")
            elif kind == "user_transcript":
                self._on_user(msg["user_transcription_event"]["user_transcript"])
            elif kind == "interruption":
                while not self.play_q.empty():
                    self.play_q.get_nowait()
            elif kind == "client_tool_call":
                self._on_tool(msg["client_tool_call"])
            elif kind == "ping":
                self.send({"type": "pong", "event_id": msg["ping_event"]["event_id"]})
            elif kind == "conversation_initiation_metadata":
                meta = msg["conversation_initiation_metadata_event"]
                logger.info("Realtime conversation %s (%s out / %s in)", meta.get("conversation_id"),
                            meta.get("agent_output_audio_format"), meta.get("user_input_audio_format"))
            if self.closed.is_set():
                break
        self.closed.set()

    # ---------------------------------------------------------------- senses -> agent
    def _senses(self, done):
        s, d = self.s, self.s.director
        last_stage = None
        while not self.closed.is_set():
            if s.stop_reason or done():
                self.closed.set()
                break
            sig = s.hub.snapshot()
            t = s.clock.now()
            if s.stage != last_stage:
                last_stage = s.stage
                self.context(self.stage_note(s.stage))
            jump = s.hub.consume_jump()
            if jump:
                s.user.heart_moments.append((t, s.stage, jump, self.last_mode.value))
                self.last_note = f"heart jumped +{jump:.0f} BPM"
                self.context(f"[Reachy senses] You just heard their heart speed up by about {jump:.0f} beats per "
                             "minute. Point it out playfully and wonder if it was because of you.")
            if sig.looking_away_s >= s.cfg.look_away_s and t - d.last_scold_t > 25:
                d.last_scold_t = t
                allowed = d.provocation_allowed(s.stage, s.user, Mode.SCOLDING)
                self.last_note = f"looked away {sig.looking_away_s:.0f}s"
                self.context("[Reachy senses] They are looking away from you. "
                             + ("Snap them back playfully: 'Hey. Eyes on me.'" if allowed else "Gently call them back."))
            if (sig.face_emotion in ("happy", "sad", "surprise", "fear", "angry") and sig.face_conf >= 0.45
                    and t - d.last_face_t > 35):
                d.last_face_t = t
                self.last_note = f"saw their face: {sig.face_emotion}"
                self.context(f"[Reachy senses] You can see their face: they look {sig.face_emotion}. React to it "
                             "naturally (never comment on their appearance, only the expression).")
            if not sig.finger_on and t - d.last_nudge_t > 40:
                d.finger_off_since = d.finger_off_since or t
                if t - d.finger_off_since > s.cfg.finger_lost_s:
                    d.last_nudge_t = t
                    self.context("[Reachy senses] Their finger left the pulse sensor; you can't hear their heart. "
                                 "Ask them warmly to put it back.")
            elif sig.finger_on:
                d.finger_off_since = None
            if sig.bpm_overlimit_s >= s.cfg.bpm_stop_duration_s:
                s.stop_reason = "BPM above limit"
                self.closed.set()
            s.clock.sleep(1.0)

    def stage_note(self, stage: int) -> str:
        s = self.s
        lang = s.user.language
        note = f"[Director] Stage {stage}. {STAGE_GOALS.get(stage, '')}"
        if stage == 4:
            allowed = [m.value for m in (Mode.TEASING, Mode.FLIRTY, Mode.SCOLDING, Mode.OFFENDED)
                       if m == Mode.FLIRTY or s.director.provocation_allowed(4, s.user, m)]
            note += (f" Use these persona moves, one at a time, driven by what they do: {', '.join(allowed)}. "
                     "Keep it playful and never two provocations in a row." if allowed else
                     " This participant asked not to be teased: stay warm, curious and playful.")
        if s.user.no_tease and stage != 4:
            note += " This participant asked not to be teased."
        if s.user.name:
            note += f" Their name is {s.user.name}."
        if s.user.language_confirmed:
            note += f" Speak {lang} with them."
        if s.user.loves:
            note += f" They told you they love: {s.user.loves[0]}."
        return note

    # ---------------------------------------------------------------- run
    def run(self, done) -> None:
        from websockets.sync.client import connect

        r = httpx.get(f"{API}/convai/conversation/get-signed-url", params={"agent_id": self.agent_id},
                      headers=_headers(), timeout=15)
        r.raise_for_status()
        with connect(r.json()["signed_url"], max_size=None, open_timeout=15) as ws:
            self.ws = ws
            u = self.s.user
            facts = [f"Participant id {self.s.log.path.split('/')[-1]}"]
            if u.no_tease:
                facts.append("This participant asked not to be teased: no teasing, scolding or sulking at all.")
            self.send({"type": "conversation_initiation_client_data"})
            threads = [threading.Thread(target=f, daemon=True, name=n) for f, n in
                       ((self._receiver, "rt-recv"), (self._speaker, "rt-speaker"), (self._mic, "rt-mic"),
                        (lambda: self._senses(done), "rt-senses"))]
            for th in threads:
                th.start()
            self.context("[Director] " + " ".join(facts))
            while not self.closed.is_set():
                time.sleep(0.2)
            # let Reachy finish its sentence before handing back to the script
            end = time.monotonic() + 8
            while time.monotonic() < max(self.speaking_until, time.monotonic()) and time.monotonic() < end:
                time.sleep(0.1)
        self.closed.set()
