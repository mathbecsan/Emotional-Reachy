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
                    self._goto(p)
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

    def close(self) -> None:
        self._stop.set()


class SimBody(BaseBody):
    """No robot: sleeps through the keyframes so timing stays realistic."""

    def __init__(self, clock):
        super().__init__()
        self.clock = clock

    def _goto(self, p: Pose) -> None:
        self.clock.sleep(p.dur)


class ReachyMiniBody(BaseBody):
    def __init__(self, robot, use_emotion_library: bool = True, rng: random.Random | None = None):
        super().__init__()
        import numpy as np
        from reachy_mini.utils import create_head_pose

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

    def _load_library(self) -> None:
        try:
            from reachy_mini.motion.recorded_move import RecordedMoves

            self.library = RecordedMoves(EMOTION_LIBRARY)  # downloads the dataset on first use
            self.available = set(self.library.list_moves())
            logger.info("Emotion library loaded: %d moves", len(self.available))
        except (ImportError, OSError, ValueError) as e:
            logger.warning("Emotion library unavailable, using keyframes only: %s", e)

    def _runner(self, name_or_seq, loop, stop):
        if isinstance(name_or_seq, str) and name_or_seq not in KEYFRAMES_FIRST and self.library is not None:
            names = [n for n in MODE_EMOTIONS.get(name_or_seq, []) if n in self.available]
            if names:
                move = self.library.get(self.rng.choice(names))

                def run() -> None:
                    while True:
                        t0 = time.monotonic()
                        while not stop.is_set() and (t := (time.monotonic() - t0) * self.speed) < move.duration:
                            head, antennas, body_yaw = move.evaluate(t)
                            self._set_target(head, antennas, body_yaw)
                            time.sleep(1.0 / CONTROL_HZ)
                        if not loop or stop.is_set():
                            return

                return run
        return super()._runner(name_or_seq, loop, stop)

    def _set_target(self, head, antennas, body_yaw) -> None:
        try:
            self.robot.set_target(head=head, antennas=self.np.asarray(antennas), body_yaw=body_yaw)
        except (RuntimeError, ConnectionError, ValueError) as e:
            logger.warning("set_target failed: %s", e)

    _body = 0.0   # last body yaw we commanded (deg)

    def _goto(self, p: Pose) -> None:
        """Send one keyframe, coordinated so the head travels with the body (body/coordination.py):
        big body turns are split into steps, the head stays within 40 deg of the body."""
        from .coordination import coordinate, turn_steps

        np = self.np
        delta = p.body_yaw - self._body
        if abs(delta) > 50:                       # big turn: head and body travel together in steps
            steps = turn_steps(self._body, p.body_yaw, head_offset=max(-40.0, min(40.0, p.yaw - p.body_yaw)))
            for yaw, body in steps[:-1]:
                head = self.create_head_pose(z=p.z, yaw=yaw, mm=True, degrees=True)
                self.robot.goto_target(head=head, body_yaw=np.deg2rad(body), duration=max(0.3, p.dur / len(steps)))
        yaw, body, pitch, roll = coordinate(p.yaw, p.body_yaw, p.pitch, p.roll, delta)
        head = self.create_head_pose(x=p.x, z=p.z, roll=roll, pitch=pitch, yaw=yaw, mm=True, degrees=True)
        self.robot.goto_target(head=head, antennas=np.deg2rad(list(p.ant)), body_yaw=np.deg2rad(body),
                               duration=p.dur if abs(delta) <= 50 else max(0.3, p.dur / max(1, int(abs(delta) // 50) + 1)))
        self._body = body

    def wake_up(self) -> None:
        """Runs on the gesture thread, so Reachy can start talking while it lifts its head."""
        self.current = "wake"
        stop = self._next_stop()
        keyframes = super()._runner("wake", False, stop)

        def run() -> None:
            try:
                self.robot.wake_up()  # also plays wake_up.wav, which fails when the daemon runs --no-media
            except Exception as e:
                logger.warning("SDK wake_up incomplete (%s); continuing with keyframes", e)
            keyframes()

        self._spawn(run)

    def go_to_sleep(self) -> None:
        self.current = "to_sleep"
        stop = self._next_stop()
        keyframes = super()._runner("to_sleep", False, stop)

        def run() -> None:
            try:
                self.robot.goto_sleep()
            except Exception as e:
                logger.warning("SDK goto_sleep failed (%s); using keyframes", e)
                keyframes()

        self._spawn(run)
