"""Tone of voice: *how* the participant says something, not only what.

The live agent receives the words (its own speech recognition); this listens to the same
microphone and measures, per utterance:
  * loudness (dB, speech frames only),
  * pitch (median F0, by autocorrelation) and how much it moves (the spread, in semitones),
  * speed (energy peaks per second, roughly syllables),
and compares them with *this person's own* earlier utterances, because voices differ far more
between people than within one person. The result is a short description for the agent, e.g.
"quieter and slower than before, with a flat pitch (sounds low or tired)".

Plain signal processing (numpy only): no model to download, a few milliseconds per utterance.
"""
from dataclasses import dataclass, field

import numpy as np

RATE = 16000
FRAME = 640              # 40 ms analysis frames
HOP = 320
MIN_VOICED_S = 0.6       # shorter = a cough, a "hm": not described
END_QUIET_S = 0.7        # this much quiet ends the utterance
BASELINE_N = 2           # utterances heard before comparing with "usual"


@dataclass
class ToneReading:
    seconds: float
    loudness_db: float
    pitch_hz: float | None
    spread_st: float          # pitch movement (semitones, interquartile range)
    rate: float               # energy peaks per second
    labels: list[str] = field(default_factory=list)
    mood: str | None = None   # a cautious guess from the combination
    text: str = ""            # the sentence sent to the agent


def _pitch(frame: np.ndarray) -> float | None:
    f = frame - frame.mean()
    if float(np.sqrt(np.mean(f ** 2))) < 1e-4:
        return None
    ac = np.correlate(f, f, "full")[len(f) - 1:]
    ac /= ac[0] + 1e-12
    lo, hi = RATE // 400, RATE // 75            # 75-400 Hz
    lag = lo + int(np.argmax(ac[lo:hi]))
    return RATE / lag if ac[lag] > 0.35 else None


def analyse(audio: np.ndarray, floor: float) -> tuple[float, float | None, float, float] | None:
    """(loudness dB, median pitch, pitch spread st, rate) of one utterance, or None if too little voice."""
    frames = [audio[i:i + FRAME] for i in range(0, len(audio) - FRAME, HOP)]
    if not frames:
        return None
    rms = np.array([np.sqrt(np.mean(f ** 2)) for f in frames])
    voiced = rms > max(floor * 2.0, 0.004)
    if voiced.sum() * HOP / RATE < MIN_VOICED_S * 0.6:
        return None
    loud = float(20 * np.log10(np.mean(rms[voiced]) + 1e-9))
    f0 = [p for f, v in zip(frames, voiced) if v and (p := _pitch(f)) is not None]
    pitch = float(np.median(f0)) if len(f0) >= 5 else None
    spread = 0.0
    if pitch and len(f0) >= 5:
        st = 12 * np.log2(np.array(f0) / pitch)
        spread = float(np.percentile(st, 75) - np.percentile(st, 25))
    env = np.convolve(rms, np.ones(3) / 3, "same")
    peaks = ((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] > max(floor * 3, 0.006))).sum()
    rate = float(peaks / max(0.3, voiced.sum() * HOP / RATE))
    return loud, pitch, spread, rate


class VoiceTone:
    """Feed microphone blocks (float32, 16 kHz); returns a ToneReading when an utterance ends."""

    def __init__(self):
        self.floor = 0.0
        self.buf: list[np.ndarray] = []
        self.quiet = 0.0
        self.talking = False
        self.history: list[ToneReading] = []

    def reset(self) -> None:
        """Reachy started talking (half duplex): drop the half-heard utterance."""
        self.buf, self.quiet, self.talking = [], 0.0, False

    def feed(self, block: np.ndarray) -> ToneReading | None:
        rms = float(np.sqrt(np.mean(block ** 2)))
        if not self.talking:
            self.floor = rms if not self.floor else 0.95 * self.floor + 0.05 * min(rms, self.floor * 3)
        start = max(self.floor * 2.5, 0.008)
        dur = len(block) / RATE
        if rms > start:
            self.talking, self.quiet = True, 0.0
        elif self.talking:
            self.quiet += dur
        if self.talking:
            self.buf.append(block.copy())
        if self.talking and (self.quiet >= END_QUIET_S or len(self.buf) * dur > 15):
            audio = np.concatenate(self.buf)
            self.reset()
            return self.read(audio)
        return None

    def read(self, audio: np.ndarray) -> ToneReading | None:
        a = analyse(audio, self.floor)
        if a is None:
            return None
        r = ToneReading(len(audio) / RATE, *a)
        self.describe(r)
        self.history.append(r)
        return r

    def describe(self, r: ToneReading) -> None:
        base = self.history[-6:]
        labels = []
        if len(base) >= BASELINE_N:
            med = lambda xs: float(np.median(xs)) if xs else None   # noqa: E731
            loud = med([b.loudness_db for b in base])
            pitch = med([b.pitch_hz for b in base if b.pitch_hz])
            spread = med([b.spread_st for b in base if b.pitch_hz])
            rate = med([b.rate for b in base])
            if r.loudness_db > loud + 4:
                labels.append("louder")
            elif r.loudness_db < loud - 4:
                labels.append("quieter")
            if r.pitch_hz and pitch:
                d = 12 * np.log2(r.pitch_hz / pitch)
                labels += ["higher-pitched"] if d > 2 else ["lower-pitched"] if d < -2 else []
            if r.pitch_hz and spread:
                labels += ["more animated"] if r.spread_st > spread * 1.5 + 0.5 else \
                          ["flatter"] if r.spread_st < spread * 0.6 else []
            if rate:
                labels += ["faster"] if r.rate > rate * 1.3 else ["slower"] if r.rate < rate * 0.7 else []
        else:                                  # first utterances: only clear extremes, in absolute terms
            if r.pitch_hz and r.spread_st > 5:
                labels.append("very animated")
            elif r.pitch_hz and r.spread_st < 1.0 and r.seconds > 1.5:
                labels.append("flat")
        r.labels = labels
        has = set(labels)
        if {"louder", "more animated"} <= has or {"higher-pitched", "faster", "more animated"} <= has:
            r.mood = "excited or energised"
        elif {"quieter", "slower"} <= has or ({"quieter", "flatter"} <= has):
            r.mood = "low, tired or unsure"
        elif {"faster", "higher-pitched"} <= has and "louder" not in has:
            r.mood = "nervous or rushed"
        elif "louder" in has and "flatter" in has:
            r.mood = "firm or irritated"
        elif "very animated" in has:
            r.mood = "lively"
        elif r.seconds < 1.2 and "quieter" in has:
            r.mood = "hesitant"
        if labels:
            words = " and ".join(labels[:3])
            compare = " than before" if len(base) >= BASELINE_N else ""
            r.text = f"they said that {words}{compare}" + (f" (sounds {r.mood})" if r.mood else "")
