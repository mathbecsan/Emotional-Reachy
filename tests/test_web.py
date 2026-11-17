from fastapi.testclient import TestClient

from beating_in_sync_app.config import Config
from beating_in_sync_app.events import EventBus
from beating_in_sync_app.runtime import SessionRunner
from beating_in_sync_app.web import create_app


def test_api_basics(tmp_path):
    bus = EventBus()
    client = TestClient(create_app(SessionRunner(bus, Config(sessions_dir=str(tmp_path))), bus, Config(sessions_dir=str(tmp_path))))
    assert client.get("/").status_code == 200
    assert client.get("/static/js/main.js").status_code == 200
    names = {p["name"] for p in client.get("/api/profiles").json()}
    assert {"beating_in_sync", "gentle"} <= names
    assert client.get("/api/state").json()["running"] is False
    assert client.post("/api/command", json={"cmd": "/next"}).status_code == 409   # no session yet
    assert client.get("/api/sessions").json() == []
    assert client.get("/api/sessions/../../etc/passwd").status_code == 404


def test_websocket_snapshot(tmp_path):
    bus = EventBus()
    cfg = Config(sessions_dir=str(tmp_path))
    client = TestClient(create_app(SessionRunner(bus, cfg), bus, cfg))
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["kind"] == "snapshot"
