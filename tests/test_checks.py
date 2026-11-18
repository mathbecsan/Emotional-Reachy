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
