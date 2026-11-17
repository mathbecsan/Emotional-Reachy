"""Entry point: CLI (`beating-in-sync`) and Reachy Mini App (`BeatingInSyncApp`).

    beating-in-sync                       # web UI on :7860, simulated robot
    beating-in-sync --robot               # connect to Reachy Mini
    beating-in-sync --headless --scenario scenarios/demo_participant.json --scale 30
    beating-in-sync --headless --listener console
"""
import argparse
import logging
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from .config import config_from_env
from .events import EventBus
from .runtime import SessionOptions, SessionRunner
from .web import create_app, mount_routes


logger = logging.getLogger(__name__)

UI_PORT = 7860


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="beating-in-sync", description="Beating in Sync: Reachy hears your heart.")
    p.add_argument("--robot", action="store_true", help="connect to a Reachy Mini (default: simulated body)")
    p.add_argument("--robot-name", default=None)
    p.add_argument("--headless", action="store_true", help="run one session in the terminal, no web UI")
    p.add_argument("--participant", default="P00")
    p.add_argument("--profile", default="beating_in_sync")
    p.add_argument("--no-tease", action="store_true", help="skip stage 4 (pre-interview answer)")
    p.add_argument("--no-llm", action="store_true", help="offline templates only")
    p.add_argument("--heart", choices=["sim", "arduino", "arduino-sim"], default="sim",
                   help="sim: modelled BPM; arduino: the two MAX30102 sensors; arduino-sim: real pipeline, fake IR")
    p.add_argument("--port", dest="heart_port", default=None, help="Arduino serial port (default: auto-detect)")
    p.add_argument("--pulse-mode", choices=["wake", "one", "two"], default=None)
    p.add_argument("--camera", action="store_true", help="face emotion + attention from the camera")
    p.add_argument("--list-ports", action="store_true", help="list serial ports and exit")
    p.add_argument("--check", action="store_true", help="preflight: Reachy daemon, pulse sensors, Claude key")
    p.add_argument("--listener", choices=["elevenlabs", "console", "mic", "scenario", "web"], default=None)
    p.add_argument("--scenario", default=None)
    p.add_argument("--voice", choices=["elevenlabs", "mac", "sim"], default="elevenlabs")
    p.add_argument("--scale", type=float, default=1.0, help="speed up the session clock (simulation only)")
    p.add_argument("--ui-port", type=int, default=UI_PORT)
    p.add_argument("--debug", action="store_true")
    return p.parse_args(argv)


def setup_logging(debug: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "anthropic", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def load_env() -> None:
    """.env from the working directory, then the project root (where `.env.example` lives)."""
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def options_from_args(args: argparse.Namespace) -> SessionOptions:
    listener = args.listener or ("scenario" if args.scenario else "elevenlabs")
    return SessionOptions(participant=args.participant, profile=args.profile, no_tease=args.no_tease,
                          llm=not args.no_llm, heart=args.heart, heart_port=args.heart_port,
                          pulse_mode=args.pulse_mode, camera=args.camera, listener=listener,
                          scenario=args.scenario, voice=args.voice, time_scale=args.scale)


def run(args: argparse.Namespace, robot=None, settings_app=None, stop_event: threading.Event | None = None) -> None:
    load_env()
    cfg = config_from_env()
    bus = EventBus()

    if robot is None and args.robot:
        from reachy_mini import ReachyMini

        # Speech and music play on this computer, so Reachy's media pipeline isn't needed
        # (and the daemon may run with --no-media, where initialising it hangs).
        robot = ReachyMini(media_backend="no_media", **({"robot_name": args.robot_name} if args.robot_name else {}))
        logger.info("Connected to Reachy Mini")
    runner = SessionRunner(bus, cfg, robot)

    if args.headless:
        runner.start(options_from_args(args))
        runner.wait()
        return

    if settings_app is not None:
        mount_routes(settings_app, runner, bus, cfg)
        logger.info("Web UI mounted on the Reachy Mini app server")
        (stop_event or threading.Event()).wait()
        return

    import uvicorn

    server = uvicorn.Server(uvicorn.Config(create_app(runner, bus, cfg), host="0.0.0.0", port=args.ui_port,
                                           log_level="warning"))
    logger.info("Web UI at http://localhost:%d", args.ui_port)
    if stop_event is None:
        server.run()
        return
    # Started by the Reachy Mini dashboard: serve until it asks the app to stop.
    threading.Thread(target=server.run, daemon=True, name="ui-server").start()
    stop_event.wait()
    server.should_exit = True


def preflight() -> int:
    """Room check before a participant comes in. Returns the number of problems."""
    import json
    import os
    import urllib.error
    import urllib.request

    from .perception.pulse_sensor import find_arduino, list_ports

    load_env()
    problems = 0

    def report(ok: bool, what: str, detail: str = "") -> None:
        nonlocal problems
        problems += not ok
        print(f"[{'ok' if ok else '!!'}] {what}{': ' + detail if detail else ''}")

    try:
        with urllib.request.urlopen("http://localhost:8000/api/daemon/status", timeout=3) as r:
            status = json.load(r)
        report(not status.get("error"), "Reachy daemon", status.get("error") or f"state {status.get('state')}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        report(False, "Reachy daemon", f"not reachable on :8000 ({e})")

    ports = list_ports()
    report(bool(ports), "Serial ports", ", ".join(f"{p['device']}{' (in use)' if p['busy'] else ''}" for p in ports) or "none")
    port = find_arduino()
    report(port is not None, "Pulse Arduino", port or "no free port is streaming ir1,ir2 (plugged in? pulse_triple.py closed?)")

    el = os.environ.get("ELEVENLABS_API_KEY")
    if el:
        try:
            r = urllib.request.urlopen(urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription",
                                                              headers={"xi-api-key": el}), timeout=8)
            sub = json.load(r)
            report(True, "ElevenLabs", f"{sub.get('character_limit', 0) - sub.get('character_count', 0)} characters left")
        except (urllib.error.URLError, TimeoutError) as e:
            report(False, "ElevenLabs", f"key rejected or unreachable ({e})")
    else:
        report(False, "ElevenLabs", "no ELEVENLABS_API_KEY: no voice, no hearing")
    try:
        import sounddevice as sd

        names = [d["name"] for d in sd.query_devices()]
        report(any("Reachy" in n for n in names), "Reachy audio", "Reachy Mini Audio found" if any("Reachy" in n for n in names)
               else "Reachy's mic/speaker not found; laptop audio will be used")
    except (ImportError, OSError) as e:
        report(False, "Audio devices", str(e))
    try:
        import cv2

        casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        seen = []
        for idx in (0, 1, 2):
            cap = cv2.VideoCapture(idx)
            frame = None
            for _ in range(15):
                ok, frame = cap.read()
                if ok:
                    break
                time.sleep(0.05)
            if frame is not None and ok:
                faces = len(casc.detectMultiScale(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 1.2, 5, minSize=(60, 60)))
                seen.append(f"index {idx}: {frame.shape[1]}x{frame.shape[0]}, {faces} face(s)")
            cap.release()
        report(bool(seen), "Camera", "; ".join(seen) if seen else
               "no frames: allow Camera for this app in System Settings > Privacy & Security > Camera")
    except ImportError:
        report(False, "Camera", "OpenCV not installed: pip install -e '.[vision]'")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    report(has_key, "Claude", "key found" if has_key else "no ANTHROPIC_API_KEY: Reachy will use offline English lines")
    return problems


def main() -> None:
    args = parse_args()
    setup_logging(args.debug)
    if args.check:
        raise SystemExit(preflight())
    if args.list_ports:
        from .perception.pulse_sensor import list_ports

        for p in list_ports():
            print(p["device"], "-", p["description"])
        return
    run(args)


try:
    from reachy_mini import ReachyMini, ReachyMiniApp

    class BeatingInSyncApp(ReachyMiniApp):
        """Reachy Mini Apps entry point: the dashboard starts this with a connected robot."""

        custom_app_url = f"http://0.0.0.0:{UI_PORT}/"
        dont_start_webserver = False

        def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
            args = parse_args([])
            setup_logging(False)
            run(args, robot=reachy_mini, settings_app=getattr(self, "settings_app", None), stop_event=stop_event)

except ImportError:  # SDK not installed: CLI + simulation still work
    BeatingInSyncApp = None


if __name__ == "__main__":
    main()
