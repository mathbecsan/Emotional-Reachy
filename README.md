# Beating in Sync — Emotional Reachy

A Reachy Mini that hears your heart. Over a 15-minute session it wakes up when
your heartbeat touches it, gets to know you in your own language, tells you its
own stories, teases, flirts and sulks on cue from your words, your face, where
you look and your pulse, then drops the act, says something sincere and goes
back to sleep. Your heartbeat is then played back as colour and waves.

Built from the team's three design docs (Interaction Protocol, Interview Guide,
Reachy Personality and Behaviour), structured like
[pollen-robotics/reachy_mini_conversation_app](https://github.com/pollen-robotics/reachy_mini_conversation_app),
with emotion recognition from
[kudosscience/fer_and_ter_model](https://github.com/kudosscience/fer_and_ter_model)
and [introlab/emotion_recognition](https://github.com/introlab/emotion_recognition),
and the pulse sensors / beat detection from the cs334_project
(`pulse_double/pulse_double.ino`, `pulse_double/pulse_triple.py`).

## Quick start

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[robot,sensor]"          # add ,vision / ,mic / ,text-emotion as needed
cp .env.example .env                       # put ANTHROPIC_API_KEY in it
beating-in-sync                            # web UI at http://localhost:7860, simulated robot
```

| Run | Command |
|---|---|
| Rehearse in the browser, no hardware | `beating-in-sync` → Start session (Heart: Simulated) |
| Real pulse sensors + real Reachy | `beating-in-sync --robot` → Heart: Arduino pulse sensors |
| Check the beat pipeline without sensors | Heart: *Arduino pipeline, simulated signal* |
| Terminal only, typed participant | `beating-in-sync --headless --listener console` |
| Automated scripted participant | `beating-in-sync --headless --no-llm --scenario scenarios/demo_participant.json --scale 30` |
| **Room preflight** (daemon, Arduino, Claude key) | `beating-in-sync --check` |
| Find the Arduino's port | `beating-in-sync --list-ports` |
| As a Reachy Mini app (dashboard) | installed via the `reachy_mini_apps` entry point `BeatingInSyncApp` |

## Live conversation (default)

Stages 1-4 run as one **realtime conversation with an ElevenLabs Agent** — the same
shape as Pollen's conversation app: realtime speech in and out, a personality
profile, and tools that move the robot.

- The agent is created automatically on first run from `profiles/<name>/profile.md`
  + the fixed safety rules (ids cached in the git-ignored `.agent_cache.json`; edit
  the profile and a new agent is made). LLM: `claude-sonnet-4-6` inside ElevenLabs
  (`BIS_AGENT_LLM` to change), voice `eleven_v4_turbo` with Callum.
- It listens continuously through Reachy's mic, answers anything, asks its own
  questions, switches language when asked, and speaks from Reachy's speaker (mic muted
  while it talks so it never hears itself).
- It moves Reachy by calling `express(mode)` / `dance()`. The Director vetoes moves
  that break the rules (teasing an opted-out participant, three provocations in a row,
  provoking after discomfort) and tells the agent why.
- The Director feeds it what Reachy senses as silent context: heart jumps, faces,
  looking away, finger off the sensor, and each stage's goal (stage 4 lists the
  persona moves allowed for this participant). The stop word still stops everything.
- Stages advance on the protocol's timings and on what Reachy learned (name and
  language → stage 3; five turns → stage 4; three persona moves → music).
- If the live agent is unavailable, the session falls back to the scripted Director
  mode automatically. Choose "Scripted" in the start form to force it.

## Voice and hearing (ElevenLabs)

Put `ELEVENLABS_API_KEY=...` in `.env` (never commit it). Reachy then speaks with
ElevenLabs' multilingual low-latency model (`eleven_flash_v2_5`, voice "Callum —
Husky Trickster", override with `ELEVENLABS_VOICE_ID`) **through its own speaker**
(the "Reachy Mini Audio" device), and hears through its own mic with ElevenLabs
Scribe, which also detects the language. The noise floor is measured before every
listen, so Reachy's fan doesn't trigger it. Lines typed in the UI work alongside the
mic. Without a key: macOS voice + typed input.

## The room setup (hardware)

1. **Reachy Mini**: daemon running (`reachy-mini-daemon`), motors powered. If the
   status shows a motor error after fixing power, `curl -X POST localhost:8000/api/daemon/restart`. Check
   `curl localhost:8000/api/daemon/status` reports no error.
2. **Pulse sensors**: Arduino Nano with two MAX30102 sensors (red lights on all
   three boards), plugged in by USB. Firmware is already on the Nano; it prints
   `ir1,ir2` per sample at 115200 baud. Sensor 1 = A4/A5, sensor 2 = D4/D5.
3. **Close `pulse_triple.py` and the Arduino IDE serial monitor** — only one
   program can read the port. The web UI shows both sensors' waveforms, so you
   don't need the pygame windows during a session.
4. Port: leave on *auto-detect* (it only accepts a free port that is actually
   streaming `ir1,ir2`, and never touches the Reachy daemon's port) or pick it.

### How the two sensors drive the session (`BIS_PULSE_MODE`)

- **one** (default): a finger on either sensor -> once a pulse locks, Reachy starts
  **snoring** while the 60 s baseline is recorded, then wakes up and starts talking.
- **wake**: stage 0, the participant rests one finger on **sensor 1**
  for the 60 s baseline. Stage 1, the UI prompts them to **press sensor 2** —
  that pulse is what wakes Reachy. After that BPM is the mean of both sensors.
- **two**: sensor 2 is a second person. Both fingers on → two people in the room
  (Reachy flirts with one to make the other jealous) and, if both hearts settle
  within 3 BPM, Reachy has its *"you're beating in sync"* moment.

If the participant lets go of the sensors for 6 s mid-conversation, Reachy asks
for their heartbeat back.

## How Reachy decides what to do

Every turn: **sense → decide → write → move + speak → listen**.

- **Senses** (`perception/`): heart (baseline, +15 BPM jumps, flat stretches,
  130 BPM safety stop), camera (FER emotion with the kudosscience CNN, looking
  away, number of people, dancing), words (DistilBERT TER or a multilingual
  lexicon; compliments, contradictions, laughter, discomfort, questions; name,
  language, "something you love"). Face and text are fused 0.6/0.4 as in the
  kudosscience fusion; heart adds arousal.
- **Director** (`brain/director.py`) picks the **mode** (Sleepy, Curious,
  Excited, Flirty, Teasing, Offended, Scolding, Sincere) and the **act**:
  ask, react, tell a story, share a confession, call back something you said,
  answer your question, comment on your heart, provoke, nudge, invite you to
  dance, say goodbye. It enforces the Personality doc's rules in code: at most
  2 provocations in a row, discomfort twice ends provocation, sad/scared
  participants get gentleness, no teasing for participants who opted out — and
  **at most 2 questions in a row**, so Reachy tells and reacts instead of
  interrogating. Silence is answered with a story, not another question.
- **Writer** (`brain/writer.py`): Claude (`claude-opus-5-5`, low effort, structured
  output) writes the line in the participant's language from the Director's
  brief, the user model and the conversation. Offline templates take over if
  there is no API key, the call fails, or a line crosses a red line
  (`brain/safety.py`: appearance, sexual content, insults, mocking language,
  health claims from the heartbeat).
- **Body** (`body/`): one keyframe gesture per mode (lean-in, nose-up turn
  away, snap back…) plus recorded emotions from the Pollen emotions library,
  `wake_up()` / `goto_sleep()` from the SDK, dancing in stage 5.

Personalities live in `profiles/<name>/profile.md` (TOML front matter + persona
prompt). `gentle` has no provocation stage. The safety rules are appended to
every profile and can't be edited away.

## Off-Brand Reachy (persona interview)

From "Off-Brand Reachy: Persona Script & App Spec": Reachy interviews the
participant and slips between personas a cute robot "shouldn't" have, all in
one voice, so it feels like one robot losing control of its personality.

- **Cast** (`src/beating_in_sync_app/brain/personas.py`, the single source of truth):
  Base Reachy, Bored teenager, Burned-out employee, Noir detective, Diva
  celebrity, Hype-bro life coach, Villain, Tía chismosa, Hypochondriac, plus
  idea-bank personas (Very flirty, Jealous, Smug, Passive-aggressive, Grumpy,
  Melodramatic). Each has its goal, delivery, bridges, questions, reactions with
  the participant's own words, silence and barge-in lines, camera reactions and gestures.
- **Gestures**: the spec's 33 `express` gestures (eye roll, hat brim, hair flip,
  twirl, villain rise…) are in `body/gestures.py`, clamped to the SDK ranges.
- **Profile** `profiles/off_brand_reachy/profile.md` (`kind = "personas"`). The
  live agent gets the session's cast as a dynamic variable, so changing the cast
  never rebuilds the agent; tools `reachy_gesture`, `reachy_switch_persona`, `dance`.
- **The Director** counts exchanges and tells the agent when to glitch into the
  next persona (as a `[Director]` turn: live tests showed contextual updates alone
  are ignored for this), switches after ~11 s of silence, and closes as Base Reachy
  with the debrief line. "Reachy, reset", "that's not funny" or a discomfort cue
  sends Reachy back to Base at once; a second discomfort cue drops every teasing persona.
- Works offline too (scripted conversation): the same cast speaks its scripted lines.

## Facilitator UI

- **Build session**: pick the script (Off-Brand Reachy, Beating in Sync, Gentle),
  choose which personalities take part and their order (drag, arrows, add/remove;
  Base Reachy always opens and closes), exchanges per persona, heartbeat wake-up
  on/off, music on/off, no-teasing, and the hardware. Save it as a **preset**
  (`presets/*.json`) to repeat a test condition exactly; four presets ship with the repo.
  For Beating in Sync the personalities are the stage-4 persona moves (Flirty,
  Teasing, Offended, Scolding).
- **Personalities**: the catalog, filterable, with each persona's script and a
  "Try a gesture" button that moves the robot.
- **Live**: in persona sessions a strip shows the cast (done / now / next); click
  a persona to jump to it, or use Next persona, Reset to Base, Close interview.
  Also: stage strip with protocol countdown, Reachy's mode/act and *why*,
  heart chart (baseline band, stage bands, a dot per Reachy turn, ringed when
  the heart triggered it), both pulse sensors, conversation log with detected
  emotion and cues, what Reachy knows, and controls: Next stage, Scold now
  (if the camera attention check is unreliable), **Pause** (= the stop word:
  sincere goodbye, sleep). Participant lines can be typed (rehearsal / Wizard-of-Oz)
  or come from the microphone.
- **Sessions**: replay with the moves the participant actually saw (for the
  post-interview) and which reactions came from their heartbeat (for the debrief);
  persona sessions list each persona with replies, laughs and peak BPM, and resets.
- **Projection**: stage 7 — the heartbeat as colour and waves, full screen (F).

## Safety (from the protocol)

The stop word **"pause"**, the Pause button, or BPM above 130 for 30 s stop the
act immediately; stage 6 (sincere goodbye) always runs. Participants who'd
rather not be teased skip stage 4. Any internal error also ends in the goodbye.

## Session data

`sessions/<time>_<participant>.jsonl`: every heart sample, stage change,
utterance (with language, emotion, cues), turn (mode, act, reason, line, source)
and facilitator command.

## Development

```bash
pip install -e . pytest httpx ruff
ruff check src tests && pytest -q
```

Layout: `src/beating_in_sync_app/` (`main.py`, `runtime.py`, `session.py`,
`web.py`, `events.py`, `perception/`, `brain/`, `body/`, `static/`),
`profiles/`, `scenarios/`, `tests/`. Architecture: `docs/scheme.mmd`.
Tunable numbers: `config.py` (override with `BIS_<FIELD>` env vars).

Stage 5 music: put one file per language in `assets/music/<lang>.mp3`
(plus `default.mp3`).
