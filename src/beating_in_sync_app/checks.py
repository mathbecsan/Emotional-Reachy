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
            sub = _get("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": key}, timeout=6)
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
        t0 = last = time.monotonic()
        problem = None
        try:
            while not self.stop_event.is_set() and time.monotonic() - t0 < self.seconds:
                raw = ser.readline().decode(errors="ignore").replace("\x00", "").strip()
                if "not found" in raw:
                    problem = raw
                try:
                    vals = [int(x) for x in raw.split(",")]
                except ValueError:
                    vals = []
                now = time.monotonic()
                for b, v in zip(bufs, vals):
                    b.push(v, now)
                if now - last >= 0.25:
                    last = now
                    sensors = []
                    for i, (b, a) in enumerate(zip(bufs, ans)):
                        ts, vs = b.snapshot()
                        a.update(ts, vs, now)
                        sensors.append({"n": i + 1, "finger": b.finger_on(now), "bpm": round(a.bpm) if a.has_signal and a.bpm else None,
                                        "raw": vals[i] if i < len(vals) else None})
                    self.bus.emit("probe", ok=problem is None and bool(vals), port=port, sensors=sensors,
                                  left=round(self.seconds - (now - t0)),
                                  detail=problem or ("Streaming" if vals else "No data from the Arduino"),
                                  fix="Check the sensor's 4 wires (SDA→A4, SCL→A5, power, ground), then replug the USB."
                                  if problem or not vals else "")
        finally:
            ser.close()
            self.bus.emit("probe", done=True)
