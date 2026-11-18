"""Thread-safe event bus between the session (worker thread) and the web UI (asyncio).

The session calls `emit(kind, **data)` from any thread. The web layer
subscribes an asyncio queue per websocket. A running `state` dict is kept so a
browser that connects mid-session immediately sees where things are.
"""
import asyncio
import threading
import time
from collections import deque
from typing import Any


class EventBus:
    def __init__(self, history: int = 400):
        self._lock = threading.Lock()
        self._subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self.recent: deque[dict[str, Any]] = deque(maxlen=history)
        self.state: dict[str, Any] = {"running": False}

    def emit(self, kind: str, **data: Any) -> None:
        event = {"kind": kind, "ts": time.time(), **data}
        with self._lock:
            if kind != "heart":
                self.recent.append(event)
            self._update_state(event)
            subs = list(self._subs)
        for loop, queue in subs:
            loop.call_soon_threadsafe(queue.put_nowait, event)

    def _update_state(self, e: dict[str, Any]) -> None:
        k = e["kind"]
        if k == "session":
            self.state = {"running": e.get("status") == "running", **{x: e.get(x) for x in ("participant", "profile", "sim", "llm")}}
        elif k == "stage":
            self.state.update(stage=e["stage"], stage_started=e["ts"], stage_seconds=e.get("seconds"))
        elif k == "turn":
            self.state.update(mode=e["mode"], act=e["act"], why=e["why"])
        elif k == "user":
            self.state["user"] = e["user"]
        elif k == "cast":
            self.state.update(cast=e["cast"], switch_every=e.get("switch_every"))
        elif k == "persona":
            self.state.update(persona=e["persona"], cast=e.get("cast", self.state.get("cast")))
        elif k == "senses":
            self.state["senses"] = e["senses"]

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs = [(lp, x) for lp, x in self._subs if x is not q]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"state": dict(self.state), "recent": list(self.recent)}


class NullBus(EventBus):
    """For CLI runs without the web UI."""
