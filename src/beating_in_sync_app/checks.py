"""Setup checks for the web UI's "Check setup" page: is everything connected
before a participant sits down? Each check returns {ok, detail, fix}.

Quick checks (no hardware is held): daemon, robot link, serial ports, voice
service, Reachy's audio devices. Interactive tests (only while no session
runs): move Reachy, speak through its speaker, record the mic and transcribe
it, stream the pulse sensors live, grab a camera frame.
"""
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

from .perception.pulse_sensor import BAUD, BeatAnalyzer, SampleBuffer, find_arduino, list_ports


logger = logging.getLogger(__name__)
DAEMON = "http://localhost:8000"


def _get(url: str, headers: dict | None = None, timeout: float = 3):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout) as r:
        return json.load(r)


_sub_cache: tuple[float, dict] | None = None


def _subscription(key: str) -> dict:
    global _sub_cache
    if _sub_cache and time.monotonic() - _sub_cache[0] < 60:
        return _sub_cache[1]
    sub = _get("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": key}, timeout=6)
    _sub_cache = (time.monotonic(), sub)
    return sub


def quick(runner) -> dict:
    out = {}
    try:
        st = _get(f"{DAEMON}/api/daemon/status")
        err = st.get("error")
        out["daemon"] = {"ok": not err and st.get("state") == "running",
                         "detail": err or f"Running ({st.get('state')})",
                         "fix": "Restart the robot in Reachy Mini Control." if err else ""}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        out["daemon"] = {"ok": False, "detail": "Not running",
                         "fix": "Open Reachy Mini Control and turn the robot on, then press Connect Reachy."}
    linked = runner.robot is not None and runner.robot_ok()
    out["robot"] = {"ok": linked, "detail": "Connected" if linked else "Not connected",
                    "fix": "" if linked else "Press Connect Reachy (after the daemon is running)."}
    ports = list_ports()
    free = [p["device"] for p in ports if not p["busy"] and "usbserial" in p["device"]]
    out["sensors"] = {"ok": bool(free) or runner.running, "detail": ", ".join(free) or
                      ("In use by the running session" if runner.running else "No Arduino found"),
                      "fix": "" if free else "Plug in the Arduino (USB) and close the Arduino IDE serial monitor."}
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        out["voice"] = {"ok": False, "detail": "No API key", "fix": "Add ELEVENLABS_API_KEY to the .env file."}
    else:
        try:
            sub = _subscription(key)
            left = sub.get("character_limit", 0) - sub.get("character_count", 0)
            out["voice"] = {"ok": left > 500, "detail": f"Connected · {left:,} characters left",
                            "fix": "" if left > 500 else "The ElevenLabs plan is almost used up."}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            out["voice"] = {"ok": False, "detail": "Key rejected or no internet", "fix": "Check the Wi-Fi and the key in .env."}
    try:
        import sounddevice as sd

        names = [d["name"] for d in sd.query_devices()]
        has = any("Reachy" in n for n in names)
        out["audio"] = {"ok": has, "detail": "Reachy's mic and speaker found" if has else "Using this computer's mic and speaker",
                        "fix": "" if has else "Check Reachy's USB cable."}
    except (ImportError, OSError) as e:
        out["audio"] = {"ok": False, "detail": str(e), "fix": "Install the mic extra: pip install -e '.[mic]'"}
    return out


def speak(text: str = "Hi! I'm Reachy. I can hear you, and now you can hear me.") -> dict:
    from . import elevenlabs
    from .clock import Clock

    if not elevenlabs.api_key():
        return {"ok": False, "detail": "No ElevenLabs key", "fix": "Add ELEVENLABS_API_KEY to .env."}
    v = elevenlabs.ElevenLabsVoice(Clock(1.0))
    t = time.monotonic()
    v.say(text, "en", 1.0, "base")
    return {"ok": True, "detail": f"Played on {'Reachy' if v.device is not None else 'this computer'} ({time.monotonic() - t:.1f} s)"}


def listen(seconds: float = 4.0) -> dict:
    """Record a few seconds and transcribe them: proves mic + speech recognition end to end."""
    import numpy as np
    import sounddevice as sd

    from . import elevenlabs
    from .clock import Clock

    dev = elevenlabs.find_device("Reachy Mini Audio", "input")
    audio = sd.rec(int(16000 * seconds), samplerate=16000, channels=1, dtype="float32", device=dev)
    sd.wait()
    level = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.abs(audio).max())
    heard = None
    if elevenlabs.api_key() and peak > 0.02:
        u = elevenlabs.ElevenLabsListener(Clock(1.0)).transcribe(audio[:, 0])
        heard = u.text if u else None
    ok = peak > 0.02
    return {"ok": ok, "level": round(min(1.0, level * 20), 2), "heard": heard,
            "detail": (f"Heard: “{heard}”" if heard else "Sound picked up") if ok else "Silence: nothing reached the mic",
            "fix": "" if ok else "Speak louder or check that Reachy's USB audio is connected.",
            "device": "Reachy" if dev is not None else "this computer"}


def camera(index: int = 0) -> dict:
    try:
        import cv2
    except ImportError:
        return {"ok": False, "detail": "OpenCV not installed", "fix": "pip install -e '.[vision]'"}
    cap = cv2.VideoCapture(index)
    frame, ok = None, False
    for _ in range(20):
        ok, frame = cap.read()
        if ok:
            break
        time.sleep(0.05)
    cap.release()
    if not ok:
        return {"ok": False, "detail": f"No picture from camera {index}",
                "fix": "Allow the camera in System Settings › Privacy & Security › Camera."}
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = len(casc.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 1.2, 5, minSize=(60, 60)))
    return {"ok": True, "faces": faces,
            "detail": f"Camera works · {faces} face{'s' if faces != 1 else ''} in view" if faces else "Camera works · no face in view yet",
            "fix": "" if faces else "Sit in front of Reachy to test face detection."}


def camera_snapshot(index: int) -> bytes | None:
    """One JPEG from camera `index` (for the picker), or None if it gives no picture."""
    import cv2

    cap = cv2.VideoCapture(index)
    frame = None
    try:
        if not cap.isOpened():
            return None
        for _ in range(30):
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
                if f.mean() > 3:      # some cameras start with black frames
                    break
            time.sleep(0.05)
    finally:
        cap.release()
    if frame is None:
        return None
    h_, w_ = frame.shape[:2]
    frame = cv2.resize(frame, (320, int(320 * h_ / w_)))
    return cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()


def camera_names() -> list[str]:
    """Camera names as macOS lists them (order may differ from OpenCV's indices)."""
    import subprocess

    try:
        out = subprocess.run(["system_profiler", "SPCameraDataType"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip().rstrip(":") for line in out.splitlines() if line.startswith("    ") and not line.startswith("      ") and line.strip().endswith(":")]


class SensorProbe(threading.Thread):
    """Streams both pulse sensors to the UI (finger on/off, live BPM) for up to 90 s."""

    def __init__(self, bus, port: str | None = None, seconds: float = 90):
        super().__init__(daemon=True, name="sensor-probe")
        self.bus, self.port, self.seconds = bus, port, seconds
        self.stop_event = threading.Event()

    def run(self):
        import serial

        free = [p["device"] for p in list_ports() if not p["busy"] and "usbserial" in p["device"]]
        port = self.port or (free[0] if len(free) == 1 else find_arduino())   # one FTDI port = the Nano: skip probing
        if not port:
            self.bus.emit("probe", ok=False, detail="No Arduino streaming pulse data",
                          fix="Plug in the Arduino and close the Arduino IDE serial monitor.")
            return
        try:
            ser = serial.Serial(port, BAUD, timeout=0.5)
        except (OSError, serial.SerialException) as e:
            self.bus.emit("probe", ok=False, detail=f"Can't open {port}: {e}", fix="Close other programs using the port.")
            return
        bufs, ans = [SampleBuffer(), SampleBuffer()], [BeatAnalyzer(), BeatAnalyzer()]
        time.sleep(2)  # the Nano resets when the port opens
        ser.reset_input_buffer()
        t0 = last = last_data = time.monotonic()
        problem, problem_t = None, 0.0
        vals = []
        try:
            while not self.stop_event.is_set() and time.monotonic() - t0 < self.seconds:
                raw = ser.readline().decode(errors="ignore").replace("\x00", "").strip()
                now = time.monotonic()
                if "not found" in raw:
                    problem, problem_t = raw, now
                try:
                    parsed = [int(x) for x in raw.split(",")]
                except ValueError:
                    parsed = []
                if len(parsed) >= 2:            # a good line: the board works (forget an old "not found")
                    vals, last_data = parsed, now
                    if now - problem_t > 3:
                        problem = None
                for b, v in zip(bufs, parsed):
                    b.push(v, now)
                if now - last >= 0.25:
                    last = now
                    sensors = []
                    for i, (b, a) in enumerate(zip(bufs, ans)):
                        ts, vs = b.snapshot()
                        a.update(ts, vs, now)
                        sensors.append({"n": i + 1, "finger": b.finger_on(now), "bpm": round(a.bpm) if a.has_signal and a.bpm else None,
                                        "raw": vals[i] if i < len(vals) else None})
                    # Only call it a failure when it lasts: right after the port opens the board resets
                    # and the first lines are garbage (that used to fail a re-test that was fine).
                    stale = now - last_data > 4
                    ok = not stale and problem is None
                    self.bus.emit("probe", ok=ok, port=port, sensors=sensors, left=round(self.seconds - (now - t0)),
                                  starting=now - t0 < 4 and not vals,
                                  detail=problem or ("Streaming" if ok else "No data from the Arduino for 4 seconds"),
                                  fix="" if ok else "Check the sensor's 4 wires (SDA→A4, SCL→A5, power, ground), then unplug and replug the Arduino's USB.")
        finally:
            ser.close()
            self.bus.emit("probe", done=True)


# ---------------------------------------------------------------- voices
_voices_cache: list | None = None


def voices() -> list[dict]:
    """ElevenLabs stock voices for the voice picker (cloned voices of team members are left out)."""
    global _voices_cache
    if _voices_cache is not None:
        return _voices_cache
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return []
    data = _get("https://api.elevenlabs.io/v1/voices", {"xi-api-key": key}, timeout=8)
    out = []
    for v in data.get("voices", []):
        if v.get("category") not in ("premade", "professional"):
            continue
        name, _, desc = v["name"].partition(" - ")
        lab = v.get("labels") or {}
        out.append({"id": v["voice_id"], "name": name.strip(), "description": desc.strip() or lab.get("descriptive", ""),
                    "accent": lab.get("accent"), "gender": lab.get("gender"), "age": lab.get("age"),
                    "preview": v.get("preview_url")})
    _voices_cache = out
    return out


# ---------------------------------------------------------------- sounds
def sounds(seconds: float = 6.0) -> dict:
    """Record the room and report speech AND other sounds (ElevenLabs tags events like
    (phone ringing), (music), (laughter)) plus the background noise level."""
    import io
    import re
    import wave

    import httpx
    import numpy as np
    import sounddevice as sd

    from . import elevenlabs

    dev = elevenlabs.find_device("Reachy Mini Audio", "input")
    audio = sd.rec(int(16000 * seconds), samplerate=16000, channels=1, dtype="float32", device=dev)
    sd.wait()
    a = audio[:, 0]
    frames = a[: len(a) // 1600 * 1600].reshape(-1, 1600)
    rms = np.sqrt((frames ** 2).mean(axis=1)) + 1e-9
    noise_db = float(20 * np.log10(np.percentile(rms, 20)))
    peak_db = float(20 * np.log10(rms.max()))
    levels = [round(float(min(1.0, r * 25)), 2) for r in rms]
    speech, events = None, []
    key = elevenlabs.api_key()
    if key and peak_db - noise_db > 4:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
        try:
            r = httpx.post(f"{elevenlabs.API}/speech-to-text", headers={"xi-api-key": key}, timeout=30,
                           data={"model_id": elevenlabs.STT_MODEL, "tag_audio_events": "true"},
                           files={"file": ("room.wav", buf.getvalue(), "audio/wav")})
            r.raise_for_status()
            text = (r.json().get("text") or "").strip()
            # Scribe tags sounds as (laughter) or [music]; everything else is speech
            events = sorted({e.strip().lower() for e in re.findall(r"[\(\[]([^)\]]{2,40})[\)\]]", text)})
            speech = re.sub(r"[\(\[][^)\]]*[\)\]]", "", text).strip(" .,") or None
        except httpx.HTTPError as e:
            logger.warning("sound test transcription failed: %s", e)
    from .perception.audio_tagger import AudioTagger, summarise
    from .perception.sound_events import analyse, describe

    local = analyse(a)
    tagger = AudioTagger.get()
    tags = tagger.tag(a) if tagger.ok and peak_db - noise_db > 4 else []
    if tagger.ok:
        # The classifier names non-speech sounds far better than the speech service's guesses.
        events = [t["label"].lower() for t in tags if t["category"] not in ("speech", "other", "noise") and t["score"] >= 0.15]
        cats = summarise([t for t in tags if t["score"] >= 0.15])
        if "noise" in cats and not events:
            events.append(cats["noise"].lower())
    if local["claps"] >= 2 and not any("clap" in e or "applause" in e for e in events):
        events.append(f"clapping ({local['claps']} claps)")
    if not tagger.ok:
        for e in describe(local):
            if e not in events:
                events.append(e)
    quiet = peak_db - noise_db <= 6 and not events
    loud_room = noise_db > -35
    parts = []
    if speech:
        parts.append(f"Speech: “{speech}”")
    if events:
        parts.append("Sounds: " + ", ".join(events))
    if not parts:
        parts.append("Nothing stood out from the background" if quiet else "Sound picked up, nothing recognised")
    return {"ok": not quiet, "speech": speech, "events": events, "levels": levels, "analysis": local, "tags": tags,
            "classifier": "AudioSet classifier" if tagger.ok else ("loading…" if not tagger.ready.is_set() else "acoustic rules only"),
            "noise_db": round(noise_db), "peak_db": round(peak_db), "device": "Reachy" if dev is not None else "this computer",
            "detail": " · ".join(parts),
            "fix": ("The room is noisy: Reachy may mishear. Close doors or move away from fans." if loud_room else
                    "Speak, clap or play a sound from your phone near Reachy, then test again." if quiet else "")}


# ---------------------------------------------------------------- face following
class TrackProbe(threading.Thread):
    """Camera test: finds the person, tells whether they face Reachy or are turned away,
    and (with the robot connected) turns Reachy's head to follow them. Runs up to 40 s."""

    def __init__(self, bus, robot=None, index: int = 0, seconds: float = 90):
        super().__init__(daemon=True, name="track-probe")
        self.bus, self.robot, self.index, self.seconds = bus, robot, index, seconds
        self.stop_event = threading.Event()
        self.jpeg: bytes | None = None      # latest frame with the face box, for the live preview

    def run(self):
        try:
            import cv2
        except ImportError:
            self.bus.emit("track", ok=False, detail="OpenCV not installed", fix="pip install -e '.[vision]'", done=True)
            return
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            self.bus.emit("track", ok=False, detail="The camera didn't open",
                          fix="Allow the camera in System Settings › Privacy & Security › Camera, then try again.", done=True)
            return
        front = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        side = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
        look = body = pitch = 0.0          # where Reachy looks / where its body points (deg, + = Reachy's left)
        last_dir, lost_since = 0.0, None
        t0, seen_front, seen_away, moved = time.monotonic(), 0, 0, 0.0
        last_x = None
        np_ = __import__("numpy")
        try:
            from reachy_mini.utils import create_head_pose
        except ImportError:
            create_head_pose = None
        try:
            while not self.stop_event.is_set() and time.monotonic() - t0 < self.seconds:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                h_, w_ = frame.shape[:2]
                gray = cv2.cvtColor(cv2.resize(frame, (w_ // 2, h_ // 2)), cv2.COLOR_BGR2GRAY)
                faces = front.detectMultiScale(gray, 1.2, 5, minSize=(40, 40))
                facing = len(faces) > 0
                if not facing:
                    faces = side.detectMultiScale(gray, 1.2, 5, minSize=(40, 40))
                    if not len(faces):        # profile facing the other way: detect on the mirror, map back
                        flipped = side.detectMultiScale(cv2.flip(gray, 1), 1.2, 5, minSize=(40, 40))
                        faces = [(gray.shape[1] - x - fw, y, fw, fh) for (x, y, fw, fh) in flipped]
                preview = cv2.resize(frame, (480, int(480 * h_ / w_)))
                if len(faces):
                    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                    k = 480 / (w_ / 2)
                    cv2.rectangle(preview, (int(x * k), int(y * k)), (int((x + fw) * k), int((y + fh) * k)),
                                  (168, 224, 123) if facing else (77, 201, 255), 3)
                self.jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 65])[1].tobytes()
                now = time.monotonic()
                searching = False
                if len(faces):
                    lost_since = None
                    fx = (x + fw / 2) / (w_ / 2) * 2 - 1
                    fy = (y + fh / 2) / (h_ / 2) * 2 - 1
                    if last_x is not None:
                        moved += abs(fx - last_x)
                    last_x = fx
                    seen_front += facing
                    seen_away += not facing
                    step = -fx * 9                      # face right of centre -> turn right (negative)
                    look = max(-160.0, min(160.0, look + step))
                    if abs(step) > 1:
                        last_dir = 1.0 if step > 0 else -1.0
                    pitch = max(-20.0, min(20.0, pitch + fy * 3))
                else:
                    # Lost them: they probably walked out of view, so keep turning the way they went.
                    lost_since = lost_since or now
                    if last_dir and now - lost_since < 6 and abs(look) < 150:
                        look = max(-155.0, min(155.0, look + last_dir * 4))
                        searching = True
                # The body follows once the head is more than 30 deg off it; the head stays within 45 deg of the body.
                gap = look - body
                if abs(gap) > 30:
                    body = max(-150.0, min(150.0, body + max(-5.0, min(5.0, gap - (25 if gap > 0 else -25)))))
                look = max(body - 45, min(body + 45, look))
                if self.robot is not None and create_head_pose is not None:
                    try:
                        self.robot.set_target(head=create_head_pose(yaw=look, pitch=pitch, degrees=True), body_yaw=float(np_.deg2rad(body)))
                    except Exception as e:  # robot link lost mid-test: keep reporting the camera
                        logger.debug("follow failed: %s", e)
                        self.robot = None
                left = round(self.seconds - (now - t0))
                if len(faces):
                    # Where the person stands, in degrees from Reachy's front (+ = the person's left).
                    # Following recentres the face in the picture, so add Reachy's own turn back in.
                    angle = fx * 30 - (look if self.robot is not None else 0.0)
                    self.bus.emit("track", ok=True, face=True, x=round(float(fx), 2), y=round(float(fy), 2),
                                  state="facing" if facing else "turned", angle=round(float(angle)), head_yaw=round(look),
                                  body=round(body), following=self.robot is not None, left=left,
                                  facing_seen=seen_front, away_seen=seen_away, moved=round(moved, 1))
                else:
                    self.bus.emit("track", ok=True, face=False, state="search" if searching else "none", head_yaw=round(look),
                                  body=round(body), following=self.robot is not None, left=left,
                                  facing_seen=seen_front, away_seen=seen_away, moved=round(moved, 1))
                time.sleep(0.08)
        finally:
            cap.release()
            if self.robot is not None:
                try:
                    from reachy_mini.utils import create_head_pose

                    self.robot.goto_target(head=create_head_pose(), body_yaw=0.0, duration=1.5)
                except Exception as e:
                    logger.debug("recenter failed: %s", e)
            self.bus.emit("track", done=True, facing_seen=seen_front, away_seen=seen_away, moved=round(moved, 1))


# ---------------------------------------------------------------- range of motion
# Each move: (key, label, group, [(pose, seconds), ...]); pose keys: yaw pitch roll x z (head, deg/mm),
# body (deg), ant (two antenna angles, deg). Every move returns to neutral afterwards.
def _seq(*poses, dur=0.7):
    return [(p, dur) for p in poses]


MOVES = [
    ("look_left", "Look left", "Head", _seq(dict(yaw=40))),
    ("look_right", "Look right", "Head", _seq(dict(yaw=-40))),
    ("look_up", "Look up", "Head", _seq(dict(pitch=-25))),
    ("look_down", "Look down", "Head", _seq(dict(pitch=25))),
    ("look_up_left", "Look up and left", "Head", _seq(dict(yaw=30, pitch=-20))),
    ("look_down_right", "Look down and right", "Head", _seq(dict(yaw=-30, pitch=20))),
    ("tilt_left", "Tilt left", "Head", _seq(dict(roll=25))),
    ("tilt_right", "Tilt right", "Head", _seq(dict(roll=-25))),
    ("circle", "Roll the head in a circle", "Head", _seq(dict(pitch=-15), dict(yaw=25), dict(pitch=15), dict(yaw=-25), dur=0.45)),
    ("nod", "Nod yes", "Expressions", _seq(dict(pitch=15), dict(pitch=-5), dict(pitch=15), dur=0.3)),
    ("shake", "Shake no", "Expressions", _seq(dict(yaw=25), dict(yaw=-25), dict(yaw=20), dur=0.3)),
    ("curious", "Curious tilt", "Expressions", _seq(dict(roll=20, pitch=-8, ant=(-30, 10)), dur=0.6)),
    ("lift", "Stretch up", "Height & lean", _seq(dict(z=20))),
    ("sink", "Sink down", "Height & lean", _seq(dict(z=-15))),
    ("lean_forward", "Lean forward", "Height & lean", _seq(dict(x=15, pitch=10))),
    ("lean_back", "Lean back", "Height & lean", _seq(dict(x=-15, pitch=-10))),
    ("turn_left", "Turn the body left (150°)", "Body", _seq(dict(body=75, yaw=75), dict(body=150, yaw=150), dur=1.6)),
    ("turn_right", "Turn the body right (150°)", "Body", _seq(dict(body=-75, yaw=-75), dict(body=-150, yaw=-150), dur=1.6)),
    ("over_shoulder", "Look over the shoulder", "Body", _seq(dict(body=90, yaw=140), dur=2.0)),
    ("ant_one", "Both antennas one way", "Antennas", _seq(dict(ant=(-60, -60)))),
    ("ant_other", "Both antennas the other way", "Antennas", _seq(dict(ant=(60, 60)))),
    ("ant_left", "Left antenna only", "Antennas", _seq(dict(ant=(0, -60)))),
    ("ant_right", "Right antenna only", "Antennas", _seq(dict(ant=(-60, 0)))),
    ("ant_wave", "Wave the antennas", "Antennas", _seq(dict(ant=(-50, 40)), dict(ant=(40, -50)), dict(ant=(-50, 40)), dur=0.25)),
]
MOBILITY = [(k, label) for k, label, *_ in MOVES]


def mobility(robot, bus, group: str | None = None) -> dict:
    """Run Reachy through its range of motion, step by step (the body turns +-150 deg: its limit is +-160,
    so a full 360 isn't possible). `group` limits the test to Head / Expressions / Height & lean / Body / Antennas."""
    if robot is None:
        return {"ok": False, "detail": "Reachy isn't connected", "fix": "Connect Reachy first (step 1 of the setup)."}
    import numpy as np
    from reachy_mini.utils import create_head_pose

    moves = [m for m in MOVES if not group or m[2] == group]
    done, body_issue = [], None

    def body_now():
        j, _ = robot.get_current_joint_positions()
        return float(np.rad2deg(j[0]))

    def go(p, dur):
        head = create_head_pose(x=p.get("x", 0), z=p.get("z", 0), roll=p.get("roll", 0), pitch=p.get("pitch", 0),
                                yaw=p.get("yaw", 0), mm=True, degrees=True)
        robot.goto_target(head=head, antennas=np.deg2rad(list(p.get("ant", (0, 0)))), body_yaw=np.deg2rad(p.get("body", 0)),
                          duration=dur)

    try:
        for key, label, grp, seq in moves:
            bus.emit("mobility", step=key, label=label, group=grp, status="moving")
            start = body_now()
            for pose, dur in seq:
                go(pose, dur)
            turned = None
            if any("body" in p for p, _ in seq):
                time.sleep(0.2)
                target = seq[-1][0]["body"]
                turned = body_now() - start
                if abs(turned) < abs(target) * 0.4 or (target and turned * target < 0):
                    body_issue = (key, round(turned))
            go({}, 2.0 if turned is not None else 0.6)
            if turned is not None and body_issue and body_issue[0] == key:
                bus.emit("mobility", step=key, label=label, group=grp, status="failed", measured=round(turned))
                continue
            done.append(key)
            bus.emit("mobility", step=key, label=label, group=grp, status="done", measured=None if turned is None else round(turned))
    except Exception as e:  # SDK errors when the daemon drops mid-test
        bus.emit("mobility", step=None, status="error")
        return {"ok": False, "done": done, "detail": f"Stopped after {len(done)} of {len(moves)} moves",
                "fix": f"Check that nothing blocks Reachy and that it's on in Reachy Mini Control. ({e})"}
    if body_issue:
        return {"ok": False, "done": done, "body_stuck": True,
                "detail": f"The body didn't turn (it moved {body_issue[1]}° instead of about 150°). The head moves, the body motor doesn't.",
                "fix": BODY_FIX}
    return {"ok": True, "done": done, "detail": f"All {len(done)} moves played"}


BODY_FIX = ("The body motor has probably stopped itself after an overload (it does this to protect itself when it's "
            "blocked). Check that nothing is touching the base or wrapped around it, then power-cycle Reachy: unplug its "
            "power for 10 seconds, plug it back in, turn it on again in Reachy Mini Control, and press Connect Reachy.")


def body_check(robot) -> dict:
    """Turn the body 25° each way and measure it: catches a body motor that has shut itself off."""
    if robot is None:
        return {"ok": False, "detail": "Reachy isn't connected", "fix": "Press Connect Reachy first."}
    import numpy as np
    from reachy_mini.utils import create_head_pose

    def body_now():
        j, _ = robot.get_current_joint_positions()
        return float(np.rad2deg(j[0]))

    try:
        start = body_now()
        robot.goto_target(head=create_head_pose(yaw=25, degrees=True), body_yaw=np.deg2rad(25), duration=1.0)
        time.sleep(0.2)
        left = body_now() - start
        robot.goto_target(head=create_head_pose(yaw=-25, degrees=True), body_yaw=np.deg2rad(-25), duration=1.4)
        time.sleep(0.2)
        right = body_now() - start
        robot.goto_target(head=create_head_pose(), body_yaw=0.0, duration=1.0)
    except Exception as e:  # SDK errors when the daemon drops
        return {"ok": False, "detail": f"Couldn't move the body: {e}", "fix": BODY_FIX}
    moved = left - right
    if moved < 20:
        return {"ok": False, "moved": round(moved), "detail": f"The body barely turned ({moved:.0f}° of 50°).", "fix": BODY_FIX}
    return {"ok": True, "moved": round(moved), "detail": f"The body turns ({moved:.0f}° of 50°)."}



def chat_turn(text: str, listen_s: float = 7.0) -> dict:
    """Setup conversation: Reachy says a line, then listens for the reply (same pipeline as a session)."""
    from . import elevenlabs
    from .clock import Clock

    if not elevenlabs.api_key():
        return {"ok": False, "detail": "No ElevenLabs key", "fix": "Add ELEVENLABS_API_KEY to .env."}
    clock = Clock(1.0)
    voice = elevenlabs.ElevenLabsVoice(clock)
    voice.say(text, "en", 1.0, "base")
    if listen_s <= 0:
        return {"ok": True, "heard": None, "speaker": "Reachy" if voice.device is not None else "this computer"}
    u = elevenlabs.ElevenLabsListener(clock).listen(listen_s)
    return {"ok": True, "heard": u.text if u else None, "lang": u.language if u else None,
            "speaker": "Reachy" if voice.device is not None else "this computer"}
