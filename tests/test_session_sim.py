import json
from pathlib import Path

from beating_in_sync_app.config import Config
from beating_in_sync_app.events import EventBus
from beating_in_sync_app.runtime import SessionOptions, SessionRunner


SCENARIO = Path(__file__).parents[1] / "scenarios" / "demo_participant.json"


def run(tmp_path, **kw):
    bus = EventBus()
    runner = SessionRunner(bus, Config(sessions_dir=str(tmp_path)))
    runner.start(SessionOptions(llm=False, voice="sim", listener="scenario", scenario=str(SCENARIO), time_scale=40, **kw))
    runner.wait()
    log = next(tmp_path.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_full_protocol_runs_and_ends_sincere(tmp_path):
    events = run(tmp_path)
    stages = [e["stage"] for e in events if e["kind"] == "stage"]
    assert stages == [0, 1, 2, 3, 4, 5, 6, 7]
    turns = [e for e in events if e["kind"] == "turn"]
    assert turns[-1]["mode"] == "sincere" and turns[-1]["act"] == "goodbye"
    assert any(t["act"] == "story" for t in turns)          # Reachy tells, not only asks
    assert {"teasing", "scolding"} <= {t["mode"] for t in turns}


def test_no_tease_skips_stage_4(tmp_path):
    events = run(tmp_path, no_tease=True)
    assert any(e["kind"] == "stage" and e["stage"] == 4 and e.get("skipped") for e in events)
    assert not {"teasing", "offended", "scolding"} & {e["mode"] for e in events if e["kind"] == "turn"}
