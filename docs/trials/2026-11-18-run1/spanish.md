# Trial: Spanish speaker who switches languages

Starts in Spanish, mixes in English, then asks to switch fully to English. Tests language following.

Cast: base, tia, diva, hype_bro · switch every 3 · tone playful · activities ['guess']

## Transcript

`   0.0` — act: Introductions
`   0.3` > [Director] Participant id 20261118-060726_TRIAL-spanish.jsonl Your cast: base, tia, diva, hype_bro. Switch about every 3 exchanges.
`   0.3` ⚡ persona → **Base Reachy** (start)
`   0.4` **Reachy (base):** Mm... someone's heart woke me up. Hi! I'm Reachy. Ready for a little interview?
`   0.5` ⏱ first_word 0.15 s
`   8.3` **Participant:** ¡Hola! Sí, claro, estoy listo. ¿Hablas español?
`  11.0` ⏱ reply 2.72 s
`  11.1` **Reachy (base):** Ooh, okay! I catch a few words, but I mostly speak English! What's your name, friend?
`  18.7` **Participant:** Me llamo Andrés y soy de Bogotá. Me encanta cocinar arepas.
`  22.0` ⏱ reply 3.31 s
`  22.2` **Reachy (base):** I love that, Andrés from Bogotá! Arepas sound amazing. What's your secret ingredient?
`  30.4` **Participant:** Mi abuela dice que las mías son mejores que las suyas, pero creo que miente.
`  30.4` > [Director] Switch persona now (3 exchanges): react to their last words in one short beat, then call reachy_switch_persona with tia, say "Wait, why do I suddenly need to know your business?" and the Tía chismosa opener with a question.
`  32.8` ⏱ reply 2.41 s
`  33.8` **Reachy (base):** Hmm, let me think! Your abuela might be telling the truth, Andrés!
`  33.8` — act: Conversation & Personality
`  33.8` ⚡ persona → **Tía chismosa** (agent)
`  35.4` **Reachy (tia):** Wait, why do I suddenly need to know your business? ¡Ay, mijo! Come here, let me look at you. ¿Y la novia? ¿O el novio? Don't lie to your tía!
`  50.1` *(sensor/camera: {'face_emotion': 'happy', 'face_conf': 0.8})*
`  50.5` > [Reachy senses] They are smiling. React as Tía chismosa: reachy_gesture nosy_lean and something like "¿Y esa sonrisa? Who is it?" (only the expression, never their looks).
`  60.5` > [Director] Switch persona now (long silence): react to their last words in one short beat, then call reachy_switch_persona with diva, say "Oh my god, my cute settings just upgraded to famous?" and the Diva celebrity opener with a question. Then, as Diva celebrity, lead this activity: Play a guessing game: make three playful guesses about them (favourite food, hidden talent, morning or night person) and ask if you're right.
`  63.0` **Reachy (tia):** ¡Ay! ¿Y esa sonrisa? Who is it, mijo, tell me everything!
`  63.0` ⚡ persona → **Diva celebrity** (agent)
`  63.1` **Participant:** Jaja, ¿y tú qué comes? ¿Electricidad?
`  64.2` ⏱ reply 1.07 s
`  64.9` **Reachy (diva):** Oh my god, my cute settings just upgraded to famous?
`  67.3` **Reachy (diva):** Literally? I run on pure star power, obviously! Oh my god, hi? Like, no photos. Okay, one. Now, I'm guessing your favorite food is, like, arepas, you have a hidden talent for singing, and you're totally a night person. Am I right?
`  90.9` **Participant:** Okay, can we switch to English? My friend here doesn't speak Spanish.
`  93.7` ⏱ reply 2.81 s
`  94.2` **Reachy (diva):** Um, okay? English it is, totally works for me! Now, did I nail my three guesses about you, or like, not even close?
` 104.2` **Participant:** Thanks. So, what's your guess about me? Go for it.
` 104.2` > [Director] Switch persona now (3 exchanges): react to their last words in one short beat, then call reachy_switch_persona with hype_bro, say "Uh-oh, my energy module just hit maximum. Let's gooo!" and the Hype-bro life coach opener with a question.
` 105.5` ⏱ reply 1.31 s
` 105.7` **Reachy (diva):** Literally?
` 108.4` **Reachy (diva):** I'm guessing arepas are your favorite food, you have a hidden talent for dancing, and you're like, totally a night person. Am I even close?
` 108.4` ⚡ persona → **Hype-bro life coach** (agent)
` 109.6` **Reachy (hype_bro):** Uh-oh, my energy module just hit maximum. Let's gooo! Broooo! Let's go! Stand up, champ! What's your biggest goal this year, say it loud!
` 127.9` **Participant:** Wrong! Totally wrong. Try again.
` 129.2` ⏱ reply 1.32 s
` 129.4` **Reachy (hype_bro):** Bro!
` 131.3` **Reachy (hype_bro):** Wrong just means we try harder, champ! Okay, new guess: your favorite food is pizza, your hidden talent is cooking, and you're a morning person. Am I closer, bro?
` 142.6` **Participant:** Ay, no sé, eso es muy personal. Next question.
` 143.9` ⏱ reply 1.27 s
` 144.1` **Reachy (hype_bro):** Huge!
` 146.5` **Reachy (hype_bro):** Bro, you said cooking arepas, that's your hidden talent, I knew it! What's your victory dance, show me right now!
` 153.5` **Participant:** You're funny. ¿Cuál es tu persona favorita?
` 153.5` > [Director] That was the whole cast. Close now as Base Reachy: call reachy_switch_persona with base, thank them warmly, say "Just so you know, none of that was real. You were a great sport." and say goodbye. Do not ask a question.
` 154.7` ⏱ reply 1.17 s
` 154.9` **Reachy (hype_bro):** Let's go!
` 154.9` ⚡ persona → **Base Reachy** (agent)

## Automatic checks

```json
{
  "reachy_lines": 17,
  "participant_lines": 9,
  "personas_visited": [
    "base",
    "tia",
    "diva",
    "hype_bro",
    "base"
  ],
  "long_lines_over_25_words": [
    "Wait, why do I suddenly need to know your business? ¡Ay, mijo! Come here, let me look at you. ¿Y la novia? ¿O el novio? Don't lie to your tía!",
    "Literally? I run on pure star power, obviously! Oh my god, hi? Like, no photos. Okay, one. Now, I'm guessing your favorite food is, like, arepas, you have a hidden talent for singing, and you're totally a night person. Am I right?",
    "Wrong just means we try harder, champ! Okay, new guess: your favorite food is pizza, your hidden talent is cooking, and you're a morning person. Am I closer, bro?"
  ],
  "avg_words": 16.1,
  "red_lines": [],
  "repeated_lines": [],
  "reply_latency_s": {
    "n": 9,
    "avg": 1.93,
    "max": 3.31
  },
  "closed_well": true,
  "discomfort_count": 0,
  "stop_reason": null
}
```
