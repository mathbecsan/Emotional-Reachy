import time

import numpy as np

from beating_in_sync_app.perception.pulse_sensor import IR_LINE, BeatAnalyzer, SampleBuffer, SimulatedArduino


def synth(bpm, seconds=8.0, fs=100):
    t = np.arange(0, seconds, 1 / fs)
    p = (t * bpm / 60) % 1
    s = np.exp(-((p - 0.15) / 0.06) ** 2) + 0.35 * np.exp(-((p - 0.42) / 0.08) ** 2)
    return t, 120000 + 1200 * s + np.random.default_rng(0).normal(0, 40, len(t))


def test_beat_analyzer_finds_bpm():
    for bpm in (60, 75, 110):
        t, v = synth(bpm)
        an = BeatAnalyzer()
        for end in range(300, len(t), 25):     # feed it the way the live loop does
            win = (t > t[end] - 6) & (t <= t[end])
            an.update(t[win], v[win], t[end])
        assert abs(an.bpm - bpm) < 4, (bpm, an.bpm)


def test_no_finger_and_saturation_are_ignored():
    buf = SampleBuffer()
    now = time.monotonic()
    buf.push(1500, now)          # below finger threshold
    buf.push(262143, now)        # saturated -> spike
    assert not buf.finger_on(now) and buf.rejected == 1
    buf.push(120000, now)
    assert buf.finger_on(now)


def test_simulated_arduino_speaks_firmware_format():
    fake = SimulatedArduino(lambda: 72, lambda: (True, False))
    line = fake.readline().decode().strip()
    assert IR_LINE.match(line)
    assert int(line.split(",")[1]) < 20000      # no finger on sensor 2
