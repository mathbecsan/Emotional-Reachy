"""Session flow v2, Phase 1: Act 1 (stir on contact, the latch, lifted fingers) and non-blocking gestures."""
import random
import threading
import time
from types import SimpleNamespace

from beating_in_sync_app.body.moves import BaseBody
from beating_in_sync_app.config import Config
from beating_in_sync_app.session import COAX_LINES, STIR_LINES, Session


class FakeClock:
    scale = 1.0

    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


class Recorder:
    def __init__(self):
        self.events, self.plays, self.clips = [], [], []

    def event(self, kind, t, **kw):
        self.events.append((kind, t, kw))

    def play(self, name, loop=False):
        self.plays.append(name)

    def say_clip(self, text, lang="en", rate=1.0, mode=""):
        self.clips.append(text)

    say = say_clip


def act1(finger, bpm, cfg=None):
    """Run Act 1 against a scripted sensor: finger(t) -> bool, bpm(t) -> float | None."""
    rec, clock = Recorder(), FakeClock()
    s = Session.__new__(Session)
    s.cfg = cfg or Config()
    s.clock, s.rng, s.log, s.body, s.voice = clock, random.Random(1), rec, rec, rec
    s.hub = SimpleNamespace(snapshot=lambda: SimpleNamespace(finger_on=finger(clock.t), bpm=bpm(clock.t)))
    s.listener, s.force_next, s.realtime_agent, s.show, s.live = object(), False, None, None, None
    s.contact_t, s.wake_now = None, False
    s.check_safety = lambda: None
    s.act1_asleep()
    for th in threading.enumerate():          # let the clip threads finish recording
        if th.name == "clip":
            th.join(timeout=1)
    return s, rec, clock


def sensor_texts(rec):
    return [kw["text"] for kind, _, kw in rec.events if kind == "sensor"]


def test_stirs_on_contact_and_wakes_at_the_first_heartbeat():
    s, rec, clock = act1(lambda t: t >= 1.0, lambda t: 72.0 if t >= 4.0 else None)
    texts = sensor_texts(rec)
    assert texts[0] == "Fingertip felt: Reachy stirs." and texts[-1] == "Heartbeat felt: Reachy wakes up."
    assert rec.plays[:2] == ["snore", "stir"]
    assert rec.clips[0] in STIR_LINES
    assert 4.0 <= clock.t < 4.3 and s.wake_now
    assert any(kind == "latency" and kw["measure"] == "contact_to_wake" for kind, _, kw in rec.events)


def test_a_lifted_finger_is_coaxed_back_and_never_restarts_the_session():
    # On 1-3 s, off 3-12 s, back from 12 s; the heartbeat is never readable.
    s, rec, clock = act1(lambda t: 1.0 <= t < 3.0 or t >= 12.0, lambda t: None)
    texts = sensor_texts(rec)
    assert texts.count("Fingertip felt: Reachy stirs.") == 1          # latched: one contact, one session
    assert "check_sensor" in rec.plays                                 # glance at the sensor after 1.5 s
    assert any(c in COAX_LINES for c in rec.clips)                     # sleepy coaxing after 5 s
    # Contact time adds up across the lift: 2 s before + 8 s after = 10 s -> wakes around t = 20.
    assert 19.8 <= clock.t <= 20.4
    assert "anyway" in texts[-1] and s.wake_now


def test_a_brush_of_the_hand_is_not_a_session():
    s, rec, clock = act1(lambda t: t >= 30.0, lambda t: 70.0 if t >= 31.0 else None)
    assert [t for kind, t, kw in rec.events if kind == "sensor"][0] >= 30.0
    assert not any(c in COAX_LINES for c in rec.clips)


class SlowBody(BaseBody):
    """Each keyframe takes real time, like goto_target on the robot."""

    def __init__(self):
        super().__init__()
        self.done = []

    def _goto(self, p):
        time.sleep(0.2)
        self.done.append(p)


def test_play_never_blocks_the_caller():
    body = SlowBody()
    body.play("wake")
    t0 = time.monotonic()
    body.play("curious")            # interrupts "wake" mid-keyframe
    body.play("listen")
    assert time.monotonic() - t0 < 0.05
    body.wait()
    assert body.current == "listen"


# ---------------------------------------------------------------- gaze (body/gaze.py)
from beating_in_sync_app.body.gaze import Gaze  # noqa: E402


def follow(gaze, face_x, seconds, start=0.0, step=0.02):
    """Simulate the loop: the head turns, the camera sees the face move toward the image centre."""
    t = start
    person = None
    while t < start + seconds:
        yaw, pitch, body, lean = gaze.step(t)
        gaze.commanded(t, yaw, pitch)
        if person is None:
            person = yaw - face_x * 35.0            # where the person really is (world frame)
        x = (yaw - person) / 35.0                   # where they appear in the image now
        gaze.observe(x, 0.0, 0.15, t)
        t += step
    return gaze.step(t), person


def test_gaze_turns_to_the_person_and_the_body_follows():
    g = Gaze()
    (yaw, pitch, body, lean), person = follow(g, face_x=0.9, seconds=6)   # far to the right of the image
    assert person < -25
    assert abs(yaw - person) < 4                    # head on the person (micro eye movements allowed)
    assert body < -5                                # the body turned partway to face them


def test_gaze_leans_in_when_the_person_is_far():
    g = Gaze()
    for i in range(100):
        t = i * 0.02
        g.commanded(t, 0.0, 0.0)
        g.observe(0.0, 0.0, 0.05, t)                # a small face: far away
        lean = g.step(t)[3]
    assert lean > 3


def test_gaze_eases_back_when_the_person_leaves():
    g = Gaze()
    (yaw, *_), person = follow(g, face_x=0.8, seconds=4)
    for i in range(int(40 / 0.05)):                 # 40 s with nobody in view
        y = g.step(4 + i * 0.05)[0]
    assert abs(y) < 3


# ---------------------------------------------------------------- tone of voice (perception/prosody.py)
import numpy as np  # noqa: E402

from beating_in_sync_app.perception.prosody import VoiceTone  # noqa: E402


def voice(seconds, f0, loud, wobble=0.0, rate=4.0, sr=16000):
    t = np.arange(int(seconds * sr)) / sr
    f = f0 * (1 + wobble * np.sin(2 * np.pi * 1.5 * t))
    phase = 2 * np.pi * np.cumsum(f) / sr
    syll = 0.55 + 0.45 * np.sin(2 * np.pi * rate * t)          # syllable-like loudness bumps
    return (loud * syll * (np.sin(phase) + 0.5 * np.sin(2 * phase))).astype("float32")


def say(tone, audio):
    out = None
    quiet = np.zeros(1600, dtype="float32")
    for i in range(0, len(audio), 1600):
        out = tone.feed(audio[i:i + 1600]) or out
    for _ in range(10):
        out = tone.feed(quiet) or out
    return out


def test_tone_compares_with_the_persons_usual_voice():
    tone = VoiceTone()
    for _ in range(5):
        tone.feed(np.zeros(1600, dtype="float32") + 1e-4)
    for _ in range(2):
        assert say(tone, voice(2.0, 140, 0.05, wobble=0.05)) is not None       # their usual voice
    lively = say(tone, voice(2.0, 180, 0.15, wobble=0.25, rate=6))
    assert {"louder", "higher-pitched"} <= set(lively.labels) and lively.mood == "excited or energised"
    low = say(tone, voice(2.0, 120, 0.015, wobble=0.0, rate=2))
    assert {"quieter"} <= set(low.labels) and "low" in (low.mood or "")
    assert "than before" in low.text


def test_gaze_stops_chasing_with_a_fixed_camera():
    g = Gaze()
    for i in range(400):                            # the face never moves in the image, whatever the head does
        t = i * 0.02
        yaw, pitch, *_ = g.step(t)
        g.commanded(t, yaw, pitch)
        g.observe(0.9, 0.0, 0.15, t)
    assert g.fixed_camera and abs(g.step(9.0)[0]) < 40
