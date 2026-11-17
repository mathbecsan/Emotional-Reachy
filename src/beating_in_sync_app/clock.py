import time


class Clock:
    """Session clock. In simulation `scale` > 1 makes the session run faster,
    so a 15-minute protocol can be tested in under a minute."""

    def __init__(self, scale: float = 1.0):
        self.scale = max(scale, 1e-6)
        self._t0 = time.monotonic()

    def now(self) -> float:
        return (time.monotonic() - self._t0) * self.scale

    def sleep(self, seconds: float):
        if seconds > 0:
            time.sleep(seconds / self.scale)
