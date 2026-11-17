import random

from beating_in_sync_app.brain.answers import answer
from beating_in_sync_app.brain.director import Director
from beating_in_sync_app.brain.modes import Act, Mode
from beating_in_sync_app.brain.user_model import UserModel
from beating_in_sync_app.brain.writer import TemplateWriter
from beating_in_sync_app.perception.fusion import Affect
from beating_in_sync_app.perception.text import TextAnalyzer, TextEmotion
from beating_in_sync_app.signals import Signals


analyze = TextAnalyzer(TextEmotion("/nonexistent"))


def test_real_room_questions_get_real_answers():
    # Questions people actually asked Reachy in the first room test.
    for q, intent in [("Can you hear me?", "hear"), ("Can you say hi?", "speak"), ("How do you feel?", "feel"),
                      ("¿Me escuchas?", "hear"), ("Who are you?", "who"), ("¿Cómo estás?", "feel"),
                      ("Can you see me?", "see"), ("Are you alive?", "alive")]:
        assert answer(q, "en")[1] == intent, q


def test_stage1_question_is_answered_then_back_to_script(cfg):
    d, w, user = Director(cfg, random.Random(0)), TemplateWriter(random.Random(0)), UserModel()
    ana = analyze("Can you hear me? Hi. Can you say hi?", "en")
    note = d.decide(1, 10, Signals(), 0, ana, Affect(), user)
    assert note.act == Act.ANSWER
    line = w.write(note, user, {"text": ana.text}, [], {})
    assert "hear you" in line.speech and "heart that woke me" in line.speech


def test_stage2_question_answered_and_name_still_asked(cfg):
    d, w, user = Director(cfg, random.Random(0)), TemplateWriter(random.Random(0)), UserModel()
    ana = analyze("How do you feel today?", "en")
    note = d.decide(2, 10, Signals(), 0, ana, Affect(), user)
    line = w.write(note, user, {"text": ana.text}, [], {})
    assert note.act == Act.ANSWER and "name" in line.speech


def test_smile_is_noticed_out_loud_once_in_a_while(cfg):
    d, w, user = Director(cfg, random.Random(0)), TemplateWriter(random.Random(0)), UserModel(name="Ana")
    smiling = Signals(face_visible=True, face_emotion="happy", face_conf=0.7)
    note = d.decide(3, 100, smiling, 0, analyze("I love music from my country", "en"), Affect(), user)
    assert note.act == Act.FACE and note.face == "happy"
    assert "smil" in w.write(note, user, None, [], {}).speech.lower()
    again = d.decide(3, 110, smiling, 0, analyze("yes I do", "en"), Affect(), user)
    assert again.act != Act.FACE                                  # 35 s cooldown


def test_sad_face_gets_sincere(cfg):
    d = Director(cfg, random.Random(0))
    note = d.decide(3, 100, Signals(face_emotion="sad", face_conf=0.8), 0, analyze("I am fine", "en"),
                    Affect("sad", 0.8, -0.7, 0, "face"), UserModel())
    assert note.act == Act.FACE and note.mode == Mode.SINCERE


def test_question_beats_persona_move_and_finger_nudge(cfg):
    # From the room: "In which language were we speaking before?" got a scold; must be answered.
    d, user = Director(cfg, random.Random(0)), UserModel(name="Dylan", language="es")
    d.decide(4, 10, Signals(finger_on=False), 0, analyze("hola", "es"), Affect(), user)
    note = d.decide(4, 30, Signals(finger_on=False), 0, analyze("In which language were we speaking before?", "en"),
                    Affect(), user)
    assert note.act == Act.ANSWER


def test_room_complaints_have_answers():
    for q, intent in [("Why are you talking in English?", "language_complaint"),
                      ("So now you're being mean to us", "mean"), ("Answer something to me", "answer_me"),
                      ("I have already repeated my name three times", "repeat_name")]:
        assert answer(q, "es")[1] == intent


def test_third_person_name():
    assert analyze("he's saying that his name is Dylan", "en").name == "Dylan"
