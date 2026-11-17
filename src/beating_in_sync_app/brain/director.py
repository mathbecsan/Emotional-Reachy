"""The Director decides, every turn, *how Reachy feels* (mode) and *what it
does with its turn* (act). The line itself is written afterwards by the
LLM or the offline templates, but they cannot override these decisions --
that keeps the safety rules enforceable in code, not only in a prompt.

Mode rules (from "Reachy Personality and Behaviour"):
  * heart jump (+15 BPM)        -> comment on it, then Flirty or Excited
  * long flat heart stretch     -> Teasing
  * compliment / smiles         -> Flirty
  * contradiction / laughing    -> Offended
  * short answers / silence     -> Teasing
  * looking away 3+ s / phone   -> Scolding
  * new language                -> Curious
  * max 2 provocations in a row, then a warm mode
  * 2x discomfort               -> Curious/Sincere for the rest of the session
Added here so the participant feels *heard*:
  * negative affect (sad/afraid) beats provocation -> Curious/Sincere, softly
  * Reachy never asks more than 2 questions in a row; it reacts, tells a story,
    shares something, or calls back to what they said instead.
"""
import random
from dataclasses import dataclass, field
from typing import Optional

from ..config import Config
from ..perception.fusion import Affect
from ..perception.text import Analysis
from ..signals import Signals
from .modes import PROVOCATIONS, Act, Mode
from .stories import pick_story
from .user_model import UserModel


STAGE_GOALS = {
    0: "Asleep. Only mumble sleepily, if anything.",
    1: "Wake up surprised: someone's heartbeat woke you. Find out if it was them.",
    2: "Introductions: learn their name and the language they feel most like themselves in. Repeat the name (sometimes wrong on purpose, playfully, blaming your own ears). Let them correct you.",
    3: "Conversation in THEIR language. Core prompt: 'Tell me something you love that most people don't know about.' React with real interest (or mock boredom if they're curt), share your own related story, build on what they say.",
    4: "Provocation: theatrical persona moves (tease, compliment that turns flirty, sudden scolding) driven by how they act. Comment on heartbeat jumps. Keep it playful.",
    5: "Music: a song from their culture is playing. You dance, then invite them: 'Your turn. Show me how you'd move to this.' React to whether they move.",
    6: "Drop the act. Sincere, slow, specific: mention something real they shared, thank them by name, say goodnight in their language, go back to sleep.",
}


@dataclass
class DirectorNote:
    stage: int
    mode: Mode
    act: Act
    goal: str
    reason: str
    expects_reply: bool = True
    allow_question: bool = True
    story: Optional[dict] = None
    heart_jump: float = 0.0
    callback: Optional[str] = None
    two_people: bool = False
    say_name_wrong: bool = False
    constraints: list = field(default_factory=list)


class Director:
    def __init__(self, cfg: Config, rng: random.Random, provocations=("teasing", "offended", "scolding"),
                 flirt_with_two_people: bool = True):
        self.cfg, self.rng = cfg, rng
        self.allowed_provocations = {Mode(p) for p in provocations}
        self.flirt_with_two_people = flirt_with_two_people
        self.mode_history: list[Mode] = []
        self.act_history: list[Act] = []
        self.questions_in_row = 0
        self.stories_used: set = set()
        self.stage4_moves: list[Mode] = []
        self.last_lang: Optional[str] = None
        self.last_scold_t = -1e9
        self.finger_off_since: Optional[float] = None
        self.last_nudge_t = -1e9
        self.sync_commented = False

    # ------------------------------------------------------------------ helpers
    def provocation_allowed(self, stage: int, user: UserModel, mode: Mode) -> bool:
        if user.no_tease or user.discomfort_count >= self.cfg.discomfort_limit or mode not in self.allowed_provocations:
            return False
        if stage == 4:
            return True
        if stage == 3:
            return mode == Mode.TEASING           # "mock boredom" only
        return False

    def _provocations_in_row(self) -> int:
        n = 0
        for m in reversed(self.mode_history):
            if m in PROVOCATIONS:
                n += 1
            else:
                break
        return n

    def _warm_for(self, affect: Affect, user: UserModel) -> Mode:
        if affect.negative or user.discomfort_count:
            return Mode.SINCERE if affect.valence < -0.5 else Mode.CURIOUS
        if affect.valence > 0.4 and affect.arousal > 0.3:
            return Mode.EXCITED
        return self.rng.choice([Mode.CURIOUS, Mode.FLIRTY, Mode.EXCITED])

    # --------------------------------------------------------------- main entry
    def decide(self, stage: int, t: float, sig: Signals, jump: float, ana: Optional[Analysis],
               affect: Affect, user: UserModel, continuing: bool = False) -> DirectorNote:
        """`continuing` = Reachy already had the floor (stage opening, or it paused
        after a story and nobody jumped in) -- not the participant being silent."""
        silent = ana is None and not continuing
        cues = set() if ana is None else ana.cues
        mode, act, reason = None, None, ""

        # Discomfort is counted before anything else so the rules below see it.
        if "discomfort" in cues:
            user.discomfort_count += 1

        # ---- fixed-mode stages ------------------------------------------------
        if stage == 0:
            mode, act, reason = Mode.SLEEPY, Act.SELF_DISCLOSE, "asleep"
        elif stage == 1:
            mode, act, reason = Mode.CURIOUS, (Act.ASK if silent else Act.REACT), "waking up"
        elif stage == 6:
            mode, act, reason = Mode.SINCERE, Act.GOODBYE, "repair and goodbye"
        elif stage == 5:
            mode = Mode.EXCITED
            act = Act.INVITE if Act.INVITE not in self.act_history[-3:] else Act.REACT
            reason = "music"

        # ---- the sensors: let go of the sensor / two hearts in sync -------------
        if sig.finger_on:
            self.finger_off_since = None
        elif self.finger_off_since is None:
            self.finger_off_since = t
        finger_off_s = 0.0 if self.finger_off_since is None else t - self.finger_off_since
        if mode is None and 2 <= stage <= 4:
            if finger_off_s >= self.cfg.finger_lost_s and t - self.last_nudge_t > 30:
                self.last_nudge_t = t
                mode, act, reason = Mode.CURIOUS, Act.NUDGE, f"finger off the sensors {finger_off_s:.0f}s"
            elif sig.hearts_in_sync and not self.sync_commented and stage >= 3:
                self.sync_commented = True
                mode, act, reason = Mode.EXCITED, Act.HEART_SYNC, "both hearts at the same tempo"

        # ---- signal-driven modes (stages 2-4) ----------------------------------
        if mode is None:
            new_lang = (ana is not None and ana.language and ana.language != self.last_lang
                        and ana.language not in user.languages_heard and self.last_lang is not None)
            if "discomfort" in cues:
                mode, act, reason = (Mode.SINCERE, Act.REACT, "participant uncomfortable -> back off")
            elif jump >= 1:
                mode = Mode.FLIRTY if (affect.valence >= 0 and stage >= 3 and not user.no_tease) else Mode.EXCITED
                act, reason = Act.HEART_COMMENT, f"heart jumped +{jump:.0f} BPM"
            elif sig.looking_away_s >= self.cfg.look_away_s and t - self.last_scold_t > 20:
                mode, act, reason = Mode.SCOLDING, Act.CHALLENGE, f"looked away {sig.looking_away_s:.0f}s"
                self.last_scold_t = t
            elif continuing:
                prev = self.mode_history[-1] if self.mode_history else Mode.CURIOUS
                mode = prev if prev in (Mode.CURIOUS, Mode.EXCITED, Mode.FLIRTY) else Mode.CURIOUS
                act, reason = Act.ASK, "Reachy keeps the floor"
            elif new_lang:
                mode, act, reason = Mode.CURIOUS, Act.REACT, f"new language heard: {ana.language}"
            elif not silent and affect.negative:
                mode = Mode.SINCERE if affect.valence < -0.5 else Mode.CURIOUS
                act, reason = Act.REACT, f"participant seems {affect.label} -> gentle"
            elif "compliment" in cues:
                mode, act, reason = Mode.FLIRTY, Act.REACT, "compliment"
            elif "contradiction" in cues or ("laugh" in cues and stage == 4 and self.rng.random() < 0.6):
                mode, act, reason = Mode.OFFENDED, Act.CHALLENGE, "contradicted / laughed at Reachy"
            elif "ask_robot" in cues:
                mode = Mode.FLIRTY if stage == 4 and self.rng.random() < 0.4 else Mode.CURIOUS
                act, reason = Act.ANSWER, "they asked Reachy something"
            elif (silent or ana.words <= self.cfg.short_answer_words) and stage >= 3:
                mode, act, reason = Mode.TEASING, Act.CHALLENGE, "silence / short answer"
            elif sig.bpm_flat and stage == 4:
                mode, act, reason = Mode.TEASING, Act.CHALLENGE, "heart flat for a long time"
            elif "love_talk" in cues or (ana and ana.words >= self.cfg.long_answer_words):
                mode = Mode.FLIRTY if stage == 4 else (Mode.EXCITED if affect.valence > 0.3 else Mode.CURIOUS)
                act, reason = Act.REACT, "engaged / talking about something they love"
            else:
                mode, act, reason = Mode.CURIOUS, Act.REACT, "default"

            # Stage 4 needs 2-3 *different* persona moves; nudge toward an unused one.
            if stage == 4 and mode in (Mode.CURIOUS, Mode.EXCITED) and not affect.negative and "discomfort" not in cues:
                unused = [m for m in (Mode.TEASING, Mode.FLIRTY, Mode.SCOLDING)
                          if m not in self.stage4_moves and (m == Mode.FLIRTY or m in self.allowed_provocations)]
                if unused:
                    mode = unused[0]
                    act = Act.CHALLENGE if mode in PROVOCATIONS else Act.REACT
                    reason += f" -> stage-4 move: {mode.value}"

        # ---- hard rules ----------------------------------------------------------
        if mode in PROVOCATIONS and not self.provocation_allowed(stage, user, mode):
            reason += f" | {mode.value} not allowed here -> warm"
            mode = self._warm_for(affect, user)
            if act == Act.CHALLENGE:
                act = Act.STORY if silent else Act.REACT
        if mode in PROVOCATIONS and self._provocations_in_row() >= self.cfg.max_provocations_in_row:
            reason += " | 2 provocations in a row -> warm"
            mode = self._warm_for(affect, user)
            act = Act.REACT if act == Act.CHALLENGE else act
        if mode == Mode.FLIRTY and (user.no_tease or user.discomfort_count >= self.cfg.discomfort_limit):
            mode = Mode.CURIOUS

        # ---- turn-taking: don't interrogate -----------------------------------
        note = DirectorNote(stage=stage, mode=mode, act=act, goal=STAGE_GOALS.get(stage, ""), reason=reason,
                            heart_jump=jump, two_people=sig.num_people >= 2)
        self._shape_act(note, stage, silent, ana, user)

        # ---- bookkeeping ----------------------------------------------------------
        self.mode_history.append(note.mode)
        self.act_history.append(note.act)
        if stage == 4 and note.mode in (Mode.TEASING, Mode.FLIRTY, Mode.SCOLDING, Mode.OFFENDED) \
                and note.mode not in self.stage4_moves:
            self.stage4_moves.append(note.mode)
        if ana is not None and ana.language:
            self.last_lang = ana.language
            user.languages_heard.add(ana.language)
        if note.story:
            self.stories_used.add(note.story["id"])
        self.questions_in_row = self.questions_in_row + 1 if note.expects_reply and note.allow_question else 0
        return note

    def _shape_act(self, note: DirectorNote, stage: int, silent: bool, ana: Optional[Analysis], user: UserModel):
        """Decide whether Reachy asks, tells, reacts or shares -- and whether it
        waits for an answer at all."""
        topics = (ana.topics if ana else []) + user.topics[-3:]

        if note.act in (Act.NUDGE, Act.HEART_SYNC):
            return
        if stage == 2 and note.act not in (Act.HEART_COMMENT, Act.ANSWER):
            if user.name and not user.said_name_wrong and not user.name_confirmed:
                note.act = Act.NAME_PLAY
            elif not user.name or not user.language_confirmed:
                note.act = Act.ASK
            note.say_name_wrong = note.act == Act.NAME_PLAY and self.rng.random() < 0.75
            note.expects_reply = True
            return

        if stage == 3 and not user.loves and note.act in (Act.ASK, Act.REACT, Act.CHALLENGE) and \
                Act.ASK not in self.act_history[-2:] and note.mode != Mode.TEASING:
            note.act = Act.ASK          # the protocol's fixed stage-3 question
            note.constraints.append("Ask: 'Tell me something you love that most people don't know about.'")
            return

        if stage in (3, 4) and note.act == Act.REACT:
            r = self.rng.random()
            used_story_recently = Act.STORY in self.act_history[-3:]
            if not used_story_recently and r < 0.45:
                story = pick_story(topics, "funny" if note.mode in (Mode.EXCITED, Mode.TEASING) else "tender",
                                   self.stories_used, self.rng)
                if story:
                    note.act, note.story = Act.STORY, story
            elif r < 0.65 and (user.loves or user.facts) and Act.CALLBACK not in self.act_history[-4:]:
                note.act = Act.CALLBACK
                note.callback = (user.loves or user.facts)[0]
            elif r < 0.8:
                note.act = Act.SELF_DISCLOSE

        if silent and note.act in (Act.REACT, Act.ASK) and stage in (3, 4):
            story = pick_story(user.topics, None, self.stories_used, self.rng)
            if story and Act.STORY not in self.act_history[-2:]:
                note.act, note.story = Act.STORY, story
                note.reason += " | silence -> Reachy fills it with a story"

        # Question budget.
        if self.questions_in_row >= self.cfg.max_questions_in_row:
            note.allow_question = False
            note.constraints.append("Do NOT ask a question this turn. Make a statement, react, or tell something.")
            if note.act == Act.ASK:
                note.act = Act.SELF_DISCLOSE

        # Some acts are complete on their own: Reachy keeps the floor and goes on.
        if note.act in (Act.STORY, Act.SELF_DISCLOSE) and self.rng.random() < 0.4:
            note.expects_reply = False
            note.constraints.append("End with a statement, not a question; Reachy will keep talking after a short pause.")
        if note.act == Act.GOODBYE:
            note.expects_reply = False
        if note.two_people and note.mode == Mode.FLIRTY and self.flirt_with_two_people:
            note.constraints.append("Two people are in front of you: flirt with the one who is talking and playfully make the other one 'jealous'.")
