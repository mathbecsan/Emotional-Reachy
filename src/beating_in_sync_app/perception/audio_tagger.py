"""What kind of sound is this? An AudioSet classifier (MIT's Audio Spectrogram Transformer,
527 classes: Piano, Guitar, Singing, Clapping, Ringtone, Laughter, Dog, Speech, ...).

Speech recognition only returns words (and guesses at the rest, e.g. "jingle" for a piano
recording), so non-speech sounds are named here instead. The model downloads once
(~350 MB, Hugging Face cache) and runs on the CPU in a fraction of a second per clip.
If it can't load, callers fall back to perception/sound_events.py (simple acoustics).
"""
import logging
import threading

import numpy as np


logger = logging.getLogger(__name__)
MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"
SR = 16000

# AudioSet label -> what Reachy cares about (first match wins)
CATEGORIES = [
    ("singing", ("singing", "choir", "humming", "vocal music", "rapping", "a capella", "yodeling", "chant", "beatboxing")),
    ("clapping", ("clapping", "applause", "finger snapping", "hands")),
    ("laughter", ("laugh", "giggle", "chuckle", "snicker")),
    ("phone", ("ringtone", "telephone", "alarm", "beep", "buzzer")),
    ("music", ("music", "piano", "keyboard", "guitar", "drum", "violin", "fiddle", "cello", "bass", "synthesizer", "organ",
               "orchestra", "trumpet", "saxophone", "flute", "harp", "ukulele", "percussion", "strum", "plucked",
               "jingle", "song", "theme", "electronic", "hip hop", "rock", "pop", "jazz", "classical", "techno", "reggae")),
    ("speech", ("speech", "conversation", "narration", "babbling", "whispering", "child speech")),
    ("noise", ("noise", "hubbub", "traffic", "vehicle", "engine", "wind", "fan", "air conditioning", "static", "hum",
               "mechanisms", "rumble", "crowd", "chatter")),
]


def category(label: str) -> str:
    low = label.lower()
    for cat, words in CATEGORIES:
        if any(w in low for w in words):
            return cat
    return "other"


class AudioTagger:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.model = self.fe = None
        self.error: str | None = None
        self.ready = threading.Event()

    @classmethod
    def get(cls) -> "AudioTagger":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                threading.Thread(target=cls._instance._load, daemon=True, name="audio-tagger").start()
            return cls._instance

    def _load(self):
        try:
            import torch
            from transformers import ASTFeatureExtractor, ASTForAudioClassification

            self.fe = ASTFeatureExtractor.from_pretrained(MODEL)
            self.model = ASTForAudioClassification.from_pretrained(MODEL).eval()
            self.torch = torch
            torch.set_num_threads(max(1, (torch.get_num_threads() or 4) // 2))
            logger.info("Audio tagger ready (%s)", MODEL)
        except Exception as e:  # missing package, no internet on first run, ...: fall back to acoustics
            self.error = f"{type(e).__name__}: {e}"
            logger.warning("Audio tagger unavailable: %s", self.error)
        finally:
            self.ready.set()

    @property
    def ok(self) -> bool:
        return self.model is not None

    def tag(self, audio: np.ndarray, top: int = 6, min_score: float = 0.08) -> list[dict]:
        """[{label, score, category}] for a 16 kHz mono clip, best first."""
        if not self.ok:
            return []
        a = np.asarray(audio, dtype=np.float32)
        peak = float(np.abs(a).max()) or 1.0
        a = a / peak * 0.5                      # level-normalise: quiet phone speakers still count
        with self.torch.inference_mode():
            inputs = self.fe(a, sampling_rate=SR, return_tensors="pt")
            probs = self.torch.sigmoid(self.model(**inputs).logits[0]).numpy()
        idx = np.argsort(probs)[::-1][:top]
        labels = self.model.config.id2label
        return [{"label": labels[int(i)], "score": round(float(probs[i]), 2), "category": category(labels[int(i)])}
                for i in idx if probs[i] >= min_score]


def summarise(tags: list[dict]) -> dict:
    """Best label per category, e.g. {"music": "Piano", "singing": "Singing"}."""
    out: dict[str, str] = {}
    for t in tags:
        out.setdefault(t["category"], t["label"])
    return out
