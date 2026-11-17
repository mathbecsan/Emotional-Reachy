"""Heart-rate monitoring: baseline, jumps, flat stretches, safety limit.

BPM comes from one of two sources:
  * ArduinoPulseSource (perception/pulse_sensor.py) - the two MAX30102 sensors.
  * SimHeartSource - synthetic heart that *reacts* to what Reachy does
    (scolding spikes it, sincere mode calms it), so the heart-driven branches
    can be tested without hardware. It can also drive a simulated Arduino, so
    the real beat-detection pipeline runs end to end without the sensors.
"""
import math
import random
import statistics
import threading
from collections import deque

from ..clock import Clock
from ..config import Config
from ..signals import SignalHub


class HeartAnalyzer:
    """Turns raw BPM samples into the signals the Director needs."""

    def __init__(self, cfg: Config, hub: SignalHub, clock: Clock, logger=None):
        self.cfg, self.hub, self.clock, self.logger = cfg, hub, clock, logger
        self.samples = deque()            # (t, bpm)
        self.baseline = None
        self.collect_baseline = True
        self._last_jump_t = -1e9
        self._over_since = None

    def _window(self, seconds, end_offset=0.0):
        now = self.clock.now()
        return [b for t, b in self.samples if now - end_offset - seconds <= t <= now - end_offset]

    def baseline_ready(self) -> bool:
        return self.baseline is not None

    def settle_baseline(self) -> None:
        """Stage 0 ended early (Next stage / timeout): use the median of what was recorded,
        so heart-jump comments still work for the rest of the session."""
        if self.baseline is None and len(self.samples) >= 5:
            self.baseline = statistics.median(b for _, b in self.samples)

    def push(self, bpm):
        now = self.clock.now()
        if bpm is None or bpm <= 0:
            return
        self.samples.append((now, bpm))
        while self.samples and now - self.samples[0][0] > 180:
            self.samples.popleft()
        if self.logger:
            self.logger.heart(now, bpm)

        # Stage 0: lock a baseline after 60 s of stable signal.
        if self.collect_baseline and self.baseline is None:
            w = self._window(self.cfg.baseline_window_s)
            span = now - self.samples[0][0]
            if span >= self.cfg.baseline_window_s and len(w) > 5 and statistics.pstdev(w) < self.cfg.baseline_max_std:
                self.baseline = statistics.fmean(w)

        recent = self._window(5) or [bpm]
        cur = statistics.fmean(recent)
        base = self.baseline or cur
        delta = cur - base

        # Jump: big rise vs. baseline, or a fast rise vs. the previous 30 s.
        prev = self._window(30, end_offset=5)
        short_rise = cur - statistics.median(prev) if len(prev) > 3 else 0.0
        jump = (delta >= self.cfg.bpm_jump_threshold or short_rise >= self.cfg.bpm_short_jump)
        fire = jump and now - self._last_jump_t > self.cfg.bpm_jump_cooldown_s and self.baseline is not None
        if fire:
            self._last_jump_t = now

        flat_w = self._window(self.cfg.bpm_flat_window_s)
        flat = (len(flat_w) > 10 and now - self.samples[0][0] > self.cfg.bpm_flat_window_s
                and statistics.pstdev(flat_w) < self.cfg.bpm_flat_max_std)

        if cur > self.cfg.bpm_stop_limit:
            self._over_since = self._over_since if self._over_since is not None else now
        else:
            self._over_since = None
        over_s = 0.0 if self._over_since is None else now - self._over_since

        upd = dict(bpm=round(cur, 1), baseline_bpm=self.baseline,
                   bpm_delta=round(delta, 1), bpm_flat=flat, bpm_overlimit_s=over_s)
        if fire:
            upd.update(bpm_jump=True, bpm_jump_size=round(max(delta, short_rise), 1))
        self.hub.update(**upd)


class SimHeartSource(threading.Thread):
    """Synthetic heart that responds to Reachy's behaviour (see `react`)."""

    # How much each Reachy mode tends to raise a participant's heart rate.
    MODE_EFFECT = {"scolding": 19, "flirty": 11, "offended": 8, "teasing": 6,
                   "excited": 5, "curious": 1, "sincere": -6, "sleepy": -2}

    def __init__(self, analyzer: HeartAnalyzer, clock: Clock, seed=7, push=True):
        super().__init__(daemon=True)
        self.a, self.clock = analyzer, clock
        self.rng = random.Random(seed)
        self.rest = 71.0 + self.rng.uniform(-4, 4)
        self.offset = 0.0
        self.hand_on = False        # stage-1 wake gesture (sensor 2 / "hand on pad")
        self.finger_on = False      # participant's finger on sensor 1 (the "/finger on" button)
        self.push = push            # False: only model the BPM, a SimulatedArduino reports it
        self._bpm = self.rest
        self._lock = threading.Lock()
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def react(self, mode: str):
        self.bump(self.MODE_EFFECT.get(mode, 0) * self.rng.uniform(0.6, 1.3))

    def bump(self, amount: float):
        with self._lock:
            self.offset += amount

    def set_hand(self, on: bool):
        self.hand_on = on

    def set_finger(self, on: bool):
        self.finger_on = on

    def current_bpm(self) -> float:
        return self._bpm

    def fingers(self):
        return (self.finger_on, self.hand_on)

    def run(self):
        while not self.stop_event.is_set():
            with self._lock:
                self.offset *= 0.93          # arousal decays back to rest
            t = self.clock.now()
            self._bpm = self.rest + self.offset + 1.2 * math.sin(t / 7) + self.rng.gauss(0, 0.8)
            if self.push:
                if self.finger_on:
                    self.a.push(round(self._bpm, 1))
                # Simulation: any finger on a sensor counts as the pulse that wakes Reachy.
                self.a.hub.update(pulse_present=self.finger_on or self.hand_on, finger_on=self.finger_on)
            self.clock.sleep(1.0)
