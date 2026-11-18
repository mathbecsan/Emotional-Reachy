"""Profiles: `profiles/<name>/profile.md` = TOML front matter (+++) + persona prompt.

Same convention as reachy_mini_conversation_app. The persona is editable;
the safety rules and the Director contract (brain/prompts.py) are not, and
are always appended after it.
"""
import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"


@dataclass
class Profile:
    name: str
    display_name: str
    description: str
    prompt: str
    accent: str = "#ff5a6e"
    provocations: list[str] = field(default_factory=lambda: ["teasing", "offended", "scolding"])
    flirt_with_two_people: bool = True
    kind: str = "modes"              # modes (Beating in Sync Director) | personas (Off-Brand cast)
    personas: list[str] = field(default_factory=list)   # default cast / selectable persona moves
    switch_every: int = 5            # personas: exchanges before glitching into the next one
    music: bool = True               # stage 5 dance by default


def list_profiles(extra_dir: Path | None = None) -> list[str]:
    dirs = [PROFILES_DIR] + ([extra_dir] if extra_dir else [])
    return sorted({p.parent.name for d in dirs if d.is_dir() for p in d.glob("*/profile.md")})


def load_profile(name: str, extra_dir: Path | None = None) -> Profile:
    for d in ([extra_dir] if extra_dir else []) + [PROFILES_DIR]:
        path = d / name / "profile.md"
        if path.exists():
            break
    else:
        raise FileNotFoundError(f"profile '{name}' not found in {PROFILES_DIR}")
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    if text.startswith("+++"):
        _, front, text = text.split("+++", 2)
        meta = tomllib.loads(front)
    logger.info("Loaded profile %s from %s", name, path)
    return Profile(
        name=name,
        display_name=meta.get("display_name", name),
        description=meta.get("description", ""),
        prompt=text.strip(),
        accent=meta.get("accent", "#ff5a6e"),
        provocations=list(meta.get("provocations", ["teasing", "offended", "scolding"])),
        flirt_with_two_people=bool(meta.get("flirt_with_two_people", True)),
        kind=meta.get("kind", "modes"),
        personas=list(meta.get("personas", [])),
        switch_every=int(meta.get("switch_every", 5)),
        music=bool(meta.get("music", True)),
    )


MODE_PERSONALITIES = ["flirty", "teasing", "offended", "scolding"]   # selectable persona moves (stage 4)


def selectable(profile: Profile) -> list[str]:
    """Personalities a facilitator can switch on or off for this profile."""
    if profile.kind == "personas":
        from .brain.personas import PERSONAS

        return list(PERSONAS)
    return MODE_PERSONALITIES


def default_selection(profile: Profile) -> list[str]:
    if profile.kind == "personas":
        from .brain.personas import DEFAULT_ORDER

        return profile.personas or DEFAULT_ORDER
    return (["flirty"] if profile.flirt_with_two_people or profile.provocations else []) + profile.provocations
