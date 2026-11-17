"""Camera perception: facial emotion, attention, number of people, movement.

Facial emotion uses the FER2013 CNN from kudosscience/fer_and_ter_model
(src/fer/camera_fer_inference.py). The layer layout below matches that
repo exactly so its `models/fer2013_final_model.pth` loads unchanged.
Download the weights into ./models/ (see README).

Attention = a *frontal* face is detected (Haar frontal cascade). When the
participant turns their head or looks at their phone, the frontal detector
loses them and `looking_away_s` starts counting -> Scolding after 3 s.
If the camera is unreliable, the facilitator can trigger Scolding by key.
"""
import logging
import os
import threading
import time

from ..config import Config
from ..signals import SignalHub


logger = logging.getLogger(__name__)

FER_LABELS = {0: "angry", 1: "disgust", 2: "fear", 3: "happy", 4: "sad", 5: "surprise", 6: "neutral"}


def build_emotion_cnn():
    import torch.nn as nn
    import torch.nn.functional as F

    class EmotionCNN(nn.Module):
        def __init__(self, num_classes=7, dropout_rate=0.5):
            super().__init__()
            self.conv1 = nn.Conv2d(1, 32, 3, padding=1); self.bn1 = nn.BatchNorm2d(32)
            self.conv2 = nn.Conv2d(32, 64, 3, padding=1); self.bn2 = nn.BatchNorm2d(64)
            self.conv3 = nn.Conv2d(64, 128, 3, padding=1); self.bn3 = nn.BatchNorm2d(128)
            self.conv4 = nn.Conv2d(128, 256, 3, padding=1); self.bn4 = nn.BatchNorm2d(256)
            self.pool = nn.MaxPool2d(2, 2)
            self.adaptive_pool = nn.AdaptiveAvgPool2d((1, 1))
            self.dropout = nn.Dropout(dropout_rate)
            self.fc1 = nn.Linear(256, 512); self.fc2 = nn.Linear(512, 256); self.fc3 = nn.Linear(256, num_classes)

        def forward(self, x):
            x = self.pool(F.relu(self.bn1(self.conv1(x))))
            x = self.pool(F.relu(self.bn2(self.conv2(x))))
            x = self.pool(F.relu(self.bn3(self.conv3(x))))
            x = self.pool(F.relu(self.bn4(self.conv4(x))))
            x = self.adaptive_pool(x).view(x.size(0), -1)
            x = self.dropout(F.relu(self.fc1(x)))
            x = self.dropout(F.relu(self.fc2(x)))
            return self.fc3(x)

    return EmotionCNN()


class FacePerception(threading.Thread):
    def __init__(self, cfg: Config, hub: SignalHub, show_window=False, session_log=None):
        super().__init__(daemon=True)
        self.cfg, self.hub, self.show, self.log = cfg, hub, show_window, session_log
        self.model = None

    def _load_model(self):
        if not os.path.exists(self.cfg.fer_model_path):
            logger.warning("FER weights not found at %s; attention only, no facial emotion.", self.cfg.fer_model_path)
            return
        import torch
        m = build_emotion_cnn()
        ck = torch.load(self.cfg.fer_model_path, map_location="cpu")
        m.load_state_dict(ck["model_state_dict"] if isinstance(ck, dict) and "model_state_dict" in ck else ck)
        m.eval()
        self.model = m

    def _predict(self, gray_face):
        import cv2
        import torch
        x = cv2.resize(gray_face, (48, 48)).astype("float32") / 255.0
        x = (x - 0.5) / 0.5                                   # same normalisation as the repo
        with torch.no_grad():
            p = torch.softmax(self.model(torch.from_numpy(x)[None, None]), dim=1)[0]
        i = int(p.argmax())
        return FER_LABELS[i], float(p[i])

    def run(self):
        import cv2
        self._load_model()
        frontal = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        cap = cv2.VideoCapture(self.cfg.camera_index)
        ok = cap.isOpened() and cap.read()[0]
        if not ok:
            msg = ("Camera unavailable: allow camera access for this app in System Settings > Privacy & Security > "
                   f"Camera (index {self.cfg.camera_index}). Reachy continues without seeing faces.")
            logger.error(msg)
            if self.log is not None:
                self.log.event("sensor", 0.0, text=msg)
            return
        logger.info("Camera %s open: face emotion + attention on", self.cfg.camera_index)
        if self.log is not None:
            self.log.event("sensor", 0.0, text="Camera on: Reachy can see faces.")
        last_seen = time.monotonic()
        prev_gray = None
        smooth = {}
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = frontal.detectMultiScale(gray, 1.2, 5, minSize=(60, 60))
            now = time.monotonic()
            upd = {"face_visible": len(faces) > 0, "num_people": max(1, len(faces))}
            if len(faces):
                last_seen = now
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])      # closest person
                fh, fw = gray.shape
                upd.update(face_x=round(((x + w / 2) / fw) * 2 - 1, 2), face_y=round(((y + h / 2) / fh) * 2 - 1, 2))
                if self.model is not None:
                    label, conf = self._predict(gray[y:y + h, x:x + w])
                    # exponential smoothing so one noisy frame doesn't flip Reachy's mood
                    for k in FER_LABELS.values():
                        smooth[k] = 0.8 * smooth.get(k, 0.0) + 0.2 * (conf if k == label else 0.0)
                    best = max(smooth, key=smooth.get)
                    upd.update(face_emotion=best, face_conf=round(smooth[best], 2))
            upd["looking_away_s"] = 0.0 if len(faces) else now - last_seen
            if prev_gray is not None:
                diff = cv2.absdiff(cv2.GaussianBlur(gray, (9, 9), 0), cv2.GaussianBlur(prev_gray, (9, 9), 0))
                upd["motion_energy"] = round(min(1.0, float(diff.mean()) / 25.0), 2)
            prev_gray = gray
            self.hub.update(**upd)
            if self.show:
                for (x, y, w, h) in faces:
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 255), 2)
                cv2.imshow("reachy eyes", frame)
                cv2.waitKey(1)
