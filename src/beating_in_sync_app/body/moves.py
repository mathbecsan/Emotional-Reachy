"""Body backends. Gestures play on a background thread so Reachy moves while
it talks; a new gesture interrupts the current one.

ReachyMiniBody follows reachy_mini_conversation_app (moves.py /
dance_emotion_moves.py):
  * recorded emotions from the `pollen-robotics/reachy-mini-emotions-library`
    dataset (RecordedMoves), evaluated at ~60 Hz through `ReachyMini.set_target`;
  * keyframe gestures (body/gestures.py) through `ReachyMini.goto_target` for
    the moves the library doesn't have (lean-in, nose-up turn away, snap back);
  * `wake_up()` / `goto_sleep()` from the SDK for stage 1 and the end.
"""
import logging
import math
import random
import threading
import time

from .gestures import GESTURES, Pose, dance_moves


logger = logging.getLogger(__name__)

EMOTION_LIBRARY = "pollen-robotics/reachy-mini-emotions-library"
CONTROL_HZ = 60.0

# Recorded emotions that fit each mode (names from the emotions library).
# Modes whose signature motion matters for the protocol (flirty lean-in,
# offended turn-away, scolding snap) keep their keyframes as first choice.
MODE_EMOTIONS = {
    "curious": ["attentive1", "attentive2", "thoughtful1"],
    "excited": ["laughing1", "laughing2", "success1", "amazed1"],
    "flirty": ["loving1", "shy1"],
    "teasing": ["boredom1", "boredom2", "impatient2"],
    "offended": ["displeased1", "go_away1"],
    "scolding": ["irritated1", "impatient2"],
    "sincere": ["grateful1", "calming1", "relief1"],
    "sleepy": ["sleep1", "exhausted1"],
}
KEYFRAMES_FIRST = {"flirty", "offended", "scolding", "wake", "to_sleep", "listen", "think", "attend"}


def styled(seq, intensity: float = 1.0, speed: float = 1.0) -> list:
    """Scale a keyframe sequence: intensity = size of the motion (0.3-1.3), speed = tempo (0.5-1.5).
    Head yaw stays within 40 deg of the body (body/coordination.py) and the body within +-160."""
    if intensity == 1.0 and speed == 1.0:
        return list(seq)
    out = []
    for p in seq:
        body = max(-160.0, min(160.0, p.body_yaw * intensity))
        yaw = max(body - 40.0, min(body + 40.0, p.yaw * intensity))   # body/coordination.py
        out.append(Pose(p.roll * intensity, p.pitch * intensity, yaw, p.z * intensity, p.x * intensity,
                        (p.ant[0] * intensity, p.ant[1] * intensity), body, max(0.08, p.dur / speed)))
    return out


class BaseBody:
    intensity = 1.0     # session settings from the builder ("How Reachy moves")
    speed = 1.0

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.current: str | None = None

    def play(self, name_or_seq, loop: bool = False) -> None:
        """Start a gesture and return at once. The new gesture waits for the old one's current
        keyframe on its own thread, so callers (the voice receiver, the session loop) never block."""
        self.current = name_or_seq if isinstance(name_or_seq, str) else "sequence"
        logger.debug("gesture %s", self.current)
        self._spawn(self._runner(name_or_seq, loop, self._next_stop()))

    def _next_stop(self) -> threading.Event:
        self._stop.set()
        self._stop = threading.Event()
        return self._stop

    def _spawn(self, run) -> None:
        prev, stop = self._thread, self._stop

        def chained() -> None:
            if prev is not None and prev.is_alive():
                prev.join(timeout=3)          # the SDK refuses overlapping moves
            if not stop.is_set():
                run()

        self._thread = threading.Thread(target=chained, daemon=True, name="gesture")
        self._thread.start()

    def _runner(self, name_or_seq, loop, stop):
        seq = GESTURES.get(name_or_seq, GESTURES["curious"]) if isinstance(name_or_seq, str) else name_or_seq
        seq = styled(seq, self.intensity, self.speed)

        def run() -> None:
            while True:
                for p in seq:
                    if stop.is_set():
                        return
                    self._step(p, stop)
                if not loop or stop.is_set():
                    return

        return run

    def dance(self, bpm: float = 100, seconds: float = 8) -> None:
        self.play(dance_moves(bpm, seconds))
        self.current = "dance"

    def wait(self) -> None:
        if self._thread:
            self._thread.join()

    def wake_up(self) -> None:
        self.play("wake")

    def look_at(self, face_x: float, face_y: float) -> None:
        """Turn the head toward the person's face (image coords -1..1)."""
        self.play([Pose(yaw=-face_x * 28, pitch=face_y * 12, dur=0.5)])

    def go_to_sleep(self) -> None:
        self.play("to_sleep")

    def _goto(self, p: Pose) -> None:
        raise NotImplementedError

    def _step(self, p: Pose, stop: threading.Event) -> None:
        self._goto(p)

    # Gaze (body/gaze.py): only the robot body follows the person; the simulator ignores it.
    def attach_eyes(self, hub) -> None:
        pass

    def set_awake(self, awake: bool) -> None:
        pass

    def close(self) -> None:
        self._stop.set()


class SimBody(BaseBody):
    """No robot: sleeps through the keyframes so timing stays realistic."""

    def __init__(self, clock):
        super().__init__()
        self.clock = clock

    def _goto(self, p: Pose) -> None:
        self.clock.sleep(p.dur)


def _ease(u: float) -> float:
    """Smoothstep: slow in, slow out (no jolts at the start or end of a move)."""
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _lerp_pose(a: Pose, b: Pose, u: float) -> Pose:
    m = lambda x, y: x + (y - x) * u      # noqa: E731
    return Pose(m(a.roll, b.roll), m(a.pitch, b.pitch), m(a.yaw, b.yaw), m(a.z, b.z), m(a.x, b.x),
                (m(a.ant[0], b.ant[0]), m(a.ant[1], b.ant[1])), m(a.body_yaw, b.body_yaw), b.dur)


class ReachyMiniBody(BaseBody):
    """One motion loop drives the robot (set_target at LOOP_HZ). Every tick it sends
    gaze (where the person is, body/gaze.py) + gesture (the current keyframe or recorded
    emotion, eased in and out). So Reachy keeps looking at the person while it gestures, and
    a new gesture starts from wherever the last one was (no jumps when one interrupts another).
    The SDK's own wake_up / goto_sleep moves pause the loop while they run."""

    LOOP_HZ = 50.0
    BODY_MAX_SPEED = 110.0     # deg/s: big body turns stay smooth
    IDLE_RETURN_S = 2.5        # awake and no gesture this long -> ease back to neutral (gaze stays)

    def __init__(self, robot, use_emotion_library: bool = True, rng: random.Random | None = None, gaze: bool = True):
        super().__init__()
        import numpy as np
        from reachy_mini.utils import create_head_pose

        from .gaze import Gaze

        self.np, self.create_head_pose = np, create_head_pose
        self.robot = robot
        self.rng = rng or random.Random()
        try:
            robot.enable_motors()
        except Exception as e:  # SDK raises various errors when the daemon is unhappy; keep going and log
            logger.error("Could not enable Reachy's motors: %s", e)
        self.library = None
        self.available: set[str] = set()
        if use_emotion_library:
            threading.Thread(target=self._load_library, daemon=True, name="emotion-library").start()
        self.gaze = Gaze(self.rng) if gaze else None
        self.hub = None
        self.awake = False
        self.gaze_weight = 0.0           # eases 0 -> 1 after waking, 1 -> 0 when going to sleep
        self._g = self._read_pose()      # gesture pose (relative to the gaze direction)
        self._moving_until = 0.0         # a gesture is in motion until then
        self._sdk_busy = threading.Event()
        self._closed = threading.Event()
        self._last_body = self._g.body_yaw
        self._face_t = 0.0
        self._loop = threading.Thread(target=self._motion_loop, daemon=True, name="motion")
        self._loop.start()

    # ------------------------------------------------------------------ setup
    def _load_library(self) -> None:
        try:
            from reachy_mini.motion.recorded_move import RecordedMoves

            self.library = RecordedMoves(EMOTION_LIBRARY)  # downloads the dataset on first use
            self.available = set(self.library.list_moves())
            logger.info("Emotion library loaded: %d moves", len(self.available))
        except (ImportError, OSError, ValueError) as e:
            logger.warning("Emotion library unavailable, using keyframes only: %s", e)

    def attach_eyes(self, hub) -> None:
        """Faces come from the session's camera thread (perception/face.py) through the signal hub."""
        self.hub = hub

    def set_awake(self, awake: bool) -> None:
        self.awake = awake

    def _matrix_pose(self, m, antennas_rad=None, body_rad: float = 0.0) -> Pose:
        from scipy.spatial.transform import Rotation as R

        np = self.np
        m = np.asarray(m)
        roll, pitch, yaw = R.from_matrix(m[:3, :3]).as_euler("xyz", degrees=True)
        ant = tuple(float(np.rad2deg(a)) for a in antennas_rad) if antennas_rad is not None else (0.0, 0.0)
        return Pose(float(roll), float(pitch), float(yaw), float(m[2, 3] * 1000), float(m[0, 3] * 1000), ant,
                    float(np.rad2deg(body_rad)), 0.0)

    def _read_pose(self) -> Pose:
        """Where the robot really is (after the SDK moved it, or at start-up)."""
        try:
            head = self.robot.get_current_head_pose()
            joints, ants = self.robot.get_current_joint_positions()
            return self._matrix_pose(head, ants, joints[0])
        except Exception as e:  # no daemon / old SDK: assume neutral
            logger.debug("couldn't read the robot's pose: %s", e)
            return Pose(dur=0.0)

    # ------------------------------------------------------------------ gestures
    def play(self, name_or_seq, loop: bool = False) -> None:
        if not self.awake and time.monotonic() > self._moving_until and not self._sdk_busy.is_set():
            self._g = self._read_pose()      # something else may have moved the robot since (checks, another session)
            self._last_body = self._g.body_yaw
        super().play(name_or_seq, loop)

    def _step(self, p: Pose, stop: threading.Event) -> None:
        """Ease from the current gesture pose to keyframe p over p.dur (the loop sends it)."""
        start, t0 = self._g, time.monotonic()
        dur = max(0.05, p.dur)
        self._moving_until = t0 + dur + 0.1
        while not stop.is_set() and not self._closed.is_set():
            u = (time.monotonic() - t0) / dur
            self._g = _lerp_pose(start, p, _ease(u))
            if u >= 1:
                return
            time.sleep(1.0 / self.LOOP_HZ)

    def _goto(self, p: Pose) -> None:      # used by callers outside the runner
        self._step(p, threading.Event())

    def _runner(self, name_or_seq, loop, stop):
        if isinstance(name_or_seq, str) and name_or_seq not in KEYFRAMES_FIRST and self.library is not None:
            names = [n for n in MODE_EMOTIONS.get(name_or_seq, []) if n in self.available]
            if names:
                move = self.library.get(self.rng.choice(names))

                def run() -> None:
                    while True:
                        t0, start = time.monotonic(), self._g
                        while not stop.is_set() and (t := (time.monotonic() - t0) * self.speed) < move.duration:
                            head, antennas, body_yaw = move.evaluate(t)
                            target = self._matrix_pose(head, antennas, body_yaw)
                            # blend in over the first 0.4 s, so the recorded move starts from where Reachy is
                            self._g = _lerp_pose(start, target, _ease(t / 0.4)) if t < 0.4 else target
                            self._moving_until = time.monotonic() + 0.2
                            time.sleep(1.0 / self.LOOP_HZ)
                        if not loop or stop.is_set():
                            return

                return run
        return super()._runner(name_or_seq, loop, stop)

    # ------------------------------------------------------------------ the loop
    def _motion_loop(self) -> None:
        from .coordination import coordinate

        np, period = self.np, 1.0 / self.LOOP_HZ
        last = time.monotonic()
        neutral = Pose(dur=0.0)
        while not self._closed.is_set():
            now = time.monotonic()
            dt, last = now - last, now
            if self._sdk_busy.is_set():
                time.sleep(period)
                continue
            gaze_on = self.gaze is not None and self.awake
            target_w = 1.0 if gaze_on else 0.0
            self.gaze_weight += (1 - math.exp(-dt / 0.9)) * (target_w - self.gaze_weight)
            if self.gaze is not None and self.hub is not None:
                s = self.hub.snapshot()
                if s.face_t and s.face_t != self._face_t:
                    self._face_t = s.face_t
                    self.gaze.observe(s.face_x, s.face_y, s.face_w, s.face_t, s.others_x)
            gy = gp = gb = gl = 0.0
            if self.gaze is not None:
                gy, gp, gb, gl = (v * self.gaze_weight for v in self.gaze.step(now))
            moving = now < self._moving_until
            if self.awake and not moving and (now - self._moving_until) > self.IDLE_RETURN_S:
                self._g = _lerp_pose(self._g, neutral, 1 - math.exp(-dt / 1.2))   # settle, keep looking
            if not moving and self.gaze_weight < 0.01 and not self.awake:
                time.sleep(period)               # asleep and still: nothing to send
                continue
            p = self._g
            body = gb + p.body_yaw
            step = self.BODY_MAX_SPEED * dt
            body = max(self._last_body - step, min(self._last_body + step, body))
            yaw, body, pitch, roll = coordinate(gy + p.yaw, body, gp + p.pitch, p.roll, 0.0)
            self._last_body = body
            try:
                head = self.create_head_pose(x=p.x + gl, z=p.z, roll=roll, pitch=pitch, yaw=yaw, mm=True, degrees=True)
                self.robot.set_target(head=head, antennas=np.deg2rad(list(p.ant)), body_yaw=float(np.deg2rad(body)))
            except Exception as e:  # link hiccup: keep looping, the next tick retries
                logger.debug("set_target failed: %s", e)
            if self.gaze is not None:
                self.gaze.commanded(now, yaw, pitch)
            time.sleep(max(0.0, period - (time.monotonic() - now)))

    def _sdk(self, fn, label: str) -> bool:
        """Run one of the SDK's own moves with the loop paused, then pick up from where it left the robot."""
        self._sdk_busy.set()
        try:
            fn()
            return True
        except Exception as e:
            logger.warning("SDK %s incomplete (%s); continuing with keyframes", label, e)
            return False
        finally:
            self._g = self._read_pose()
            self._last_body = self._g.body_yaw
            self._sdk_busy.clear()

    def wake_up(self) -> None:
        """A gradual wake from wherever Reachy is (no SDK snap to neutral first), then the gaze
        fades in so it turns to the person. Runs on the gesture thread: Reachy talks meanwhile."""
        self.current = "wake"
        stop = self._next_stop()
        keyframes = super()._runner("wake", False, stop)

        self.awake = True        # the gaze fades in during the stretch: Reachy "finds" the person
        self._spawn(keyframes)

    def go_to_sleep(self) -> None:
        """Wind down slowly (gaze fades out, head and antennas lower), then the SDK's sleep pose."""
        self.current = "to_sleep"
        self.awake = False
        stop = self._next_stop()
        wind_down = super()._runner("wind_down", False, stop)

        def run() -> None:
            wind_down()
            if not stop.is_set() and not self._sdk(self.robot.goto_sleep, "goto_sleep"):
                super(ReachyMiniBody, self)._runner("to_sleep", False, stop)()

        self._spawn(run)

    def close(self) -> None:
        super().close()
        self._closed.set()
