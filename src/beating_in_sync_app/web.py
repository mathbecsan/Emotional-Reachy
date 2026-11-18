"""Web UI backend: facilitator console, session replays, and the Part 2 projection.

Mounted on the FastAPI app the Reachy Mini dashboard hands to the app
(`ReachyMiniApp.settings_app`), or on our own uvicorn server on :7860 when
run standalone -- the same arrangement as reachy_mini_conversation_app.
"""
import asyncio
import json
import logging
from dataclasses import asdict, fields
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import checks
from .body.gestures import EXPRESS_GESTURES, GESTURES
from .brain.personas import BASE, DEFAULT_ORDER, catalog
from .config import Config
from .events import EventBus
from .perception.pulse_sensor import list_ports
from .personality import PROFILES_DIR, default_selection, list_profiles, load_profile, selectable
from .runtime import SessionOptions, SessionRunner


logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


class CommandBody(BaseModel):
    cmd: str


class PresetBody(BaseModel):
    name: str
    description: str = ""
    options: dict


PRESETS_DIR = PROFILES_DIR.parent / "presets"


def _preset_path(name: str) -> Path:
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name.strip().lower()).strip("-")
    if not slug:
        raise HTTPException(400, "preset name is empty")
    return PRESETS_DIR / f"{slug}.json"


class SayBody(BaseModel):
    text: str
    lang: str | None = None


def read_session_log(path: Path) -> dict:
    heart, events = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        (heart if e["kind"] == "heart" else events).append(e)
    return {"name": path.stem, "heart": [[e["t"], e["bpm"]] for e in heart], "events": events}


def mount_routes(app: FastAPI, runner: SessionRunner, bus: EventBus, cfg: Config) -> None:
    sessions_dir = Path(cfg.sessions_dir)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"  # don't keep stale UI modules
        return response

    try:
        app.middleware("http")(no_cache)
    except RuntimeError as e:  # the dashboard's app may already be running
        logger.debug("no-cache middleware not added: %s", e)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    async def state() -> dict:
        return {**bus.snapshot(), "running": runner.running, "robot": runner.robot is not None}

    @app.get("/api/profiles")
    async def profiles() -> list[dict]:
        out = []
        for name in list_profiles():
            p = load_profile(name)
            out.append({"name": name, "display_name": p.display_name, "description": p.description,
                        "accent": p.accent, "provocations": p.provocations, "kind": p.kind,
                        "selectable": selectable(p), "default_selection": default_selection(p),
                        "switch_every": p.switch_every, "music": p.music})
        return out

    @app.get("/api/personas")
    async def personas() -> dict:
        from .brain.activities import ACTIVITIES

        return {"personas": catalog(), "base": BASE, "default_order": DEFAULT_ORDER, "gestures": EXPRESS_GESTURES,
                "activities": [{"key": k, **{x: v[x] for x in ("label", "icon", "text")}} for k, v in ACTIVITIES.items()]}

    @app.post("/api/gesture/{name}")
    async def gesture(name: str, intensity: float = 1.0, speed: float = 1.0) -> dict:
        if name not in GESTURES:
            raise HTTPException(404, "unknown gesture")
        try:
            runner.preview_gesture(name, intensity, speed)
        except RuntimeError as e:
            raise HTTPException(409, str(e)) from e
        return {"status": "playing", "gesture": name}

    # ------------------------------------------------------------ Check setup
    probe = {"thread": None}

    def idle() -> None:
        if runner.running:
            raise HTTPException(409, "A session is running: tests are available once it ends.")

    @app.get("/api/check")
    async def check_all() -> dict:
        return await asyncio.to_thread(checks.quick, runner)

    @app.post("/api/check/connect")
    async def check_connect() -> dict:
        idle()
        try:
            await asyncio.to_thread(runner.connect_robot)
        except Exception as e:  # SDK raises several error types when the daemon is down
            return {"ok": False, "detail": "Couldn't connect", "fix": f"Turn the robot on in Reachy Mini Control first. ({e})"}
        return {"ok": True, "detail": "Connected"}

    @app.post("/api/check/move")
    async def check_move() -> dict:
        try:
            runner.preview_gesture("nod_yes")
        except RuntimeError as e:
            return {"ok": False, "detail": str(e), "fix": "Connect Reachy first."}
        return {"ok": True, "detail": "Reachy nodded. Did you see it move?"}

    @app.post("/api/check/speaker")
    async def check_speaker() -> dict:
        idle()
        return await asyncio.to_thread(checks.speak)

    @app.post("/api/check/mic")
    async def check_mic() -> dict:
        idle()
        try:
            return await asyncio.to_thread(checks.listen)
        except Exception as e:  # PortAudio errors when no input device
            return {"ok": False, "detail": f"Microphone error: {e}", "fix": "Check Reachy's USB audio connection."}

    @app.post("/api/check/camera")
    async def check_camera() -> dict:
        idle()
        return await asyncio.to_thread(checks.camera, cfg.camera_index)

    @app.post("/api/check/sensors")
    async def check_sensors(body: dict | None = None) -> dict:
        idle()
        t = probe["thread"]
        if t is not None and t.is_alive():         # let the previous test release the port first
            t.stop_event.set()
            await asyncio.to_thread(t.join, 5)
        port = (body or {}).get("port") or cfg.heart_port
        probe["thread"] = checks.SensorProbe(bus, port)
        probe["thread"].start()
        return {"ok": True, "detail": "Listening to the sensors for 90 s"}

    @app.post("/api/check/sounds")
    async def check_sounds() -> dict:
        idle()
        try:
            return await asyncio.to_thread(checks.sounds)
        except Exception as e:  # PortAudio errors when no input device
            return {"ok": False, "detail": f"Microphone error: {e}", "fix": "Check Reachy's USB audio connection."}

    track = {"thread": None}

    @app.post("/api/check/track")
    async def check_track() -> dict:
        idle()
        t = track["thread"]
        if t is not None and t.is_alive():
            t.stop_event.set()
            await asyncio.to_thread(t.join, 2)
        robot = runner.robot if runner.robot_ok() else None
        track["thread"] = checks.TrackProbe(bus, robot, cfg.camera_index)
        track["thread"].start()
        return {"ok": True, "following": robot is not None}

    repair_lock = asyncio.Lock()

    def stop_probes() -> list[str]:
        stopped = []
        for name, holder in (("sensor test", probe), ("camera test", track)):
            t = holder["thread"]
            if t is not None and t.is_alive():
                t.stop_event.set()
                t.join(timeout=5)
                stopped.append(name)
        return stopped

    @app.post("/api/repair")
    async def repair() -> dict:
        """One-button repair (repair.py): stale link, leftover tests, daemon, motors, sleep/wake reset, checks."""
        from .repair import Repair

        if repair_lock.locked():
            raise HTTPException(409, "A repair is already running.")
        async with repair_lock:
            return await asyncio.to_thread(Repair(runner, bus, cfg, stop_probes).run)

    @app.get("/api/check/cameras")
    async def cameras() -> dict:
        return {"current": cfg.camera_index, "names": await asyncio.to_thread(checks.camera_names), "indices": [0, 1, 2]}

    @app.get("/api/check/camera/{index}.jpg")
    async def camera_jpg(index: int):
        from fastapi.responses import Response

        idle()
        t = track["thread"]
        if t is not None and t.is_alive():
            t.stop_event.set()
            await asyncio.to_thread(t.join, 2)
        jpg = await asyncio.to_thread(checks.camera_snapshot, index)
        if jpg is None:
            raise HTTPException(404, "no picture from this camera")
        return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/check/camera/use")
    async def camera_use(body: dict) -> dict:
        index = int(body.get("index", 0))
        cfg.camera_index = runner.cfg.camera_index = index
        try:                                         # remember it across restarts (.env is git-ignored)
            env = PROFILES_DIR.parent / ".env"
            lines = [ln for ln in (env.read_text().splitlines() if env.exists() else []) if not ln.startswith("BIS_CAMERA_INDEX=")]
            env.write_text("\n".join(lines + [f"BIS_CAMERA_INDEX={index}"]) + "\n")
        except OSError as e:
            logger.warning("couldn't save the camera choice: %s", e)
        return {"ok": True, "index": index}

    @app.post("/api/check/track/center")
    async def check_track_center() -> dict:
        t = track["thread"]
        if t is not None and t.is_alive():
            t.center(3.0)
        return {"ok": True}

    @app.post("/api/check/track/stop")
    async def check_track_stop() -> dict:
        t = track["thread"]
        if t is not None:
            t.stop_event.set()
        return {"ok": True}

    @app.post("/api/check/mobility")
    async def check_mobility(body: dict | None = None) -> dict:
        idle()
        robot = runner.robot if runner.robot_ok() else None
        await asyncio.to_thread(runner.wait_preview)
        return await asyncio.to_thread(checks.mobility, robot, bus, (body or {}).get("group"))

    @app.post("/api/check/body")
    async def check_body() -> dict:
        idle()
        robot = runner.robot if runner.robot_ok() else None
        return await asyncio.to_thread(checks.body_check, robot, runner.wait_preview)

    @app.get("/api/check/moves")
    async def check_moves() -> list[dict]:
        return [{"key": k, "label": label, "group": g} for k, label, g, _ in checks.MOVES]

    @app.get("/api/check/track/frame.jpg")
    async def track_frame():
        """Latest camera frame while the camera test runs (polled: no long-lived connection)."""
        from fastapi.responses import Response

        t = track["thread"]
        if t is None or t.jpeg is None:
            raise HTTPException(404, "no frame yet")
        return Response(t.jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/check/chat")
    async def check_chat(body: dict) -> dict:
        idle()
        text = str(body.get("text", ""))[:240]
        if say_lock.locked():
            return {"ok": False, "detail": "Reachy is still talking"}
        async with say_lock:
            try:
                return await asyncio.to_thread(checks.chat_turn, text, float(body.get("listen", 7)))
            except Exception as e:  # audio device errors
                return {"ok": False, "detail": f"Audio error: {e}", "fix": "Check Reachy's USB audio connection."}

    say_lock = asyncio.Lock()

    @app.post("/api/check/say")
    async def check_say(body: dict) -> dict:
        """Reachy speaks a short instruction during the setup (e.g. the Follow me game)."""
        idle()
        text = str(body.get("text", ""))[:300]
        if not text:
            return {"ok": False}
        async with say_lock:                        # queue behind anything Reachy is already saying
            return await asyncio.to_thread(checks.speak, text)

    @app.get("/api/voices")
    async def list_voices() -> list[dict]:
        try:
            return await asyncio.to_thread(checks.voices)
        except Exception as e:  # offline / key problem: the picker shows the default voice only
            logger.warning("voices unavailable: %s", e)
            return []

    @app.post("/api/check/sensors/stop")
    async def check_sensors_stop() -> dict:
        t = probe["thread"]
        if t is not None:
            t.stop_event.set()
        return {"ok": True}

    @app.get("/api/presets")
    async def presets() -> list[dict]:
        out = []
        for p in sorted(PRESETS_DIR.glob("*.json")) if PRESETS_DIR.is_dir() else []:
            try:
                out.append({"id": p.stem, **json.loads(p.read_text(encoding="utf-8"))})
            except json.JSONDecodeError:
                logger.warning("Skipping unreadable preset %s", p)
        return out

    @app.post("/api/presets")
    async def save_preset(body: PresetBody) -> dict:
        known = {f.name for f in fields(SessionOptions)} - {"participant"}
        path = _preset_path(body.name)
        PRESETS_DIR.mkdir(exist_ok=True)
        data = {"name": body.name.strip(), "description": body.description.strip(),
                "options": {k: v for k, v in body.options.items() if k in known}}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"id": path.stem, **data}

    @app.delete("/api/presets/{preset_id}")
    async def delete_preset(preset_id: str) -> dict:
        path = _preset_path(preset_id)
        if not path.exists():
            raise HTTPException(404, "no such preset")
        path.unlink()
        return {"status": "deleted"}

    @app.get("/api/ports")
    async def ports() -> list[dict]:
        return list_ports()

    @app.get("/api/options")
    async def options() -> dict:
        return {f.name: getattr(SessionOptions(), f.name) for f in fields(SessionOptions)}

    @app.post("/api/session/start")
    async def start(opts: dict) -> dict:
        known = {f.name for f in fields(SessionOptions)}
        try:
            o = SessionOptions(**{k: v for k, v in opts.items() if k in known})
            for holder in (probe, track):            # free the Arduino port and the camera for the session
                t = holder["thread"]
                if t is not None and t.is_alive():
                    t.stop_event.set()
                    await asyncio.to_thread(t.join, 3)
            runner.start(o)
        except (RuntimeError, FileNotFoundError, TypeError) as e:
            raise HTTPException(409, str(e)) from e
        return {"status": "started", "options": asdict(o)}

    @app.post("/api/command")
    async def command(body: CommandBody) -> dict:
        try:
            runner.command(body.cmd if body.cmd.startswith("/") else "/" + body.cmd)
        except RuntimeError as e:
            raise HTTPException(409, str(e)) from e
        return {"status": "ok"}

    @app.post("/api/say")
    async def say(body: SayBody) -> dict:
        try:
            runner.participant_says(body.text, body.lang)
        except RuntimeError as e:
            raise HTTPException(409, str(e)) from e
        return {"status": "ok"}

    @app.get("/api/sessions")
    async def sessions() -> list[dict]:
        if not sessions_dir.is_dir():
            return []
        out = []
        for p in sorted(sessions_dir.glob("*.jsonl"), reverse=True):
            n_turns = sum(1 for line in p.open(encoding="utf-8") if '"kind": "turn"' in line)
            out.append({"name": p.stem, "size": p.stat().st_size, "turns": n_turns})
        return out

    @app.get("/api/sessions/{name}")
    async def session_detail(name: str) -> dict:
        path = (sessions_dir / f"{name}.jsonl").resolve()
        if path.parent != sessions_dir.resolve() or not path.exists():
            raise HTTPException(404, "no such session")
        return read_session_log(path)

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        queue = bus.subscribe()
        try:
            await socket.send_json({"kind": "snapshot", **bus.snapshot(), "running": runner.running})
            while True:
                event = await queue.get()
                await socket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except asyncio.CancelledError:
            raise
        finally:
            bus.unsubscribe(queue)


def create_app(runner: SessionRunner, bus: EventBus, cfg: Config, warm_audio: bool | None = None) -> FastAPI:
    import os

    app = FastAPI(title="Beating in Sync")
    if warm_audio if warm_audio is not None else not os.environ.get("PYTEST_CURRENT_TEST"):                                   # load the sound classifier in the background
        from .perception.audio_tagger import AudioTagger

        AudioTagger.get()
    mount_routes(app, runner, bus, cfg)
    return app
