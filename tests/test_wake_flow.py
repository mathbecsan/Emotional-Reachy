import json
import threading
import time
from pathlib import Path

from beating_in_sync_app.body.moves import ReachyMiniBody
from beating_in_sync_app.config import Config
from beating_in_sync_app.events import EventBus
from beating_in_sync_app.runtime import SessionOptions, SessionRunner


SCENARIO = Path(__file__).parents[1] / "scenarios" / "demo_participant.json"


def run_session(tmp_path, scenario_steps=None, cfg=None, time_scale=40, **kw):
    path = SCENARIO
    if scenario_steps is not None:
        path = tmp_path / "s.json"
        path.write_text(json.dumps(scenario_steps))
    runner = SessionRunner(EventBus(), cfg or Config(sessions_dir=str(tmp_path)))
    runner.start(SessionOptions(llm=False, voice="sim", listener="scenario", scenario=str(path), time_scale=time_scale, **kw))
    runner.wait()
    return [json.loads(x) for x in next(tmp_path.glob("*.jsonl")).read_text().splitlines()]


def kinds(events):
    out = []
    for e in events:
        if e["kind"] == "stage":
            out.append(f"stage{e['stage']}")
        elif e["kind"] == "sensor" and "snoring" in e["text"]:
            out.append("pulse")
        elif e["kind"] == "say" and e["text"] == "(snoring)":
            out.append("snore")
        elif e["kind"] == "baseline":
            out.append("baseline")
        elif e["kind"] == "say" and "woke me up" in e["text"]:
            out.append("wake")
    return out


def test_pulse_then_snore_then_wake_then_dialogue(tmp_path):
    seq = kinds(run_session(tmp_path))
    assert seq.index("stage0") < seq.index("pulse") < seq.index("snore") < seq.index("baseline")
    assert seq.index("baseline") < seq.index("stage1") < seq.index("wake") < seq.index("stage2")
    assert seq[-1] == "stage7"


def test_no_snoring_before_a_finger(tmp_path):
    steps = [{"wait": 30}, {"cmd": "/finger on"}, {"say": "hi", "lang": "en"}]
    events = run_session(tmp_path, steps)
    seq = kinds(events)
    pulse_t = next(e["t"] for e in events if e["kind"] == "sensor" and "snoring" in e["text"])
    assert pulse_t >= 30                                   # silent sleep until the finger lands
    assert not any(e["kind"] == "heart" and e["t"] < 29 for e in events)
    assert "snore" in seq and "wake" in seq


def test_arduino_pipeline_simulated_signal_wakes_reachy(tmp_path):
    steps = [{"cmd": "/finger on"}, {"cmd": "/hand on"}, {"say": "it was me", "lang": "en"}]
    # The Arduino pipeline runs in real time, so: real clock, short stages, short baseline.
    cfg = Config(sessions_dir=str(tmp_path), baseline_window_s=6, listen_timeout_s=1,
                 stage_time={0: 30, 1: 10, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 1}, music_seconds=2)
    seq = kinds(run_session(tmp_path, steps, cfg=cfg, time_scale=1, heart="arduino-sim", pulse_mode="one"))
    assert "pulse" in seq and "wake" in seq


class FakeRobot:
    """Stands in for reachy_mini.ReachyMini; records calls, fails like a --no-media daemon."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def _rec(self, name, **kw):
        with self.lock:
            self.calls.append((name, kw))

    def enable_motors(self):
        self._rec("enable_motors")

    def wake_up(self):
        self._rec("wake_up")
        raise AttributeError("'NoneType' object has no attribute 'play_sound'")

    def goto_sleep(self):
        self._rec("goto_sleep")

    def goto_target(self, head=None, antennas=None, duration=0.5, body_yaw=0.0):
        assert head.shape == (4, 4) and len(antennas) == 2 and duration > 0
        self._rec("goto_target", duration=duration)
        time.sleep(0.001)

    def set_target(self, head=None, antennas=None, body_yaw=None):
        self._rec("set_target")


def test_reachy_body_with_fake_robot():
    robot = FakeRobot()
    body = ReachyMiniBody(robot, use_emotion_library=False)
    body.go_to_sleep()
    body.play("snore", loop=False)
    body.wait()
    body.wake_up()          # SDK sound fails -> must not raise, keyframes still play
    body.wait()
    body.play("scolding")
    body.wait()
    names = [c[0] for c in robot.calls]
    assert names[0] == "enable_motors"
    assert "goto_sleep" in names and "wake_up" in names
    assert names.count("goto_target") >= 8


def test_waits_as_long_as_needed_for_a_finger(tmp_path):
    # 300 s with nobody touching the sensors (longer than stage 0's 120 s), then a finger.
    steps = [{"wait": 300}, {"cmd": "/finger on"}, {"say": "hi", "lang": "en"}]
    events = run_session(tmp_path, steps)
    pulse_t = next(e["t"] for e in events if e["kind"] == "sensor" and "snoring" in e["text"])
    stage1_t = next(e["t"] for e in events if e["kind"] == "stage" and e["stage"] == 1)
    assert pulse_t >= 300 and stage1_t > pulse_t
    assert not any(e["kind"] == "say" and e["t"] < pulse_t for e in events)   # silent until the pulse
