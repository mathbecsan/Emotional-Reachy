"""Non-speech sounds from the microphone: claps, music or singing, loud noise.

Speech recognition only returns words, so a participant who claps, sings or plays
music would be invisible to Reachy. This detector runs on raw audio (16 kHz mono
float) with simple acoustic features, no model download:

  * clap   - a sharp, broadband transient: energy jumps >= 15 dB within ~30 ms
             above the recent floor and is mostly high-frequency;
  * music  - sustained tonal sound (strong periodicity) for >= 2.5 s with few
             pauses; long voiced stretches separate singing/music from speech,
             which pauses every few hundred milliseconds;
  * noise  - loud, sustained, non-tonal sound (fan, crowd, traffic).

`analyse(audio)` labels a recording (setup check); `SoundWatcher.feed(chunk)` runs
on the live microphone during a session and returns events as they happen.
"""
from collections import deque

import numpy as np


SR = 16000
FRAME = 512                       # 32 ms


def _frames(a: np.ndarray, n: int = FRAME) -> np.ndarray:
    a = a[: len(a) // n * n]
    return a.reshape(-1, n) if len(a) else np.zeros((0, n))


def _db(x: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=-1)) + 1e-7)


def _tonal(frame: np.ndarray) -> float:
    """Periodicity strength 0..1 (normalised autocorrelation peak for 80-1000 Hz)."""
    f = frame - frame.mean()
    e = float((f * f).sum())
    if e < 1e-8:
        return 0.0
    ac = np.correlate(f, f, mode="full")[len(f) - 1:]
    lo, hi = SR // 1000, SR // 80
    return float(max(0.0, ac[lo:hi].max() / e))


def _highness(frame: np.ndarray) -> float:
    """Share of energy above 2 kHz."""
    spec = np.abs(np.fft.rfft(frame * np.hanning(len(frame)))) ** 2
    cut = int(2000 / (SR / 2) * len(spec))
    tot = spec.sum() + 1e-12
    return float(spec[cut:].sum() / tot)


def analyse(audio: np.ndarray) -> dict:
    """Label a recording: {"claps": n, "music": bool, "noise": bool, "floor_db", "loud_db", "tonal_ratio", "longest_voiced_s"}."""
    fr = _frames(np.asarray(audio, dtype=np.float32))
    if not len(fr):
        return {"claps": 0, "music": False, "noise": False, "floor_db": -90, "loud_db": -90, "tonal_ratio": 0.0, "longest_voiced_s": 0.0}
    db = _db(fr)
    # The quiet part of the recording, but never louder than a typical room: a song that fills
    # the whole recording must not become its own "background".
    floor = min(float(np.percentile(db, 15)), -42.0)
    claps, last = 0, -99
    for i in range(2, len(db)):
        recent = np.median(db[max(0, i - 15):i - 1])
        if db[i] - recent >= 15 and db[i] > floor + 18 and i - last > 4 and _highness(fr[i]) > 0.25:
            claps += 1
            last = i
    active = db > floor + 10
    tonal = np.array([_tonal(f) > 0.45 if a else False for f, a in zip(fr, active)])
    run = best = 0
    for t in tonal:
        run = run + 1 if t else 0
        best = max(best, run)
    longest = best * FRAME / SR
    act_s = active.sum() * FRAME / SR
    tonal_ratio = float(tonal.sum() / max(1, active.sum()))
    music = act_s >= 2.5 and tonal_ratio >= 0.55 and longest >= 0.9
    noise = act_s >= 2.5 and tonal_ratio < 0.25 and claps < 3 and float(np.percentile(db, 60)) > floor + 20
    return {"claps": claps, "music": bool(music), "noise": bool(noise), "floor_db": round(floor), "loud_db": round(float(db.max())),
            "tonal_ratio": round(tonal_ratio, 2), "longest_voiced_s": round(longest, 2)}


def describe(a: dict) -> list[str]:
    out = []
    if a["music"]:
        out.append("music or singing")
    if a["claps"] >= 2:
        out.append(f"clapping ({a['claps']} claps)")
    elif a["claps"] == 1:
        out.append("a clap or knock")
    if a["noise"]:
        out.append("loud background noise")
    return out


class SoundWatcher:
    """Live detector for the session microphone: feed 100 ms chunks, get events with a cooldown."""

    def __init__(self, window_s: float = 4.0, cooldown_s: float = 20.0):
        self.buf: deque = deque(maxlen=int(window_s * SR / 1600))
        self.cooldown_s = cooldown_s
        self.last: dict[str, float] = {}
        self.t = 0.0

    def feed(self, chunk: np.ndarray) -> list[str]:
        self.t += len(chunk) / SR
        self.buf.append(np.asarray(chunk, dtype=np.float32))
        if len(self.buf) < self.buf.maxlen or int(self.t * 10) % 10:   # analyse once a second on a full window
            return []
        a = analyse(np.concatenate(self.buf))
        found = []
        if a["music"]:
            found.append("music")
        if a["claps"] >= 2:
            found.append("clapping")
        out = [e for e in found if self.t - self.last.get(e, -1e9) >= self.cooldown_s]
        for e in out:
            self.last[e] = self.t
        return out

    def reset(self) -> None:
        self.buf.clear()
