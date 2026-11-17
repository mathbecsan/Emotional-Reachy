from beating_in_sync_app.brain.safety import is_stop, violates
from beating_in_sync_app.perception.fusion import fuse
from beating_in_sync_app.perception.text import TextAnalyzer, TextEmotion
from beating_in_sync_app.session import clean_love


analyze = TextAnalyzer(TextEmotion("/nonexistent"))


def test_extracts_name_and_language():
    assert analyze("My name is Tomas").name == "Tomas"
    assert analyze("me llamo Lucía").name == "Lucía"
    assert analyze("I feel most like myself in Spanish").mentioned_language == "es"


def test_cues():
    assert "compliment" in analyze("you're so funny").cues
    assert "contradiction" in analyze("No, it's Tomas!").cues
    assert "contradiction" not in analyze("No sé").cues
    assert "discomfort" in analyze("please stop it, that's mean").cues
    assert "laugh" in analyze("jajaja").cues


def test_red_lines():
    assert violates("You have a gorgeous face") == "appearance"
    assert violates("Your heart rate means you have arrhythmia") == "health-claim"
    assert violates("You're an idiot") == "insult"
    assert violates("Hey. Eyes on me. I'm talking.") is None
    assert violates("Good night, time to go back to bed.") is None


def test_stop_word():
    assert is_stop("pause", ("pause", "stop"))
    assert is_stop("Pause please", ("pause",))
    assert not is_stop("I paused my music yesterday to come here", ("pause",))


def test_fusion_agreement_boosts():
    a = fuse("happy", 0.7, "happy", 0.6, 0.0)
    assert a.label == "happy" and a.conf > 0.6 and a.valence > 0
    assert fuse(None, 0, None, 0, 20).arousal > 0


def test_clean_love():
    assert clean_love("Me encanta cocinar las recetas de mi abuela, sobre todo los tamales") == "cocinar las recetas de mi abuela"
