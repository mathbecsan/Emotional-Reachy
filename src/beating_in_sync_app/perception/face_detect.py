"""Find and keep the person in view.

* Detection: OpenCV's YuNet CNN face detector (opencv_zoo, ~230 KB ONNX), much more
  robust than Haar cascades in dim light, at angles and in profile (the approach of
  Gaurav-Gosain/reachy_vision, which uses a CNN detector for the same reason). Falls
  back to Haar if the model can't be loaded.
* Identity: when several faces are visible, the one nearest the last known position
  wins, so Reachy keeps following the same person.
* Continuity: when the face disappears (turned away, walking, motion blur), a short-term
  visual tracker (OpenCV MIL) keeps following the head-and-shoulders region for a few
  seconds, so Reachy doesn't freeze or give up the moment the face is not detected.
"""
import logging
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)
MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "face_detection_yunet_2023mar.onnx"
TRACK_HOLD_S = 3.0          # keep following with the visual tracker this long without a face


@dataclass
class Target:
    x: float                 # centre, -1 (left of image) .. 1 (right)
    y: float                 # centre, -1 (top) .. 1 (bottom)
    w: float                 # face width as a share of the image width
    box: tuple               # (x, y, w, h) in pixels of the analysed image
    score: float
    source: str              # "face" | "tracker"
    frontal: bool            # eyes and nose visible (facing Reachy)


def ensure_model() -> Path | None:
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 100_000:
        return MODEL_PATH
    try:
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        return MODEL_PATH
    except OSError as e:
        logger.warning("Couldn't download the YuNet face model (%s); using Haar cascades", e)
        return None


class FaceFinder:
    def __init__(self, width: int = 480, acquire: float = 0.6, keep: float = 0.45):
        import cv2

        self.cv2, self.width = cv2, width
        self.acquire, self.keep = acquire, keep
        self.yunet = None
        model = ensure_model()
        if model is not None and hasattr(cv2, "FaceDetectorYN"):
            try:
                self.yunet = cv2.FaceDetectorYN.create(str(model), "", (width, width), keep, 0.3, 5000)
            except cv2.error as e:
                logger.warning("YuNet unavailable (%s); using Haar cascades", e)
        self.haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.tracker = None
        self.track_t = 0.0
        self.last: Target | None = None
        self.count = 0                       # faces in the last frame (people in view)

    @property
    def engine(self) -> str:
        return "YuNet CNN" if self.yunet is not None else "Haar cascade"

    def _faces(self, img):
        """[(x, y, w, h, score, frontal)] in img pixels."""
        cv2 = self.cv2
        h, w = img.shape[:2]
        if self.yunet is not None:
            self.yunet.setInputSize((w, h))
            _, faces = self.yunet.detect(img)
            out = []
            for f in faces if faces is not None else []:
                x, y, fw, fh = (float(v) for v in f[:4])
                # landmarks: right eye, left eye, nose, mouth corners. Facing = nose between the eyes.
                rex, lex, nx = float(f[4]), float(f[6]), float(f[8])
                lo, hi = min(rex, lex), max(rex, lex)
                frontal = lo + 0.15 * (hi - lo) < nx < hi - 0.15 * (hi - lo)
                out.append((x, y, fw, fh, float(f[-1]), frontal))
            return out
        gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        return [(float(x), float(y), float(fw), float(fh), 0.7, True)
                for (x, y, fw, fh) in self.haar.detectMultiScale(gray, 1.15, 6, minSize=(40, 40))]

    def find(self, frame) -> Target | None:
        cv2 = self.cv2
        h0, w0 = frame.shape[:2]
        img = cv2.resize(frame, (self.width, int(self.width * h0 / w0)))
        h, w = img.shape[:2]
        now = time.monotonic()
        need = self.keep if self.last is not None else self.acquire     # easier to keep than to acquire
        faces = [f for f in self._faces(img) if f[4] >= need]
        self.count = len(faces)
        if faces:
            if self.last is not None:          # same person: nearest to where they were
                lx = (self.last.x + 1) / 2 * w
                ly = (self.last.y + 1) / 2 * h
                faces.sort(key=lambda f: (f[0] + f[2] / 2 - lx) ** 2 + (f[1] + f[3] / 2 - ly) ** 2)
            else:
                faces.sort(key=lambda f: -f[2] * f[3])
            x, y, fw, fh, score, frontal = faces[0]
            # head-and-shoulders box for the fallback tracker
            bx, by = max(0, x - fw * 0.4), max(0, y - fh * 0.2)
            bw, bh = min(w - bx, fw * 1.8), min(h - by, fh * 2.2)
            try:
                self.tracker = cv2.TrackerMIL_create()
                self.tracker.init(img, (int(bx), int(by), int(bw), int(bh)))
                self.track_t = now
            except (cv2.error, AttributeError):
                self.tracker = None
            self.last = Target((x + fw / 2) / w * 2 - 1, (y + fh / 2) / h * 2 - 1, fw / w, (x, y, fw, fh), score, "face", frontal)
            return self.last
        if self.tracker is not None and now - self.track_t < TRACK_HOLD_S:
            ok, (bx, by, bw, bh) = self.tracker.update(img)
            if ok:
                cx, cy = bx + bw / 2, by + bh * 0.3          # the head sits in the top of the box
                self.last = Target(cx / w * 2 - 1, cy / h * 2 - 1, bw / w / 1.8, (bx, by, bw, bh), 0.0, "tracker", False)
                return self.last
        self.tracker = None
        self.last = None
        return None
