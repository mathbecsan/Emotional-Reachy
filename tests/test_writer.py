import random

from beating_in_sync_app.brain.director import DirectorNote
from beating_in_sync_app.brain.modes import Act, Mode
from beating_in_sync_app.brain.user_model import UserModel
from beating_in_sync_app.brain.writer import ClaudeWriter, TemplateWriter, mangle_name
from beating_in_sync_app.config import Config
from beating_in_sync_app.personality import load_profile


def test_missing_credentials_fall_back_to_templates(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", "/nonexistent")
    notes = []
    w = ClaudeWriter(Config(), TemplateWriter(random.Random(0)), load_profile("beating_in_sync"))
    w.notify = notes.append
    note = DirectorNote(stage=6, mode=Mode.SINCERE, act=Act.GOODBYE, goal="", reason="")
    user = UserModel(name="Ana", language="es", loves=["bailar salsa"])
    for _ in range(2):
        line = w.write(note, user, None, [], {})
        assert line.source == "template" and "Ana" in line.speech and "Buenas noches" in line.speech
    assert len(notes) == 1          # warned once, then stays offline


def test_name_is_wrong_but_close():
    assert mangle_name("Tomas") != "Tomas" and mangle_name("Tomas")[:3] == "Tom"
