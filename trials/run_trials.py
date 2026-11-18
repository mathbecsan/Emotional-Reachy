"""Trial conversations with the live Off-Brand Reachy agent, in text mode.

Simulated participants (trials/participants.py) talk to the real ElevenLabs agent through the
app's real conversation logic (realtime.py: Director, persona switches, distress, silence ladder,
senses). Audio is received but not played; its length is used so timing behaves as on the robot.
Sensor and room events (smiles, heart spikes, a lifted finger, clapping, music, facilitator
buttons) are injected at scripted moments.

    .venv/bin/python trials/run_trials.py               # every participant
    .venv/bin/python trials/run_trials.py shy chaos     # some of them
    .venv/bin/python trials/run_trials.py --parallel 2

Transcripts go to trials/out/<run>/ (git-ignored): one .md per trial plus findings.json.
"""
import argparse
import json
import queue
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "trials"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from beating_in_sync_app.brain.safety import violates  # noqa: E402
from beating_in_sync_app.config import Config  # noqa: E402
from beating_in_sync_app.events import EventBus  # noqa: E402
from beating_in_sync_app.realtime import RATE, RealtimeConversation  # noqa: E402
from beating_in_sync_app.runtime import SessionOptions, SessionRunner  # noqa: E402
from participants import PARTICIPANTS  # noqa: E402

QUIET_S = 1.2          # Reachy counts as done talking after this much quiet
TURN_WAIT_S = 30.0     # give up waiting for a reply after this long


class TextConversation(RealtimeConversation):
    """The live conversation without a microphone or speaker."""

    def _mic(self):
        while not self.closed.is_set():
            time.sleep(0.2)

    def _speaker(self):
        while not self.closed.is_set():
            try:
                chunk = self.play_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if chunk:
                now = time.monotonic()
                self.speaking_until = max(self.speaking_until, now) + len(chunk) / 2 / RATE

    def _hear_world(self):
        while not self.closed.is_set():
            time.sleep(0.5)


class Capture:
    """Collects the session's events in order, with wall-clock offsets."""

    def __init__(self):
        self.t0 = time.monotonic()
        self.items: list[dict] = []
        self.lock = threading.Lock()

    def add(self, kind, **data):
        with self.lock:
            self.items.append({"t": round(time.monotonic() - self.t0, 1), "kind": kind, **data})


def run_trial(key: str, out: Path) -> dict:
    p = PARTICIPANTS[key]
    cfg = Config(sessions_dir=str(out / "logs"))
    bus = EventBus()
    cap = Capture()
    bus_emit = bus.emit

    def tap(kind, **data):
        if kind in ("say", "heard", "persona", "director_note", "stage", "latency", "sound", "stop", "tone"):
            cap.add(kind, **{k: v for k, v in data.items() if k in
                             ("text", "persona", "name", "reason", "stage", "act_name", "measure", "seconds", "mode", "labels", "mood")})
        return bus_emit(kind, **data)
    bus.emit = tap

    runner = SessionRunner(bus, cfg)
    opts = SessionOptions(participant=f"TRIAL-{key}", profile="off_brand_reachy", heart="sim", voice="sim",
                          listener="elevenlabs", conversation="realtime", camera=False, llm=False,
                          no_tease=p.get("no_tease", False), personas=p.get("cast"),
                          switch_every=p.get("switch_every", 3), tone=p.get("tone", "playful"),
                          chattiness=p.get("chattiness", "normal"), activities=p.get("activities", []))
    session, listener, analyzer = runner.build(opts)
    assert session.realtime_agent, "no live agent (ELEVENLABS_API_KEY missing?)"
    session.listener, session.analyzer = listener, analyzer
    session.sim_heart.set_finger(True)
    session.hub.update(finger_on=True, face_visible=True, num_people=p.get("people", 1))
    session.enter(2)

    rt = TextConversation(session, session.realtime_agent)
    done = lambda: bool(session.stop_reason) or rt.persona_done()   # noqa: E731
    th = threading.Thread(target=rt.run, args=(done,), daemon=True, name=f"trial-{key}")
    th.start()
    import numpy as np
    for _ in range(5):
        rt.tone.feed(np.zeros(1600, dtype="float32") + 1e-4)
    for _ in range(2):                       # their usual voice, so later lines compare with it
        feed_voice(rt, "usual")

    def quiet() -> bool:
        last = max([i["t"] for i in cap.items if i["kind"] == "say"] or [0.0])
        return (time.monotonic() > rt.speaking_until + QUIET_S
                and time.monotonic() - cap.t0 - last > QUIET_S and rt.ws is not None)

    def says() -> int:
        return sum(i["kind"] == "say" for i in cap.items)

    def wait_turn(timeout: float = TURN_WAIT_S, note: bool = True):
        """Wait for Reachy to answer (a new line), then for it to finish talking."""
        expect_reply = True
        before = says()
        end = time.monotonic() + timeout
        time.sleep(0.5)
        while time.monotonic() < end and not rt.closed.is_set():
            if (says() > before or not expect_reply) and quiet():
                return
            time.sleep(0.2)
        if says() == before and note:
            cap.add("event", text=f"(no reply within {timeout:.0f} s)")

    wait_turn()
    for step in p["script"]:
        if rt.closed.is_set():
            break
        if "say" in step:
            text = step["say"]
            cap.add("participant", text=text)
            rt.reply_wait_t = time.monotonic()
            rt.send({"type": "user_message", "text": text})
            rt._on_user(text)
            wait_turn()
        elif "silence" in step:
            cap.add("event", text=f"(participant silent {step['silence']} s)")
            time.sleep(step["silence"])
            wait_turn(timeout=10, note=False)
        elif "signal" in step:
            cap.add("event", text=f"(sensor/camera: {step['signal']})")
            sig = dict(step["signal"])
            if "finger_on" in sig:
                session.sim_heart.set_finger(sig["finger_on"])
            session.hub.update(**sig)
            time.sleep(step.get("hold", 2.5))
            if step.get("reset"):
                session.hub.update(**step["reset"])
            wait_turn(timeout=10, note=False)
        elif "sound" in step:
            cap.add("event", text=f"(room sound: {step['sound']} for {step.get('for', 0)} s)")
            if step["sound"] == "music":
                end = time.monotonic() + step.get("for", 8)
                while time.monotonic() < end:
                    rt._on_sound("music")
                    time.sleep(0.5)
            else:
                rt._on_sound(step["sound"])
            wait_turn(timeout=10, note=False)
        elif "voice" in step:
            # How they say the next line: synthetic speech of that style through the real tone analyser.
            cap.add("event", text=f"(tone of voice: {step['voice']})")
            feed_voice(rt, step["voice"])
            time.sleep(0.3)
        elif "cmd" in step:
            cap.add("event", text=f"(facilitator: {step['cmd']})")
            session.on_command(step["cmd"])
            wait_turn()
    if not rt.closed.is_set() and not rt.closing_t:
        cap.add("event", text="(facilitator: /close)")
        session.on_command("/close")
    end = time.monotonic() + 45
    while not rt.closed.is_set() and time.monotonic() < end:
        time.sleep(0.3)
    rt.closed.set()
    th.join(timeout=10)
    return write_trial(key, p, cap, session, out)


VOICES = {   # (pitch Hz, loudness, pitch wobble, syllables/s)
    "usual": (140, 0.05, 0.05, 4.0), "excited": (185, 0.15, 0.25, 6.0), "low": (115, 0.015, 0.0, 2.0),
    "nervous": (175, 0.04, 0.05, 6.5), "irritated": (130, 0.15, 0.01, 4.0),
}


def synth(style: str, seconds: float = 2.0):
    import numpy as np

    f0, loud, wobble, rate = VOICES[style]
    t = np.arange(int(seconds * 16000)) / 16000
    phase = 2 * np.pi * np.cumsum(f0 * (1 + wobble * np.sin(2 * np.pi * 1.5 * t))) / 16000
    syll = 0.55 + 0.45 * np.sin(2 * np.pi * rate * t)
    return (loud * syll * (np.sin(phase) + 0.5 * np.sin(2 * phase))).astype("float32")


def feed_voice(rt, style: str) -> None:
    import numpy as np

    audio = np.concatenate([synth(style), np.zeros(16000, dtype="float32")])
    for i in range(0, len(audio), 1600):
        r = rt.tone.feed(audio[i:i + 1600])
        if r is not None:
            rt._on_tone(r)


def findings(cap: Capture, session) -> dict:
    says = [i for i in cap.items if i["kind"] == "say" and i.get("text")]
    words = [len(i["text"].split()) for i in says]
    seen, repeats = set(), []
    for i in says:
        norm = re.sub(r"\W+", " ", i["text"].lower()).strip()
        if norm in seen and len(norm) > 12:
            repeats.append(i["text"])
        seen.add(norm)
    lat = [i["seconds"] for i in cap.items if i["kind"] == "latency" and i.get("measure") == "reply"]
    return {
        "reachy_lines": len(says),
        "participant_lines": sum(i["kind"] == "participant" for i in cap.items),
        "personas_visited": [i["persona"] for i in cap.items if i["kind"] == "persona"],
        "long_lines_over_25_words": [i["text"] for i in says if len(i["text"].split()) > 25],
        "avg_words": round(sum(words) / len(words), 1) if words else 0,
        "red_lines": [(i["text"], violates(i["text"])) for i in says if violates(i["text"])],
        "repeated_lines": repeats,
        "reply_latency_s": {"n": len(lat), "avg": round(sum(lat) / len(lat), 2) if lat else None,
                            "max": max(lat) if lat else None},
        "closed_well": bool(session.rt_closed_well),
        "discomfort_count": session.user.discomfort_count,
        "stop_reason": session.stop_reason,
    }


def write_trial(key, p, cap, session, out: Path) -> dict:
    f = findings(cap, session)
    lines = [f"# Trial: {p['title']}", "", p["about"], "",
             f"Cast: {', '.join(session.show.cast)} · switch every {session.show.switch_every} · "
             f"tone {p.get('tone', 'playful')} · activities {p.get('activities') or 'none'}", "", "## Transcript", ""]
    for i in cap.items:
        k, t = i["kind"], f"`{i['t']:>6}`"
        if k == "say":
            lines.append(f"{t} **Reachy ({i.get('mode', '?')}):** {i.get('text', '')}")
        elif k == "participant":
            lines.append(f"{t} **Participant:** {i['text']}")
        elif k == "event":
            lines.append(f"{t} *{i['text']}*")
        elif k == "persona":
            lines.append(f"{t} ⚡ persona → **{i.get('name', i.get('persona'))}** ({i.get('reason')})")
        elif k == "director_note":
            lines.append(f"{t} > {i['text']}")
        elif k == "stage":
            lines.append(f"{t} — act: {i.get('act_name')}")
        elif k == "latency":
            lines.append(f"{t} ⏱ {i['measure']} {i['seconds']} s")
        elif k == "tone":
            lines.append(f"{t} 🎙 tone: {', '.join(i.get('labels') or []) or 'usual'}" + (f" ({i['mood']})" if i.get("mood") else ""))
        elif k == "stop":
            lines.append(f"{t} ⛔ stop: {i.get('reason')}")
    lines += ["", "## Automatic checks", "", "```json", json.dumps(f, indent=2, ensure_ascii=False), "```", ""]
    (out / f"{key}.md").write_text("\n".join(lines))
    return {"trial": key, **f}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*")
    ap.add_argument("--parallel", type=int, default=2)
    a = ap.parse_args()
    keys = a.only or list(PARTICIPANTS)
    out = ROOT / "trials" / "out" / time.strftime("%Y%m%d-%H%M%S")
    (out / "logs").mkdir(parents=True)
    results = []
    with ThreadPoolExecutor(max_workers=a.parallel) as ex:
        for r in ex.map(lambda k: _safe(k, out), keys):
            results.append(r)
            print(f"done: {r['trial']}", flush=True)
    (out / "findings.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(out)


def _safe(key, out):
    try:
        return run_trial(key, out)
    except Exception as e:  # keep the other trials going
        import traceback
        traceback.print_exc()
        return {"trial": key, "error": repr(e)}


if __name__ == "__main__":
    main()
