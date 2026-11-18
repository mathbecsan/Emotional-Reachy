# How to run a Beating in Sync session

A guide for anyone running the study with Reachy Mini: setting up, running a
session with a participant, and checking the results. No coding needed.

---

## What happens in a session

1. Reachy is asleep. The participant rests a finger on a **pulse sensor**.
2. Reachy hears the heartbeat, **snores** for about a minute while it learns the
   participant's resting heart rate, then **wakes up**.
3. Reachy talks with the participant. In the *Off-Brand Reachy* experience it
   slips between **personalities** (a bored teenager, a noir detective, a
   hype-bro…), reacting to what the participant says, their face and their heart.
4. Reachy closes as its friendly self, says goodbye, and goes back to sleep.
5. Everything is saved, so you can replay the session afterwards.

---

## What you need

| Thing | What it's for |
|---|---|
| Reachy Mini, plugged in by USB | The robot: moves, speaks, listens, sees |
| The pulse sensors (Arduino Nano + 2 sensors), plugged in by USB | Reads the heartbeat |
| A Mac with this project installed | Runs the app, the "brain" |
| Internet (Wi-Fi) | Reachy's voice and hearing (ElevenLabs) |
| The `.env` file with the ElevenLabs key | Ask the project team; it's never shared publicly |

---

## Every time: start everything (2 minutes)

There are **three pieces**, and they start in this order:

1. **Reachy's robot software (the daemon):** open **Reachy Mini Control** and turn
   the robot on. Reachy should stiffen and hold its head up.
2. **The app:** open **Terminal** and run these two commands. The first goes to
   the project folder; replace the path with where the project is on your Mac.
   ```bash
   cd path/to/Emotional-Reachy
   ```
   ```bash
   .venv/bin/beating-in-sync --robot
   ```
   Leave this Terminal window open for the whole session. Closing it stops Reachy.
3. **The web page:** open **http://localhost:7860** in Chrome.

> The web page is only the control panel. If you open it in two windows, they show
> the same thing. What matters is that the app (step 2) is running.

---

## The four steps in the web page

The bar at the top always shows where you are:
**1 Check setup → 2 New session → 3 Session → 4 Results**.
The coloured dots at the top right (**Reachy · Sensors · Voice**) are green when
that part is ready. Click them to open Check setup.

### 1 · Check setup (before every participant)

Each row tests one part. Green means ready; red tells you what to do.

| Row | Press | You should see |
|---|---|---|
| **Reachy** | *Connect Reachy*, then *Test movement* | Reachy nods |
| **Pulse sensors** | *Test sensors*, then rest a finger on each sensor | "Finger detected" and a heart rate after about 5 s |
| **Speaker** | *Play a hello* | Reachy says hello out loud |
| **Microphone** | *Record 4 seconds*, then speak | What you said, written out |
| **Camera** | *Test camera*, sitting in front of Reachy | "1 face in view" |
| **Voice service** | (automatic) | "Connected" and characters left |

Then press **Next: New session**.

### 2 · New session (a 4-step wizard)

1. **Experience:** choose the kind of interaction.
   - **Off-Brand Reachy**: a short interview where Reachy keeps glitching between personalities.
   - **Beating in Sync**: the original 15-minute protocol (stages 0–7).
   - **Gentle**: Beating in Sync without any teasing.
   - Or click a **saved setup** to load everything in one go.
2. **Personalities:** who Reachy becomes, and in what order.
   - Tap a card on the right to add it. Use ↑ ↓ (or drag) to reorder, × to remove.
   - *Base Reachy* always opens and closes, and is where Reachy returns after a reset.
   - Cards marked **teases** are skipped if the participant doesn't want to be teased.
   - *About each personality ↗* shows each one's lines and gestures, with a button to try a gesture on Reachy.
3. **Behaviour:** how Reachy acts.
   - **Size of gestures**: Subtle, Gentle, Normal or Dramatic.
   - **Speed of gestures**: Slow, Normal or Fast.
   - **Switch personality every**: how many replies before the next personality.
   - **Teasing allowed**, **Wake up with a heartbeat**, **React to the face** (camera), **Music and dance**.
4. **Start:** type the **participant ID** (for example `P07`), check the summary,
   and press **Start session**. *Save setup* stores these choices under a name,
   so every participant in a study condition gets exactly the same session.

### 3 · Session

- **At the start:** the status says *"Asleep · ask the participant to rest a finger on a pulse sensor"*.
- **Once the pulse is found:** it changes to *Snoring*, and then Reachy wakes up.
- **During the conversation:**
  - The **Personality now** strip shows who Reachy is and who comes next. Click a name to jump to it.
  - **Next personality**: glitch into the next one now.
  - **Reset to Base**: back to friendly Reachy for the rest of the session.
  - **Close interview**: Reachy wraps up and says goodbye.
  - **End session**: stop at any time. Reachy says a kind goodbye and sleeps.
- **The participant can always say "Reachy, reset"** to bring back friendly Reachy.
  Saying "that's not funny", or showing discomfort, does the same automatically.

### 4 · Results

Pick a session to replay it: the conversation, the heart-rate graph, which
personality was on when the heart rate rose, laughs, and any resets. *Project*
shows the heartbeat as a full-screen visual for the end of the experience.

---

## Debug mode (for the team)

Switch **Debug** on (top right) to see the technical side:

- the stage timeline, the live heart chart and both sensor waveforms;
- why Reachy chose each reaction, and what it knows about the participant;
- the simulators: a fake finger or heartbeat, a fake face, typing as the participant;
- in **New session → Start**, the hardware options. For example, a *simulated
  heart* lets you rehearse without the sensors, and *typed only* lets you rehearse
  without speaking.

Switch it off again before a participant sits down.

---

## When something goes wrong

| What you see | What to do |
|---|---|
| Reachy talks but doesn't move | The robot software stopped. Turn the robot on in **Reachy Mini Control**, then **Check setup → Connect Reachy**. |
| Finger on the sensor, nothing happens | **Check setup → Test sensors.** "No data" or "Sensor 1 not found" means a loose wire: check SDA→A4, SCL→A5, power and ground, then unplug and replug the Arduino's USB. |
| "Finger detected" but no heart rate | Press more lightly and keep still. Cold fingers take longer. |
| Reachy doesn't hear the participant | **Check setup → Record 4 seconds.** Speak closer to Reachy. |
| No voice at all | Check the Wi-Fi, then **Check setup → Voice service**. |
| The page says "offline" | The app isn't running: start it again (step 2 above). |
| A session seems stuck | **End session**, then start a new one. Nothing is lost: the log is saved. |

---

## Safety and ethics (from the study protocol)

- Tell participants before they start that Reachy will change personalities and
  act rude or strange **on purpose**, and that **"Reachy, reset"** stops it at once.
- Teasing targets answers only, never appearance, identity or anything personal.
- If the heart rate stays very high (above 130 BPM for 30 s), the session stops by itself.
- At the end, Reachy says: *"None of that was real. You were a great sport."*
- Session logs contain what participants said. Keep the `sessions/` folder
  private; it is never uploaded to GitHub.
