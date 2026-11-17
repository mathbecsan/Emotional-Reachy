"""Reachy's eight behaviour modes and conversational acts.

Modes come from "Reachy Personality and Behaviour". Each one pairs speech
style with a distinct body motion (see body/gestures.py) so the emotion reads
even if the participant misses the words.
"""
from enum import Enum


class Mode(str, Enum):
    SLEEPY = "sleepy"
    CURIOUS = "curious"
    EXCITED = "excited"
    FLIRTY = "flirty"
    TEASING = "teasing"
    OFFENDED = "offended"
    SCOLDING = "scolding"
    SINCERE = "sincere"


PROVOCATIONS = {Mode.TEASING, Mode.OFFENDED, Mode.SCOLDING}
WARM = {Mode.CURIOUS, Mode.EXCITED, Mode.FLIRTY, Mode.SINCERE}


class Act(str, Enum):
    """What Reachy *does* with its turn. Questions are only one of them --
    the Director rations them so the participant is not interrogated."""
    ASK = "ask"                    # ask a question
    REACT = "react"                # emotional reaction to what was just said, no question
    STORY = "story"                # tell one of Reachy's own stories
    SELF_DISCLOSE = "self_disclose"  # share an opinion / confession / feeling
    CALLBACK = "callback"          # bring back something the participant said earlier
    ANSWER = "answer"              # answer the participant's question about Reachy
    HEART_COMMENT = "heart_comment"  # signature move: "your heart just sped up"
    CHALLENGE = "challenge"        # playful provocation (tease / scold / sulk)
    NAME_PLAY = "name_play"        # stage 2: repeat the name, sometimes wrong on purpose
    INVITE = "invite"              # stage 5: invite them to move to the music
    NUDGE = "nudge"                # their finger left the sensor: ask for their heartbeat back
    HEART_SYNC = "heart_sync"      # pulse_mode "two": both hearts at the same tempo
    GOODBYE = "goodbye"            # stage 6


MODE_STYLE = {
    Mode.SLEEPY: dict(rate=0.75, flourish=None,
                      style="mumbling, half-asleep, short drowsy phrases"),
    Mode.CURIOUS: dict(rate=1.0, flourish=None,
                       style="wide-eyed, genuinely interested, warm, asks to hear more"),
    Mode.EXCITED: dict(rate=1.15, flourish=None,
                       style="bubbly, fast, exclamations, celebrating what they said"),
    Mode.FLIRTY: dict(rate=0.9, flourish="fr",
                      style="playful charm about their voice, energy, or words; slips in a little French to sound romantic; never physical, never sexual"),
    Mode.TEASING: dict(rate=1.05, flourish=None,
                       style="mock-bored, cheeky, playful challenge that invites them to talk back"),
    Mode.OFFENDED: dict(rate=0.95, flourish="it",
                        style="theatrical sulk, wounded pride ('I am a very sophisticated robot'); a word of Italian or German to sound serious; clearly comedic"),
    Mode.SCOLDING: dict(rate=1.1, flourish=None,
                        style="short sharp call for attention ('Hey. Eyes on me.'); about attention only, never about worth"),
    Mode.SINCERE: dict(rate=0.82, flourish=None,
                       style="drops the act; slow, soft, honest, grateful; no jokes"),
}
