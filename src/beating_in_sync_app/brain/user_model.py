"""What Reachy remembers about this participant during the session.
Used for callbacks ("you said you love your grandmother's tamales...") and
for the sincere goodbye, which should feel specific to *them*."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class UserModel:
    name: Optional[str] = None
    name_confirmed: bool = False
    said_name_wrong: bool = False
    language: str = "en"               # language Reachy should speak
    language_confirmed: bool = False
    languages_heard: set = field(default_factory=set)
    loves: list = field(default_factory=list)      # "something you love that most people don't know"
    facts: list = field(default_factory=list)      # short notes (from LLM memory_notes or rules)
    topics: list = field(default_factory=list)
    no_tease: bool = False              # pre-interview: would rather not be teased
    discomfort_count: int = 0
    laughed: int = 0
    compliments_given: int = 0
    total_words: int = 0
    turns: int = 0
    silences: int = 0
    affect_history: list = field(default_factory=list)   # (t, label, valence, arousal)
    heart_moments: list = field(default_factory=list)    # (t, stage, jump, what Reachy just did)
    danced: bool = False

    @property
    def avg_words(self) -> float:
        return self.total_words / self.turns if self.turns else 0.0

    def remember(self, note: str):
        note = note.strip()
        if note and note not in self.facts:
            self.facts.append(note)
            self.facts[:] = self.facts[-12:]

    def summary(self) -> dict:
        return {
            "name": self.name, "language": self.language, "loves": self.loves[-3:],
            "facts": self.facts[-8:], "topics": self.topics[-5:],
            "talkativeness": "chatty" if self.avg_words > 14 else "quiet" if self.avg_words and self.avg_words < 5 else "normal",
            "laughed": self.laughed, "discomfort_count": self.discomfort_count,
            "silences": self.silences, "danced": self.danced,
            "heart_moments": [f"stage {s}: +{j:.0f} BPM after Reachy was {w}" for _, s, j, w in self.heart_moments[-4:]],
        }
