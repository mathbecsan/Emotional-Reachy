"""The 15-minute "Beating in Sync" session: stages 0-7 of the Interaction
Protocol, run as a loop of sense -> decide -> write -> move+speak -> listen.

Every stage has a fixed opening (from the protocol), but what happens after
it depends on the participant: their words, their face, where they look,
and their heartbeat.
"""
import logging
import random
import re
from typing import Optional

from .body.gestures import GESTURES, at_speed, transition
from .body.voice import music_for
from .brain.director import Director
from .brain.modes import MODE_STYLE, Act, Mode
from .brain.persona_show import slot_from
from .brain.personas import DISTRESS_LINE, RESET_LINE
from .brain.safety import is_stop
from .brain.stories import LANG_NAME, PHRASES, phrase
from .brain.user_model import UserModel
from .perception.fusion import fuse


LOVE_LEAD = re.compile(r"^(well,?\s*|so,?\s*|um+,?\s*)?(i (really )?(love|like|adore)|me encanta(n)?|amo|j'adore|j'aime|adoro|ich liebe)\s+", re.I)


def clean_love(text: str) -> str:
    """'Me encanta cocinar las recetas de mi abuela, sobre todo...' -> 'cocinar las recetas de mi abuela'"""
    t = LOVE_LEAD.sub("", text.strip())
    t = re.split(r"[,.;!?]| sobre todo | especially | because | porque ", t)[0]
    return " ".join(t.split()[:10])


logger = logging.getLogger(__name__)


class StopSession(Exception):
    pass


# Session flow v2: five acts on top of the protocol's stage numbers (stage -> act).
ACT_OF_STAGE = {0: 1, 1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 5, 7: 5}
ACT_NAMES = {1: "Asleep", 2: "Wake-up & Analysis", 3: "Introductions", 4: "Conversation & Personality", 5: "Goodbye"}

# Act 1 sounds: short, predictable, so they play from the local clip cache with no network wait.
STIR_LINES = ["Mm?", "Hmm... someone's there...", "Mmh... a heartbeat..."]
COAX_LINES = ["Come back... I was almost awake...", "Mmm... where did you go...", "Your heart... it was warm..."]

GESTURE_FOR = {Mode.SLEEPY: "sleepy", Mode.CURIOUS: "curious", Mode.EXCITED: "excited", Mode.FLIRTY: "flirty",
               Mode.TEASING: "teasing", Mode.OFFENDED: "offended", Mode.SCOLDING: "scolding", Mode.SINCERE: "sincere"}


class Session:
    def __init__(self, cfg, clock, hub, heart, body, voice, writer, session_log, user: UserModel, profile,
                 sim_heart=None, rng=None, realtime_agent: str | None = None, show=None,
                 heart_wake: bool = True, music: bool = True, flirty: bool = True):
        self.cfg, self.clock, self.hub, self.heart = cfg, clock, hub, heart
        self.body, self.voice, self.writer, self.log = body, voice, writer, session_log
        self.user, self.sim_heart = user, sim_heart
        self.rng = rng or random.Random(cfg.seed)
        self.director = Director(cfg, self.rng, profile.provocations, profile.flirt_with_two_people, flirty)
        self.show = show                  # PersonaShow for Off-Brand sessions, else None
        self.heart_wake, self.music = heart_wake, music
        self.rt = None                    # live RealtimeConversation, while one runs
        self.pending: list[tuple[str, str | None]] = []   # facilitator persona commands (offline loop)
        self.listener = None
        self.analyzer = None
        self.stage = 0
        self.stage_t0 = 0.0
        self.turns_in_stage = 0
        self.transcript = []
        self.force_next = False
        self.stop_reason: Optional[str] = None
        self.realtime_agent = realtime_agent   # ElevenLabs agent id: stages 1-4 run as a live conversation
        self.live = None                  # live conversation opened at the first touch, before Reachy wakes
        self.contact_t: Optional[float] = None   # monotonic time the fingertip first landed (latency stamps)
        self.wake_now = False             # Act 1 is over: wake even without a readable heartbeat

    # ================================================================ commands
    def on_command(self, line: str):
        """Facilitator keys (also used by the simulator and scenarios)."""
        p = line.strip().lstrip("/").split()
        if not p:
            return
        c, args = p[0].lower(), p[1:]
        self.log.event("command", self.clock.now(), cmd=line)
        if c in ("sleep", "pause", "stop"):
            self.stop_reason = f"facilitator: {c}"
        elif c == "next" and self.show is not None and self.stage >= 2:
            self.persona_cmd("next")
        elif c == "next":
            self.force_next = True
        elif c == "persona" and args and self.show is not None:
            self.persona_cmd("jump", args[0])
        elif c == "reset" and self.show is not None:
            self.persona_cmd("reset")
        elif c in ("close", "finish") and self.show is not None:
            self.persona_cmd("close")
        elif c in ("extend", "more", "keep") and self.show is not None:
            self.persona_cmd("extend")      # Keep talking: another round past the planned length
        elif c == "hand" and self.sim_heart:
            self.sim_heart.set_hand(not args or args[0] != "off")
        elif c == "finger" and self.sim_heart:
            self.sim_heart.set_finger(not args or args[0] != "off")
        elif c == "bpm" and self.sim_heart and args:
            self.sim_heart.bump(float(args[0]))
        elif c == "look":
            away = args and args[0] == "away"
            self.hub.update(looking_away_s=float(args[1]) if away and len(args) > 1 else (5.0 if away else 0.0),
                            face_visible=not away)
        elif c == "scold":
            self.hub.update(looking_away_s=99.0)
        elif c == "people" and args:
            self.hub.update(num_people=int(args[0]))
        elif c == "face" and args:
            self.hub.update(face_emotion=args[0], face_conf=float(args[1]) if len(args) > 1 else 0.7)
        elif c == "move" and args:
            self.hub.update(motion_energy=float(args[0]))
        elif c == "notease":
            self.user.no_tease = True
        elif c == "status":
            s = self.hub.snapshot()
            logger.info("status stage=%s bpm=%s base=%s d=%s away=%s people=%s user=%s", self.stage, s.bpm,
                        s.baseline_bpm, s.bpm_delta, s.looking_away_s, s.num_people, self.user.summary())

    # ================================================================ helpers
    def elapsed(self):
        return self.clock.now() - self.stage_t0

    def stage_over(self):
        return self.force_next or self.elapsed() > self.cfg.stage_time[self.stage]

    def note_baseline(self):
        """Log the resting heartbeat once it's known (after waking, when Reachy woke at the first beat)."""
        if self.heart.baseline is not None and not getattr(self, "_baseline_logged", False):
            self._baseline_logged = True
            logger.info("heart baseline = %s BPM", round(self.heart.baseline, 1))
            self.log.event("baseline", self.clock.now(), bpm=self.heart.baseline)

    def check_safety(self):
        self.note_baseline()
        s = self.hub.snapshot()
        if s.bpm_overlimit_s >= self.cfg.bpm_stop_duration_s:
            self.stop_reason = f"BPM above {self.cfg.bpm_stop_limit:.0f} for {s.bpm_overlimit_s:.0f}s"
        if self.stop_reason:
            raise StopSession(self.stop_reason)

    def enter(self, stage):
        self.note_baseline()
        self.stage, self.stage_t0, self.turns_in_stage, self.force_next = stage, self.clock.now(), 0, False
        # The resting heartbeat is learned in stage 0, or right after waking when Reachy wakes at the first beat.
        self.heart.collect_baseline = stage == 0 or (self.cfg.wake_on_first_heartbeat and self.heart.baseline is None)
        logger.info("=== STAGE %s (act %s) ===", stage, ACT_OF_STAGE[stage])
        self.log.event("stage", self.clock.now(), stage=stage, seconds=self.cfg.stage_time[stage] / self.clock.scale,
                       act=ACT_OF_STAGE[stage], act_name=ACT_NAMES[ACT_OF_STAGE[stage]])

    def latency(self, kind: str, seconds: float, **extra) -> None:
        """One latency measurement for the console's latency card and the replay (session flow v2, section 4)."""
        logger.info("latency %s = %.2f s", kind, seconds)
        self.log.event("latency", self.clock.now(), measure=kind, seconds=round(seconds, 2), **extra)

    def since_contact(self) -> Optional[float]:
        import time
        return time.monotonic() - self.contact_t if self.contact_t is not None else None

    def speak(self, text, mode: Mode, lang=None, gesture=None):
        self.body.play(gesture or GESTURE_FOR[mode], loop=mode == Mode.SLEEPY)
        self.log.event("say", self.clock.now(), text=text, mode=mode.value, lang=lang or self.user.language)
        self.voice.say(text, lang or self.user.language, MODE_STYLE[mode]["rate"], mode.value)
        self.transcript.append({"reachy": text, "mode": mode.value})
        if self.sim_heart:
            self.sim_heart.react(mode.value)

    def hear(self, timeout=None):
        sig = self.hub.snapshot()
        if sig.face_visible and (abs(sig.face_x) > 0.15 or abs(sig.face_y) > 0.2):
            self.body.look_at(sig.face_x, sig.face_y)   # turn toward the person while listening
        else:
            self.body.play("listen")
        self.log.event("listening", self.clock.now(), timeout=timeout or self.cfg.listen_timeout_s)
        u = self.listener.listen(timeout or self.cfg.listen_timeout_s)
        self.check_safety()
        if u is None:
            self.user.silences += 1
            self.log.event("heard", self.clock.now(), text=None)
            return None
        if is_stop(u.text, self.cfg.stop_words):
            self.stop_reason = f"participant said '{u.text}'"
            raise StopSession(self.stop_reason)
        ana = self.analyzer(u.text, u.language)
        self.transcript.append({"participant": u.text, "lang": u.language})
        self._absorb(ana)
        self.log.event("heard", self.clock.now(), text=u.text, lang=u.language, emotion=ana.emotion,
                       emotion_conf=round(ana.emotion_conf, 2), cues=sorted(ana.cues))
        self.emit_user()
        return ana

    def emit_user(self):
        self.log.event("user", self.clock.now(), user=self.user.summary() | {
            "name_confirmed": self.user.name_confirmed, "language_confirmed": self.user.language_confirmed,
            "no_tease": self.user.no_tease})

    def _absorb(self, ana):
        """Rule-based updates to the user model (the LLM adds more on top)."""
        u = self.user
        u.turns += 1
        u.total_words += ana.words
        u.laughed += "laugh" in ana.cues
        u.compliments_given += "compliment" in ana.cues
        for t in ana.topics:
            if t not in u.topics:
                u.topics.append(t)
        if self.stage == 2:
            if ana.name and not u.name:
                u.name = ana.name
            elif u.said_name_wrong and not u.name_confirmed:
                if ana.name:
                    u.name = ana.name
                u.name_confirmed = True
            lang = ana.mentioned_language or (ana.language if ana.language and ana.language != "en" else None)
            if lang and u.name_confirmed:
                u.language, u.language_confirmed = lang, True
        if self.stage in (3, 4) and not u.loves and ana.words >= 4 and "bored_user" not in ana.cues \
                and "ask_robot" not in ana.cues and (
                "love_talk" in ana.cues or self.director.act_history[-1:] == [Act.ASK]):
            u.loves.append(clean_love(ana.text))

    def turn(self, ana, continuing=False):
        """One Reachy turn: sense -> decide -> write -> move + speak."""
        self.check_safety()
        sig = self.hub.snapshot()
        jump = self.hub.consume_jump() if self.stage >= 2 else 0.0
        affect = fuse(sig.face_emotion, sig.face_conf, ana.emotion if ana else None,
                      ana.emotion_conf if ana else 0.0, sig.bpm_delta, self.cfg.fusion_weights)
        self.user.affect_history.append((self.clock.now(), affect.label, affect.valence, affect.arousal))
        note = self.director.decide(self.stage, self.clock.now(), sig, jump, ana, affect, self.user, continuing)
        logger.info("director %s/%s <- %s (affect %s v=%+.2f a=%+.2f via %s; bpm %s d=%+.1f)", note.mode.value,
                    note.act.value, note.reason, affect.label, affect.valence, affect.arousal, affect.source, sig.bpm,
                    sig.bpm_delta)
        senses = {"bpm": sig.bpm, "baseline_bpm": sig.baseline_bpm and round(sig.baseline_bpm),
                  "bpm_change_vs_baseline": sig.bpm_delta, "looking_away_s": round(sig.looking_away_s, 1),
                  "people_in_view": sig.num_people, "face": sig.face_emotion,
                  "participant_affect": {"label": affect.label, "valence": round(affect.valence, 2), "arousal": affect.arousal}}
        last = {"text": ana.text, "language": ana.language, "emotion": ana.emotion, "cues": sorted(ana.cues)} if ana else \
            ({"continuing_own_turn": True} if continuing else {"silence": True})
        line = self.writer.write(note, self.user, last, self.transcript, senses)

        # Facts the LLM extracted.
        u = self.user
        if line.user_name and not u.name:
            u.name = line.user_name
        if line.user_language and self.stage == 2 and line.user_language in LANG_NAME:
            u.language, u.language_confirmed = line.user_language, True
        if line.love and line.love not in u.loves:
            u.loves.append(line.love)
        for n in line.memory_notes:
            u.remember(n)
        if note.act == Act.NAME_PLAY:
            u.said_name_wrong = True
        if jump:
            u.heart_moments.append((self.clock.now(), self.stage, jump, self.director.mode_history[-2].value
                                    if len(self.director.mode_history) > 1 else "?"))

        self.log.event("turn", self.clock.now(), stage=self.stage, heard=ana.text if ana else None,
                       heard_lang=ana.language if ana else None, cues=sorted(ana.cues) if ana else [],
                       affect=affect.__dict__, mode=note.mode.value, act=note.act.value, why=note.reason,
                       story=note.story["id"] if note.story else None, said=line.speech, source=line.source,
                       bpm=sig.bpm, bpm_delta=sig.bpm_delta, heart_jump=jump)
        self.speak(line.speech, note.mode, line.language)
        if note.mode == Mode.SCOLDING and self.sim_heart:
            self.hub.update(looking_away_s=0.0, face_visible=True)   # sim: they look back after being scolded
        self.log.event("senses", self.clock.now(), senses=senses)
        self.emit_user()
        self.turns_in_stage += 1
        return note

    def converse(self, done):
        """Turn loop shared by stages 2-4: Reachy speaks, then either waits for
        the participant or keeps the floor (stories, confessions)."""
        # Each stage opens with Reachy taking the floor. After every hear() there is
        # always one more turn, so the last thing the participant said gets a reaction.
        ana, continuing = None, True
        while True:
            note = self.turn(ana, continuing)
            if done() or self.stage_over():
                break
            if note.expects_reply:
                ana, continuing = self.hear(), False
            else:
                # Reachy pauses; if the participant jumps in, great -- otherwise Reachy goes on.
                ana = self.hear(timeout=3.0)
                continuing = ana is None
                if continuing:
                    self.user.silences -= 1      # a pause after a story isn't the participant being quiet

    # ================================================================ stages
    def run(self, listener, analyzer):
        self.listener, self.analyzer = listener, analyzer
        prewarm = getattr(self.voice, "prewarm", None)
        if prewarm:
            prewarm(self.SNORES + STIR_LINES + COAX_LINES, "sleepy", 0.7)
        try:
            if self.heart_wake:
                self.stage0_baseline()
            if self.show is not None:
                self.persona_stages()
            elif not (self.realtime_agent and self.realtime_stages()):
                self.scripted_stages()
            if self.music:
                self.stage5_music()
        except StopSession as e:
            logger.warning("STOP: %s -> sincere goodbye", e)
            self.log.event("stop", self.clock.now(), reason=str(e), stage=self.stage)
            self.body.play("sincere")
        except Exception as e:
            # Never leave a participant mid-provocation: log it, then still say goodbye.
            logger.exception("Session error in stage %s", self.stage)
            self.log.event("stop", self.clock.now(), reason=f"internal error: {e}", stage=self.stage)
        if self.live is not None:        # opened at the first touch but never used (stopped before waking)
            self.live.discard()
            self.live = None
        self.stop_reason = None          # stage 6 always runs, even after a stop
        self.heart.settle_baseline()     # short session: use what was recorded as the resting heartbeat
        self.note_baseline()
        if self.show is not None:
            self.persona_goodbye()
        else:
            self.stage6_goodbye()
        self.stage7_visualization()

    SNORES = ["Zzz... hnnnk... zzz...", "Mmm... five more minutes...", "Zzzzz... shhhh... zzz...",
              "Hnnnk... mmm... no... not the pasta... zzz...", "Zzz... ba-dum... ba-dum... zzz..."]

    @property
    def skip_provocation(self) -> bool:
        return self.user.no_tease or not self.director.allowed_provocations

    def scripted_stages(self):
        """Stages 1-4 with the Director + writer (offline-capable)."""
        if self.stage < 1:
            self.stage1_wake()
        if self.stage <= 2:
            self.stage2_intro()
        if self.stage <= 3:
            self.stage3_conversation()
        if self.skip_provocation:
            logger.info("=== STAGE 4 skipped (no teasing for this participant / profile) ===")
            self.log.event("stage", self.clock.now(), stage=4, skipped=True)
        elif self.stage <= 4:
            self.stage4_provocation()

    def realtime_stages(self) -> bool:
        """Stages 1-4 as one live conversation with the ElevenLabs agent. False = fall back to scripted."""
        from .realtime import RealtimeConversation

        self.enter(1)
        if not self.woken():
            self.log.event("prompt", self.clock.now(), text=self.cfg.prompts["wake"])
        while not self.woken() and not self.stage_over():
            self.check_safety()
            self.listener_peek()
        self.body.wake_up()
        self.body.wait()
        u, d = self.user, self.director

        def done() -> bool:
            if self.stop_reason:
                return True
            if self.stage == 1 and (self.turns_in_stage >= 1 or self.stage_over()):
                self.enter(2)
            elif self.stage == 2 and ((u.name and u.language_confirmed) or self.turns_in_stage >= 6 or self.stage_over()):
                self.enter(3)
            elif self.stage == 3 and (self.turns_in_stage >= 5 or self.stage_over()):
                if self.skip_provocation:
                    self.log.event("stage", self.clock.now(), stage=4, skipped=True)
                    return True
                self.enter(4)
            elif self.stage == 4 and (len(d.stage4_moves) >= self.cfg.provocation_moves or self.stage_over()):
                return True
            return False

        try:
            RealtimeConversation(self, self.realtime_agent).run(done)
        except Exception as e:  # network / account / audio problems: never strand the participant
            logger.exception("Realtime conversation failed; continuing with the scripted conversation")
            self.log.event("sensor", self.clock.now(), text=f"Live conversation unavailable ({e}); switching to scripted mode.")
            return False
        self.check_safety()
        return True

    # ================================================================ Off-Brand personas
    def persona_opener(self) -> str:
        from .brain.personas import BASE, PERSONAS

        lead = "Mm... someone's heart woke me up. " if self.heart_wake else ""
        opener = PERSONAS[BASE].opener
        if self.show is not None and len(self.show.cast) > 1 and opener.endswith("Ready for a little interview?"):
            # A playful disclaimer up front, so the persona changes later feel expected (user feedback 2026-11-18).
            opener = opener.replace("Ready for a little interview?", "Fair warning: my personality glitches "
                                    "sometimes, so I might not stay... me. Ready for a little interview?")
        return lead + opener

    def persona_event(self, reason: str, source: str = "persona") -> None:
        p, show = self.show.current, self.show
        if self.stage == 2 and p.key != "base":
            self.enter(3)        # the first glitch ends the introductions: Act 4 begins
        self.log.event("persona", self.clock.now(), persona=p.key, name=p.name, color=p.color, reason=reason,
                       index=show.i, cast=show.cast, reset=show.reset_mode)
        self.log.event("turn", self.clock.now(), stage=self.stage, mode=p.key, act="switch", why=f"{p.name} ({reason})",
                       heard=None, said="", source=source, heart_jump=0, bpm=self.hub.snapshot().bpm)

    def persona_cmd(self, kind: str, key: str | None = None) -> None:
        if self.rt is not None and not self.rt.closed.is_set():
            self.rt.persona_command(kind, key)
        else:
            self.pending.append((kind, key))

    def persona_say(self, text: str, gesture: str | None, act: str, heard: str | None = None, why: str = "") -> None:
        p = self.show.current
        if gesture in GESTURES:
            self.body.play(at_speed(gesture, 0.6 if p.key == "burned_out" else 1.0))
        sig = self.hub.snapshot()
        self.log.event("turn", self.clock.now(), stage=self.stage, mode=p.key, act=act, why=why or p.name, heard=heard,
                       said=text, source="persona", bpm=sig.bpm, bpm_delta=sig.bpm_delta, heart_jump=0)
        self.log.event("say", self.clock.now(), text=text, mode=p.key, lang="en")
        self.voice.say(text, "en", p.voice[2], p.key)
        self.transcript.append({"reachy": text, "mode": p.key})

    def persona_switch(self, reason: str) -> bool:
        """Glitch into the next persona. False when the cast is done."""
        show = self.show
        if show.advance(reason) is None:
            return False
        gesture, text = show.entrance()
        self.body.play(transition(gesture, show.glitch_gesture(self.rng)))
        self.persona_event(reason)
        self.persona_say(text, None, "switch", why=f"glitch into {show.current.name} ({reason})")
        act = show.next_activity()
        if act:
            self.persona_say(act["line"], show.current.gestures[0], "activity", why=act["label"])
        return True

    def persona_stages(self):
        """Wake (on the heartbeat, if enabled), then the persona interview: live agent first, offline loop as fallback."""
        from .realtime import RealtimeConversation

        self.enter(1)
        if self.heart_wake:
            if not self.woken():
                self.log.event("prompt", self.clock.now(), text=self.cfg.prompts["wake"])
            while not self.woken() and not self.stage_over():
                self.check_safety()
                self.listener_peek()
        import time
        self.wake_t = time.monotonic()
        self.body.wake_up()          # no wait: Reachy starts talking while it lifts its head
        self.enter(2)                # Base Reachy's opener; the first glitch moves on to Act 4
        if self.realtime_agent:
            try:
                rt, self.live = self.live or RealtimeConversation(self, self.realtime_agent), None
                rt.run(lambda: bool(self.stop_reason) or rt.persona_done())
                self.check_safety()
                if rt.closing_t:
                    return
                logger.warning("Live conversation ended before the close; continuing offline")
            except StopSession:
                raise
            except Exception as e:  # network / account / audio problems: never strand the participant
                logger.exception("Realtime persona conversation failed; continuing offline")
                self.log.event("sensor", self.clock.now(), text=f"Live conversation unavailable ({e}); switching to offline lines.")
            finally:
                self.rt = None
        self.persona_offline()

    def persona_offline(self):
        show = self.show
        if not self.transcript:
            self.persona_event("start")
            self.persona_say(self.persona_opener(), show.current.entrance, "opener")
        while not show.finished:
            self.check_safety()
            while self.pending:
                kind, key = self.pending.pop(0)
                if kind == "next" and not self.persona_switch("facilitator"):
                    show.finished = True
                elif kind == "jump" and show.jump_to(key, "facilitator"):
                    gesture, text = show.entrance()
                    self.persona_event("facilitator")
                    self.persona_say(text, gesture, "switch")
                elif kind == "reset":
                    show.reset("facilitator")
                    self.persona_event("reset")
                    self.persona_say(RESET_LINE, "antenna_wave", "reset")
                elif kind == "close":
                    show.finished = True
                elif kind == "extend":
                    show.extend("facilitator")
                    self.log.event("ending", self.clock.now(), status="extended", by="facilitator")
            if show.finished:
                break
            ana = self.hear()
            if ana is None:
                line, step = show.silence_line()
                if step == "switch":
                    if not self.persona_switch("long silence"):
                        self.offline_end()
                    continue
                self.persona_say(line, "tremble" if step == "rescue" else show.current.gestures[0], step,
                                 why=f"silence ladder: {step}")
                continue
            text = ana.text
            if show.is_reset(text):
                show.reset("participant")
                self.persona_event("reset")
                self.persona_say(RESET_LINE, "antenna_wave", "reset", heard=text, why="stop word: Reachy, reset")
                continue
            if show.is_distress(text) or "discomfort" in ana.cues:
                self.user.discomfort_count += 1
                show.reset("distress")
                if self.user.discomfort_count >= self.cfg.discomfort_limit:
                    show.drop_teasing()
                self.persona_event("distress")
                self.persona_say(f"{DISTRESS_LINE} {show.question()}", "nod_yes", "distress", heard=text,
                                 why="discomfort -> Base Reachy")
                continue
            show.on_exchange()
            if show.reset_mode and show.exchanges >= show.switch_every:
                self.offline_end()
                if show.finished:
                    break
                continue
            p = show.current
            if show.switch_due():
                body = p.reactions.get("answer", "{slot}? Huh.").replace("{slot}", slot_from(text))
                self.persona_say(f"{show.bridge()} {body}", p.gestures[0], "react", heard=text)
                if not self.persona_switch(f"{show.switch_every} exchanges"):
                    self.offline_end()
                continue
            gesture = self.rng.choice(p.gestures)
            line = show.reaction(text, ana.cues, ana.words)
            sig = self.hub.snapshot()
            if show.exchanges % 3 == 2:          # every 2-3 turns: react to what the camera sees
                seen = ("away" if sig.looking_away_s >= self.cfg.look_away_s else
                        "smile" if sig.face_emotion == "happy" and sig.face_conf >= 0.5 else
                        "moving" if sig.motion_energy > 0.35 else None)
                if seen:
                    gesture, cam = p.camera[seen].split("|")
                    line = f"{cam} {line}"
            self.persona_say(line, gesture, "react", heard=text)

    def offline_end(self) -> None:
        """Planned length reached (offline lines): ask before closing; keep going on a yes or Keep talking."""
        show = self.show
        self.log.event("ending", self.clock.now(), status="soon", persona=show.current.key)
        self.persona_say("Oh no, I think we're almost out of time. Want to keep talking a little longer?",
                         show.current.gestures[0], "ending", why="planned length reached")
        ana = self.hear()
        asked = any(k == "extend" for k, _ in self.pending)
        self.pending = [p for p in self.pending if p[0] != "extend"]
        # Anything but a clear "no" (or silence) means they're still talking: keep going.
        if asked or (ana is not None and not show.wants_end(ana.text)):
            show.extend("facilitator" if asked else "participant")
            self.log.event("ending", self.clock.now(), status="extended", by="facilitator" if asked else "participant")
            self.persona_say("Yay! Okay, let's keep going.", show.current.gestures[0], "ending")
        else:
            show.finished = True
            self.log.event("ending", self.clock.now(), status="closing", by="participant" if ana else "time")

    def persona_goodbye(self):
        self.enter(6)
        if not (self.rt_closed_well):
            glitch = not self.show.reset_mode and self.show.current.key != "base"
            self.show.reset_mode = True           # always close as Base Reachy, always warm
            self.persona_event("close")
            self.persona_say(self.show.closing(glitch), "antenna_wave", "goodbye", why="closing (Base Reachy)")
        self.body.wait()
        self.body.go_to_sleep()
        self.body.wait()

    rt_closed_well = False

    def woken(self) -> bool:
        """The participant's heartbeat should wake Reachy now."""
        if self.wake_now:
            return True
        sig = self.hub.snapshot()
        return sig.pulse_present or (self.cfg.wake_on_first_heartbeat and sig.bpm is not None and sig.finger_on)

    def on_contact(self) -> None:
        """Act 1: a fingertip landed. Reachy stirs at once, and the live conversation starts
        connecting now, so it is ready by the time Reachy is awake (session flow v2, section 4)."""
        import time
        self.contact_t = time.monotonic()
        self.log.event("sensor", self.clock.now(), text="Fingertip felt: Reachy stirs.")
        self.body.play("stir")
        self.say_clip(self.rng.choice(STIR_LINES))
        if self.realtime_agent and self.show is not None and self.live is None:
            from .realtime import RealtimeConversation
            try:
                self.live = RealtimeConversation(self, self.realtime_agent)
                self.live.preconnect()
            except Exception as e:  # no audio device etc.: connect later, as before
                logger.warning("Could not open the live conversation early: %s", e)
                self.live = None

    def say_clip(self, text: str) -> None:
        """A short sleepy sound from the local clip cache, without holding up the Act 1 loop."""
        import threading
        if getattr(self, "_clip_thread", None) is not None and self._clip_thread.is_alive():
            return
        play = getattr(self.voice, "say_clip", self.voice.say)
        self.log.event("say", self.clock.now(), text=text, mode="sleepy", lang="en")
        self._clip_thread = threading.Thread(target=play, args=(text, "en", 0.7, "sleepy"), daemon=True, name="clip")
        self._clip_thread.start()

    def act1_asleep(self) -> None:
        """Act 1 (session flow v2): asleep until a fingertip lands, then stirring while the first
        heartbeat is read. Once touched, the session is latched: a lifted finger is coaxed back,
        never a reason to start over."""
        self.body.play("snore", loop=True)
        contact_total, off_since, last_coax, last_t = 0.0, None, -1e9, self.clock.now()
        glanced = False
        while not self.force_next:
            self.check_safety()
            now = self.clock.now()
            dt, last_t = now - last_t, now
            sig = self.hub.snapshot()
            if sig.finger_on:
                if self.contact_t is None:
                    self.on_contact()
                elif off_since is not None and now - off_since >= self.cfg.finger_glance_s:
                    self.body.play("stir")                 # back: stir again where it left off
                off_since, glanced = None, False
                contact_total += dt
                if sig.bpm is not None:
                    self.log.event("sensor", self.clock.now(), text="Heartbeat felt: Reachy wakes up.")
                    break
                if contact_total >= self.cfg.contact_wake_s:
                    self.log.event("sensor", self.clock.now(),
                                   text=f"No clear heartbeat after {self.cfg.contact_wake_s:.0f} s of contact: Reachy wakes up anyway.")
                    break
            elif self.contact_t is not None:
                off_since = off_since if off_since is not None else now
                gone = now - off_since
                if gone >= self.cfg.finger_glance_s and not glanced:
                    glanced = True
                    self.body.play("check_sensor")
                if gone >= self.cfg.finger_lost_s and now - last_coax > 8:
                    last_coax = now
                    self.say_clip(self.rng.choice(COAX_LINES))
            if hasattr(self.listener, "steps"):
                self.listener_peek()
            else:
                self.clock.sleep(0.1)
        if self.force_next:
            self.log.event("sensor", self.clock.now(), text="Facilitator: wake now.")
        if self.contact_t is not None:
            self.latency("contact_to_wake", self.since_contact())
        self.wake_now = True

    def stage0_baseline(self):
        """Asleep and silent until a pulse arrives; then Reachy snores while the
        baseline is recorded, and wakes up once it has 60 s of stable heartbeat."""
        self.enter(0)
        self.log.event("prompt", self.clock.now(), text=self.cfg.prompts["baseline"])
        self.body.go_to_sleep()
        self.body.wait()
        if self.cfg.wake_on_first_heartbeat:
            self.act1_asleep()
            return
        snoring, last_snore = False, -1e9
        # No timeout before the first pulse: Reachy sleeps until someone touches a sensor
        # (the facilitator can still press Next stage). The stage clock starts at the pulse.
        while not (self.heart.baseline_ready() or (snoring and self.stage_over()) or self.force_next):
            self.check_safety()
            sig = self.hub.snapshot()
            if sig.bpm is not None and sig.finger_on and not snoring:
                snoring = True
                self.stage_t0 = self.clock.now()
                self.log.event("sensor", self.clock.now(), text="Pulse detected: Reachy starts snoring.")
                self.log.event("stage_clock", self.clock.now(), stage=0,
                               seconds=self.cfg.stage_time[0] / self.clock.scale)
                self.body.play("snore", loop=True)
            if snoring and self.clock.now() - last_snore > 12:
                self.voice.say(self.rng.choice(self.SNORES), "en", 0.7, "sleepy")
                self.log.event("say", self.clock.now(), text="(snoring)", mode="sleepy", lang="en")
                last_snore = self.clock.now()
            self.listener_peek()
        self.heart.settle_baseline()
        logger.info("heart baseline = %s BPM", self.heart.baseline and round(self.heart.baseline, 1))
        self.log.event("baseline", self.clock.now(), bpm=self.heart.baseline)
        self._baseline_logged = True

    def stage1_wake(self):
        self.enter(1)
        if not self.woken():
            self.log.event("prompt", self.clock.now(), text=self.cfg.prompts["wake"])
        nudged = False
        while not self.woken() and not self.stage_over():
            self.check_safety()
            if not nudged and self.elapsed() > 25:
                # Still asleep: a sleepy mumble invites the participant to press the sensor.
                self.voice.say("Mmm... is someone there? I can't... quite... hear you...", "en", 0.75, "sleepy")
                nudged = True
            self.listener_peek()
        sig = self.hub.snapshot()
        self.body.wake_up()
        self.body.wait()
        if sig.num_people >= 2:
            # Personality doc: surprised to see people, greets in Spanish then English.
            self.speak("¡Hola, hola! ¿Cómo están, amigos? ... Oh! Hi everyone, I am Reachy.", Mode.EXCITED, "es")
        self.speak("Mm... someone's heart woke me up. Was that you?", Mode.CURIOUS, "en")
        self.director.mode_history.append(Mode.CURIOUS)
        self.director.act_history.append(Act.ASK)
        ana = self.hear()
        self.turn(ana)                      # react to whatever they said (or didn't)

    def listener_peek(self):
        """While waiting for the hand, still accept facilitator commands."""
        if hasattr(self.listener, "steps"):
            if self.listener.done:
                self.clock.sleep(1)
                return
            step = self.listener.steps[self.listener.i]
            if "wait" in step:
                self.listener.i += 1
                self.clock.sleep(step["wait"])
                return
            if "cmd" in step:
                self.listener.i += 1
                logger.info("[event] %s", step["cmd"])
                self.on_command(step["cmd"])
                return
        self.clock.sleep(1.0)

    def stage2_intro(self):
        self.enter(2)
        self.body.play("flirty")       # lean in
        self.converse(lambda: self.user.name_confirmed and self.user.language_confirmed)
        if not self.user.language_confirmed:
            # fall back to whatever language we heard most
            heard = [t.get("lang") for t in self.transcript if t.get("lang")]
            if heard:
                self.user.language = max(set(heard), key=heard.count)

    def stage3_conversation(self):
        self.enter(3)
        lang = self.user.language
        logger.info("switching to %s", LANG_NAME.get(lang, lang))
        self.converse(lambda: (self.turns_in_stage >= 4 and self.user.loves) or self.turns_in_stage >= 7)

    def stage4_provocation(self):
        self.enter(4)
        self.converse(lambda: len(self.director.stage4_moves) >= self.cfg.provocation_moves)

    def stage5_music(self):
        self.enter(5)
        path = music_for(self.user.language, self.cfg.music_dir)
        self.speak(phrase("music_intro", self.user.language), Mode.EXCITED, self.user.language
                   if self.user.language in PHRASES["music_intro"] else "en")
        handle = self.voice.play_music(path, self.cfg.music_seconds)
        self.body.dance(bpm=100, seconds=self.cfg.music_seconds * 0.4)
        self.body.wait()
        self.check_safety()
        self.turn(None)                           # INVITE: "Your turn. Show me how you'd move."
        self.body.dance(bpm=100, seconds=self.cfg.music_seconds * 0.5)
        ana = self.hear(timeout=self.cfg.music_seconds * 0.4)
        s = self.hub.snapshot()
        self.user.danced = s.motion_energy > 0.35 or bool(ana and ana.cues & {"laugh"})
        if self.user.danced:
            self.user.remember("danced with Reachy to the song")
        self.turn(ana)
        self.voice.stop_music(handle)

    def stage6_goodbye(self):
        self.enter(6)
        self.turn(None)
        self.body.wait()
        self.body.go_to_sleep()
        self.body.wait()

    def stage7_visualization(self):
        self.enter(7)
        self.log.event("visualization", self.clock.now(), log=self.log.path)
        self.log.event("session_end", self.clock.now(), log=self.log.path)
