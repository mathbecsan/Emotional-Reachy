"""Gaze: keep Reachy looking at the person for the whole conversation.

The camera sits in Reachy's head, so a face at image position x means the person is at
(head yaw when the frame was taken) - x * HALF_FOV in the world frame. The gaze keeps a short
history of where the head pointed, so frames are placed correctly even while a gesture is
moving the head (approach of the setup checklist's follow-me test, after Gaurav-Gosain/reachy_vision).

What it produces is a direction (head yaw / pitch, body yaw, a small lean); the body's motion
loop adds the current gesture on top, so Reachy can sulk, nod or dance *toward* the person.

Behaviour, so the movement reads as intentional rather than mechanical:
  * fast head, slow body: the body only turns while the head is twisted, like a person shifting
    their weight to face someone;
  * trying to see better: leans in a little when the face is small (far away) or only half seen;
  * small eye movements every few seconds and, when others are in view, a short glance at them
    before coming back;
  * person lost: holds, then glances the way they went, then eases back toward the middle.
"""
import math
import random
import time
from collections import deque

HALF_FOV = 35.0        # deg, half the camera's horizontal field of view
HALF_VFOV = 22.0       # deg, half the vertical field of view
MAX_REL = 35.0         # head stays within this of the body (body/coordination.py allows 40)
HEAD_TAU = 0.35        # s: how quickly the head turns to the target (smaller = snappier)
BODY_TAU = 1.6         # s: the body follows slowly
BODY_DEADBAND = 14.0   # deg of head twist before the body starts turning


class Gaze:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.history: deque = deque(maxlen=120)     # (t, head yaw actually commanded, pitch)
        self.yaw = self.pitch = self.body = self.lean = 0.0
        self.person_yaw = self.person_pitch = 0.0
        self.seen_t = -1e9
        self.moving_dir = 0.0
        self.face_w = 0.15
        self.others: list[float] = []               # world yaw of other people in view
        self.micro = (0.0, 0.0)
        self.next_micro = 0.0
        self.glance_until = self.next_glance = 0.0
        self.glance_yaw = 0.0
        self.last_t = time.monotonic()
        self.fixed_camera = False
        self.cam_ref: tuple[float, float] | None = None
        self.cam_strikes = 0

    # ------------------------------------------------------------------ inputs
    def commanded(self, t: float, yaw: float, pitch: float) -> None:
        """The motion loop reports where it actually pointed the head (gaze + gesture)."""
        self.history.append((t, yaw, pitch))

    def _pointing_at(self, t: float) -> tuple[float, float]:
        best = (self.yaw, self.pitch)
        for ht, y, p in reversed(self.history):
            best = (y, p)
            if ht <= t:
                break
        return best

    def observe(self, x: float, y: float, w: float, t: float, others: list[float] | None = None) -> None:
        """A face at image position (x, y), w = face width / image width, seen at time t (monotonic)."""
        head, pitch = self._pointing_at(t - 0.08)      # the motors lag the command a little
        self._check_camera(head, x)
        if self.fixed_camera:                           # camera not on the head: point, don't chase
            self.person_yaw += 0.3 * (-x * HALF_FOV * 0.6 - self.person_yaw)
            self.seen_t, self.face_w = t, w
            return
        person = head - x * HALF_FOV
        if abs(person - self.person_yaw) > 1.5:
            self.moving_dir = 1.0 if person > self.person_yaw else -1.0
        self.person_yaw += 0.6 * (person - self.person_yaw)
        target_pitch = max(-20.0, min(20.0, pitch + y * HALF_VFOV))
        self.person_pitch += 0.4 * (target_pitch - self.person_pitch)
        self.face_w = w
        self.seen_t = t
        self.others = [head - ox * HALF_FOV for ox in (others or [])]

    def _check_camera(self, head: float, x: float) -> None:
        """Safety: with the camera in Reachy's head, turning the head moves the face across the image.
        If the head turned a lot and the face didn't move, the camera is fixed (e.g. the laptop's):
        chasing would spin Reachy, so the gaze switches to plain pointing."""
        if self.fixed_camera:
            return
        if self.cam_ref is None:
            self.cam_ref = (head, x)
            return
        h0, x0 = self.cam_ref
        if abs(head - h0) >= 30:
            expected = (head - h0) / HALF_FOV           # the face should slide this far in the image
            # Someone walking while Reachy follows also keeps a steady offset for a moment, so it
            # takes the face stuck near the edge twice in a row to decide the camera is fixed.
            stuck = abs(x - x0) < 0.25 * abs(expected) and abs(x) > 0.4
            self.cam_strikes = self.cam_strikes + 1 if stuck else 0
            self.fixed_camera = self.cam_strikes >= 2
            self.cam_ref = (head, x)

    # ------------------------------------------------------------------ output
    def step(self, now: float | None = None) -> tuple[float, float, float, float]:
        """(head yaw, head pitch, body yaw, lean mm) to look at the person now."""
        now = time.monotonic() if now is None else now
        dt = max(1e-3, min(0.2, now - self.last_t))
        self.last_t = now
        gone = now - self.seen_t
        target_yaw, target_pitch = self.person_yaw, self.person_pitch
        lean = 0.0
        if gone < 1.2:
            if self.face_w < 0.08:
                lean = 6.0                  # far away: lean in, trying to see them better
            elif self.face_w > 0.40:
                lean = -4.0                 # very close: ease back a little
            if now > self.next_micro:       # small eye movements: alive, not locked on
                self.micro = (self.rng.uniform(-2.5, 2.5), self.rng.uniform(-1.5, 1.5))
                self.next_micro = now + self.rng.uniform(1.8, 4.0)
            if self.others and now > self.next_glance and now > self.glance_until + 6:
                self.glance_yaw = self.rng.choice(self.others)
                self.glance_until = now + self.rng.uniform(0.9, 1.5)
                self.next_glance = now + self.rng.uniform(10, 20)
            if now < self.glance_until:
                target_yaw = self.glance_yaw
            target_yaw += self.micro[0]
            target_pitch += self.micro[1]
        elif gone < 4.0:
            target_yaw = self.person_yaw + self.moving_dir * 12.0      # glance the way they went
        elif gone < 30.0:
            k = min(1.0, (gone - 4.0) / 12.0)                          # ease back toward the middle
            target_yaw = self.person_yaw * (1 - k)
            target_pitch = self.person_pitch * (1 - k)
        else:
            target_yaw = target_pitch = 0.0
        a = 1 - math.exp(-dt / HEAD_TAU)
        self.yaw += a * (target_yaw - self.yaw)
        self.pitch += a * (target_pitch - self.pitch)
        self.lean += (1 - math.exp(-dt / 0.8)) * (lean - self.lean)
        twist = self.yaw - self.body
        if abs(twist) > BODY_DEADBAND:
            self.body += (1 - math.exp(-dt / BODY_TAU)) * (twist - math.copysign(BODY_DEADBAND * 0.5, twist))
        self.body = max(-150.0, min(150.0, self.body))
        self.yaw = max(self.body - MAX_REL, min(self.body + MAX_REL, self.yaw))
        return self.yaw, self.pitch, self.body, self.lean

    def seeing(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return now - self.seen_t < 1.2

    def where(self) -> str:
        """Where the person is, from Reachy's point of view, in words."""
        y = self.person_yaw
        return "straight in front of you" if abs(y) < 15 else ("to your left" if y > 0 else "to your right")
