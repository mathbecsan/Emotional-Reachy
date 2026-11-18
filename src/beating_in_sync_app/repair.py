"""One-button repair: walk through everything that commonly goes wrong, fix what
can be fixed, and leave Reachy in a fresh, known state so the next test is genuine.

Typical causes it handles:
  * the laptop slept, so the robot link went stale while still looking "connected";
  * overlapping tests: a move, the sensor test or the camera test still running;
  * the robot software (daemon) not running (it is started if Reachy is plugged in);
  * motors switched off;
  * Reachy left in an odd pose: it is put to sleep and woken up again.

Each step reports {step, label, status: ok|fixed|failed|skipped, detail, fix} on the
event bus ("repair") as it goes, so the web page can show it live.
"""
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .perception.pulse_sensor import list_ports


logger = logging.getLogger(__name__)
DAEMON = "http://localhost:8000"


def _daemon_status():
    try:
        with urllib.request.urlopen(f"{DAEMON}/api/daemon/status", timeout=3) as r:
            return json.load(r)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _post(path: str):
    req = urllib.request.Request(f"{DAEMON}{path}", data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def reachy_port() -> str | None:
    """Reachy's own USB serial link (not the Arduino's FTDI port, not the USB billboard)."""
    for p in list_ports():
        d, desc = p["device"], p["description"].lower()
        if "usbmodem" in d and "billboard" not in desc and "usbserial" not in d:
            return d
    return None


_ours: subprocess.Popen | None = None     # the robot software this app started, if any


def _our_daemon_pids() -> list[int]:
    """Robot-software processes started by this app (same Python), even from a previous run of the app."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(line.split()[0]) for line in out.splitlines()
            if "reachy_mini.daemon.app.main" in line and sys.executable in line]


def stop_our_daemon() -> bool:
    global _ours
    if _ours is None or _ours.poll() is not None:
        _ours = None
        pids = _our_daemon_pids()
        for pid in pids:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        for _ in range(30):
            if not _our_daemon_pids():
                break
            time.sleep(0.5)
        return bool(pids)
    _ours.terminate()
    try:
        _ours.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _ours.kill()
    _ours = None
    return True


def _port_busy(port: str) -> bool:
    return any(p["device"] == port and p["busy"] for p in list_ports())


def start_daemon(log_dir: Path, tries: int = 2) -> tuple[bool, str]:
    """Start the robot software with this app's own Reachy SDK, if Reachy is plugged in."""
    global _ours
    port = reachy_port()
    if not port:
        return False, "Reachy isn't plugged in (no Reachy USB port found)."
    for _ in range(30):                      # a previous copy may still be shutting down and holding the port
        if not _port_busy(port):
            break
        time.sleep(0.5)
    else:
        return False, f"Reachy's USB port ({port}) is held by another program, probably a copy of the robot software."
    log_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(tries):
        log = open(log_dir / "daemon.log", "a")
        _ours = subprocess.Popen([sys.executable, "-m", "reachy_mini.daemon.app.main", "--fastapi-port", "8000", "--fastapi-host",
                                  "0.0.0.0", "--no-media", "--no-preload-datasets", "--headless", "-p", port],
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env={**os.environ})
        for _ in range(50):                  # it takes ~10 s to configure the motors
            time.sleep(0.5)
            st = _daemon_status()
            if st and st.get("state") == "running" and not st.get("error"):
                return True, f"Started on {port}."
            if st and st.get("error"):
                break
        stop_our_daemon()                     # came up in an error state: clean restart once
        time.sleep(2)
    st = _daemon_status()
    return False, f"It didn't start cleanly ({(st or {}).get('error') or 'no answer'}). See sessions/daemon.log."


def _read_arduino(port: str, seconds: float = 3.0) -> tuple[int, str]:
    """(valid "ir1,ir2" lines read, last error line) from the Arduino, opened exclusively."""
    import serial

    try:
        ser = serial.Serial(port, 115200, timeout=0.5, exclusive=True)
    except (OSError, serial.SerialException):
        return 0, "its port is held by another program"
    try:
        time.sleep(2)                        # the Nano resets when the port opens
        ser.reset_input_buffer()
        n, bad, t0 = 0, "", time.monotonic()
        while time.monotonic() - t0 < seconds:
            line = ser.readline().decode(errors="ignore").replace("\x00", "").strip()
            parts = line.split(",")
            if len(parts) == 2 and all(p.isdigit() for p in parts):
                n += 1
            elif "not found" in line:
                bad = line
        return n, bad
    finally:
        ser.close()


class Repair:
    def __init__(self, runner, bus, cfg, stop_probes):
        self.runner, self.bus, self.cfg, self.stop_probes = runner, bus, cfg, stop_probes
        self.results: list[dict] = []

    def report(self, step: str, label: str, status: str, detail: str = "", fix: str = "") -> None:
        r = {"step": step, "label": label, "status": status, "detail": detail, "fix": fix}
        self.results = [x for x in self.results if x["step"] != step] + [r]
        self.bus.emit("repair", **r)
        logger.info("repair %s: %s %s", step, status, detail)

    def working(self, step: str, label: str, detail: str = "") -> None:
        self.bus.emit("repair", step=step, label=label, status="working", detail=detail)

    def run(self) -> dict:
        r = self.runner
        self.bus.emit("repair", started=True)

        # 1. nothing else may be using the robot
        self.working("session", "No session running")
        if r.running:
            self.report("session", "No session running", "failed", "A session is running.",
                        "End the session first (Current session › End session), then press Repair again.")
            return self.finish()
        self.report("session", "No session running", "ok")

        # 2. stop leftover tests that hold the robot, the Arduino or the camera
        self.working("tests", "Stop leftover tests")
        stopped = self.stop_probes()
        body = getattr(r, "_preview_body", None)
        if body is not None:
            body.close()
            r._preview_body = None
        self.report("tests", "Stop leftover tests", "fixed" if stopped else "ok",
                    f"Stopped: {', '.join(stopped)}." if stopped else "Nothing was left running.")

        # 3. robot software (daemon)
        self.working("daemon", "Robot software")
        st = _daemon_status()
        if st and st.get("state") == "running" and not st.get("error"):
            self.report("daemon", "Robot software", "ok", "Running.")
        elif st and (st.get("error") or st.get("state") != "running"):
            self.working("daemon", "Robot software", f"It reports a problem ({st.get('error') or st.get('state')}): restarting it…")
            if stop_our_daemon():
                ok, msg = start_daemon(Path(self.cfg.sessions_dir))
                self.report("daemon", "Robot software", "fixed" if ok else "failed", msg if ok else msg,
                            "" if ok else "Unplug Reachy's power adapter for 10 seconds, plug it back in, then press Repair again.")
                if not ok:
                    return self.finish()
            else:
                self.report("daemon", "Robot software", "failed", f"It reports an error: {st.get('error') or st.get('state')}",
                            "It was started elsewhere (Reachy Mini Control or a terminal): restart it there. If that "
                            "doesn't help, unplug Reachy's power adapter for 10 seconds.")
                return self.finish()
        else:
            self.working("daemon", "Robot software", "Not running: starting it…")
            ok, msg = start_daemon(Path(self.cfg.sessions_dir))
            if not ok:
                self.report("daemon", "Robot software", "failed", msg,
                            "Check that Reachy is plugged in (USB and power) and switched on, or start it in Reachy Mini Control.")
                return self.finish()
            self.report("daemon", "Robot software", "fixed", msg)

        # 4. a fresh link from this app (a laptop sleep leaves a stale one that looks connected)
        self.working("link", "Connection to Reachy", "Reconnecting…")
        try:
            r.connect_robot()
            self.report("link", "Connection to Reachy", "fixed", "Reconnected with a fresh link.")
        except Exception as e:  # SDK raises several error types when the daemon is unhappy
            self.report("link", "Connection to Reachy", "failed", str(e),
                        "Restart the robot software (or Reachy Mini Control) and press Repair again.")
            return self.finish()
        robot = r.robot

        # 5. motors on
        self.working("motors", "Motors switched on")
        try:
            mode = json.load(urllib.request.urlopen(f"{DAEMON}/api/motors/status", timeout=3)).get("mode")
            if mode != "enabled":
                _post("/api/motors/set_mode/enabled")
                self.report("motors", "Motors switched on", "fixed", f"They were {mode}; switched them on.")
            else:
                self.report("motors", "Motors switched on", "ok")
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            self.report("motors", "Motors switched on", "failed", str(e), "Restart the robot software.")

        # 6. sleep, then wake: back to a known pose
        self.working("reset", "Sleep and wake up", "Reachy is going to sleep…")
        try:
            try:
                robot.cancel_move()
            except Exception:  # nothing to cancel
                pass
            from .checks import goto_when_free

            robot.goto_sleep()
            time.sleep(0.8)
            self.working("reset", "Sleep and wake up", "…and waking up.")
            try:
                robot.wake_up()
            except Exception:  # wake_up also plays a sound, which fails without media; the pose part still runs
                from reachy_mini.utils import create_head_pose

                goto_when_free(robot, head=create_head_pose(), antennas=[0.0, 0.0], body_yaw=0.0, duration=1.5)
            self.report("reset", "Sleep and wake up", "fixed", "Reachy slept and woke up in its neutral pose.")
        except Exception as e:
            self.report("reset", "Sleep and wake up", "failed", str(e), "Check that nothing blocks Reachy's head or body.")

        # 7. every motor answers
        self.working("body", "Head and body move")
        from .checks import body_check

        b = body_check(robot)
        self.report("body", "Head and body move", "ok" if b["ok"] else "failed", b["detail"], b.get("fix", ""))

        # 8. pulse sensors free and streaming
        self.working("sensors", "Pulse sensors")
        free = [p["device"] for p in list_ports() if "usbserial" in p["device"]]
        busy = [p["device"] for p in list_ports() if "usbserial" in p["device"] and p["busy"]]
        if not free:
            self.report("sensors", "Pulse sensors", "failed", "No Arduino found.",
                        "Plug the Arduino's USB cable in (red lights on all boards).")
        elif busy:
            self.report("sensors", "Pulse sensors", "failed", f"{busy[0]} is held by another program.",
                        "Close the Arduino IDE serial monitor or pulse_triple.py, then press Repair again.")
        else:
            n, bad = _read_arduino(free[0])
            if n >= 50:
                self.report("sensors", "Pulse sensors", "ok", f"Arduino on {free[0]}: {n} readings in 3 s.")
            elif bad:
                self.report("sensors", "Pulse sensors", "failed", f"The Arduino says: {bad}",
                            "Check that sensor's 4 wires (SDA→A4, SCL→A5, power, ground), then unplug and replug the Arduino's USB.")
            else:
                self.report("sensors", "Pulse sensors", "failed", f"Only {n} readings in 3 s from {free[0]}.",
                            "Unplug the Arduino's USB cable, wait 5 seconds, plug it back in, then press Repair again.")

        # 9. voice and ears
        self.working("audio", "Voice and microphone")
        from .checks import quick

        q = quick(r)
        ok = q["voice"]["ok"] and q["audio"]["ok"]
        self.report("audio", "Voice and microphone", "ok" if ok else "failed",
                    f"{q['audio']['detail']} · {q['voice']['detail']}", q["voice"]["fix"] or q["audio"]["fix"])
        return self.finish()

    def finish(self) -> dict:
        failed = [x for x in self.results if x["status"] == "failed"]
        out = {"ok": not failed, "results": self.results,
               "summary": "Everything is ready." if not failed else f"{len(failed)} problem(s) still need you."}
        self.bus.emit("repair", done=True, **{k: v for k, v in out.items() if k != "results"})
        return out
