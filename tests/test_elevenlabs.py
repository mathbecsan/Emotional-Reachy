import json

import httpx
import numpy as np

from beating_in_sync_app import elevenlabs
from beating_in_sync_app.body.voice import MacVoice
from beating_in_sync_app.clock import Clock


def test_stt_maps_language_and_text(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test")
    seen = {}

    def handler(request: httpx.Request):
        seen["key"] = request.headers["xi-api-key"]
        return httpx.Response(200, json={"text": " Hola, me llamo Lucía ", "language_code": "spa",
                                         "language_probability": 0.97})

    listener = elevenlabs.ElevenLabsListener(Clock())
    listener.client = httpx.Client(transport=httpx.MockTransport(handler))
    u = listener.transcribe(np.zeros(16000, dtype="float32"))
    assert u.text == "Hola, me llamo Lucía" and u.language == "es" and seen["key"] == "test"


def test_typed_line_wins_over_mic(monkeypatch):
    listener = elevenlabs.ElevenLabsListener(Clock())
    listener.push("typed by the facilitator", "en")
    assert listener.listen(2.0).text == "typed by the facilitator"


def test_tts_failure_falls_back_to_mac_voice(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "bad")
    spoken = []
    monkeypatch.setattr(MacVoice, "say", lambda self, text, lang="en", rate=1.0, mode="": spoken.append(text))
    voice = elevenlabs.ElevenLabsVoice(Clock())
    voice.client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={})))
    voice.say("Hey. Eyes on me.", "en", 1.0, "scolding")
    assert spoken == ["Hey. Eyes on me."]


class FakeOut:
    played = []

    def __init__(self, **kw):
        self.kw = kw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, data):
        FakeOut.played.append(len(data))


def test_tts_streams_and_retries_without_language_code(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "ok")
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        assert request.url.path.endswith("/stream")
        return httpx.Response(400 if len(bodies) == 1 else 200, content=b"\x00\x00" * 160)

    voice = elevenlabs.ElevenLabsVoice(Clock())
    voice.client = httpx.Client(transport=httpx.MockTransport(handler))
    FakeOut.played = []
    monkeypatch.setattr(voice.sd, "OutputStream", FakeOut)
    voice.say("Hola", "tl", 1.0, "curious")
    assert "language_code" in bodies[0] and "language_code" not in bodies[1] and sum(FakeOut.played) == 160
