"""Multimodal affect: face + words + heart.

Face/text fusion follows the weighted-average strategy of
kudosscience/fer_and_ter_model (facial 0.6, textual 0.4; agreement boosts
confidence, disagreement keeps the stronger signal at reduced confidence).
Heart rate adds the arousal axis that neither camera nor text gives.
"""
from dataclasses import dataclass
from typing import Optional


VALENCE = {"happy": 0.9, "surprise": 0.3, "neutral": 0.0, "sad": -0.7,
           "fear": -0.6, "angry": -0.8, "disgust": -0.6}
EMO_AROUSAL = {"happy": 0.5, "surprise": 0.8, "neutral": 0.1, "sad": -0.3,
               "fear": 0.7, "angry": 0.8, "disgust": 0.3}


@dataclass
class Affect:
    label: str = "neutral"
    conf: float = 0.0
    valence: float = 0.0     # -1 (negative) .. +1 (positive)
    arousal: float = 0.0     # -1 (calm)     .. +1 (activated)
    source: str = "none"

    @property
    def negative(self) -> bool:
        return self.valence < -0.35 and self.conf >= 0.4


def fuse(face: Optional[str], face_conf: float, text: Optional[str], text_conf: float,
         bpm_delta: float, weights=None) -> Affect:
    w = weights or {"facial": 0.6, "textual": 0.4}
    face_conf = face_conf if face else 0.0
    text_conf = text_conf if text else 0.0
    if not face and not text:
        label, conf, src = "neutral", 0.0, "none"
    elif not face:
        label, conf, src = text, text_conf, "text"
    elif not text:
        label, conf, src = face, face_conf, "face"
    elif face == text:
        label, conf, src = face, min(1.0, (face_conf * w["facial"] + text_conf * w["textual"]) * 1.2), "face+text"
    elif face_conf * w["facial"] > text_conf * w["textual"]:
        label, conf, src = face, face_conf * w["facial"] * 0.8 / max(w["facial"], 1e-6), "face>text"
    else:
        label, conf, src = text, text_conf * w["textual"] * 0.8 / max(w["textual"], 1e-6), "text>face"
    heart_arousal = max(-1.0, min(1.0, bpm_delta / 20.0))
    arousal = max(-1.0, min(1.0, 0.5 * EMO_AROUSAL.get(label, 0) + 0.5 * heart_arousal))
    return Affect(label, round(conf, 2), VALENCE.get(label, 0.0) * (0.5 + 0.5 * conf), round(arousal, 2), src)
