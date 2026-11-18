"""Physical heartbeat: Arduino Nano + two MAX30102 pulse sensors.

Hardware and firmware are the team's cs334_project (`pulse_double/pulse_double.ino`):
the Nano prints one line per sample, `ir1,ir2` (raw 18-bit IR, ~100 Hz,
115200 baud). Sensor 1 is on A4/A5 (hardware I2C), sensor 2 on D4/D5.

Beat detection is ported from `pulse_double/pulse_triple.py` (SampleBuffer +
Analyzer): finger detection by IR level, saturation spikes rejected, 1.5 s
trailing-mean detrend, light smoothing, percentile auto-range, 0.65
threshold crossings with a 0.35 s refractory period, BPM = 60 / median of
the last 6 beat intervals. Same constants, so the two programs agree.

Only one program can hold the serial port: close pulse_triple.py and the
Arduino IDE serial monitor before starting a session.

How the two sensors are used (Config.pulse_mode):
  * "wake"   (default) sensor 1 = resting finger for the stage-0 baseline;
             pressing sensor 2 "brings Reachy to life" in stage 1. After that,
             BPM is the mean of whichever sensors have a lock.
  * "one"    any sensor with a pulse wakes Reachy; BPM = mean of both.
  * "two"    sensor 1 = participant, sensor 2 = a companion; both fingers on
             -> two people in the room, and Reachy can notice hearts in sync.
"""
import collections
import glob
import logging
import math
import random
import re
import shutil
import subprocess
import threading
import time

import numpy as np


logger = logging.getLogger(__name__)

# --- constants from pulse_triple.py ---------------------------------------------
WINDOW_S = 6.0          # seconds of signal history kept
FINGER_MIN = 20000      # IR below this = no finger
SAT_MAX = 262000        # IR at/above this = ADC saturated -> counted as a spike
DETREND_S = 1.5         # trailing average length that removes DC level / drift
MIN_RANGE = 30          # detrended peak-to-peak below this = no usable pulse
BEAT_THRESHOLD = 0.65
BEAT_REFRACTORY_S = 0.35
SETTLE_S = 0.6          # ignore this long after a finger lands

BAUD = 115200
IR_LINE = re.compile(r"^\d+,\d+$")
WAVE_POINTS = 90        # waveform points sent to the UI per sensor
EMIT_HZ = 5.0


class SampleBuffer:
    """Thread-safe rolling buffer of (time, IR) for one sensor (from pulse_triple.py)."""

    def __init__(self, finger_min=FINGER_MIN):
        self.finger_min = finger_min
        self.lock = threading.Lock()
        self.t: collections.deque = collections.deque()
        self.v: collections.deque = collections.deque()
        self.rejected = 0
        self.fresh_t = 0.0
        self.last_finger_t = -1e9

    def push(self, value, t=None):
        t = time.monotonic() if t is None else t
        if value < self.finger_min:
            return
        if value >= SAT_MAX:
            with self.lock:
                self.rejected += 1
            return
        with self.lock:
            self.last_finger_t = t
            if self.t and t - self.t[-1] > 0.5:
                self.t.clear()
                self.v.clear()
            if not self.t:
                self.fresh_t = t
            self.t.append(t)
            self.v.append(value)
            cutoff = t - WINDOW_S
            while self.t and self.t[0] < cutoff:
                self.t.popleft()
                self.v.popleft()

    def finger_on(self, now) -> bool:
        return now - self.last_finger_t < 0.5

    def snapshot(self):
        cutoff = time.monotonic() - WINDOW_S
        with self.lock:
            while self.t and self.t[0] < cutoff:
                self.t.popleft()
                self.v.popleft()
            ts = np.array(self.t)
            vs = np.array(self.v, dtype=float)
        if len(ts):
            keep = ts >= self.fresh_t + SETTLE_S
            ts, vs = ts[keep], vs[keep]
        return ts, vs


class BeatAnalyzer:
    """High-passes the signal, auto-ranges it to 0..1 and detects beats (from pulse_triple.py)."""

    def __init__(self, invert=False):
        self.invert = invert
        self.lo = self.hi = None
        self.last_beat = -1e9
        self.intervals: collections.deque = collections.deque(maxlen=6)
        self.bpm = 0.0
        self.has_signal = False
        self.new_beat = False

    def _lost(self):
        self.lo = self.hi = None
        self.bpm = 0.0
        self.intervals.clear()
        self.last_beat = -1e9

    def update(self, ts, vs, now):
        self.has_signal = False
        self.new_beat = False
        if len(vs) < 100 or ts[-1] - ts[0] < 1.5 or now - ts[-1] > 0.5:
            self._lost()
            return None
        fs = (len(ts) - 1) / (ts[-1] - ts[0])
        w = max(3, int(DETREND_S * fs))
        c = np.concatenate(([0.0], np.cumsum(vs)))
        n = np.arange(1, len(vs) + 1)
        start = np.maximum(0, n - w)
        ac = vs - (c[n] - c[start]) / (n - start)
        if self.invert:
            ac = -ac
        k = 2 * max(1, int(round(0.03 * fs))) + 1
        sm = np.convolve(np.pad(ac, (k // 2, k // 2), mode="edge"), np.ones(k) / k, mode="valid")
        lo, hi = np.percentile(sm, [2, 99.5])
        if hi - lo < MIN_RANGE:
            self._lost()
            return None
        if self.lo is None:
            self.lo, self.hi = lo, hi
        else:
            self.lo += (lo - self.lo) * 0.05
            self.hi += (hi - self.hi) * 0.05
        norm = np.clip((sm - self.lo) / (self.hi - self.lo), 0, 1.1)
        self.has_signal = True
        idx = np.where((norm[:-1] < BEAT_THRESHOLD) & (norm[1:] >= BEAT_THRESHOLD))[0]
        for i in idx:
            tb = ts[i + 1]
            if tb - self.last_beat > BEAT_REFRACTORY_S:
                if self.last_beat > 0:
                    self.intervals.append(tb - self.last_beat)
                self.last_beat = tb
                if now - tb < 0.3:
                    self.new_beat = True
        if len(self.intervals) >= 3:
            med = float(np.median(self.intervals))
            if 0.3 < med < 2.0:
                self.bpm = 60.0 / med
        return ts, norm


class SimulatedArduino:
    """Stands in for the serial port: emits `ir1,ir2` lines like the firmware,
    using pulse_triple.py's synthetic waveform, at the BPM a model gives."""

    def __init__(self, bpm_fn, fingers_fn, rate=100):
        self.bpm_fn, self.fingers_fn, self.rate = bpm_fn, fingers_fn, rate
        self.phase = [0.0, 0.37]
        self.last = time.monotonic()

    def readline(self) -> bytes:
        time.sleep(1.0 / self.rate)
        now = time.monotonic()
        dt, self.last = now - self.last, now
        bpm = self.bpm_fn()
        out = []
        for i, on in enumerate(self.fingers_fn()):
            if not on:
                out.append(str(random.randint(800, 3000)))
                continue
            self.phase[i] = (self.phase[i] + ((bpm + (i * 2 - 1)) / 60.0) * dt) % 1.0
            p = self.phase[i]
            s = math.exp(-((p - 0.15) / 0.06) ** 2) + 0.35 * math.exp(-((p - 0.42) / 0.08) ** 2)
            out.append(str(int(120000 + 1200 * s + random.gauss(0, 40) + 1500 * math.sin(now * 0.3 + i))))
        return (",".join(out) + "\n").encode()

    def close(self):
        pass


def _reachy_daemon_ports() -> set[str]:
    """Ports named on a running reachy-mini-daemon command line (`-p <port>`)."""
    try:
        out = subprocess.run(["ps", "-Ao", "command"], capture_output=True, text=True).stdout
    except OSError:
        return set()
    return {m.group(1) for line in out.splitlines() if "reachy-mini-daemon" in line
            for m in [re.search(r"(?:-p|--serialport)[ =](\S+)", line)] if m}


def _busy(device: str) -> bool:
    """True if the Reachy daemon owns the port or another process has it open."""
    if device in _reachy_daemon_ports():
        return True
    if not shutil.which("lsof"):
        return False
    return bool(subprocess.run(["lsof", "-t", device], capture_output=True, text=True).stdout.strip())


def list_ports() -> list[dict]:
    """Serial ports, with `busy` set when another program holds them."""
    try:
        from serial.tools import list_ports as lp

        ports = [{"device": p.device, "description": p.description or ""} for p in lp.comports()]
    except ImportError:
        ports = [{"device": d, "description": ""} for d in glob.glob("/dev/cu.*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")]
    ports = [p for p in ports if "bluetooth" not in p["device"].lower() and "debug" not in p["device"].lower()]
    for p in ports:
        p["busy"] = _busy(p["device"])
    return ports


def find_arduino(probe_s: float = 3.0) -> str | None:
    """First free port that actually streams `ir1,ir2` lines. Ports in use (Reachy's
    own USB link while its daemon runs) are never opened."""
    import serial

    for p in list_ports():
        if p["busy"]:
            logger.info("Skipping %s (in use by another program)", p["device"])
            continue
        try:
            with serial.Serial(p["device"], BAUD, timeout=0.5) as ser:
                time.sleep(2)  # the Nano resets when the port opens
                ser.reset_input_buffer()
                end = time.monotonic() + probe_s
                while time.monotonic() < end:
                    if IR_LINE.match(ser.readline().decode(errors="ignore").strip()):
                        return p["device"]
        except (OSError, serial.SerialException) as e:
            logger.info("Probe of %s failed: %s", p["device"], e)
    return None


class ArduinoPulseSource(threading.Thread):
    """Reads the Nano, runs one BeatAnalyzer per sensor, and feeds the session:
    BPM into HeartAnalyzer (1 Hz), finger/wake state into the SignalHub,
    and waveform + beats to the UI (`pulse` events)."""

    def __init__(self, heart, hub, session_log, clock, port=None, mode="wake", simulated=None,
                 finger_min=FINGER_MIN):
        super().__init__(daemon=True, name="arduino-pulse")
        self.heart, self.hub, self.log, self.clock = heart, hub, session_log, clock
        self.port, self.mode, self.simulated = port, mode, simulated
        self.bufs = [SampleBuffer(finger_min), SampleBuffer(finger_min)]
        self.analyzers = [BeatAnalyzer(), BeatAnalyzer()]
        self.stop_event = threading.Event()
        self.source_label = "simulated Arduino" if simulated else (port or "auto")
        self.wake_armed = mode != "wake"   # in "wake" mode sensor 2 only counts after the baseline

    # ---------------------------------------------------------------- serial
    def _open(self):
        if self.simulated is not None:
            return self.simulated
        import serial

        # One free FTDI (usbserial) port is the Nano: use it directly. Probing every port took seconds
        # and failed whenever the setup checklist's sensor test was still releasing the port.
        free = [p["device"] for p in list_ports() if not p["busy"] and "usbserial" in p["device"]]
        port = self.port or (free[0] if len(free) == 1 else find_arduino())
        if not port:
            raise RuntimeError("No port streaming pulse data. Is the Arduino Nano plugged in (red lights on all three boards)?")
        ser = serial.Serial(port, BAUD, timeout=1, exclusive=True)
        time.sleep(2)  # the Nano resets when the port opens
        ser.reset_input_buffer()
        self.source_label = port
        logger.info("Pulse sensors on %s", port)
        return ser

    def _connect(self):
        """Open the sensors, retrying every 3 s until they answer (or the session stops). Never gives up:
        a session that starts a moment too early, or an Arduino plugged in late, still gets its heartbeat."""
        import serial

        tries, last_note = 0, -1e9
        while not self.stop_event.is_set():
            try:
                ser = self._open()
                self.log.event("sensor", self.clock.now(), text=f"Pulse sensors connected ({self.source_label}).")
                return ser
            except (RuntimeError, OSError, serial.SerialException) as e:
                tries += 1
                if time.monotonic() - last_note > 15:     # say it once, then every 15 s while it lasts
                    last_note = time.monotonic()
                    logger.error("Pulse sensors unavailable: %s", e)
                    self.log.event("sensor", self.clock.now(), text=f"Pulse sensors unavailable, retrying: {e}")
                self.stop_event.wait(3.0)
        return None

    def _reader(self, ser):
        try:
            self._read_lines(ser)
        except Exception as e:  # USB unplugged or port lost: the analysis loop reconnects
            logger.error("Pulse sensors disconnected: %s", e)
        finally:
            try:
                ser.close()
            except Exception:
                pass

    def _read_lines(self, ser):
        while not self.stop_event.is_set():
            line = ser.readline()
            try:
                vals = [int(p) for p in line.decode(errors="ignore").strip().split(",")]
            except ValueError:
                text = line.decode(errors="ignore").strip()
                if "not found" in text:  # firmware: "Sensor 1 not found"
                    logger.error("Arduino: %s", text)
                    self.log.event("sensor", self.clock.now(), text=f"Arduino says: {text}. Check the wiring.")
                continue
            t = time.monotonic()
            for buf, v in zip(self.bufs, vals):
                buf.push(v, t)

    # ---------------------------------------------------------------- analysis
    def run(self):
        while not self.stop_event.is_set():
            ser = self._connect()
            if ser is None:
                return
            reader = threading.Thread(target=self._reader, args=(ser,), daemon=True, name="arduino-serial")
            reader.start()
            self._analyse(reader)
            if not self.stop_event.is_set():
                self.log.event("sensor", self.clock.now(), text="Pulse sensors disconnected: reconnecting…")

    def _analyse(self, reader):
        last_bpm_push = last_emit = 0.0
        was = [False, False]
        while not self.stop_event.is_set() and reader.is_alive():
            now = time.monotonic()
            results = []
            for buf, an in zip(self.bufs, self.analyzers):
                ts, vs = buf.snapshot()
                results.append(an.update(ts, vs, now))
            fingers = [b.finger_on(now) for b in self.bufs]
            locked = [an.bpm if an.has_signal and an.bpm else 0.0 for an in self.analyzers]
            for i in range(2):
                if fingers[i] != was[i]:
                    self.log.event("sensor", self.clock.now(),
                                   text=f"Sensor {i + 1}: finger {'on' if fingers[i] else 'off'}")
            was = fingers

            if now - last_bpm_push >= 1.0:
                last_bpm_push = now
                self._push_heart(fingers, locked)
            if now - last_emit >= 1.0 / EMIT_HZ:
                last_emit = now
                self._emit(fingers, results)
            time.sleep(0.05)

    def _push_heart(self, fingers, locked):
        if self.mode == "two":
            bpm = locked[0] or None
        else:
            vals = [b for b in locked if b]
            bpm = sum(vals) / len(vals) if vals else None
        if bpm:
            self.heart.push(round(bpm, 1))
        if self.mode == "wake":
            if self.heart.baseline_ready():
                self.wake_armed = True
            wake = self.wake_armed and fingers[1] and bool(locked[1] or locked[0])
        else:
            wake = any(locked)
        upd = {"finger_on": any(fingers), "pulse_present": wake,
               "sensor_bpms": [round(b, 1) if b else None for b in locked]}
        if self.mode == "two":
            both = all(locked)
            upd["companion_bpm"] = round(locked[1], 1) if locked[1] else None
            upd["hearts_in_sync"] = both and abs(locked[0] - locked[1]) < 3.0
            if fingers[1]:
                upd["num_people"] = 2
        self.hub.update(**upd)

    def _emit(self, fingers, results):
        sensors = []
        beat = False
        for i, (an, res) in enumerate(zip(self.analyzers, results)):
            wave = []
            if res is not None:
                ts, norm = res
                grid = np.linspace(ts[-1] - 3.0, ts[-1], WAVE_POINTS)
                wave = np.round(np.interp(grid, ts, norm), 3).tolist()
            beat = beat or an.new_beat
            sensors.append({"finger": fingers[i], "signal": an.has_signal, "bpm": round(an.bpm, 1) if an.bpm else None,
                            "spikes": self.bufs[i].rejected, "wave": wave})
        # Waveforms are UI-only; they are not written to the session log.
        if self.log.bus is not None:
            self.log.bus.emit("pulse", source=self.source_label, mode=self.mode, sensors=sensors, beat=beat)

    def stop(self):
        self.stop_event.set()
