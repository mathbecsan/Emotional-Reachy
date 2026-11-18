"""Activities Reachy can lead during a session, and the tone settings.

Each activity has an instruction for the live agent (handed over at a persona
switch, in that persona's style) and a line for the offline loop.
"""
ACTIVITIES = {
    "music_dance": {"label": "Music & dance", "icon": "♫", "text": "A song in their language, then a dance together.",
                    "agent": "Invite them to dance with you: call dance, and dare them to copy your moves.",
                    "line": "Okay, music time. Show me your best move. I'll go first!"},
    "sing": {"label": "Sing a song", "icon": "🎤", "text": "Reachy makes up a tiny song about them.",
             "agent": "Sing a tiny made-up song (four short lines) about something they told you, then ask them to rate it.",
             "line": "I wrote you a song. La la la, you are my favourite human, la la. Rate it, one to ten?"},
    "story": {"label": "Tell a story", "icon": "📖", "text": "A very short story in the current personality.",
              "agent": "Tell a very short story (three sentences) in your current personality, then ask what they would have done.",
              "line": "Story time. Once, a robot fell asleep in a museum and woke up as art. What would you have done?"},
    "guess": {"label": "Guessing game", "icon": "?", "text": "Reachy guesses things about them from their answers.",
              "agent": "Play a guessing game: make three playful guesses about them (favourite food, hidden talent, morning or night person) and ask if you're right.",
              "line": "Guessing game! You're a night person who secretly loves cereal. Am I right?"},
    "mirror": {"label": "Copy my moves", "icon": "↔", "text": "Reachy does a gesture and they copy it, then swap.",
               "agent": "Play copy-my-moves: do a gesture (call reachy_gesture), ask them to copy it, then ask them to invent one for you.",
               "line": "Copy me! Head tilt, like this. Now you invent one for me."},
    "heart": {"label": "Heartbeat challenge", "icon": "♥", "text": "Reachy tries to make their heart beat faster.",
              "agent": "Heartbeat challenge: tell them you'll try to make their heart beat faster with one surprising compliment or a dramatic reveal, then ask if it worked.",
              "line": "Heartbeat challenge. I'm going to make your heart race. You have the best laugh in this building. Did it work?"},
}

TONES = {
    "warm": "Overall tone: warm and gentle, even inside the off-brand personalities.",
    "playful": "Overall tone: playful and cheeky.",
    "bold": "Overall tone: bold and theatrical: commit fully to each personality.",
}
CHATTINESS = {
    "brief": "Keep replies very short: one sentence, under 15 words.",
    "normal": "",
    "chatty": "You may use up to three sentences when telling something, but still end with a question.",
}
DURATIONS = {"quick": 240, "standard": 480, "long": 720}   # seconds of conversation


def style_prompt(tone: str, chattiness: str, activities: list[str]) -> str:
    parts = [TONES.get(tone, ""), CHATTINESS.get(chattiness, "")]
    acts = [ACTIVITIES[a]["label"] for a in activities if a in ACTIVITIES]
    if acts:
        parts.append("Activities in this session (the Director will tell you when): " + ", ".join(acts) + ".")
    return "\n".join(p for p in parts if p)


def switch_every_for(duration: str | None, cast_len: int, seconds_per_exchange: float = 13) -> int | None:
    if duration not in DURATIONS:
        return None
    return max(2, min(8, round(DURATIONS[duration] / max(1, cast_len) / seconds_per_exchange)))
