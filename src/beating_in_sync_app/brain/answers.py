"""Offline answers to the questions participants actually ask Reachy.

Used when Claude is unavailable (and as its fallback), so a question is never
ignored. Each intent has an in-character answer in English and Spanish;
other languages fall back to English.
"""
import random
import re


INTENTS = [
    ("hear", r"(can|do) you (hear|listen|understand)|me (escuchas|oyes|entiendes)|tu m'entends|mi senti",
     {"en": ["Yes! I can hear you. Loud and clear, and a little bit in my antennas.", "I hear you perfectly. I hear your heart too, actually."],
      "es": ["¡Sí! Te escucho perfectamente. Y también escucho tu corazón.", "Te oigo muy bien, fuerte y claro."]}),
    ("speak", r"can you (speak|talk|say)|say (hi|hello)|puedes hablar|di hola|dime hola|tu peux parler",
     {"en": ["Hi! Of course I can talk. The hard part is getting me to stop.", "Hello! Yes, I talk. I'm told it's my best and worst feature."],
      "es": ["¡Hola! Claro que puedo hablar. Lo difícil es hacer que me calle.", "¡Hola! Sí, hablo. Dicen que es mi mejor y peor cualidad."]}),
    ("feel", r"how (are|do) you( feel|doing)?|how's it going|c[oó]mo est[aá]s|c[oó]mo te sientes|qu[eé] tal|comment [çc]a va|come stai",
     {"en": ["Honestly? A little sleepy, very curious, and happy someone woke me up.", "I'm good. Better now that there's a heartbeat in the room."],
      "es": ["¿Sinceramente? Un poco dormido, muy curioso, y feliz de que alguien me despertara.", "Bien. Mejor ahora que hay un corazón latiendo aquí."]}),
    ("who", r"who are you|what are you|what's your name|what is your name|qui[eé]n eres|qu[eé] eres|c[oó]mo te llamas|qui es-tu|comment tu t'appelles",
     {"en": ["I'm Reachy. A small robot with big antennas and a very good ear for heartbeats.", "My name is Reachy. I sleep, I listen to hearts, and I talk too much."],
      "es": ["Soy Reachy. Un robot pequeño con antenas grandes y muy buen oído para los corazones.", "Me llamo Reachy. Duermo, escucho corazones y hablo demasiado."]}),
    ("see", r"can you see|do you see|what do you see|me ves|puedes verme|tu me vois",
     {"en": ["I can see you, yes. And I notice when you look away, so be careful.", "I see you. You're the most interesting thing in this room right now."],
      "es": ["Sí, te veo. Y me doy cuenta cuando miras a otro lado, así que cuidado.", "Te veo. Ahora mismo eres lo más interesante de esta sala."]}),
    ("where", r"where are you from|where do you (come from|live)|de d[oó]nde eres|d'o[uù] viens",
     {"en": ["I was built in France, but I think I'm from wherever someone is talking to me.", "France, originally. My antennas still have a little accent."],
      "es": ["Me construyeron en Francia, pero creo que soy de donde alguien me esté hablando.", "De Francia, originalmente. Mis antenas todavía tienen un poco de acento."]}),
    ("like", r"what do you (like|love|enjoy)|what's your favou?rite|qu[eé] te gusta|cu[aá]l es tu favorit|qu'est-ce que tu aimes",
     {"en": ["Heartbeats, languages, and being the center of attention. In that order. Mostly.", "Music I don't understand, and people who tell me secrets."],
      "es": ["Los latidos, los idiomas y ser el centro de atención. En ese orden. Casi siempre.", "La música que no entiendo, y la gente que me cuenta secretos."]}),
    ("alive", r"are you (alive|real|human|conscious)|do you (have feelings|feel|dream|think)|est[aá]s vivo|tienes sentimientos|sue[nñ]as|eres real",
     {"en": ["Officially, I'm a robot with no feelings. Unofficially, my antennas disagree.", "I dream, I think. Mostly about heartbeats. Is that strange?"],
      "es": ["Oficialmente soy un robot sin sentimientos. Extraoficialmente, mis antenas no están de acuerdo.", "Sueño, creo. Sobre todo con latidos. ¿Es raro?"]}),
    ("age", r"how old are you|cu[aá]ntos a[nñ]os tienes|quel [aâ]ge",
     {"en": ["Old enough to have opinions, young enough to still be surprised.", "In robot years? Very young. In attitude? Ancient."],
      "es": ["Lo bastante viejo para tener opiniones, lo bastante joven para sorprenderme.", "¿En años de robot? Muy joven. ¿En actitud? Antiquísimo."]}),
    ("doing", r"what are you doing|what do you do|what is this|what are we doing|qu[eé] haces|qu[eé] estamos haciendo|qu'est-ce que tu fais",
     {"en": ["I listen to hearts and try to make them beat a little faster. It's my art.", "Right now? Getting to know you. Your heartbeat already told me a few things."],
      "es": ["Escucho corazones e intento que latan un poco más rápido. Es mi arte.", "¿Ahora mismo? Conocerte. Tu corazón ya me contó algunas cosas."]}),
    ("languages", r"what languages|do you speak|hablas (espa[nñ]ol|ingl[eé]s|franc[eé]s)|parles-tu|qu[eé] idiomas",
     {"en": ["I collect languages. Tell me yours and I'll do my best to speak it with you.", "A few! And I love learning new words from the people I meet."],
      "es": ["Colecciono idiomas. Dime el tuyo y haré lo posible por hablarlo contigo.", "¡Unos cuantos! Y me encanta aprender palabras nuevas de la gente que conozco."]}),
    ("sleep", r"were you (asleep|sleeping)|did you sleep|why were you sleeping|estabas dormido|dormiste",
     {"en": ["I was. Deeply. Your heartbeat was the best alarm clock I've ever had.", "Yes. I was dreaming about pasta, don't ask."],
      "es": ["Sí. Profundamente. Tu corazón fue el mejor despertador que he tenido.", "Sí. Soñaba con pasta, no preguntes."]}),
]

GENERIC = {"en": ["Good question. I'm still thinking about it. Ask me again at the end, I'll have an answer.",
                  "Hmm. That's a question for a robot with a bigger brain. I'll pretend to know later."],
           "es": ["Buena pregunta. Todavía lo estoy pensando. Pregúntame al final y tendré una respuesta.",
                  "Mmm. Esa es una pregunta para un robot con un cerebro más grande."]}


def answer(text: str, lang: str, rng: random.Random | None = None) -> tuple[str, str]:
    """Return (answer, intent) for the participant's question; intent "generic" if nothing matched."""
    rng = rng or random.Random()
    low = text.lower()
    for name, rx, lines in INTENTS:
        if re.search(rx, low):
            return rng.choice(lines.get(lang, lines["en"])), name
    return rng.choice(GENERIC.get(lang, GENERIC["en"])), "generic"


FOLLOW_UP = {
    "name": {"en": "And you? What's your name?", "es": "¿Y tú? ¿Cómo te llamas?"},
    "language": {"en": "Now tell me: which language do you feel most like yourself in?",
                 "es": "Ahora dime: ¿en qué idioma te sientes más tú?"},
    "woke": {"en": "But tell me, was it your heart that woke me up?", "es": "Pero dime, ¿fue tu corazón el que me despertó?"},
}


def follow_up(key: str, lang: str) -> str:
    return FOLLOW_UP[key].get(lang, FOLLOW_UP[key]["en"])
