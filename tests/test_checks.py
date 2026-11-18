"""Check setup API and the motion settings."""
from fastapi.testclient import TestClient

from beating_in_sync_app.body.gestures import GESTURES
from beating_in_sync_app.body.moves import styled
from beating_in_sync_app.config import Config
from beating_in_sync_app.events import EventBus
from beating_in_sync_app.runtime import SessionRunner
from beating_in_sync_app.web import create_app


def test_motion_intensity_and_speed_scale_keyframes_within_limits():
    seq = GESTURES["twirl"]
    small = styled(seq, 0.5, 1.0)
    assert abs(small[0].body_yaw) == abs(seq[0].body_yaw) * 0.5
    fast = styled(seq, 1.0, 1.5)
    assert fast[0].dur < seq[0].dur
    big = styled(seq, 1.3, 1.0)
    assert all(abs(p.body_yaw) <= 160 and abs(p.yaw - p.body_yaw) <= 60 for p in big)
    assert styled(seq) == list(seq)


def test_check_api_reports_without_hardware(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    bus, cfg = EventBus(), Config(sessions_dir=str(tmp_path))
    client = TestClient(create_app(SessionRunner(bus, cfg), bus, cfg))
    c = client.get("/api/check").json()
    assert set(c) >= {"daemon", "robot", "sensors", "voice", "audio"}
    assert c["robot"]["ok"] is False and c["robot"]["fix"]
    assert c["voice"]["ok"] is False and "ELEVENLABS_API_KEY" in c["voice"]["fix"]
    r = client.post("/api/check/move").json()
    assert r["ok"] is False and "Connect" in r["fix"]


def _signals():
    import numpy as np

    sr, rng = 16000, np.random.default_rng(0)
    t = np.arange(sr * 5) / sr
    room = rng.normal(0, 0.002, len(t))
    claps = room.copy()
    for s in (0.5, 1.3, 2.0, 2.8, 3.5):
        i, n = int(s * sr), int(0.03 * sr)
        claps[i:i + n] += rng.normal(0, 0.4, n) * np.exp(-np.arange(n) / 150)
    f0 = 220 + 15 * np.sin(2 * np.pi * 5 * t)
    sing = room + 0.2 * np.sin(2 * np.pi * np.cumsum(f0) / sr)
    speech = room + 0.2 * np.sin(2 * np.pi * 150 * t) * ((t % 0.35) < 0.2)
    return room, claps, sing, speech


def test_sound_events_tell_claps_music_and_speech_apart():
    from beating_in_sync_app.perception.sound_events import analyse, describe

    room, claps, sing, speech = _signals()
    assert describe(analyse(room)) == []
    assert analyse(claps)["claps"] == 5
    assert describe(analyse(sing)) == ["music or singing"]
    assert not analyse(speech)["music"]              # speech pauses too often to count as singing


def test_live_session_reacts_to_a_performance():
    import types

    from beating_in_sync_app.perception.sound_events import SoundWatcher
    from beating_in_sync_app.realtime import RealtimeConversation

    _, claps, sing, _ = _signals()
    w = SoundWatcher(window_s=3.0, cooldown_s=2.0)
    events = [e for i in range(0, len(sing), 1600) for e in w.feed(sing[i:i + 1600])]
    assert "music" in events
    rc = RealtimeConversation.__new__(RealtimeConversation)
    played, notes = [], []
    rc.s = types.SimpleNamespace(body=types.SimpleNamespace(play=played.append), clock=types.SimpleNamespace(now=lambda: 1.0),
                                 log=types.SimpleNamespace(event=lambda *a, **k: notes.append(k)))
    rc.show, rc.closing_t, rc.performing_since, rc.last_music_t, rc.last_clap_t = None, 0.0, 0.0, 0.0, 0.0
    sent = []
    rc.direct = sent.append
    rc._on_sound("music")
    assert played == ["excited"] and rc.performing_since and not sent      # sways along, doesn't talk over it
    rc._performance_over()
    assert "just performed" in sent[-1]
    rc._on_sound("clapping")
    assert "clapping" in sent[-1]
