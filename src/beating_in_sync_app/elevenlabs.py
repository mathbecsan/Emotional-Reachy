"""ElevenLabs speech for Reachy: multilingual text-to-speech (its voice) and
speech-to-text with language detection (its ears).

The API key is read from the environment (ELEVENLABS_API_KEY, set in .env);
it is never stored in code or logs.
"""
import hashlib
import io
import logging
import os
import queue
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import json

import httpx

from .body.voice import MacVoice
from .perception.speech import Utterance

CLIP_DIR = Path(__file__).resolve().parents[2] / ".voice_cache"   # git-ignored: pre-recorded predictable lines
PLAY_MARGIN_S = 12.0     # speech may run this long past its expected length before it's cut off


logger = logging.getLogger(__name__)

API = "https://api.elevenlabs.io/v1"
DEFAULT_VOICE = "N2lVS1w4EtoT3dr4eOWO"   # "Callum - Husky Trickster": theatrical, playful
TTS_MODEL = "eleven_flash_v2_5"          # low latency, multilingual
STT_MODEL = "scribe_v1"

# Scribe returns ISO 639-3; the rest of the app uses ISO 639-1.
ISO3_TO_1 = {"eng": "en", "spa": "es", "fra": "fr", "ita": "it", "deu": "de", "por": "pt", "cmn": "zh", "zho": "zh",
             "yue": "zh", "jpn": "ja", "kor": "ko", "hin": "hi", "ara": "ar", "rus": "ru", "tur": "tr", "fas": "fa",
             "pes": "fa", "vie": "vi", "tgl": "tl", "fil": "tl", "nld": "nl", "pol": "pl", "ukr": "uk", "swe": "sv"}

# Per-mode delivery: theatrical modes get more expressive (lower stability) voices.
MODE_VOICE = {"sleepy": (0.8, 0.0), "sincere": (0.75, 0.1), "curious": (0.5, 0.3), "excited": (0.35, 0.6),
              "flirty": (0.4, 0.5), "teasing": (0.35, 0.55), "offended": (0.35, 0.6), "scolding": (0.45, 0.4)}


def api_key() -> Optional[str]:
    return os.environ.get("ELEVENLABS_API_KEY") or None


def find_device(name_part: str, kind: str) -> Optional[int]:
    """Index of the first audio device whose name contains `name_part` (e.g. "Reachy Mini Audio")."""
    import sounddevice as sd

    key = "max_output_channels" if kind == "output" else "max_input_channels"
    for i, d in enumerate(sd.query_devices()):
        if name_part.lower() in d["name"].lower() and d[key] > 0:
            return i
    return None


class ElevenLabsVoice(MacVoice):
    """Speaks through Reachy's own speaker when it is connected (else this computer's);
    falls back to macOS `say` if the API fails."""

    RATE = 16000  # Reachy Mini Audio runs at 16 kHz; ElevenLabs returns raw PCM at that rate

    def __init__(self, clock, voice_id: Optional[str] = None, output: Optional[str] = None):
        import numpy as np
        import sounddevice as sd

        super().__init__(clock)
        self.np, self.sd = np, sd
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
        self.client = httpx.Client(timeout=20)
        self.device = find_device(output or os.environ.get("BIS_AUDIO_OUTPUT", "Reachy Mini Audio"), "output")
        logger.info("Reachy's voice: ElevenLabs %s on %s", self.voice_id,
                    "Reachy's speaker" if self.device is not None else "the default speaker")

    def _stream(self, body):
        return self.client.stream("POST", f"{API}/text-to-speech/{self.voice_id}/stream",
                                  params={"output_format": "pcm_16000", "optimize_streaming_latency": "3"},
                                  headers={"xi-api-key": api_key() or ""}, json=body)

    def _body(self, text, lang, rate, mode) -> dict:
        from .brain.personas import PERSONAS

        stability, style = PERSONAS[mode].voice[:2] if mode in PERSONAS else MODE_VOICE.get(mode, (0.5, 0.3))
        body = {"text": text, "model_id": TTS_MODEL,
                "voice_settings": {"stability": stability, "similarity_boost": 0.8, "style": style,
                                   "speed": max(0.7, min(1.2, rate))}}
        if lang and len(lang) == 2:
            body["language_code"] = lang
        return body

    # ---------------------------------------------------------------- clip cache (session flow v2, section 4)
    def _clip_path(self, body) -> Path:
        key = json.dumps([self.voice_id, body], sort_keys=True).encode()
        return CLIP_DIR / f"{hashlib.sha1(key).hexdigest()[:16]}.pcm"

    def _record(self, body, path: Path) -> bool:
        try:
            with self._stream(body) as r:
                if r.status_code >= 400:
                    r.read()
                    r.raise_for_status()
                data = b"".join(r.iter_bytes())
        except httpx.HTTPError as e:
            logger.warning("Could not pre-record %r: %s", body.get("text"), e)
            return False
        CLIP_DIR.mkdir(exist_ok=True)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(data[: len(data) - len(data) % 2])
        tmp.replace(path)
        return True

    def prewarm(self, lines, mode="", rate=1.0, lang="en") -> None:
        """Record predictable lines once, in the background, so they later play with no network wait."""
        todo = [b for b in (self._body(t, lang, rate, mode) for t in lines) if not self._clip_path(b).exists()]
        if not todo or not api_key():
            return

        def go() -> None:
            done = sum(self._record(b, self._clip_path(b)) for b in todo)
            logger.info("Pre-recorded %d of %d lines", done, len(todo))
        threading.Thread(target=go, daemon=True, name="prewarm").start()

    def say_clip(self, text, lang="en", rate=1.0, mode=""):
        """Play a pre-recorded line from disk (recording it first if it isn't cached yet)."""
        body = self._body(text, lang, rate, mode)
        path = self._clip_path(body)
        if not path.exists() and not (api_key() and self._record(body, path)):
            return self.say(text, lang, rate, mode)
        logger.info("REACHY (%s, %s, clip)> %s", mode, lang, text)
        pcm = self.np.frombuffer(path.read_bytes(), dtype="<i2").astype("float32") / 32768.0
        try:
            with self.sd.OutputStream(samplerate=self.RATE, channels=2, dtype="float32", device=self.device) as out:
                out.write(self.np.repeat(pcm[:, None], 2, axis=1))
        except self.sd.PortAudioError as e:
            logger.warning("Clip playback failed: %s", e)

    def say(self, text, lang="en", rate=1.0, mode=""):
        logger.info("REACHY (%s, %s)> %s", mode, lang, text)
        body = self._body(text, lang, rate, mode)
        for attempt in (0, 1):
            try:
                if self._play_stream(body):
                    return
            except httpx.HTTPStatusError as e:
                if attempt == 0 and e.response.status_code in (400, 422) and "language_code" in body:
                    body.pop("language_code")          # model may not accept this language code
                    continue
                logger.warning("ElevenLabs TTS failed (%s); using the macOS voice", e)
            except (httpx.HTTPError, self.sd.PortAudioError) as e:
                logger.warning("ElevenLabs TTS failed (%s); using the macOS voice", e)
            break
        return super().say(text, lang, rate, mode)

    def _play_stream(self, body) -> bool:
        """Play audio as it arrives: Reachy starts talking after the first chunk, not the whole sentence."""
        np = self.np
        # Watchdog: a stalled audio device used to block out.write() forever, freezing the whole
        # session (no next stage, /pause ignored). Past a generous deadline the stream is aborted
        # and the session carries on.
        deadline = PLAY_MARGIN_S + len(body.get("text", "")) / 6.0
        stuck = threading.Event()
        with self._stream(body) as r:
            if r.status_code >= 400:
                r.read()
                r.raise_for_status()
            with self.sd.OutputStream(samplerate=self.RATE, channels=2, dtype="float32", device=self.device) as out:
                def abort():
                    stuck.set()
                    try:
                        out.abort()
                    except Exception:
                        pass
                timer = threading.Timer(deadline, abort)
                timer.daemon = True
                timer.start()
                try:
                    carry = b""
                    for chunk in r.iter_bytes():
                        if stuck.is_set():
                            break
                        chunk = carry + chunk
                        usable = len(chunk) - len(chunk) % 2
                        chunk, carry = chunk[:usable], chunk[usable:]
                        if chunk:
                            pcm = np.frombuffer(chunk, dtype="<i2").astype("float32") / 32768.0
                            try:
                                out.write(np.repeat(pcm[:, None], 2, axis=1))
                            except self.sd.PortAudioError:
                                if stuck.is_set():
                                    break
                                raise
                finally:
                    timer.cancel()
        if stuck.is_set():
            logger.warning("Speech playback stalled for %.0f s; cut it off so the session continues", deadline)
        return True


class ElevenLabsListener:
    """Microphone -> energy endpointing -> ElevenLabs Scribe (text + language).
    Lines typed in the web UI are accepted at the same time, so the facilitator
    can always step in if recognition misses something."""

    def __init__(self, clock, samplerate=16000, start_rms=0.012, end_silence_s=0.75, max_s=20.0):
        import numpy as np
        import sounddevice as sd

        self.np, self.sd = np, sd
        self.clock = clock
        self.sr, self.th, self.end_s, self.max_s = samplerate, start_rms, end_silence_s, max_s
        self.client = httpx.Client(timeout=30)
        self.typed: "queue.Queue[Utterance]" = queue.Queue()
        self.lang: Optional[str] = None
        self.level = 0.0
        self.noise = 0.0

    def push(self, text: str, language: Optional[str] = None):
        self.typed.put(Utterance(text, language, duration_s=len(text.split()) * 0.4))

    def _typed(self) -> Optional[Utterance]:
        try:
            return self.typed.get_nowait()
        except queue.Empty:
            return None

    def listen(self, timeout: float) -> Optional[Utterance]:
        np, sd = self.np, self.sd
        time.sleep(0.2)  # let Reachy's own voice die out of the room before listening
        block = int(self.sr * 0.1)
        chunks, started, quiet, t0 = [], False, 0.0, time.monotonic()
        pre: list = []                     # keep 0.3 s before the trigger so first syllables aren't cut
        real_timeout = timeout / self.clock.scale
        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", blocksize=block) as stream:
            # Measure the room (Reachy's fan, ventilation) so the threshold sits above it.
            floor = [float(np.sqrt(np.mean(stream.read(block)[0] ** 2))) for _ in range(3)]
            self.noise = 0.7 * self.noise + 0.3 * min(floor) if self.noise else min(floor)
            start_th = max(self.th, self.noise * 1.8)   # people often speak from a metre or two away
            end_th = max(self.th * 0.7, self.noise * 1.3)
            while True:
                typed = self._typed()
                if typed is not None and not started:
                    return typed
                data, _ = stream.read(block)
                rms = float(np.sqrt(np.mean(data ** 2)))
                self.level = rms
                if not started:
                    pre = (pre + [data[:, 0].copy()])[-3:]
                if rms > start_th:
                    if not started:
                        chunks.extend(pre[:-1])
                    started, quiet = True, 0.0
                elif started:
                    quiet = quiet + 0.1 if rms < end_th else 0.0
                if started:
                    chunks.append(data[:, 0].copy())
                if not started and time.monotonic() - t0 > real_timeout:
                    return None
                if started and (quiet >= self.end_s or len(chunks) * 0.1 > self.max_s):
                    break
        if len(chunks) * 0.1 < 0.4:     # a cough or a bump, not speech
            return None
        return self.transcribe(np.concatenate(chunks))

    def transcribe(self, audio) -> Optional[Utterance]:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes((self.np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        try:
            r = self.client.post(f"{API}/speech-to-text", headers={"xi-api-key": api_key() or ""},
                                 data={"model_id": STT_MODEL, "tag_audio_events": "false"},
                                 files={"file": ("speech.wav", buf.getvalue(), "audio/wav")})
            r.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("ElevenLabs STT failed: %s", e)
            return None
        out = r.json()
        text = (out.get("text") or "").strip()
        if not text:
            return None
        code = ISO3_TO_1.get(out.get("language_code", ""), out.get("language_code") or None)
        if code and (out.get("language_probability") or 1) > 0.5:
            self.lang = code
        logger.info("heard (%s): %s", self.lang, text)
        return Utterance(text, self.lang, duration_s=len(audio) / self.sr)
