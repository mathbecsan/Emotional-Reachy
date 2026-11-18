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

## Finding your way in the web page

- **Start screen:** press any key, or tap, to open the **main menu**.
- **Main menu:** use ↑ ↓ (or the mouse) to choose, and Enter to open. The panel on
  the right explains each option and shows its status (for example *"Needs attention: Reachy"*).
- **The bar at the top** always shows where you are (for example *Main menu › New session › 4 · Voice & tone*)
  and whether **Reachy · Sensors · Voice** are ready (green dots). Click the dots to open the setup checklist.
- **Inside a step-by-step flow:** **Enter** = next, **Esc** = back. You can also click any step to jump to it.

### Setup checklist (before every participant)

Seven short screens that **unlock in order**: pass a step (or press *Skip*) to open the next one.
The map on the left shows each step's result: **✓** passed, **!** needs fixing, **–** skipped, 🔒 not yet unlocked.
Every screen says what is being tested, gives feedback straight away, and, if
something fails, explains what it means and what to try.

| Step | What you do | Passes when |
|---|---|---|
| **1 Connect Reachy** | Press *Connect Reachy*, watch it nod, answer *Yes* | Reachy nods |
| **2 Pulse sensors** | Rest a finger lightly on each sensor and keep still | A heart rate appears (about 5 s) |
| **3 Camera & gaze** | Watch yourself in the live picture; look at Reachy, turn your head away, look back. *Wrong camera?* shows each camera so you can pick Reachy's | All three ticks appear |
| **4 Microphone & sounds** | *Record speech* and say a sentence; *Record a performance* and clap a rhythm, sing, or play music | Reachy writes out what you said **and** names the performance (clapping, music or singing) |
| **5 Speaker** | *Play Reachy's voice*, answer whether you heard it clearly | You answer *Yes* |
| **6 Follow me** | Press *Start the game*. Reachy tells you out loud where to go (in front, your left, your right, back to the middle); the banner and the map show it too | Reachy turns to follow you through all four positions |
| **7 Range of motion** | Clear the space, press *Run every move* (or *Run* one group: head, expressions, height & lean, body, antennas) | You answer *Yes* after all 24 moves |

The **Summary** lists what's still needed. Reachy, sensors, microphone and speaker must pass before a real session.

- *Follow me* uses the camera: following a voice by sound alone isn't available yet.
- Reachy's body turns up to 150° each way. Its limit is 160°, so a full 360° turn isn't possible.

### New session (seven small screens)

1. **Experience:** *Off-Brand Reachy* (a short interview where Reachy glitches between personalities),
   *Beating in Sync* (the original 15-minute protocol) or *Gentle* (no teasing). Or load a **saved setup**.
2. **Personalities:**
   - Tap Reachy's costumes to add or remove them. The number on each card is its place in the **line-up** below, and the ‹ › buttons reorder it.
   - *Base Reachy* always opens and closes.
   - **Teasing allowed** off skips the personalities marked *teases*.
3. **Movement:** the size of gestures (Subtle → Dramatic) and their speed; whether Reachy follows the
   participant's face. *Try it on Reachy* shows the result on the robot.
4. **Voice & tone:** pick Reachy's voice (▶ plays a sample), the tone (Warm, Playful or Bold) and how much it talks.
5. **Length:** Quick (about 4 min), Standard (8) or Long (12). Reachy adjusts how long each personality
   lasts. **Wake up with a heartbeat** makes Reachy sleep and snore until a finger is on a sensor.
6. **Activities:** music & dance, a made-up song, a story, a guessing game, copy-my-moves, the
   heartbeat challenge. Reachy brings them up at personality switches, in that personality's style.
7. **Ready:** the cast on stage, a summary (each line has *Change*), the **participant ID**, then
   **▶ Start session**. *Save setup* stores everything under a name, so each study condition is identical.

### Current session

- **Performances:** if the participant claps, sings or plays music, Reachy notices it (not only words).
  During music it sways along without talking over it, then reacts to the performance in the current personality.

- The status says what Reachy is doing (*Asleep · ask the participant to rest a finger…*, *Snoring*, *In conversation*).
- The current personality appears as Reachy in costume.
- **Personality now** shows the line-up. Click a name to jump to it, or use **Next personality**, **Reset to Base** or **Close interview**.
- **End session** stops kindly at any time.
- The participant can always say **"Reachy, reset"**.

### Results

Replays: the conversation, the heart-rate graph, and how the participant reacted to each personality.

## Debug mode (for the team)

Switch **Debug** on (top right) to see the technical side:

- the stage timeline, the live heart chart and both sensor waveforms;
- why Reachy chose each reaction, and what it knows about the participant;
- the simulators: a fake finger or heartbeat, a fake face, typing as the participant;
- on the **Ready** screen of New session, the hardware options. For example, a *simulated
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
| The camera step says "No one in view" | Sit about an arm's length in front of Reachy, in good light (not in front of a window). |
| The microphone step hears nothing | Speak from where the participant sits; check Reachy's USB cable. |
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
