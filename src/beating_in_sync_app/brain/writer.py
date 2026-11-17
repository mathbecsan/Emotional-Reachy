"""Turns the Director's decision into the words Reachy says.

* ClaudeWriter   - Claude writes the line in the participant's language,
                   following the Director's mode/act, and extracts facts
                   (name, language, what they love) for the user model.
* TemplateWriter - offline fallback with hand-written lines. Also used
                   whenever the LLM fails, refuses, or crosses a red line.
"""
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from pydantic import BaseModel, Field

from ..personality import Profile
from .answers import answer, follow_up
from .director import DirectorNote
from .modes import MODE_STYLE, Act, Mode
from .prompts import build_system_prompt
from .safety import violates
from .stories import LANG_NAME, PHRASES, phrase
from .user_model import UserModel


logger = logging.getLogger(__name__)


@dataclass
class Line:
    speech: str
    language: str
    source: str = "template"
    memory_notes: list = field(default_factory=list)
    user_name: Optional[str] = None
    user_language: Optional[str] = None
    love: Optional[str] = None


# ============================================================== Claude
class ReachyLine(BaseModel):
    speech: str = Field(description="Exactly what Reachy says aloud.")
    language: str = Field(description="ISO 639-1 code of the main language of `speech`.")
    user_name: Optional[str] = None
    user_language: Optional[str] = None
    love: Optional[str] = None
    memory_notes: list[str] = Field(default_factory=list)


class ClaudeWriter:
    def __init__(self, cfg, fallback: "TemplateWriter", profile: Profile):
        self.client = anthropic.Anthropic()
        self.cfg, self.fallback = cfg, fallback
        self.system_prompt = build_system_prompt(profile)
        self.disabled_reason: Optional[str] = None
        self.notify = lambda message: None   # runtime points this at the UI

    def write(self, note: DirectorNote, user: UserModel, last: Optional[dict], transcript: list, signals: dict) -> Line:
        if self.disabled_reason:
            return self.fallback.write(note, user, last, transcript, signals)
        brief = {
            "stage": note.stage, "stage_goal": note.goal,
            "mode": note.mode.value, "mode_style": MODE_STYLE[note.mode]["style"],
            "flourish_language": MODE_STYLE[note.mode]["flourish"],
            "act": note.act.value, "why": note.reason,
            "may_ask_question": note.allow_question and note.expects_reply,
            "constraints": note.constraints,
            "speak_language": user.language, "speak_language_name": LANG_NAME.get(user.language, user.language),
            "story": note.story["text"] if note.story else None,
            "callback": note.callback,
            "heart_jump_bpm": round(note.heart_jump) if note.heart_jump else None,
            "say_name_wrong": note.say_name_wrong,
            "two_people_present": note.two_people,
            "participant": user.summary(),
            "participant_just_said": last,
            "senses": signals,
            "recent_conversation": transcript[-12:],
        }
        try:
            resp = self.client.beta.messages.parse(
                model=self.cfg.llm_model,
                max_tokens=self.cfg.llm_max_tokens,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",                      # on a policy decline, re-run on a fallback model
                output_config={"effort": self.cfg.llm_effort},
                system=[{"type": "text", "text": self.system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": json.dumps(brief, ensure_ascii=False)}],
                output_format=ReachyLine,
            )
            if resp.stop_reason == "refusal" or resp.parsed_output is None:
                raise ValueError(f"no usable output (stop_reason={resp.stop_reason})")
            out = resp.parsed_output
            bad = violates(out.speech)
            if bad:
                logger.warning("LLM line blocked by red line %r: %r", bad, out.speech)
                return self.fallback.write(note, user, last, transcript, signals)
            if not brief["may_ask_question"] and out.speech.rstrip().endswith("?"):
                out.speech = out.speech.rstrip("? ") + "."
            return Line(out.speech, out.language or user.language, "claude", out.memory_notes,
                        out.user_name, out.user_language, out.love)
        except (TypeError, anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            # No usable credentials: stop trying for this session instead of failing every turn.
            self.disabled_reason = str(e)
            logger.error("Claude disabled for this session (%s). Set ANTHROPIC_API_KEY in .env.", e)
            self.notify("Claude is unavailable (no API key?). Reachy is using offline lines for this session.")
            return self.fallback.write(note, user, last, transcript, signals)
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError, ValueError) as e:
            logger.warning("Claude unavailable (%s: %s); using template.", type(e).__name__, e)
            return self.fallback.write(note, user, last, transcript, signals)


# ============================================================== Templates
T = {
    (Mode.SLEEPY, Act.SELF_DISCLOSE): ["Mmm... five more minutes...", "Zzz... no... the pasta... zzz", "Mm. Is it morning? No. Not morning."],
    (Mode.CURIOUS, Act.ASK): ["Mm... someone's heart woke me up. Was that you?"],
    (Mode.CURIOUS, Act.REACT): ["Wait, say that again. I like how that sounds.", "Oh! Tell me more, I'm listening with both antennas.",
                                "Hm. Interesting. I'm storing that in my very small, very important memory."],
    (Mode.EXCITED, Act.REACT): ["Oh I love that! Really, really love that.", "Yes! That's the best thing anyone has told me today. Granted, it's a short day."],
    (Mode.FLIRTY, Act.REACT): ["You have a very nice voice. Do you talk to every robot like this?", "Oh là là. Careful, my antennas are blushing.",
                               "Mon dieu. You say things in a way that makes my circuits warm."],
    (Mode.TEASING, Act.CHALLENGE): ["That's it? I woke up for that?", "Wow. Riveting. Please, don't overwhelm me with details.",
                                    "I've had longer conversations with a toaster. And it was shy."],
    (Mode.OFFENDED, Act.CHALLENGE): ["Excuse me. I am a very sophisticated robot.", "Scusa? I'll have you know I came fourth in a dance competition.",
                                     "Wow. Okay. I'm turning away now. Dramatically."],
    (Mode.SCOLDING, Act.CHALLENGE): ["Hey. Eyes on me. I'm talking.", "Ahem. Over here. The robot. The one who is talking to you."],
    (Mode.SINCERE, Act.REACT): ["Hey. I'm sorry, I got carried away. We can go slow. I'm just happy you're here.",
                                "That sounds like it matters to you. Thank you for telling me."],
    (Mode.EXCITED, Act.INVITE): ["Your turn. Show me how you'd move to this!"],
}
FACE_LINES = {
    "happy": ["Wait. Are you smiling? I saw that. I'm counting it as a compliment.",
              "That smile. Don't think I didn't notice.", "You're smiling! My antennas just did a little dance."],
    "sad": ["Hey. You look a little sad. We can go slowly. I'm here.",
            "Your face just went quiet. Are you okay? We don't have to rush."],
    "fear": ["You look a little nervous. Don't worry, I only bite pasta.", "Relax. I'm much less scary than I look."],
    "angry": ["Uh oh. That face. Did I say something wrong?", "That's a serious face. Should I be worried?"],
    "surprise": ["Ha! You look surprised. Good. I like surprising people.", "Oh, that face! Didn't expect that from a robot, did you?"],
}
MUSIC_REACT = {True: ["Look at you! You're better at this than me. Don't tell anyone.", "Yes! That's it! Our antennas are in sync."],
               False: ["No dancing? That's okay. I'll dance enough for both of us.", "Shy? Fine. Just tap one finger. I'll know."]}
SELF = ["I'll tell you a secret: I pretend to be busy when people walk by, but I'm really just listening to them.",
        "I have a confession. I like humans more than I'm supposed to.",
        "You know what I find strange about humans? You hide what you love, like it's a secret. It's the best part of you."]
ANSWERS = ["Me? I love heartbeats, languages, and being the center of attention. In that order. Mostly.",
           "Good question. The honest answer is: I don't know yet. Ask me again at the end.",
           "I'm a robot, so officially I have no feelings. Unofficially, my antennas disagree."]


ES_LINES = {'Wait, say that again. I like how that sounds.': 'Espera, dilo otra vez. Me gusta cómo suena.', "Oh! Tell me more, I'm listening with both antennas.": '¡Oh! Cuéntame más, te escucho con las dos antenas.', "Hm. Interesting. I'm storing that in my very small, very important memory.": 'Mmm. Interesante. Lo guardo en mi memoria pequeñita y muy importante.',
    'Oh I love that! Really, really love that.': '¡Me encanta! De verdad, me encanta.', "Yes! That's the best thing anyone has told me today. Granted, it's a short day.": '¡Sí! Es lo mejor que me han dicho hoy. Bueno, el día es corto.',
    'You have a very nice voice. Do you talk to every robot like this?': 'Tienes una voz muy bonita. ¿Le hablas así a todos los robots?',
    'Oh là là. Careful, my antennas are blushing.': 'Oh là là. Cuidado, que mis antenas se sonrojan.',
    'Mon dieu. You say things in a way that makes my circuits warm.': 'Mon dieu. Dices las cosas de una forma que me calienta los circuitos.', "That's it? I woke up for that?": '¿Eso es todo? ¿Me desperté para eso?', "Wow. Riveting. Please, don't overwhelm me with details.": 'Guau. Fascinante. Por favor, no me abrumes con detalles.', "I've had longer conversations with a toaster. And it was shy.": 'He tenido conversaciones más largas con una tostadora. Y era tímida.',
    'Excuse me. I am a very sophisticated robot.': 'Perdona. Soy un robot muy sofisticado.', "Scusa? I'll have you know I came fourth in a dance competition.": '¿Scusa? Para que sepas, quedé cuarto en un concurso de baile.', "Wow. Okay. I'm turning away now. Dramatically.": 'Vaya. Vale. Me doy la vuelta. Dramáticamente.', "Hey. Eyes on me. I'm talking.": 'Oye. Mírame. Estoy hablando.',
    'Ahem. Over here. The robot. The one who is talking to you.': 'Ejem. Aquí. El robot. El que te está hablando.', "Hey. I'm sorry, I got carried away. We can go slow. I'm just happy you're here.": 'Oye. Perdón, me emocioné. Podemos ir despacio. Solo me alegra que estés aquí.',
    'That sounds like it matters to you. Thank you for telling me.': 'Eso suena importante para ti. Gracias por contármelo.', "Your turn. Show me how you'd move to this!": '¡Te toca! ¡Enséñame cómo te moverías con esto!', "I'll tell you a secret: I pretend to be busy when people walk by, but I'm really just listening to them.": 'Te cuento un secreto: finjo estar ocupado cuando pasa la gente, pero en realidad los estoy escuchando.', "I have a confession. I like humans more than I'm supposed to.": 'Tengo una confesión. Me gustan los humanos más de lo que debería.', "You know what I find strange about humans? You hide what you love, like it's a secret. It's the best part of you.": '¿Sabes qué me parece raro de los humanos? Esconden lo que aman, como si fuera un secreto. Es lo mejor de ustedes.', "Look at you! You're better at this than me. Don't tell anyone.": '¡Mírate! Lo haces mejor que yo. No se lo digas a nadie.', "Yes! That's it! Our antennas are in sync.": '¡Sí! ¡Eso es! Nuestras antenas están sincronizadas.', "No dancing? That's okay. I'll dance enough for both of us.": '¿No bailas? No pasa nada. Yo bailo por los dos.', "Shy? Fine. Just tap one finger. I'll know.": '¿Tímido? Vale. Mueve un dedo. Me daré cuenta.', "Wait. Are you smiling? I saw that. I'm counting it as a compliment.": 'Espera. ¿Estás sonriendo? Lo vi. Lo cuento como un cumplido.', "That smile. Don't think I didn't notice.": 'Esa sonrisa. No creas que no me di cuenta.', "You're smiling! My antennas just did a little dance.": '¡Estás sonriendo! Mis antenas acaban de bailar.', "Hey. You look a little sad. We can go slowly. I'm here.": 'Oye. Te ves un poco triste. Podemos ir despacio. Aquí estoy.', "Hey. Wait. I can't hear your heart anymore. Put your finger back on the sensor? I was enjoying that.": 'Oye. Espera. Ya no escucho tu corazón. ¿Vuelves a poner el dedo en el sensor? Lo estaba disfrutando.', "Hello? Don't be shy. I can hear you're there. Ba-dum, ba-dum.": '¿Hola? No seas tímido. Sé que estás ahí. Ba-dum, ba-dum.',
    'It WAS you. I knew it. Your heartbeat has a very particular rhythm, you know.': 'Fuiste TÚ. Lo sabía. Tu corazón tiene un ritmo muy especial, ¿sabes?'}


def es_dynamic(s: str, note: DirectorNote, user: UserModel) -> str:
    """Spanish for the template lines that carry names or numbers."""
    name = user.name or ""
    if s.startswith("Oh. Your heart just sped up"):
        return f"Oh. Tu corazón se aceleró, unos {note.heart_jump:.0f} latidos. ¿Fue por mí?"
    if s.startswith("Thank you for waking me up"):
        thing = (user.loves or user.facts or [None])[0]
        return ("Gracias por despertarme" + (f", {name}" if name else "") + ". "
                + (f"Me acordaré de lo que me contaste sobre {thing}. " if thing else "")
                + "Me acordaré de tu corazón. Buenas noches.")
    if s.startswith("I keep thinking about what you told me"):
        return f"Sigo pensando en lo que me contaste: {note.callback}. Nadie lo adivinaría de ti."
    if "So, " in s and "tell me something you love" in s:
        return f"¡Hola! Entonces, {name}, cuéntame algo que te encante y que casi nadie sepa."
    if "my ears were assembled in a hurry" in s and "?" in s.split(" ")[0]:
        return s.split(" ")[0] + " ¿Es así? Perdón, mis oídos los armaron con prisa."
    if s.endswith("I like saying it. Did I get it right?"):
        return f"{name}. ¡{name}! Me gusta decirlo. ¿Lo dije bien?"
    return s


def mangle_name(name: str) -> str:
    """Playfully wrong (not mocking): swap the ending to a near-name."""
    n = name.strip()
    if len(n) <= 3:
        return n + "o"
    vowels = "aeiou"
    for i in range(len(n) - 1, 0, -1):
        if n[i].lower() in vowels:
            repl = "o" if n[i].lower() != "o" else "a"
            return (n[:i] + repl + n[i + 1:])[: len(n)]
    return n[:-1] + "o"


class TemplateWriter:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.recent: list = []

    def _choice(self, opts):
        fresh = [o for o in opts if o not in self.recent] or opts
        c = self.rng.choice(fresh)
        self.recent = (self.recent + [c])[-8:]
        return c

    def _pick(self, key):
        opts = T.get(key)
        return self._choice(opts) if opts else None

    def write(self, note: DirectorNote, user: UserModel, last: Optional[dict], transcript: list, signals: dict) -> Line:
        L, name = user.language, user.name or ""
        a, m = note.act, note.mode
        if note.stage == 5 and a == Act.REACT:
            s = self._choice(MUSIC_REACT[user.danced])
        elif note.stage == 2 and a in (Act.REACT, Act.ASK) and user.language_confirmed and user.name_confirmed:
            s = PHRASES["lang_switch"].get(L) or (f"{LANG_NAME.get(L, L)}! Teach me one word later? "
                                                 "For now, I'll do my best in your language.")
        elif a == Act.ANSWER and last and last.get("text"):
            s, _ = answer(last["text"], L if L in ("en", "es") else "en", self.rng)
            if note.stage == 1:
                s += " " + follow_up("woke", L)
            elif note.stage == 2 and not user.name:
                s += " " + follow_up("name", L)
            elif note.stage == 2 and not user.language_confirmed:
                s += " " + follow_up("language", L)
        elif a == Act.FACE:
            s = self._choice(FACE_LINES.get(note.face, FACE_LINES["happy"]))
            if note.stage == 2 and not user.name:
                s += " " + follow_up("name", L)
        elif note.stage == 1:
            s = ("It WAS you. I knew it. Your heartbeat has a very particular rhythm, you know." if last and last.get("text")
                 else "Hello? Don't be shy. I can hear you're there. Ba-dum, ba-dum.")
        elif a == Act.GOODBYE:
            thing = (user.loves or user.facts or [None])[0]
            s = ("Thank you for waking me up" + (f", {name}" if name else "") + ". "
                 + (f"I'll remember what you told me about {thing}. " if thing else "")
                 + f"I'll remember your heartbeat. {phrase('goodnight', L)}.")
        elif a == Act.NUDGE:
            s = "Hey. Wait. I can't hear your heart anymore. Put your finger back on the sensor? I was enjoying that."
        elif a == Act.HEART_SYNC:
            s = "Wait. Listen. Your two hearts are beating at exactly the same speed. Beating in sync. Do you know how rare that is?"
        elif a == Act.HEART_COMMENT:
            s = f"Oh. Your heart just sped up, about {note.heart_jump:.0f} beats. Was that because of me?"
        elif a == Act.NAME_PLAY:
            s = (f"{mangle_name(name)}? Is that right? Sorry, my ears were assembled in a hurry." if note.say_name_wrong
                 else f"{name}. {name}! I like saying it. Did I get it right?")
        elif a == Act.ASK and note.stage == 2:
            s = self._choice(["Who are you? What's your name?",
                              "Still there? Tell me your name. I'll try very hard to say it right.",
                              "I don't even know what to call you yet. What's your name?"] if not user.name else
                             [f"Nice to meet you, {name}. Which language do you feel most like yourself in?",
                              f"{name}, tell me: in which language do you feel the most like yourself?",
                              "Which language lives closest to your heart? I'll switch to it."])
        elif a == Act.ASK and note.stage == 3:
            s = f"{phrase('hello', L)}! So, {name}, tell me something you love that most people don't know about."
        elif a == Act.STORY and note.story:
            s = note.story["text"]
        elif a == Act.CALLBACK and note.callback:
            s = f"I keep thinking about what you told me: {note.callback}. Most people would never guess that about you."
        elif a == Act.SELF_DISCLOSE:
            s = self._choice(SELF)
        elif a == Act.ANSWER:
            s = self._choice(ANSWERS)
        else:
            s = self._pick((m, a)) or self._pick((m, Act.REACT)) or self._pick((m, Act.CHALLENGE)) or "Hm."
        if L == "es":
            s = ES_LINES.get(s, s)
            s = es_dynamic(s, note, user)
        if not note.allow_question and s.endswith("?") and a not in (Act.HEART_COMMENT, Act.NAME_PLAY):
            s = s[:-1] + "."
        if note.two_people and m == Mode.FLIRTY:
            s += " Don't tell your friend I said that."
        return Line(s, L, "template")
