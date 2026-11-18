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
                         "fix": "Press Connect Reachy: it restarts the robot software by itself. If it fails again, check the robot's power supply and its USB cable or hub." if err else ""}
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


SPEECH_LOCK = threading.Lock()      # one voice at a time (instructions, hints, the chat)


def speak(text: str = "Hi! I'm Reachy. I can hear you, and now you can hear me.", wait: bool = True) -> dict:
    """Say `text` through Reachy. wait=False skips it if Reachy is already talking (used for hints)."""
    from . import elevenlabs
    from .clock import Clock

    if not elevenlabs.api_key():
        return {"ok": False, "detail": "No ElevenLabs key", "fix": "Add ELEVENLABS_API_KEY to .env."}
    if not SPEECH_LOCK.acquire(blocking=wait, timeout=15 if wait else -1):
        return {"ok": False, "detail": "Reachy is already talking"}
    try:
        v = elevenlabs.ElevenLabsVoice(Clock(1.0))
        t = time.monotonic()
        v.say(text, "en", 1.0, "base")
    finally:
        SPEECH_LOCK.release()
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


BOOT_GRACE = 12          # s allowed for the Nano's first line after the port opens


class SensorProbe(threading.Thread):
    """Streams both pulse sensors to the UI (finger on/off, live BPM) for up to 90 s."""

    def __init__(self, bus, port: str | None = None, seconds: float = 300):
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
        ser = None
        for _ in range(10):                  # exclusive: a second reader would split the lines between us
            try:
                ser = serial.Serial(port, BAUD, timeout=0.5, exclusive=True)
                break
            except (OSError, serial.SerialException) as e:
                err = e
                if self.stop_event.wait(0.5):
                    return
        if ser is None:
            self.bus.emit("probe", ok=False, detail=f"The Arduino's port is held by another program ({err}).",
                          fix="Close the Arduino IDE serial monitor or pulse_triple.py, then press Retry (or Repair).")
            return
        bufs, ans = [SampleBuffer(), SampleBuffer()], [BeatAnalyzer(), BeatAnalyzer()]
        time.sleep(2)  # the Nano resets when the port opens
        ser.reset_input_buffer()
        t0 = last = last_data = time.monotonic()
        problem, problem_t = None, 0.0
        vals, resets = [], 0
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
                if resets < 2 and ((vals and now - last_data > 3) or (problem and not vals and now - t0 > 4)):
                    # The board stopped streaming (I2C hang): reopen the port to reset it, quietly.
                    resets += 1
                    ser.close()
                    ser = serial.Serial(port, BAUD, timeout=0.5, exclusive=True)
                    time.sleep(2)
                    ser.reset_input_buffer()
                    vals, t0 = [], time.monotonic()
                    last_data, problem = t0, None
                    continue
                if len(parsed) >= 2:            # a good line: the board works (forget an old "not found")
                    resets = 0 if now - last_data < 1 else resets
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
                    # The 4 s silence clock only starts once data has flowed: a slow-booting board
                    # (it resets on every open) gets up to BOOT_GRACE s for its first line instead of
                    # failing, and a retry (which resets it again) no longer repeats the same failure.
                    booting = not vals and now - t0 < BOOT_GRACE
                    stale = (now - last_data > 4) if vals else not booting
                    ok = not stale and problem is None
                    self.bus.emit("probe", ok=ok, port=port, sensors=sensors, left=round(self.seconds - (now - t0)),
                                  starting=booting,
                                  detail=problem or ("Streaming" if ok else ("No data from the Arduino for 4 seconds" if vals
                                                     else f"The Arduino sent nothing for {BOOT_GRACE} seconds after connecting")),
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
    """Camera test and follow-me: finds the person (YuNet CNN + short-term tracker), tells whether
    they face Reachy, and turns Reachy's head and body to follow them, in the world frame, using
    the robot's real angles at capture time (approach of Gaurav-Gosain/reachy_vision: fast head,
    slow body that only turns while the head is twisted, head kept within 35 deg of the body).
    When the person is lost Reachy keeps going their way, then sweeps gently, and says out loud
    what the person should do. Runs until stopped (or 5 minutes)."""

    HALF_FOV = 35.0          # deg: half the camera's horizontal field of view
    HINT_GAP = 9.0           # s between two spoken hints

    def __init__(self, bus, robot=None, index: int = 0, seconds: float = 300, coach: bool = True):
        super().__init__(daemon=True, name="track-probe")
        self.bus, self.robot, self.index, self.seconds, self.coach = bus, robot, index, seconds, coach
        self.stop_event = threading.Event()
        self.jpeg: bytes | None = None      # latest frame with the face box, for the live preview
        self.last_hint_t = 0.0
        self.hinted: set[str] = set()
        self.center_until = 0.0              # face forward (ignore the person) until this time

    def center(self, seconds: float = 3.0) -> None:
        """Turn back to face forward for a moment, e.g. before asking the person to stand in front."""
        self.center_until = time.monotonic() + seconds

    def hint(self, code: str, text: str, force: bool = False) -> None:
        """Written hint on the page + spoken by Reachy (never twice within HINT_GAP, never over other speech)."""
        now = time.monotonic()
        self.bus.emit("track", hint=code, hint_text=text)
        if not self.coach or (not force and now - self.last_hint_t < self.HINT_GAP):
            return
        self.last_hint_t = now
        threading.Thread(target=lambda: speak(text, wait=False), daemon=True).start()

    def _pose(self):
        """Real (head_yaw, body_yaw) in degrees, world frame, or None without a robot."""
        if self.robot is None:
            return None
        import numpy as np

        try:
            m = np.asarray(self.robot.get_current_head_pose())
            j, _ = self.robot.get_current_joint_positions()
            return float(np.rad2deg(np.arctan2(m[1, 0], m[0, 0]))), float(np.rad2deg(j[0]))
        except Exception as e:  # link lost mid-test: keep reporting the camera
            logger.debug("pose read failed: %s", e)
            return None

    def run(self):
        try:
            import cv2

            from .perception.face_detect import FaceFinder
        except ImportError:
            self.bus.emit("track", ok=False, detail="OpenCV not installed", fix="pip install -e '.[vision]'", done=True)
            return
        cap = cv2.VideoCapture(self.index)
        if not cap.isOpened():
            self.bus.emit("track", ok=False, detail="The camera didn't open",
                          fix="Allow the camera in System Settings › Privacy & Security › Camera, then try again.", done=True)
            return
        finder = FaceFinder()
        try:
            from reachy_mini.utils import create_head_pose
        except ImportError:
            create_head_pose = None
        import numpy as np

        head_cmd = body_cmd = target_s = pitch = 0.0
        last_seen_yaw, last_dir, lost_since, found_once = 0.0, 0.0, None, False
        t0 = last_send = time.monotonic()
        seen_front = seen_away = 0
        self.bus.emit("track", ok=True, engine=finder.engine, face=False, state="none", head_yaw=0, body=0)
        try:
            while not self.stop_event.is_set() and time.monotonic() - t0 < self.seconds:
                pose = self._pose()                       # robot angles at capture time
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.03)
                    continue
                now = time.monotonic()
                real_head, real_body = pose if pose else (head_cmd, body_cmd)
                tgt = finder.find(frame)
                h_, w_ = frame.shape[:2]
                preview = cv2.resize(frame, (480, int(480 * h_ / w_)))
                brightness = float(preview.mean())
                if tgt is not None:
                    k = 480 / finder.width
                    x, y, bw, bh = (int(v * k) for v in tgt.box)
                    col = (168, 224, 123) if tgt.source == "face" and tgt.frontal else (77, 201, 255) if tgt.source == "face" else (255, 160, 80)
                    cv2.rectangle(preview, (x, y), (x + bw, y + bh), col, 3)
                self.jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 65])[1].tobytes()

                searching = False
                if tgt is not None:
                    if lost_since and now - lost_since > 1.5 and found_once:
                        self.hint("found", "There you are!", force=True)
                    lost_since, found_once = None, True
                    # where the person is, in the world frame (+ = Reachy's left)
                    person = real_head - tgt.x * self.HALF_FOV
                    target_s += 0.35 * (person - target_s)
                    if abs(person - last_seen_yaw) > 1:
                        last_dir = 1.0 if person > last_seen_yaw else -1.0
                    last_seen_yaw = person
                    pitch = max(-20.0, min(20.0, pitch + tgt.y * 2.5))
                    if tgt.source == "face":
                        seen_front += tgt.frontal
                        seen_away += not tgt.frontal
                    if tgt.w > 0.45:
                        self.hint("too_close", "You're very close! Take a step back so I can see your whole face.")
                    elif tgt.w < 0.06:
                        self.hint("too_far", "You're a bit far. Come a little closer to me.")
                else:
                    lost_since = lost_since or now
                    gone = now - lost_since
                    if found_once and gone < 6 and last_dir and abs(target_s - last_seen_yaw) < 70:
                        target_s = max(-150.0, min(150.0, target_s + last_dir * 3.5))   # keep going their way
                        searching = True
                        if gone > 1.5:
                            side = "left" if last_dir > 0 else "right"
                            self.hint("lost", f"I lost you! I'm looking to my {side}. Step in front of me and face me.")
                    elif gone > 6:
                        # gentle sweep around the body, like reachy_vision's idle look-around
                        target_s = body_cmd + 25 * np.sin((now - lost_since) * 0.6)
                        searching = True
                        if brightness < 45:
                            self.hint("dark", "It's quite dark. Can you turn on a light, or face the light?")
                        elif gone > 3 and not found_once:
                            self.hint("none", "I can't see anyone yet. Sit about one metre in front of me and look at me.")
                        else:
                            self.hint("lost", "I can't find you. Come and stand in front of me, facing me.")
                    if gone > 20:
                        target_s *= 0.97                         # long gone: settle back to the middle
                if now < self.center_until:              # facing forward on request: let head and body come home
                    target_s = 0.0
                    head_cmd += 0.2 * (0.0 - head_cmd)
                    body_cmd += 0.12 * (0.0 - body_cmd)
                # fast head, slow body (body only while the head is twisted), head within 35 deg of the body
                head_cmd += 0.55 * (target_s - head_cmd)
                if abs(head_cmd - body_cmd) > 12:
                    body_cmd += 0.08 * (target_s - body_cmd)
                body_cmd = max(-150.0, min(150.0, body_cmd))
                head_cmd = max(body_cmd - 35, min(body_cmd + 35, head_cmd))
                if self.robot is not None and create_head_pose is not None and now - last_send >= 0.05:
                    last_send = now
                    try:
                        self.robot.set_target(head=create_head_pose(yaw=head_cmd, pitch=pitch, degrees=True),
                                              body_yaw=float(np.deg2rad(body_cmd)))
                    except Exception as e:
                        logger.debug("follow failed: %s", e)
                        self.robot = None
                left = round(self.seconds - (now - t0))
                common = dict(ok=True, head_yaw=round(real_head), body=round(real_body), following=self.robot is not None,
                              left=left, facing_seen=seen_front, away_seen=seen_away, dark=brightness < 45)
                if tgt is not None:
                    # + = the person's left (they face Reachy), relative to Reachy's front
                    angle = -(real_head - tgt.x * self.HALF_FOV)
                    self.bus.emit("track", face=True, x=round(tgt.x, 2), y=round(tgt.y, 2), size=round(tgt.w, 2),
                                  state="facing" if tgt.source == "face" and tgt.frontal else "turned" if tgt.source == "face" else "tracking",
                                  angle=round(angle), source=tgt.source, **common)
                else:
                    self.bus.emit("track", face=False, state="search" if searching else "none", lost_s=round(now - (lost_since or now), 1), **common)
                time.sleep(0.02)
        finally:
            cap.release()
            if self.robot is not None and create_head_pose is not None:
                try:
                    from .checks import goto_when_free

                    goto_when_free(self.robot, head=create_head_pose(), body_yaw=0.0, duration=1.5)
                except Exception as e:
                    logger.debug("recenter failed: %s", e)
            self.bus.emit("track", done=True)


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
    ("over_shoulder", "Look over the shoulder", "Body", _seq(dict(body=100, yaw=140), dur=2.4)),
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

    def head_yaw_now():
        m = np.asarray(robot.get_current_head_pose())
        return float(np.rad2deg(np.arctan2(m[1, 0], m[0, 0])))

    measured = {}
    from .body.coordination import coordinate, turn_steps

    state = {"body": 0.0}

    def go(p, dur):
        """Coordinated move: big body turns go in steps with the head travelling along."""
        target_body = p.get("body", 0.0)
        delta = target_body - state["body"]
        if abs(delta) > 50:
            steps = turn_steps(state["body"], target_body, head_offset=max(-40.0, min(40.0, p.get("yaw", 0.0) - target_body)))
            for yaw, body in steps[:-1]:
                goto_when_free(robot, head=create_head_pose(yaw=yaw, degrees=True), body_yaw=np.deg2rad(body), duration=dur / len(steps))
            dur = dur / len(steps)
        yaw, body, pitch, roll = coordinate(p.get("yaw", 0.0), target_body, p.get("pitch", 0.0), p.get("roll", 0.0), delta)
        head = create_head_pose(x=p.get("x", 0), z=p.get("z", 0), roll=roll, pitch=pitch, yaw=yaw, mm=True, degrees=True)
        goto_when_free(robot, head=head, antennas=np.deg2rad(list(p.get("ant", (0, 0)))), body_yaw=np.deg2rad(body), duration=dur)
        state["body"] = body

    try:
        for key, label, grp, seq in moves:
            bus.emit("mobility", step=key, label=label, group=grp, status="moving")
            start = body_now()
            for pose, dur in seq:
                go(pose, dur)
            time.sleep(0.15)
            measured[key] = {"head_yaw": round(head_yaw_now()), "body": round(body_now()),
                             "target_yaw": seq[-1][0].get("yaw", 0), "target_body": seq[-1][0].get("body", 0)}
            turned = None
            if any("body" in p for p, _ in seq):
                time.sleep(0.2)
                target = seq[-1][0]["body"]
                turned = body_now() - start
                if abs(turned) < abs(target) * 0.4 or (target and turned * target < 0):
                    body_issue = (key, round(turned))
            go({}, 3.0 if turned is not None else 0.6)
            if turned is not None and body_issue and body_issue[0] == key:
                bus.emit("mobility", step=key, label=label, group=grp, status="failed", measured=round(turned))
                continue
            done.append(key)
            bus.emit("mobility", step=key, label=label, group=grp, status="done", measured=None if turned is None else round(turned))
    except Exception as e:  # SDK errors when the daemon drops mid-test
        bus.emit("mobility", step=None, status="error")
        return {"ok": False, "done": done, "measured": measured, "detail": f"Stopped after {len(done)} of {len(moves)} moves",
                "fix": f"Check that nothing blocks Reachy and that it's on in Reachy Mini Control. ({e})"}
    if body_issue:
        return {"ok": False, "done": done, "body_stuck": True, "measured": measured,
                "detail": f"The body didn't turn (it moved {body_issue[1]}° instead of about 150°). The head moves, the body motor doesn't.",
                "fix": BODY_FIX}
    return {"ok": True, "done": done, "measured": measured, "detail": f"All {len(done)} moves played"}


BODY_FIX = ("The body motor isn't turning. It usually stops itself after an overload (when the base is blocked). "
            "Check that nothing touches the base or is wrapped around it, then power-cycle Reachy: unplug the POWER "
            "adapter (not only the USB cable) for 10 seconds, plug it back in, restart the robot software, and press "
            "Connect Reachy. If it still doesn't turn, the body motor or its cable may need attention from Pollen support.")


def goto_when_free(robot, tries: int = 12, **kw) -> None:
    """goto_target, waiting while another move (e.g. the test nod) is still playing:
    the robot software refuses overlapping moves with "a move is already running"."""
    for i in range(tries):
        try:
            robot.goto_target(**kw)
            return
        except Exception as e:  # the SDK raises a generic error for this
            if "already running" not in str(e) or i == tries - 1:
                raise
            time.sleep(0.25)


def body_check(robot, wait_for=None) -> dict:
    """Turn the body 25° each way and measure it: catches a body motor that has shut itself off."""
    if robot is None:
        return {"ok": False, "detail": "Reachy isn't connected", "fix": "Press Connect Reachy first."}
    import numpy as np
    from reachy_mini.utils import create_head_pose

    if wait_for is not None:          # let the nod finish first
        wait_for()

    def body_now():
        j, _ = robot.get_current_joint_positions()
        return float(np.rad2deg(j[0]))

    try:
        start = body_now()
        goto_when_free(robot, head=create_head_pose(yaw=25, degrees=True), body_yaw=np.deg2rad(25), duration=1.0)
        time.sleep(0.2)
        left = body_now() - start
        goto_when_free(robot, head=create_head_pose(yaw=-25, degrees=True), body_yaw=np.deg2rad(-25), duration=1.4)
        time.sleep(0.2)
        right = body_now() - start
        goto_when_free(robot, head=create_head_pose(), body_yaw=0.0, duration=1.0)
    except Exception as e:  # SDK errors when the daemon drops
        if "already running" in str(e):
            return {"ok": False, "detail": "Reachy was still busy with another move.",
                    "fix": "Wait a second and press Test the motors again."}
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

