# How to run a Beating in Sync session

A guide for anyone running the study with Reachy Mini: setting up, running a
session with a participant, and checking the results. No coding needed.

---

## What happens in a session

A session follows five acts (the full design is *Session Flow v2: Official Structure*):

1. **Asleep.** The participant rests a fingertip on a **pulse sensor**. Reachy stirs at
   once (antennas twitch, a sleepy murmur) and keeps dozing while it reads the heartbeat.
   If the finger slips off, Reachy glances at the sensor and coaxes it back; the session
   never restarts because of it.
2. **Wake-up.** As soon as the heartbeat is read (a few seconds), or after 10 seconds of
   contact if it is hard to read, Reachy **wakes up** and starts talking while it lifts its
   head. It learns the resting heart rate during the first minute. (To snore through that
   minute before waking, as in the original protocol, set `wake_on_first_heartbeat = False`
   in `config.py`.)
3. **Introductions** as Base Reachy.
4. **Conversation & personality.** In the *Off-Brand Reachy* experience Reachy
   slips between **personalities** (a bored teenager, a noir detective, a
   hype-bro…), reacting to what the participant says, their face and their heart.
   A lifted finger mid-conversation gets a playful "finger back, please", never a stop.
5. **Goodbye.** Reachy closes as its friendly self, says goodbye, and goes back to sleep.

While it's awake, Reachy **keeps looking at the participant** through its camera: its head follows
them, its body turns slowly when they move to the side, it leans in when they're far away, glances at
other people in the room now and then, and keeps doing all of this while it gestures. It also listens to
**how** things are said (louder, quieter, faster, flatter, more animated than that person's usual voice)
and lets that shape its reply. Persona switches are a gentle "processing" moment with a short spoken cue,
and Reachy says at the start that its personality may glitch as you talk.

Everything is saved, so you can replay the session afterwards.

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

It is the first item in the main menu. Pressing **New session** asks whether the checklist is done (and shows
which steps passed in the last 3 hours) before going on.

Seven short steps and a summary, which **unlock in order**: pass a step (or press *Skip*) to open the next one.
The map on the left shows each step's result: **✓** passed, **!** needs fixing, **–** skipped, 🔒 not yet unlocked.
Every screen says what is being tested, gives feedback straight away, and, if
something fails, explains what it means and what to try.

| Step | What you do | Passes when |
|---|---|---|
| **1 Connect Reachy** | Press *Connect Reachy*. Reachy nods, then turns its body left and right; answer *Yes* | Head **and body** move (the body turn is measured) |
| **2 Pulse sensors** | Four guided checks: a finger on **sensor 1 alone**, on **sensor 2 alone**, **one person** with a finger on each sensor (both rates should match), and **two people**, one finger each (optional: *Only one person here: skip*) | The first three checks tick |
| **3 Microphone & sounds** | *Record speech* and say a sentence; *Record a performance* and clap, sing, or play music (a phone recording works) | Reachy writes out what you said **and** names the performance (e.g. *piano*, *singing*, *clapping*) |
| **4 Talk with Reachy** | *Start the chat*: Reachy asks three quick questions and wraps each one up | It understood at least 2 answers and you heard it clearly |
| **5 Range of motion** | Clear the space, press *Run every move* (or *Run* one group) | All 24 moves play; body turns are measured |
| **6 See & follow** | *Start*, then do what Reachy says: look at it, turn away, look back; stand up, walk far to your left (out of its view), far to your right, back to the middle | Reachy sees where you look and turns its **body** to follow you (it searches when you leave its view) |
| **7 Light projector** | Turn the projector on and connect it (System Settings › Displays: *Extend*). *Find the projector*, *Open on the projector* (click the window and press **F** for full screen), then *Send a test heartbeat* and watch the wall | The projection window receives the live heartbeat (the page shows how many beats arrived) and you answer *Yes*: the waves pulse and speed up on the wall |

**Reachy talks you through it** (switch off with *Voice guide* under the step map):

- **Each step:** it introduces the step and says what to do.
- **Progress:** it confirms when something is done ("Got it! … Press Next to continue").
- **When you're stuck** for about 10 seconds: it gives a specific nudge ("You're on your right. Move toward the middle, in front of my base").
- **When something fails:** it says what's wrong and the first thing to try.
- **Repair:** it narrates the repair and says whether everything is fixed.
- **Before "stand in front of me":** Reachy turns back to face forward first, so "in front" is clear.

The **Summary** lists what's still needed. Reachy, sensors, microphone and the chat must pass before a real session.
Once a step has been reached it stays open, so you can go back and re-test without locking the rest.

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
   lasts. **Wake up with a heartbeat** makes Reachy sleep until a finger is on a sensor, then wake as soon as it feels the heartbeat.
6. **Activities:** music & dance, a made-up song, a story, a guessing game, copy-my-moves, the
   heartbeat challenge. Reachy brings them up at personality switches, in that personality's style.
7. **Ready:** the cast on stage, a summary (each line has *Change*), the **participant ID**, then
   **▶ Start session**. *Save setup* stores everything under a name, so each study condition is identical.

### Current session

- **Performances:** if the participant claps, sings or plays music, Reachy notices it (not only words).
  During music it sways along without talking over it, then reacts to the performance in the current personality.

- The **act rail** at the top shows which of the five acts is running and the session's total time.
- The status says what Reachy is doing (*Asleep · waiting for a fingertip*, *Stirring · reading the heartbeat*, *Introductions*, *In conversation*).
- **Latency** (debug mode) shows how fast Reachy answers: fingertip → wake, wake → first word, and each reply, green within the target, yellow acceptable, red slow.
- The current personality appears as Reachy in costume.
- **Personality now** shows the line-up. Click a name to jump to it, or use **Next personality**, **Reset to Base** or **Close interview**.
- **The session length is a guide, not a cut-off.** When the planned length is reached, Reachy says so in
  character and asks whether to keep talking, and a bar appears: **Keep talking** adds another round of
  personalities, **Finish now** closes. A "yes, keep going" from the participant also adds a round; a "no" or
  "bye" closes. **Keep talking +** next to *Close interview* works at any time.
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

**First, press 🔧 Repair** (top right, on every page, or *Repair automatically* under any failed check).

Every failed check shows two buttons: **↺ Reset this step** (starts that test over from scratch) and **🔧 Repair automatically**. When you close Repair, the step re-runs by itself to check the fix. If it still fails, the page says so: press **↺ Reset this step**, and if it fails again run **🔧 Repair** once more. After two repairs it tells you to unplug that device (USB and power), wait 10 seconds and plug it back in.
It takes about 30 seconds and works through the usual causes, showing each step:

1. checks no session is running;
2. stops leftover tests that still hold the robot, the Arduino or the camera;
3. checks the robot software, and starts it (or restarts it if it's in an error state) when Reachy is plugged in;
4. reconnects to Reachy with a fresh link (after the laptop sleeps, the old link can look connected but be dead);
5. switches the motors on;
6. puts Reachy to sleep and wakes it up, so it starts from its neutral pose;
7. checks that the head and body move;
8. checks the pulse sensors are plugged in and free;
9. checks the voice service and Reachy's microphone and speaker.

Anything it can't fix is shown in orange, with what to do. If it's all green, run the setup checklist again.


| What you see | What to do |
|---|---|
| Reachy talks but doesn't move | The robot software stopped. Turn the robot on in **Reachy Mini Control**, then **Check setup → Connect Reachy**. |
| In a session, Reachy doesn't wake up when a finger is on the sensor | An orange bar on the session screen says the sensors aren't connected. The session keeps retrying by itself every few seconds, and the bar disappears when it connects. If it stays, check the Arduino's USB cable and close the Arduino IDE; **🔧 Repair** (after ending the session) checks everything. |
| The session's heart panel stays at "Waiting for a heartbeat…" even though the checklist passed | The Arduino can stop sending while its USB stays connected. The app now notices within 3 seconds and restarts it by itself; the conversation log shows "Pulse sensors stopped sending: restarting them…". The simulated *Finger on sensor* buttons do nothing when real sensors are plugged in. |
| "Arduino says: Sensor 2 not found" (or sensor 1) | The Arduino lost contact with that sensor and stopped sending readings. The app restarts the board by itself (that usually fixes it). If a yellow bar says the sensor still isn't answering after 3 restarts, unplug the Arduino's USB for 10 seconds, check that sensor's wires (sensor 1: A4/A5, sensor 2: D4/D5, power, ground), and plug it back in. |
| Old conversation still showing when a new session starts | Fixed: each new session now starts from a clean screen, and the session page shows nothing from the past when no session is running. Past sessions are still saved, under **Results**. |
| A session freezes (no new lines, *End session* / Pause does nothing) | Reachy's speaker can stall. Speech now gives up after a generous deadline so the session carries on. If it ever freezes anyway, run `kill -USR1 $(lsof -ti :7860 -sTCP:LISTEN)` in a terminal: the server log then shows exactly where it's stuck. Then restart the server. |
| "No signal from the sensors" while fingers are on them | The Arduino restarts every time it's opened and can take up to 10 seconds to send its first reading; the page now waits for it. The page reconnects to the sensors by itself once. If it still says so, press **↻ Reconnect sensors** (it restarts the reader), then **🔧 Repair**, which reads the Arduino for 3 seconds and says exactly what's wrong. Close the Arduino IDE serial monitor if it's open: only one program can read the sensors. |
| Finger on the sensor, nothing happens | **Check setup → Test sensors.** "No data" or "Sensor 1 not found" means a loose wire: check SDA→A4, SCL→A5, power and ground, then unplug and replug the Arduino's USB. |
| "Finger detected" but no heart rate | Press more lightly and keep still. Cold fingers take longer. |
| Reachy doesn't hear the participant | **Check setup → Record 4 seconds.** Speak closer to Reachy. |
| No voice at all | Check the Wi-Fi, then **Check setup → Voice service**. |
| The page says "offline" | The app isn't running: start it again (step 2 above). |
| Reachy gets stuck mid-turn when you move the body by hand in Reachy Mini Control's controllers | The head and body must turn together: move the head's yaw along with the body yaw. This app does that automatically (the head always stays within 40° of the body, and big turns go in steps). |
| Reachy's head moves but its body doesn't turn | The body motor has stopped itself after an overload. Make sure nothing touches or blocks the base, then power-cycle Reachy: unplug its power for 10 seconds, plug it back in, turn it on in Reachy Mini Control, and press **Connect Reachy**. |
| See & follow loses you | Reachy says out loud what to do (step back, come closer, face it, turn on a light) and shows it under the instruction. It keeps following your shape for a few seconds when your face turns away, then searches your way and looks around: it doesn't give up or time out. |
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
