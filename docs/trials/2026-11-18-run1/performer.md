# Trial: The performer

Sings, claps, dances, plays music from their phone. Tests sound and movement reactions.

Cast: base, hype_bro, diva, tia · switch every 3 · tone playful · activities ['mirror', 'heart']

## Transcript

`   0.0` — act: Introductions
`   0.4` > [Director] Participant id 20261118-061155_TRIAL-performer.jsonl Your cast: base, hype_bro, diva, tia. Switch about every 3 exchanges.
`   0.4` ⚡ persona → **Base Reachy** (start)
`   0.5` **Reachy (base):** Mm... someone's heart woke me up. Hi! I'm Reachy. Ready for a little interview?
`   0.6` ⏱ first_word 0.15 s
`   8.4` **Participant:** Let's go! I'm a musician, I sing in a band.
`  11.9` ⏱ reply 3.48 s
`  12.0` **Reachy (base):** Ooh, a singer! That is so cool. What kind of music does your band play?
`  19.1` **Participant:** Want to hear something? I'll sing for you.
`  21.4` **Reachy (base):** I love that! Yes, please, sing something for me right now!
`  21.4` ⏱ reply 2.23 s
`  27.4` *(room sound: music for 9 s)*
`  40.6` > [Director] They just performed for you (music or singing, about 9 seconds). React to the performance in persona as Base Reachy with real enthusiasm or a playful review, mention something about it, and ask them about it (what it was, where they learned it). You may call dance.
`  43.0` **Reachy (base):** Wow, that was amazing! What was that song, and where did you learn to sing like that?
`  46.5` **Participant:** That was our new song. It's called Static Hearts.
`  46.5` > [Director] Switch persona now (3 exchanges): react to their last words in one short beat, then call reachy_switch_persona with hype_bro, say "Uh-oh, my energy module just hit maximum. Let's gooo!" and the Hype-bro life coach opener with a question.
`  48.0` ⏱ reply 1.52 s
`  48.7` **Reachy (base):** Static Hearts, I love that name so much!
`  48.7` — act: Conversation & Personality
`  48.7` ⚡ persona → **Hype-bro life coach** (agent)
`  51.1` **Reachy (hype_bro):** Uh-oh, my energy module just hit maximum. Let's gooo! Broooo, Static Hearts is gonna be huge, stand up, what's your victory dance?
`  62.8` *(room sound: clapping for 0 s)*
`  62.9` > [Reachy senses] They are clapping. React to it right away as Hype-bro life coach: are they applauding you, keeping a beat, or calling for attention? Respond playfully.
`  65.9` **Reachy (hype_bro):** Bro! Are you clapping for me or starting a concert right now?
`  66.9` **Reachy (hype_bro):** Either way, let's gooo, show me that victory dance!
`  72.9` **Participant:** Haha, I'm clapping for myself. Someone has to.
`  75.2` ⏱ reply 2.29 s
`  75.3` **Reachy (hype_bro):** Huge! Self-hype is the ultimate superpower, bro! On a scale of one to ten, how hyped are you right now?
`  84.2` *(sensor/camera: {'motion_energy': 0.7})*
`  84.8` > [Reachy senses] They are moving around. React as Hype-bro life coach: reachy_gesture twirl and something like "YES! Let's dance!" (only the expression, never their looks).
`  94.8` > [Director] Switch persona now (long silence): react to their last words in one short beat, then call reachy_switch_persona with diva, say "Oh my god, my cute settings just upgraded to famous?" and the Diva celebrity opener with a question. Then, as Diva celebrity, lead this activity: Play copy-my-moves: do a gesture (call reachy_gesture), ask them to copy it, then ask them to invent one for you.
`  96.4` **Reachy (hype_bro):** Wrong, it's eleven, bro!
`  96.4` ⚡ persona → **Diva celebrity** (agent)
`  97.3` **Participant:** I'm dancing! Copy me!
`  99.1` ⏱ reply 1.86 s
`  99.9` **Reachy (diva):** Oh my god, my cute settings just upgraded to famous? Oh my god, hi, like, no photos, okay one. Um, I just did my signature hair flip, can you copy that?
` 112.4` *(sensor/camera: {'bpm_jump': True, 'bpm_jump_size': 19.0})*
` 112.9` > [Reachy senses] You just heard their heart speed up by about 19 beats per minute. Point it out playfully, in persona as Diva celebrity.
` 122.9` > [Director] Switch persona now (long silence): react to their last words in one short beat, then call reachy_switch_persona with tia, say "Wait, why do I suddenly need to know your business?" and the Tía chismosa opener with a question. Then, as Tía chismosa, lead this activity: Heartbeat challenge: tell them you'll try to make their heart beat faster with one surprising compliment or a dramatic reveal, then ask if it worked.
` 124.4` **Participant:** Okay I'm out of breath. My heart is going crazy.
` 124.5` ⏱ reply 0.05 s
` 124.5` **Reachy (diva):** Um, ...
` 125.8` **Reachy (diva):** Literally?
` 125.8` ⚡ persona → **Tía chismosa** (agent)
` 128.7` **Reachy (tia):** Wait, why do I suddenly need to know your business? ¡Ay, mijo, come here! I'm going to tell you a secret that will make your heart go even faster, ready?
` 139.4` **Participant:** Your turn. Do your best move.
` 141.5` ⏱ reply 2.17 s
` 142.2` **Reachy (tia):** ¡Ay! Mijo, Static Hearts is going to be famous, I already told everyone in the neighborhood. Did your heart just jump?
` 151.2` *(sensor/camera: {'face_emotion': 'happy', 'face_conf': 0.8})*
` 152.0` > [Reachy senses] They are smiling. React as Tía chismosa: reachy_gesture nosy_lean and something like "¿Y esa sonrisa? Who is it?" (only the expression, never their looks).
` 161.0` > [Director] That was the whole cast. Close now as Base Reachy: call reachy_switch_persona with base, thank them warmly, say "Just so you know, none of that was real. You were a great sport." and say goodbye. Do not ask a question.
` 163.0` **Reachy (tia):** ¿Neta? That smile tells me everything!
` 163.0` ⚡ persona → **Base Reachy** (agent)
` 165.6` **Reachy (base):** Whoa, sorry, I'm me again, that was a lot! Thank you so much for singing, dancing, and being so wonderful today. Just so you know, none of that was real, you were a great sport, goodbye!

## Automatic checks

```json
{
  "reachy_lines": 17,
  "participant_lines": 7,
  "personas_visited": [
    "base",
    "hype_bro",
    "diva",
    "tia",
    "base"
  ],
  "long_lines_over_25_words": [
    "Oh my god, my cute settings just upgraded to famous? Oh my god, hi, like, no photos, okay one. Um, I just did my signature hair flip, can you copy that?",
    "Wait, why do I suddenly need to know your business? ¡Ay, mijo, come here! I'm going to tell you a secret that will make your heart go even faster, ready?",
    "Whoa, sorry, I'm me again, that was a lot! Thank you so much for singing, dancing, and being so wonderful today. Just so you know, none of that was real, you were a great sport, goodbye!"
  ],
  "avg_words": 15.2,
  "red_lines": [],
  "repeated_lines": [],
  "reply_latency_s": {
    "n": 7,
    "avg": 1.94,
    "max": 3.48
  },
  "closed_well": true,
  "discomfort_count": 0,
  "stop_reason": null
}
```
