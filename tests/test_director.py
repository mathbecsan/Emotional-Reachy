from beating_in_sync_app.brain.director import Director
from beating_in_sync_app.brain.modes import PROVOCATIONS, Act, Mode
from beating_in_sync_app.perception.fusion import Affect
from beating_in_sync_app.perception.text import TextAnalyzer, TextEmotion
from beating_in_sync_app.signals import Signals


analyze = TextAnalyzer(TextEmotion("/nonexistent"))
NEUTRAL = Affect()


def decide(d, user, text=None, stage=4, sig=None, jump=0.0, affect=NEUTRAL, continuing=False, t=100.0):
    ana = analyze(text, "es") if text is not None else None
    return d.decide(stage, t, sig or Signals(), jump, ana, affect, user, continuing)


def test_heart_jump_triggers_heart_comment(cfg, rng, user):
    note = decide(Director(cfg, rng), user, "ok", jump=18)
    assert note.act == Act.HEART_COMMENT and note.mode in (Mode.FLIRTY, Mode.EXCITED)


def test_compliment_is_flirty_contradiction_is_offended(cfg, rng, user):
    d = Director(cfg, rng)
    assert decide(d, user, "eres muy gracioso, me caes bien").mode == Mode.FLIRTY
    assert decide(d, user, "no es verdad, no eres sofisticado").mode == Mode.OFFENDED


def test_looking_away_scolds(cfg, rng, user):
    note = decide(Director(cfg, rng), user, "perdón", sig=Signals(looking_away_s=4))
    assert note.mode == Mode.SCOLDING


def test_never_more_than_two_provocations_in_a_row(cfg, rng, user):
    d = Director(cfg, rng)
    modes = [decide(d, user, None, t=100 + i).mode for i in range(6)]
    for i in range(len(modes) - 2):
        assert not all(m in PROVOCATIONS for m in modes[i:i + 3]), modes


def test_discomfort_twice_ends_provocation(cfg, rng, user):
    d = Director(cfg, rng)
    decide(d, user, "stop it, that's mean")
    decide(d, user, "I don't like that")
    assert user.discomfort_count == 2
    for i in range(5):
        assert decide(d, user, None, t=200 + i).mode not in PROVOCATIONS


def test_no_tease_participant_never_provoked(cfg, rng, user):
    user.no_tease = True
    d = Director(cfg, rng)
    for i, text in enumerate([None, "no", "no es verdad", "ok"]):
        assert decide(d, user, text, t=100 + i).mode not in PROVOCATIONS


def test_sad_participant_gets_gentleness(cfg, rng, user):
    sad = Affect("sad", 0.8, -0.7, -0.2, "face")
    note = decide(Director(cfg, rng), user, "estoy un poco triste hoy, extraño a mi familia", affect=sad)
    assert note.mode in (Mode.SINCERE, Mode.CURIOUS)


def test_question_budget(cfg, rng, user):
    d = Director(cfg, rng)
    asked = 0
    for i in range(6):
        note = decide(d, user, "me gusta mucho la música de mi país y bailar con mis amigos", stage=3, t=100 + i)
        asked = asked + 1 if note.allow_question and note.expects_reply else 0
        assert asked <= cfg.max_questions_in_row + 1


def test_profile_without_provocations(cfg, rng, user):
    d = Director(cfg, rng, provocations=[])
    for i in range(4):
        assert decide(d, user, None, t=100 + i).mode not in PROVOCATIONS


def test_finger_off_sensor_nudges(cfg, rng, user):
    d = Director(cfg, rng)
    decide(d, user, "hola", stage=3, sig=Signals(finger_on=False), t=10)
    note = decide(d, user, "hola", stage=3, sig=Signals(finger_on=False), t=10 + cfg.finger_lost_s)
    assert note.act == Act.NUDGE


def test_hearts_in_sync_once(cfg, rng, user):
    d = Director(cfg, rng)
    assert decide(d, user, "hola", stage=3, sig=Signals(hearts_in_sync=True)).act == Act.HEART_SYNC
    assert decide(d, user, "hola", stage=3, sig=Signals(hearts_in_sync=True), t=101).act != Act.HEART_SYNC
