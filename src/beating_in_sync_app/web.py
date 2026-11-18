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
        return {"personas": catalog(), "base": BASE, "default_order": DEFAULT_ORDER, "gestures": EXPRESS_GESTURES}

    @app.post("/api/gesture/{name}")
    async def gesture(name: str) -> dict:
        if name not in GESTURES:
            raise HTTPException(404, "unknown gesture")
        try:
            runner.preview_gesture(name)
        except RuntimeError as e:
            raise HTTPException(409, str(e)) from e
        return {"status": "playing", "gesture": name}

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


def create_app(runner: SessionRunner, bus: EventBus, cfg: Config) -> FastAPI:
    app = FastAPI(title="Beating in Sync")
    mount_routes(app, runner, bus, cfg)
    return app
