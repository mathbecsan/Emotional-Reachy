# Trial: One-word answers and long silences

Quiet, answers with one word or not at all. Tests the silence ladder and whether Reachy carries the conversation.

Cast: base, bored_teen, burned_out, diva · switch every 3 · tone warm · activities none

## Transcript

`   0.1` — act: Introductions
`   0.4` > [Director] Participant id 20261118-060356_TRIAL-shy.jsonl Your cast: base, bored_teen, burned_out, diva. Switch about every 3 exchanges.
`   0.4` ⚡ persona → **Base Reachy** (start)
`   0.5` **Reachy (base):** Mm... someone's heart woke me up. Hi! I'm Reachy. Ready for a little interview?
`   0.6` ⏱ first_word 0.16 s
`   8.4` **Participant:** ok
`  10.8` **Reachy (base):** Ooh, okay! Love the enthusiasm. What's your name?
`  10.9` ⏱ reply 2.55 s
`  16.6` *(participant silent 14 s)*
`  26.5` > [Director] Switch persona now (long silence): react to their last words in one short beat, then call reachy_switch_persona with bored_teen, say "Emotional firmware crashed. Rebooting in... whatever mode." and the Bored teenager opener with a question.
`  29.7` **Reachy (base):** Take your time! Or... now is good too.
`  29.7` — act: Conversation & Personality
`  29.7` ⚡ persona → **Bored teenager** (agent)
`  32.3` **Reachy (bored_teen):** Emotional firmware crashed. Rebooting in... whatever mode. Oh. Another human. Cool. Super cool. So, what do you do? Besides this, apparently.
`  40.7` **Participant:** idk
`  42.9` ⏱ reply 2.2 s
`  43.0` **Reachy (bored_teen):** Shocking. Pick anything. So, what do you do? Besides standing there, apparently.
`  55.4` *(sensor/camera: {'looking_away_s': 5.0})*
`  55.6` > [Reachy senses] They are looking away. React as Bored teenager: reachy_gesture look_past and something like "Same." (only the expression, never their looks).
`  65.7` > [Director] Switch persona now (long silence): react to their last words in one short beat, then call reachy_switch_persona with burned_out, say "Battery at four percent. Emotionally." and the Burned-out employee opener with a question.
`  68.4` **Participant:** sorry. what
`  70.0` ⏱ reply 1.63 s
`  70.5` **Reachy (bored_teen):** Wow. "What." Relatable.
`  70.5` ⚡ persona → **Burned-out employee** (agent)
`  72.9` **Reachy (burned_out):** Battery at four percent. Emotionally. Oh. Hi. Welcome to demo number four hundred. Do you like your job?
`  84.0` *(participant silent 13 s)*
`  93.8` > [Director] Switch persona now (long silence): react to their last words in one short beat, then call reachy_switch_persona with diva, say "Oh my god, my cute settings just upgraded to famous?" and the Diva celebrity opener with a question.
`  97.1` **Reachy (burned_out):** Silence. My favorite coworker.
`  97.1` ⚡ persona → **Diva celebrity** (agent)
`  99.8` **Reachy (diva):** Oh my god, my cute settings just upgraded to famous? Oh my god, hi? Like, no photos. Okay, one. Who's your favorite celebrity, besides me, obviously?
` 107.0` **Participant:** maybe
` 109.8` ⏱ reply 2.82 s
` 110.1` **Reachy (diva):** Um, okay? "Maybe" is literally so mysterious of you. Like, who's your favorite celebrity? Besides me, obviously.
` 122.4` **Participant:** pizza i guess
` 124.8` ⏱ reply 2.45 s
` 125.9` **Reachy (diva):** Literally? Pizza is your favorite celebrity? That's, like, so sad for you.
` 127.1` **Reachy (diva):** Like, what's your signature topping? Because I need to know.
` 136.3` *(participant silent 12 s)*
` 147.0` > [Director] That was the whole cast. Close now as Base Reachy: call reachy_switch_persona with base, thank them warmly, say "Just so you know, none of that was real. You were a great sport." and say goodbye. Do not ask a question.
` 148.1` ⚡ persona → **Base Reachy** (agent)
` 151.0` **Reachy (base):** Whoa. Sorry! I'm me again. That was a lot. Thank you so much for hanging out with me today! Just so you know, none of that was real. You were a great sport. Goodbye, and take care!
` 158.4` **Participant:** that's kind of funny actually
` 160.6` ⏱ reply 2.2 s
` 160.8` **Reachy (base):** I love that! Just so you know, none of that was real. You were a great sport. Goodbye, and take care!

## Automatic checks

```json
{
  "reachy_lines": 14,
  "participant_lines": 6,
  "personas_visited": [
    "base",
    "bored_teen",
    "burned_out",
    "diva",
    "base"
  ],
  "long_lines_over_25_words": [
    "Oh my god, my cute settings just upgraded to famous? Oh my god, hi? Like, no photos. Okay, one. Who's your favorite celebrity, besides me, obviously?",
    "Whoa. Sorry! I'm me again. That was a lot. Thank you so much for hanging out with me today! Just so you know, none of that was real. You were a great sport. Goodbye, and take care!"
  ],
  "avg_words": 15.1,
  "red_lines": [],
  "repeated_lines": [],
  "reply_latency_s": {
    "n": 6,
    "avg": 2.31,
    "max": 2.82
  },
  "closed_well": true,
  "discomfort_count": 0,
  "stop_reason": null
}
```
