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

from .body.voice import music_for
from .brain.director import Director
from .brain.modes import MODE_STYLE, Act, Mode
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


GESTURE_FOR = {Mode.SLEEPY: "sleepy", Mode.CURIOUS: "curious", Mode.EXCITED: "excited", Mode.FLIRTY: "flirty",
               Mode.TEASING: "teasing", Mode.OFFENDED: "offended", Mode.SCOLDING: "scolding", Mode.SINCERE: "sincere"}


class Session:
    def __init__(self, cfg, clock, hub, heart, body, voice, writer, session_log, user: UserModel, profile,
                 sim_heart=None, rng=None):
        self.cfg, self.clock, self.hub, self.heart = cfg, clock, hub, heart
        self.body, self.voice, self.writer, self.log = body, voice, writer, session_log
        self.user, self.sim_heart = user, sim_heart
        self.rng = rng or random.Random(cfg.seed)
        self.director = Director(cfg, self.rng, profile.provocations, profile.flirt_with_two_people)
        self.listener = None
        self.analyzer = None
        self.stage = 0
        self.stage_t0 = 0.0
        self.turns_in_stage = 0
        self.transcript = []
        self.force_next = False
        self.stop_reason: Optional[str] = None

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
        elif c == "next":
            self.force_next = True
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

    def check_safety(self):
        s = self.hub.snapshot()
        if s.bpm_overlimit_s >= self.cfg.bpm_stop_duration_s:
            self.stop_reason = f"BPM above {self.cfg.bpm_stop_limit:.0f} for {s.bpm_overlimit_s:.0f}s"
        if self.stop_reason:
            raise StopSession(self.stop_reason)

    def enter(self, stage):
        self.stage, self.stage_t0, self.turns_in_stage, self.force_next = stage, self.clock.now(), 0, False
        self.heart.collect_baseline = stage == 0
        logger.info("=== STAGE %s ===", stage)
        self.log.event("stage", self.clock.now(), stage=stage, seconds=self.cfg.stage_time[stage] / self.clock.scale)

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
            self.body.look_at(sig.face_x, sig.face_y)   # turn toward the person before listening
            self.body.wait()
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
        if self.stage in (3, 4) and not u.loves and ana.words >= 3 and (
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
        try:
            self.stage0_baseline()
            self.stage1_wake()
            self.stage2_intro()
            self.stage3_conversation()
            if self.user.no_tease or not self.director.allowed_provocations:
                logger.info("=== STAGE 4 skipped (no teasing for this participant / profile) ===")
                self.log.event("stage", self.clock.now(), stage=4, skipped=True)
            else:
                self.stage4_provocation()
            self.stage5_music()
        except StopSession as e:
            logger.warning("STOP: %s -> sincere goodbye", e)
            self.log.event("stop", self.clock.now(), reason=str(e), stage=self.stage)
            self.body.play("sincere")
        except Exception as e:
            # Never leave a participant mid-provocation: log it, then still say goodbye.
            logger.exception("Session error in stage %s", self.stage)
            self.log.event("stop", self.clock.now(), reason=f"internal error: {e}", stage=self.stage)
        self.stop_reason = None          # stage 6 always runs, even after a stop
        self.stage6_goodbye()
        self.stage7_visualization()

    SNORES = ["Zzz... hnnnk... zzz...", "Mmm... five more minutes...", "Zzzzz... shhhh... zzz...",
              "Hnnnk... mmm... no... not the pasta... zzz...", "Zzz... ba-dum... ba-dum... zzz..."]

    def stage0_baseline(self):
        """Asleep and silent until a pulse arrives; then Reachy snores while the
        baseline is recorded, and wakes up once it has 60 s of stable heartbeat."""
        self.enter(0)
        self.log.event("prompt", self.clock.now(), text=self.cfg.prompts["baseline"])
        self.body.go_to_sleep()
        self.body.wait()
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
                self.log.event("stage", self.clock.now(), stage=0, seconds=self.cfg.stage_time[0] / self.clock.scale)
                self.body.play("snore", loop=True)
            if snoring and self.clock.now() - last_snore > 12:
                self.voice.say(self.rng.choice(self.SNORES), "en", 0.7, "sleepy")
                self.log.event("say", self.clock.now(), text="(snoring)", mode="sleepy", lang="en")
                last_snore = self.clock.now()
            self.listener_peek()
        logger.info("heart baseline = %s BPM", self.heart.baseline and round(self.heart.baseline, 1))
        self.log.event("baseline", self.clock.now(), bpm=self.heart.baseline)

    def stage1_wake(self):
        self.enter(1)
        if not self.hub.snapshot().pulse_present:
            self.log.event("prompt", self.clock.now(), text=self.cfg.prompts["wake"])
        nudged = False
        while not self.hub.snapshot().pulse_present and not self.stage_over():
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
