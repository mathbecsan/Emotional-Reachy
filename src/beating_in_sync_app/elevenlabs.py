"""ElevenLabs speech for Reachy: multilingual text-to-speech (its voice) and
speech-to-text with language detection (its ears).

The API key is read from the environment (ELEVENLABS_API_KEY, set in .env);
it is never stored in code or logs.
"""
import io
import logging
import os
import queue
import time
import wave
from typing import Optional

import httpx

from .body.voice import MacVoice
from .perception.speech import Utterance


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

    def _tts(self, body):
        return self.client.post(f"{API}/text-to-speech/{self.voice_id}", params={"output_format": "pcm_16000"},
                                headers={"xi-api-key": api_key() or ""}, json=body)

    def say(self, text, lang="en", rate=1.0, mode=""):
        logger.info("REACHY (%s, %s)> %s", mode, lang, text)
        stability, style = MODE_VOICE.get(mode, (0.5, 0.3))
        body = {"text": text, "model_id": TTS_MODEL,
                "voice_settings": {"stability": stability, "similarity_boost": 0.8, "style": style,
                                   "speed": max(0.7, min(1.2, rate))}}
        if lang and len(lang) == 2:
            body["language_code"] = lang
        try:
            r = self._tts(body)
            if r.status_code in (400, 422) and "language_code" in body:  # model may not accept this code
                body.pop("language_code")
                r = self._tts(body)
            r.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("ElevenLabs TTS failed (%s); using the macOS voice", e)
            return super().say(text, lang, rate, mode)
        pcm = self.np.frombuffer(r.content, dtype="<i2").astype("float32") / 32768.0
        stereo = self.np.repeat(pcm[:, None], 2, axis=1)
        try:
            self.sd.play(stereo, self.RATE, device=self.device)
            self.sd.wait()
        except self.sd.PortAudioError as e:
            logger.warning("Playback on device %s failed (%s); using the default speaker", self.device, e)
            self.sd.play(stereo, self.RATE)
            self.sd.wait()


class ElevenLabsListener:
    """Microphone -> energy endpointing -> ElevenLabs Scribe (text + language).
    Lines typed in the web UI are accepted at the same time, so the facilitator
    can always step in if recognition misses something."""

    def __init__(self, clock, samplerate=16000, start_rms=0.015, end_silence_s=1.0, max_s=20.0):
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
        time.sleep(0.35)  # let Reachy's own voice die out of the room before listening
        block = int(self.sr * 0.1)
        chunks, started, quiet, t0 = [], False, 0.0, time.monotonic()
        pre: list = []                     # keep 0.3 s before the trigger so first syllables aren't cut
        real_timeout = timeout / self.clock.scale
        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", blocksize=block) as stream:
            # Measure the room (Reachy's fan, ventilation) so the threshold sits above it.
            floor = [float(np.sqrt(np.mean(stream.read(block)[0] ** 2))) for _ in range(3)]
            self.noise = 0.7 * self.noise + 0.3 * min(floor) if self.noise else min(floor)
            start_th = max(self.th, self.noise * 2.5)
            end_th = max(self.th * 0.7, self.noise * 1.6)
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
