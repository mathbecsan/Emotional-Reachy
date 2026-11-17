"""Shared, thread-safe snapshot of everything Reachy can sense right now.

Perception threads (heart sensor, camera) write here; the Director reads a
copy once per turn.
"""
import threading
from dataclasses import dataclass, replace
from typing import Optional


@dataclass
class Signals:
    # heart
    pulse_present: bool = False          # wake trigger: a pulse on the "wake" sensor (see pulse_sensor.py)
    finger_on: bool = True               # any finger on any sensor (False = participant let go)
    sensor_bpms: Optional[list] = None   # per-sensor BPM from the Arduino
    companion_bpm: Optional[float] = None  # pulse_mode "two": the second person's heart
    hearts_in_sync: bool = False
    bpm: Optional[float] = None
    baseline_bpm: Optional[float] = None
    bpm_delta: float = 0.0               # current minus baseline
    bpm_jump: bool = False               # rising edge, consumed by the Director
    bpm_jump_size: float = 0.0
    bpm_flat: bool = False
    bpm_overlimit_s: float = 0.0
    # camera
    face_visible: bool = False
    looking_away_s: float = 0.0
    num_people: int = 1
    face_emotion: Optional[str] = None   # FER label (angry, disgust, fear, happy, neutral, sad, surprise)
    face_conf: float = 0.0
    face_x: float = 0.0                  # -1 (left of image) .. +1 (right), for turning toward the person
    face_y: float = 0.0
    motion_energy: float = 0.0           # 0..1, used in the music stage ("did they dance?")


class SignalHub:
    def __init__(self):
        self._s = Signals()
        self._lock = threading.Lock()

    def update(self, **kw):
        with self._lock:
            for k, v in kw.items():
                setattr(self._s, k, v)

    def snapshot(self) -> Signals:
        with self._lock:
            return replace(self._s)

    def consume_jump(self) -> float:
        """Return the jump size once, then clear it (so Reachy comments once)."""
        with self._lock:
            size = self._s.bpm_jump_size if self._s.bpm_jump else 0.0
            self._s.bpm_jump = False
            return size
