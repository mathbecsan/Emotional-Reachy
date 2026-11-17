"""Session log (JSONL): stage changes with timestamps, every heartbeat sample,
every turn (what was heard, the affect, the mode/act and why, what Reachy
said). Part 2's visualization and the post-interview debrief ("which
reactions came from your heartbeat?") can be built straight from it."""
import json
import os
import time


class SessionLog:
    def __init__(self, folder="sessions", participant="P00", bus=None):
        os.makedirs(folder, exist_ok=True)
        self.bus = bus
        self.path = os.path.join(folder, f"{time.strftime('%Y%m%d-%H%M%S')}_{participant}.jsonl")
        self.f = open(self.path, "a", buffering=1)

    def event(self, kind, t, **data):
        if self.f.closed:  # sensor threads can outlive the session by a tick
            return
        self.f.write(json.dumps({"kind": kind, "t": round(t, 2), **data}, ensure_ascii=False, default=str) + "\n")
        if self.bus is not None:
            self.bus.emit(kind, t=round(t, 2), **json.loads(json.dumps(data, default=str)))

    def heart(self, t, bpm):
        self.event("heart", t, bpm=bpm)

    def close(self):
        self.f.close()
