"""Understanding what the participant said.

* Textual emotion (TER): the DistilBERT classifier from
  kudosscience/fer_and_ter_model (models/ter_distilbert_model) when present,
  otherwise a small multilingual lexicon so the system still works offline.
* Social cues the Personality doc maps to modes: compliments -> Flirty,
  contradictions / laughing at Reachy -> Offended, short answers -> Teasing,
  discomfort -> back off.
* Facts for the user model: name, language, "something you love".
"""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional


logger = logging.getLogger(__name__)

TER_LABELS = ["angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"]

LEXICON = {
    "happy": r"\b(love|lov(e|ing)|great|amazing|happy|fun|awesome|haha|lol|nice|beautiful|excited|me encanta|feliz|genial|j'adore|g[eé]nial|content|bello|felice|toll|super|incr[ií]vel|adoro)\b",
    "sad": r"\b(sad|miss|lonely|tired|cry|lost|hard time|triste|extra[nñ]o|cansad[oa]|seul|fatigu[eé]|stanco|traurig|saudade)\b",
    "fear": r"\b(scared|afraid|nervous|anxious|worried|scary|miedo|nervios[oa]|peur|paura|angst)\b",
    "angry": r"\b(angry|annoying|annoyed|hate|mad|rude|stupid|enojad[oa]|odio|f[aâ]ch[eé]|arrabbiat[oa]|w[uü]tend)\b",
    "disgust": r"\b(gross|disgusting|ew+|yuck|asco|d[eé]go[uû]tant|schifo|ekelhaft)\b",
    "surprise": r"\b(wow|whoa|really\?|no way|what\?!|omg|en serio|vraiment|davvero|wirklich|nossa)\b",
}

CUES = {
    "compliment": r"(you('re| are) (so |really |very )?(cute|nice|sweet|funny|smart|cool|charming|adorable|lovely|great))|(i like you)|(nice voice)|(love your)|(eres (muy )?(lindo|bonito|gracioso|simp[aá]tico|tierno))|(me (caes|gustas))|(tu es (trop |tr[eè]s )?(mignon|dr[oô]le|gentil))|(sei (carino|simpatico))|(du bist (s[uü]ß|lustig))|(good robot)|(you're the best)",
    "contradiction": r"(^no[,.!]|^no,? (it's|its|that's|es|eso|c'est)\b|^nope|not true|that's wrong|you're wrong|wrong\b|actually,? (no|it)|that's not|no es (verdad|cierto)|eso no|c'est faux|pas vrai|non [eè] vero|stimmt nicht|i disagree)",
    "laugh": r"(haha|hehe|lol|lmao|jaja|jeje|kkk|mdr|😂|🤣)",
    "discomfort": r"(stop it|that's mean|not funny|uncomfortable|i don't like (that|this|it)|too much|creepy|that's rude|leave me|please (don't|no)|no me gusta|me incomoda|c'est m[eé]chant|arr[eê]te|smettila|h[oö]r auf|awkward)",
    "ask_robot": r"(\?|^\s*(what|why|how|who|where|when|do you|are you|can you|have you|qu[eé]|por qu[eé]|c[oó]mo|qui|quoi|pourquoi|est-ce|cosa|perch[eé]|was|warum|wie))",
    "love_talk": r"(i love|i really like|i'm (obsessed|passionate)|my favou?rite|me encanta|amo |me apasiona|j'adore|j'aime|adoro|ich liebe)",
    "bored_user": r"\b(boring|whatever|meh|i don't know|idk|no s[eé]|je sais pas|non lo so|wei[sß] nicht)\b",
}

LANG_NAMES = {
    "en": r"\b(english|ingl[eé]s|anglais|inglese|englisch)\b",
    "es": r"\b(spanish|espa[nñ]ol|castellano|espagnol|spagnolo|spanisch)\b",
    "fr": r"\b(french|fran[cç]ais|franc[eé]s|francese|franz[oö]sisch)\b",
    "it": r"\b(italian|italiano|italien)\b",
    "de": r"\b(german|deutsch|alem[aá]n|allemand|tedesco)\b",
    "pt": r"\b(portuguese|portugu[eê]s|portugais)\b",
    "zh": r"\b(chinese|mandarin|cantonese|chino|中文|普通话)\b",
    "ja": r"\b(japanese|japon[eé]s|日本語)\b",
    "ko": r"\b(korean|coreano|한국어)\b",
    "hi": r"\b(hindi)\b",
    "ar": r"\b(arabic|[aá]rabe|عربي)\b",
    "ru": r"\b(russian|ruso|русский)\b",
    "tr": r"\b(turkish|turco|t[uü]rk[cç]e)\b",
    "fa": r"\b(farsi|persian)\b",
    "vi": r"\b(vietnamese)\b",
    "tl": r"\b(tagalog|filipino)\b",
}

NAME_PATTERNS = [
    r"(?:my name is|i'm|i am|call me|it's|me llamo|mi nombre es|soy|je m'appelle|je suis|mi chiamo|sono|ich hei[sß]e|ich bin|meu nome [eé]|eu sou)\s+([A-ZÀ-ÿa-zà-ÿ'\-]+)",
]
NOT_NAMES = {"a", "an", "the", "fine", "good", "ok", "okay", "here", "not", "so", "very", "bien", "muy", "très", "really", "just"}

TOPIC_TAGS = {
    "music": r"(music|song|sing|guitar|piano|band|dance|m[uú]sica|canci[oó]n|bailar|musique|chanson|danser)",
    "food": r"(food|cook|bake|eat|recipe|coffee|tea|comida|cocinar|caf[eé]|cuisine|manger|cucinare)",
    "travel": r"(travel|trip|country|city|ocean|beach|mountain|viajar|playa|voyage|plage|montagne)",
    "family": r"(mom|mother|dad|father|grand|sister|brother|family|familia|mam[aá]|pap[aá]|abuel|famille|m[eè]re|p[eè]re)",
    "nature": r"(plant|garden|tree|flower|animal|dog|cat|bird|star|sky|moon|perro|gato|jard[ií]n|chien|chat|fleur)",
    "art": r"(paint|draw|art|photo|film|movie|book|read|write|poem|pintar|dibujar|libro|peinture|livre)",
    "sport": r"(sport|run|soccer|football|basketball|swim|climb|gym|f[uú]tbol|correr|nadar|courir)",
    "tech": r"(code|program|robot|computer|game|video ?game|tech|c[oó]digo|juego|jeu)",
    "sleep": r"(sleep|dream|nap|night|dormir|so[nñ]ar|r[eê]ve|sogno)",
}


@dataclass
class Analysis:
    text: str
    words: int
    language: Optional[str] = None           # spoken language (from STT)
    mentioned_language: Optional[str] = None  # language named in the text ("I feel most myself in Spanish")
    name: Optional[str] = None
    emotion: str = "neutral"
    emotion_conf: float = 0.0
    cues: set = field(default_factory=set)
    topics: list = field(default_factory=list)


class TextEmotion:
    """DistilBERT TER from kudosscience if the model folder exists; else lexicon."""

    def __init__(self, model_dir: str):
        self.model = None
        if os.path.isdir(model_dir):
            try:
                import pickle

                import torch  # noqa: F401
                from transformers import DistilBertForSequenceClassification, DistilBertTokenizer
                self.tok = DistilBertTokenizer.from_pretrained(model_dir)
                self.model = DistilBertForSequenceClassification.from_pretrained(model_dir).eval()
                enc = os.path.join(model_dir, "label_encoder.pkl")
                self.labels = list(pickle.load(open(enc, "rb")).classes_) if os.path.exists(enc) else TER_LABELS
            except (ImportError, OSError) as e:
                logger.warning("TER model unavailable (%s); using lexicon.", e)
                self.model = None

    def __call__(self, text: str):
        if self.model is not None:
            import torch
            t = self.tok(text, return_tensors="pt", truncation=True, max_length=128)
            with torch.no_grad():
                p = torch.softmax(self.model(**t).logits, dim=1)[0]
            i = int(p.argmax())
            return self.labels[i], float(p[i])
        low = text.lower()
        hits = {lab: len(re.findall(rx, low)) for lab, rx in LEXICON.items()}
        best = max(hits, key=hits.get)
        return (best, min(0.9, 0.45 + 0.15 * hits[best])) if hits[best] else ("neutral", 0.4)


class TextAnalyzer:
    def __init__(self, ter: TextEmotion):
        self.ter = ter

    def __call__(self, text: str, spoken_lang: Optional[str] = None) -> Analysis:
        low = text.lower().strip()
        a = Analysis(text=text, words=len(re.findall(r"\w+", text)), language=spoken_lang)
        a.emotion, a.emotion_conf = self.ter(text) if text.strip() else ("neutral", 0.0)
        a.cues = {c for c, rx in CUES.items() if re.search(rx, low)}
        if "laugh" in a.cues and a.emotion == "neutral":
            a.emotion, a.emotion_conf = "happy", 0.6
        a.topics = [t for t, rx in TOPIC_TAGS.items() if re.search(rx, low)]
        for code, rx in LANG_NAMES.items():
            if re.search(rx, low):
                a.mentioned_language = code
                break
        for rx in NAME_PATTERNS:
            m = re.search(rx, text, flags=re.IGNORECASE)
            if m and m.group(1).lower() not in NOT_NAMES:
                a.name = m.group(1).strip(".,!").capitalize()
                break
        if not a.name and 1 <= a.words <= 2 and text.strip()[:1].isupper() and not a.mentioned_language:
            a.name = re.findall(r"\w+", text)[0].capitalize()      # "Tomas." on its own
        return a
