"""Lines Reachy never crosses (Personality doc), enforced on every line
before it is spoken -- whether it came from the LLM or a template.

Reachy provokes the person's *behaviour in the moment*, never who they are.
"""
import re


RED_LINES = [
    # body / appearance / identity
    (r"\byour (body|face|hair|skin|lips|legs|figure|weight|eyes are|smile is)\b", "appearance"),
    (r"\b(sexy|hot|gorgeous|pretty face|beautiful (face|body|eyes)|handsome|attractive|curves)\b", "appearance"),
    (r"\b(how old|your age|too old|so young|old man|old lady)\b", "age"),
    (r"\b(your (race|gender|religion|ethnicity|nationality|skin colou?r))\b", "identity"),
    # sexual content
    (r"\b(kiss|naked|sex|seduc|undress|touch you|date me)\w*", "sexual"),
    # real insults / threats
    (r"\b(stupid|idiot|dumb|loser|ugly|pathetic|shut up|hate you|worthless|i('ll| will) hurt)\b", "insult"),
    # mocking language / accent
    (r"\b(your accent (is|sounds) (bad|weird|funny|terrible)|bad (pronunciation|accent)|speak properly|real language)\b", "language-mockery"),
    # health claims from the heartbeat
    (r"\b(diagnos\w*|arrhythmi\w*|tachycardi\w*|heart (disease|condition|problem)|unhealthy|you('re| are) (sick|ill)|medical|blood pressure)\b", "health-claim"),
]


def violates(text: str):
    low = text.lower()
    for rx, why in RED_LINES:
        if re.search(rx, low):
            return why
    return None


def is_stop(text: str, stop_words) -> bool:
    low = text.lower().strip(" .!?¡¿")
    return any(re.search(rf"(^|\b){re.escape(w)}(\b|$)", low) for w in stop_words) and len(low.split()) <= 4
