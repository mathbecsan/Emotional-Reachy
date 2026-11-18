"""Check setup API and the motion settings."""
import time

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


def test_head_never_strays_far_from_the_body():
    from beating_in_sync_app.body.coordination import MAX_RELATIVE_YAW, coordinate, turn_steps

    yaw, body, pitch, roll = coordinate(yaw=0, body=150, pitch=30, roll=20, body_delta=150)
    assert body == 150 and abs(yaw - body) <= MAX_RELATIVE_YAW        # head turns with the body
    assert abs(pitch) <= 10 and abs(roll) <= 10                        # level head during a big turn
    assert coordinate(yaw=90, body=0)[0] == MAX_RELATIVE_YAW           # head alone can't twist past the limit
    steps = turn_steps(0, 150)
    assert len(steps) == 3 and steps[-1] == (150, 150)
    assert all(abs(y - b) <= MAX_RELATIVE_YAW for y, b in steps)
    assert all(abs(b2 - b1) <= 50 for (_, b1), (_, b2) in zip([(0, 0)] + steps, steps))


def test_repair_stops_when_a_session_runs_and_finds_reachys_port(monkeypatch):
    import types

    import beating_in_sync_app.repair as repair

    events = []
    bus = types.SimpleNamespace(emit=lambda kind, **k: events.append(k))
    runner = types.SimpleNamespace(running=True)
    out = repair.Repair(runner, bus, types.SimpleNamespace(sessions_dir="/tmp"), lambda: []).run()
    assert not out["ok"] and out["results"][0]["step"] == "session" and "End the session" in out["results"][0]["fix"]
    assert events[-1]["done"]
    monkeypatch.setattr(repair, "list_ports", lambda: [
        {"device": "/dev/cu.usbserial-A1", "description": "FT232R USB UART", "busy": False},
        {"device": "/dev/cu.usbmodemSN1", "description": "USB BillBoard", "busy": False},
        {"device": "/dev/cu.usbmodem5B7B", "description": "USB Single Serial", "busy": True}])
    assert repair.reachy_port() == "/dev/cu.usbmodem5B7B"


def test_pulse_watchdog_resets_a_hung_arduino(monkeypatch):
    """The Nano can stop streaming while USB stays open: the reader must give up so the port is reopened."""
    import pytest
    from beating_in_sync_app.perception import pulse_sensor as ps

    monkeypatch.setattr(ps, "STALL_S", 0.2)

    class HungSerial:
        def __init__(self):
            self.n = 0

        def readline(self):
            self.n += 1
            if self.n <= 5:
                return b"120000,121000\n"
            time.sleep(0.05)
            return b""

    src = ps.ArduinoPulseSource.__new__(ps.ArduinoPulseSource)
    src.simulated, src.stop_event = None, __import__("threading").Event()
    src.bufs, src.lines = [ps.SampleBuffer(), ps.SampleBuffer()], 0
    with pytest.raises(RuntimeError, match="no data"):
        src._read_lines(HungSerial())
