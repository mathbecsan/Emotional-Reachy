"""Hearing the participant.

listen(timeout) returns an Utterance, or None if the participant stayed
silent (silence is a signal too: Reachy takes the initiative).

Listeners:
  * ConsoleListener  - type as the participant. Prefix a line with [es] / [fr]
                       to say which language you are "speaking". Lines that start
                       with "/" are facilitator commands (see README).
  * ScriptedListener - plays a JSON scenario (automated testing).
  * WhisperListener  - microphone + faster-whisper; whisper also identifies the
                       spoken language, which drives the Curious mode.
"""
import json
import re
import select
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Utterance:
    text: str
    language: Optional[str] = None
    duration_s: float = 0.0


LANG_PREFIX = re.compile(r"^\[(\w\w)\]\s*")


def _split_lang(line: str):
    m = LANG_PREFIX.match(line)
    return (line[m.end():], m.group(1).lower()) if m else (line, None)


class ConsoleListener:
    def __init__(self, on_command: Callable[[str], None], clock, default_lang="en"):
        self.on_command, self.clock, self.lang = on_command, clock, default_lang

    def listen(self, timeout: float) -> Optional[Utterance]:
        deadline = time.monotonic() + timeout / self.clock.scale
        print("  you> ", end="", flush=True)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                print("(silence)")
                return None
            r, _, _ = select.select([sys.stdin], [], [], left)
            if not r:
                continue
            line = sys.stdin.readline().strip()
            if not line:
                print("  you> ", end="", flush=True)
                continue
            if line.startswith("/"):
                self.on_command(line)
                print("  you> ", end="", flush=True)
                continue
            text, lang = _split_lang(line)
            if lang:
                self.lang = lang
            return Utterance(text, self.lang, duration_s=len(text.split()) * 0.4)


class ScriptedListener:
    """Scenario = list of steps:
        {"say": "Hola, soy Tomas", "lang": "es"}
        {"silence": true}                       -> participant says nothing this turn
        {"cmd": "/look away 4"}                 -> facilitator / sensor event, then keep going
    """

    def __init__(self, path: str, on_command: Callable[[str], None], clock):
        self.steps = json.load(open(path))
        self.on_command, self.clock = on_command, clock
        self.lang = "en"
        self.i = 0

    @property
    def done(self):
        return self.i >= len(self.steps)

    def listen(self, timeout: float) -> Optional[Utterance]:
        while self.i < len(self.steps):
            step = self.steps[self.i]
            self.i += 1
            if "cmd" in step:
                self.on_command(step["cmd"])
                continue
            if step.get("silence"):
                self.clock.sleep(timeout)
                return None
            self.lang = step.get("lang", self.lang)
            self.clock.sleep(step.get("delay", 1.5))
            return Utterance(step["say"], self.lang, duration_s=len(step["say"].split()) * 0.4)
        self.clock.sleep(timeout)
        return None


class WhisperListener:
    """Energy-based endpointing + faster-whisper transcription with language ID."""

    def __init__(self, on_command, clock, model_size="small", samplerate=16000,
                 silence_rms=0.012, end_silence_s=1.1, max_s=25.0):
        import numpy as np
        import sounddevice as sd
        from faster_whisper import WhisperModel
        self.np, self.sd = np, sd
        self.model = WhisperModel(model_size, compute_type="int8")
        self.on_command, self.clock = on_command, clock
        self.sr, self.th, self.end_s, self.max_s = samplerate, silence_rms, end_silence_s, max_s
        self.lang = None

    def listen(self, timeout: float) -> Optional[Utterance]:
        np, sd = self.np, self.sd
        block = int(self.sr * 0.1)
        chunks, started, quiet, t0 = [], False, 0.0, time.monotonic()
        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", blocksize=block) as st:
            while True:
                data, _ = st.read(block)
                rms = float(np.sqrt(np.mean(data ** 2)))
                if rms > self.th:
                    started, quiet = True, 0.0
                elif started:
                    quiet += 0.1
                if started:
                    chunks.append(data[:, 0].copy())
                el = time.monotonic() - t0
                if not started and el > timeout:
                    return None
                if started and (quiet >= self.end_s or len(chunks) * 0.1 > self.max_s):
                    break
        audio = np.concatenate(chunks)
        segs, info = self.model.transcribe(audio, beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segs).strip()
        if not text:
            return None
        self.lang = info.language if info.language_probability > 0.5 else (self.lang or info.language)
        return Utterance(text, self.lang, duration_s=len(audio) / self.sr)


class WebListener:
    """Participant lines typed in the web UI (rehearsals / Wizard-of-Oz runs)."""

    def __init__(self, clock):
        import queue
        self.clock = clock
        self.queue: "queue.Queue[Utterance]" = queue.Queue()
        self._empty = queue.Empty

    def push(self, text: str, language: Optional[str] = None):
        self.queue.put(Utterance(text, language, duration_s=len(text.split()) * 0.4))

    def listen(self, timeout: float) -> Optional[Utterance]:
        try:
            return self.queue.get(timeout=timeout / self.clock.scale)
        except self._empty:
            return None
