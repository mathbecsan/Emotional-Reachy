/** Mirrors brain/modes.py and the Interaction Protocol stages. */
export const MODES = {
  sleepy:   { color: "#8a8fbf", label: "Sleepy" },
  curious:  { color: "#5cc8ff", label: "Curious" },
  excited:  { color: "#ffc94d", label: "Excited" },
  flirty:   { color: "#ff6fb1", label: "Flirty" },
  teasing:  { color: "#b98cff", label: "Teasing" },
  offended: { color: "#ff9a4d", label: "Offended" },
  scolding: { color: "#ff4d4d", label: "Scolding" },
  sincere:  { color: "#7be0a8", label: "Sincere" },
};

// Session flow v2: the five acts, and which act each protocol stage belongs to.
export const ACTS = [
  { n: 1, name: "Asleep" },
  { n: 2, name: "Wake-up & Analysis" },
  { n: 3, name: "Introductions" },
  { n: 4, name: "Conversation & Personality" },
  { n: 5, name: "Goodbye" },
];
export const ACT_OF_STAGE = { 0: 1, 1: 2, 2: 3, 3: 4, 4: 4, 5: 4, 6: 5, 7: 5 };
// Latency budget (seconds): [target, acceptable] -- session flow v2, section 4.
export const LATENCY_BUDGET = { reply: [1.5, 2.5], first_word: [1.5, 2.5], contact_to_wake: [6, 10] };

export const STAGES = [
  { n: 0, name: "Baseline", secs: 120 },
  { n: 1, name: "Wake-up", secs: 60 },
  { n: 2, name: "Introductions", secs: 120 },
  { n: 3, name: "Conversation", secs: 180 },
  { n: 4, name: "Provocation", secs: 180 },
  { n: 5, name: "Music", secs: 120 },
  { n: 6, name: "Goodbye", secs: 60 },
  { n: 7, name: "Visualization", secs: 120 },
];

export const PROVOCATIONS = new Set(["teasing", "offended", "scolding"]);

export const LANGS = {
  en: "English", es: "Spanish", fr: "French", it: "Italian", de: "German", pt: "Portuguese",
  zh: "Chinese", ja: "Japanese", ko: "Korean", hi: "Hindi", ar: "Arabic", ru: "Russian",
  tr: "Turkish", fa: "Persian", vi: "Vietnamese", tl: "Tagalog",
};

export const BPM_STOP = 130;
