"""Runs a cast of personas through one interview (Off-Brand Reachy spec).

The show is a loop, not a fixed sequence: Reachy always comes back to a
question in the current persona; every `switch_every` exchanges (or after a
long silence) it glitches into the next persona; "Reachy, reset", distress
or a real problem sends it straight back to Base Reachy, and teasing
personas are dropped after the second sign of discomfort.

Used by both conversation engines: the realtime ElevenLabs agent (which
writes its own lines from `agent_prompt()` and is steered with director
notes) and the offline loop (which speaks the scripted lines below).
"""
import random
import re

from .personas import (
    BASE,
    CLOSING,
    DEBRIEF,
    DISTRESS_CUES,
    DISTRESS_LINE,
    GLITCH_GESTURES,
    PERSONAS,
    RESET_LINE,
    RESET_WORDS,
    Persona,
    normalize_cast,
)


FILLER = re.compile(r"^(well|so|um+|uh+|like|i mean|yeah|yes|no|okay|ok|oh|hmm+)[,\s]+", re.I)


def slot_from(text: str) -> str:
    """Something the participant just said, short enough to echo back: 'I build robots, mostly…' -> 'You build robots'."""
    t = text.strip()
    for _ in range(3):
        t = FILLER.sub("", t)
    t = re.split(r"[,.;!?]| because | but | porque | pero ", t)[0].strip()
    words = t.split()
    if not words:
        return "That"
    swap = {"i": "you", "i'm": "you're", "my": "your", "me": "you", "am": "are", "mine": "yours", "myself": "yourself"}
    words = [swap.get(w.lower(), w) for w in words[:6]]
    out = " ".join(words)
    return out[0].upper() + out[1:]


class PersonaShow:
    def __init__(self, cast, switch_every: int = 5, rng: random.Random | None = None, no_tease: bool = False):
        self.cast = normalize_cast(cast, no_tease)
        self.switch_every = max(2, int(switch_every))
        self.rng = rng or random.Random()
        self.i = 0                      # index in the cast
        self.exchanges = 0              # participant turns in the current persona
        self.silences = 0               # silence-ladder step in the current turn
        self.finished = False           # whole cast done -> close as Base Reachy
        self.reset_mode = False         # after a reset/distress Reachy stays Base for the rest
        self.history: list[tuple[str, str]] = [(BASE, "start")]
        self._last_bridge: dict[str, str] = {}
        self._asked: dict[str, list[str]] = {}
        self.activities: list[str] = []     # led one per persona switch (brain/activities.py)
        self.style = ""                     # tone / reply length / activity list for the agent

    # ------------------------------------------------------------ state
    @property
    def current(self) -> Persona:
        return PERSONAS[self.cast[self.i]] if not self.reset_mode else PERSONAS[BASE]

    @property
    def upcoming(self) -> Persona | None:
        if self.reset_mode or self.i + 1 >= len(self.cast):
            return None
        return PERSONAS[self.cast[self.i + 1]]

    def on_exchange(self) -> None:
        self.exchanges += 1
        self.silences = 0

    def switch_due(self) -> bool:
        return not self.finished and not self.reset_mode and self.exchanges >= self.switch_every

    def advance(self, reason: str = "cadence") -> Persona | None:
        """Move to the next persona; None (and finished) once the cast is done."""
        self.exchanges, self.silences = 0, 0
        if self.reset_mode or self.i + 1 >= len(self.cast):
            self.finished = True
            self.history.append((BASE, f"close ({reason})"))
            return None
        self.i += 1
        self.history.append((self.cast[self.i], reason))
        return self.current

    def jump_to(self, key: str, reason: str = "facilitator") -> Persona | None:
        if key not in PERSONAS:
            return None
        if key not in self.cast:
            self.cast.insert(self.i + 1, key)
        self.i, self.exchanges, self.silences, self.reset_mode = self.cast.index(key), 0, 0, False
        self.history.append((key, reason))
        return self.current

    def reset(self, reason: str = "reset") -> None:
        """Back to Base Reachy for the rest of the session (stop word, distress, a real problem)."""
        self.reset_mode = True
        self.exchanges = 0
        self.history.append((BASE, reason))

    def drop_teasing(self) -> None:
        """Second discomfort cue: no teasing personas from now on."""
        keep = [k for j, k in enumerate(self.cast) if j <= self.i or not PERSONAS[k].teases]
        self.cast = keep

    @staticmethod
    def is_reset(text: str) -> bool:
        low = re.sub(r"[^\w\s,]", "", text.lower()).strip()
        return any(low == w or low.startswith(w) for w in RESET_WORDS[:2]) or low in ("reset", "reset please")

    @staticmethod
    def is_distress(text: str) -> bool:
        low = text.lower()
        return any(c in low for c in DISTRESS_CUES)

    # ------------------------------------------------------------ offline lines
    def bridge(self) -> str:
        p = self.current
        options = [b for b in p.bridges if b != self._last_bridge.get(p.key)] or p.bridges
        b = self.rng.choice(options)
        self._last_bridge[p.key] = b
        return b

    def question(self) -> str:
        p = self.current
        asked = self._asked.setdefault(p.key, [])
        left = [q for q in p.questions if q not in asked]
        if not left:
            return p.push
        q = self.rng.choice(left)
        asked.append(q)
        return q

    def reaction(self, text: str, cues=frozenset(), words: int = 0) -> str:
        """bridge + reaction (with the participant's words) + hook, two short sentences."""
        p = self.current
        r = p.reactions
        if "ask_robot" in cues:
            line = p.why_like_this if re.search(r"why (are|do) you|por qu[eé] eres", text.lower()) else p.dont_know
            return f"{self.bridge()} {line} {self.question()}"
        if re.search(r"\b(i don'?t know|no s[eé]|no idea|dunno)\b", text.lower()):
            return f"{p.dont_know} {self.question()}"
        if "compliment" in cues and "compliment" in r:
            body = r["compliment"]
        elif "laugh" in cues and "laugh" in r:
            body = r["laugh"]
        elif "contradiction" in cues and ("pushback" in r or "clap_back" in r):
            body = r.get("pushback") or r["clap_back"]
        elif words and words <= 2 and "short" in r:
            body = r["short"]
        else:
            body = r.get("answer", "{slot}? Tell me more.")
        body = body.replace("{slot}", slot_from(text))
        hook = self.question() if self.exchanges < self.switch_every - 1 else p.push
        return f"{self.bridge()} {body} {hook}"

    def silence_line(self) -> tuple[str | None, str]:
        """Silence ladder for the offline loop: (line or None, step). Step 'switch' means glitch now."""
        self.silences += 1
        p = self.current
        if self.silences == 1:
            return p.poke, "poke"
        if self.silences == 2:
            return p.rescue, "rescue"
        return None, "switch"

    def entrance(self, p: Persona | None = None) -> tuple[str, str]:
        """(gesture, glitch + opener) for switching into persona p."""
        p = p or self.current
        q = self.question()
        return p.entrance, f"{p.glitch_in} {p.opener} {q}"

    def next_activity(self) -> dict | None:
        from .activities import ACTIVITIES

        return ACTIVITIES[self.activities.pop(0)] if self.activities else None

    def closing(self, glitch: bool = True) -> str:
        lead = f"{PERSONAS[BASE].glitch_in} " if glitch else ""
        return f"{lead}{self.rng.choice(CLOSING)} {DEBRIEF}"

    glitch_gesture = staticmethod(lambda rng=random: rng.choice(GLITCH_GESTURES))
    RESET_LINE = RESET_LINE
    DISTRESS_LINE = DISTRESS_LINE

    # ------------------------------------------------------------ agent prompt
    def agent_cast_prompt(self) -> str:
        """The cast section of the realtime agent prompt, for exactly the personas selected."""
        lines = ["## Your cast for this session (in this order)"]
        for n, key in enumerate(self.cast, 1):
            p = PERSONAS[key]
            cam = "; ".join(f"{k}: {v.split('|')[0]} + \"{v.split('|')[1]}\"" for k, v in p.camera.items())
            lines.append(
                f"{n}. {p.name} [{p.key}] ({p.mood}). Delivery: {p.delivery}. Goal: {p.goal}\n"
                f"   Glitch line into it: \"{p.glitch_in}\" Opener: \"{p.opener}\"\n"
                f"   Bridges: {' / '.join(p.bridges)}. Questions: {' | '.join(p.questions)}\n"
                f"   Reactions ({{slot}} = their words): {' | '.join(p.reactions.values())}. Push: \"{p.push}\"\n"
                f"   Gestures: entrance {p.entrance}; {', '.join(p.gestures)}. Reacting to what you see: {cam}\n"
                f"   Silence poke: \"{p.poke}\" Interrupted: \"{p.barge_in}\" \"I don't know\": \"{p.dont_know}\""
                + ("\n   Light touch: if they share a real problem, become Base Reachy and be kind." if p.fragile else ""))
        lines.append(f"Switch to the next persona after about {self.switch_every} exchanges, or when the Director "
                     "tells you to. Only use the personas listed above.")
        if self.style:
            lines.append("\n## Session style\n" + self.style)
        return "\n".join(lines)
