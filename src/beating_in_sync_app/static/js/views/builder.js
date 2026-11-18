/**
 * New session: a sequence of small screens, one decision each.
 *   Experience → Personalities → Movement → Voice & tone → Length → Activities → Ready
 * A progress track at the top shows where you are; Enter = next, Esc = back.
 */
import { h, toast, isDebug, setCrumbs, swap } from "../ui.js";
import { api } from "../api.js";
import { LANGS } from "../constants.js";
import { loadPersonas } from "../personas.js";
import { avatar } from "../components/avatar.js";

const STORE = "bis.builder.v3";
const MODE_INFO = {
  flirty: { label: "Flirty", text: "Charming, a little French.", color: "#ff6fb1", costume: "smitten" },
  teasing: { label: "Teasing", text: "Mock-bored and cheeky.", color: "#b98cff", costume: "bored_teen", teases: true },
  offended: { label: "Offended", text: "Sulks and turns away.", color: "#ff9a4d", costume: "melodramatic", teases: true },
  scolding: { label: "Scolding", text: "“Hey. Eyes on me.”", color: "#ff4d4d", costume: "villain", teases: true },
};
const STEPS = [
  { key: "experience", label: "Experience", color: "#ff5a6e" },
  { key: "personalities", label: "Personalities", color: "#b98cff" },
  { key: "movement", label: "Movement", color: "#5cc8ff" },
  { key: "voice", label: "Voice & tone", color: "#ff6fb1" },
  { key: "length", label: "Length", color: "#ffc94d" },
  { key: "activities", label: "Activities", color: "#7be0a8" },
  { key: "ready", label: "Ready", color: "#ff5a6e" },
];
const MOTION = [
  { v: 0.5, name: "Subtle", text: "Small, calm movements.", demo: 0.4 },
  { v: 0.8, name: "Gentle", text: "Soft and friendly.", demo: 0.7 },
  { v: 1.0, name: "Expressive", text: "Clear, lively gestures.", demo: 1 },
  { v: 1.2, name: "Dramatic", text: "Big, theatrical moves.", demo: 1.35 },
];
const SPEED = [{ v: 0.7, name: "Slow" }, { v: 1.0, name: "Normal" }, { v: 1.3, name: "Fast" }];
const TONES = [
  { v: "warm", name: "Warm", text: "Gentle, even inside the wild personalities." },
  { v: "playful", name: "Playful", text: "Cheeky and fun." },
  { v: "bold", name: "Bold", text: "Fully theatrical, commits to every role." },
];
const CHAT = [
  { v: "brief", name: "Brief", text: "One short sentence at a time." },
  { v: "normal", name: "Balanced", text: "One or two sentences." },
  { v: "chatty", name: "Chatty", text: "Tells a bit more before asking." },
];
const LENGTHS = [
  { v: "quick", name: "Quick", mins: 4, text: "A taste of each personality." },
  { v: "standard", name: "Standard", mins: 8, text: "Time to get to know each other." },
  { v: "long", name: "Long", mins: 12, text: "Room for stories and games." },
];
const FEATURED_VOICES = ["N2lVS1w4EtoT3dr4eOWO", "cgSgspJ2msm6clMCkdW9", "IKne3meq5aSn9XLyUdCD", "FGY2WhTYpPnrIDTdsKH5",
  "JBFqnCBsd6RMkjVDRZzb", "TX3LPaxmHKxFdv7VOQHJ", "pFZP5JQG7iQjIQuC4Bku", "SAz9YHcvj6GT2YYXdXww"];

const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (s) => { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch { /* private window */ } };

export function builderView(outlet, presetId) {
  const root = h("div", { class: "creator" }, h("p", { class: "muted" }, "Loading…"));
  outlet.replaceChildren(root);
  let alive = true, audio = null;
  Promise.all([api("/api/profiles"), loadPersonas(), api("/api/presets").catch(() => []), api("/api/ports").catch(() => []),
    api("/api/state").catch(() => ({})), api("/api/voices").catch(() => [])])
    .then((r) => alive && render(...r))
    .catch((e) => root.replaceChildren(h("p", { class: "muted" }, `Could not load: ${e.message}`)));

  function render(profiles, cat, presets, ports, serverState, voices) {
    const byName = Object.fromEntries(profiles.map((p) => [p.name, p]));
    const defaults = {
      participant: "P01", profile: byName.off_brand_reachy ? "off_brand_reachy" : profiles[0].name,
      personas: null, no_tease: false, motion_intensity: 1.0, motion_speed: 1.0, camera: true,
      voice_id: "N2lVS1w4EtoT3dr4eOWO", tone: "playful", chattiness: "normal", duration: "standard",
      activities: ["heart"], heart_wake: true, language_hint: "en",
      heart: "arduino", heart_port: "", conversation: "realtime", listener: "elevenlabs", voice: "elevenlabs", time_scale: 1,
    };
    const state = { ...defaults, ...load(), step: 0 };
    if (presetId) {
      const p = presets.find((x) => x.id === presetId);
      if (p) Object.assign(state, defaults, { participant: state.participant }, p.options, { step: 6 });
    }
    if (!byName[state.profile]) state.profile = defaults.profile;
    const prof = () => byName[state.profile];
    const isPersonas = () => prof().kind === "personas";
    const cast = () => {
      const p = prof();
      if (!isPersonas()) return state.personas?.filter((k) => MODE_INFO[k]) ?? p.default_selection;
      const list = (state.personas ?? p.default_selection).filter((k) => cat.byKey[k]);
      return list[0] === cat.base ? list : [cat.base, ...list.filter((k) => k !== cat.base)];
    };
    const effective = () => cast().filter((k) => !(state.no_tease && (cat.byKey[k]?.teases || MODE_INFO[k]?.teases)));
    const persist = () => { const { step, ...rest } = state; save(rest); };
    const set = (patch, redraw = true) => { Object.assign(state, patch); persist(); if (redraw) draw(false); };
    const go = (step) => { state.step = Math.max(0, Math.min(STEPS.length - 1, step)); audio?.pause(); draw(true); };
    const info = (k) => (isPersonas() ? { label: cat.byKey[k].name, color: cat.byKey[k].color, costume: k, text: cat.byKey[k].mood }
      : { ...MODE_INFO[k], costume: MODE_INFO[k].costume });

    const track = h("ol", { class: "track-steps" });
    const screen = h("div", { class: "creator__screen" });
    root.replaceChildren(track, screen);

    // ------------------------------------------------------------ helpers
    const optionCards = (opts, current, onPick, extra = () => null) => h("div", { class: "opt-grid", role: "radiogroup" }, opts.map((o) => h("button", {
      type: "button", role: "radio", "aria-checked": String(o.v === current), class: `opt${o.v === current ? " is-on" : ""}`,
      onclick: () => onPick(o.v),
    }, extra(o), h("strong", {}, o.name), o.text ? h("span", {}, o.text) : "")));
    const toggleRow = (label, hint, checked, onchange) => h("label", { class: "setting setting--toggle" },
      h("div", { class: "setting__label" }, h("strong", {}, label), h("span", {}, hint)),
      h("span", { class: "switch" }, h("input", { type: "checkbox", checked, onchange: (ev) => onchange(ev.target.checked) }), h("span", { class: "switch__ui", "aria-hidden": "true" })));
    const heading = (title, sub) => h("header", { class: "creator__head" }, h("h1", {}, title), sub ? h("p", {}, sub) : "");

    // ------------------------------------------------------------ screens
    const SCREENS = {
      experience: () => [
        heading("What kind of session?", "You can change everything later."),
        h("div", { class: "exp-grid" }, profiles.map((p) => h("button", {
          type: "button", class: `exp${p.name === state.profile ? " is-on" : ""}`, style: { "--accent": p.accent },
          "aria-pressed": String(p.name === state.profile),
          onclick: () => set({ profile: p.name, personas: null }),
        }, avatar(p.kind === "personas" ? "diva" : p.name === "gentle" ? "base" : "smitten", { size: 96, color: p.accent }),
        h("strong", {}, p.display_name), h("span", {}, p.description)))),
        presets.length ? h("div", { class: "creator__presets" }, h("p", { class: "creator__label" }, "Or load a saved setup"),
          h("div", { class: "chip-row" }, presets.map((p) => h("button", {
            type: "button", class: "chip-btn", title: p.description || "",
            onclick: () => { Object.assign(state, defaults, { participant: state.participant }, p.options); persist(); go(6); toast(`Loaded “${p.name}”`); },
          }, p.name)))) : "",
      ],

      personalities: () => {
        const list = cast();
        const sel = new Set(list);
        const all = isPersonas() ? cat.personas.map((p) => p.key) : Object.keys(MODE_INFO);
        const toggle = (k) => {
          if (isPersonas() && k === cat.base) { toast("Base Reachy always opens and closes the session."); return; }
          const next = sel.has(k) ? list.filter((x) => x !== k) : [...list, k];
          set({ personas: next });
        };
        const move = (i, d) => { const n = [...list]; const j = i + d; if (j < (isPersonas() ? 1 : 0) || j >= n.length) return; [n[i], n[j]] = [n[j], n[i]]; set({ personas: n }); };
        return [
          heading(isPersonas() ? "Pick Reachy's personalities" : "Pick Reachy's persona moves",
            isPersonas() ? "Tap to add or remove. They appear in the order of the line-up below." : "Used in the playful middle part of the session."),
          h("div", { class: "char-grid" }, all.map((k) => {
            const it = info(k);
            const on = sel.has(k), blocked = state.no_tease && (cat.byKey[k]?.teases || MODE_INFO[k]?.teases);
            const n = list.indexOf(k);
            return h("button", {
              type: "button", class: `char${on ? " is-on" : ""}${blocked ? " is-blocked" : ""}`, style: { "--accent": it.color },
              "aria-pressed": String(on), title: blocked ? "Skipped: teasing is off" : it.text, onclick: () => toggle(k),
            },
            on ? h("span", { class: "char__badge" }, n + 1) : "",
            avatar(it.costume, { size: 92, color: it.color, animate: on }),
            h("strong", {}, it.label), h("span", { class: "char__line" }, isPersonas() ? cat.byKey[k].sample : it.text),
            (cat.byKey[k]?.teases || MODE_INFO[k]?.teases) ? h("span", { class: "char__tag" }, "teases") : "");
          })),
          h("div", { class: "lineup" },
            h("p", { class: "creator__label" }, `Line-up · ${effective().length}`),
            h("ol", { class: "lineup__list" }, list.map((k, i) => {
              const it = info(k);
              const locked = isPersonas() && i === 0;
              return h("li", { class: "lineup__item", style: { "--accent": it.color } },
                avatar(it.costume, { size: 44, color: it.color }), h("span", {}, it.label),
                locked ? "" : h("span", { class: "lineup__btns" },
                  h("button", { type: "button", class: "icon-btn", "aria-label": `Move ${it.label} earlier`, onclick: () => move(i, -1) }, "‹"),
                  h("button", { type: "button", class: "icon-btn", "aria-label": `Move ${it.label} later`, onclick: () => move(i, 1) }, "›")));
            })),
            isPersonas() ? h("button", { type: "button", class: "chip-btn", onclick: () => set({ personas: [...cat.default_order] }) }, "Suggested line-up") : ""),
          toggleRow("Teasing allowed", "Turn off for participants who'd rather not be teased: teasing personalities are skipped.",
            !state.no_tease, (v) => set({ no_tease: !v })),
        ];
      },

      movement: () => {
        const tryIt = async () => {
          try { await api(`/api/gesture/${isPersonas() ? "big_bounce" : "curious"}?intensity=${state.motion_intensity}&speed=${state.motion_speed}`, {}); toast("Reachy is showing you"); }
          catch (e) { toast(e.message, "error"); }
        };
        return [
          heading("How does Reachy move?", "Size and speed apply to every gesture, head turn and body move."),
          h("p", { class: "creator__label" }, "Size of movements"),
          optionCards(MOTION, state.motion_intensity, (v) => set({ motion_intensity: v }),
            (o) => h("span", { class: "opt__demo", style: { "--amp": o.demo, "--spd": `${1.6 / state.motion_speed}s` } }, avatar("base", { size: 64, color: "#5cc8ff" }))),
          h("p", { class: "creator__label" }, "Speed"),
          optionCards(SPEED, state.motion_speed, (v) => set({ motion_speed: v })),
          toggleRow("Follow the participant's face", "Reachy turns toward the person and reacts to smiles and looking away (camera).", state.camera, (v) => set({ camera: v })),
          h("div", { class: "btn-row creator__try" }, h("button", { type: "button", class: "btn", onclick: tryIt }, "▶ Try it on Reachy")),
        ];
      },

      voice: () => {
        const list = voices.length ? [...voices].sort((a, b) => (FEATURED_VOICES.indexOf(a.id) + 1 || 99) - (FEATURED_VOICES.indexOf(b.id) + 1 || 99)) : [];
        const shown = state._allVoices ? list : list.filter((v) => FEATURED_VOICES.includes(v.id));
        const play = (v, btn) => {
          audio?.pause();
          if (!v.preview) return;
          audio = new Audio(v.preview);
          btn.classList.add("is-playing");
          audio.onended = audio.onpause = () => btn.classList.remove("is-playing");
          audio.play().catch(() => toast("Couldn't play the preview", "error"));
        };
        return [
          heading("How does Reachy sound?", "One voice for every personality: the wording and pace change, not the speaker."),
          h("p", { class: "creator__label" }, "Voice"),
          shown.length ? h("div", { class: "voice-grid", role: "radiogroup" }, shown.map((v) => {
            const on = v.id === state.voice_id;
            const playBtn = h("button", { type: "button", class: "voice__play", "aria-label": `Play a sample of ${v.name}`,
              onclick: (ev) => { ev.stopPropagation(); play(v, ev.currentTarget); } }, "▶");
            return h("div", { class: `voice${on ? " is-on" : ""}`, role: "radio", tabindex: "0", "aria-checked": String(on),
              onclick: () => set({ voice_id: v.id }), onkeydown: (ev) => { if (ev.key === " " || ev.key === "Enter") { ev.preventDefault(); set({ voice_id: v.id }); } } },
            playBtn, h("div", {}, h("strong", {}, v.name), h("span", {}, [v.description, v.accent].filter(Boolean).join(" · "))));
          })) : h("p", { class: "muted" }, "Voices load when the app is online. Reachy will use its default voice."),
          list.length > shown.length || state._allVoices ? h("button", { type: "button", class: "link-sm", onclick: () => set({ _allVoices: !state._allVoices }) },
            state._allVoices ? "Show fewer voices" : `Show all ${list.length} voices`) : "",
          h("p", { class: "creator__label" }, "Tone"),
          optionCards(TONES, state.tone, (v) => set({ tone: v })),
          h("p", { class: "creator__label" }, "How much Reachy talks"),
          optionCards(CHAT, state.chattiness, (v) => set({ chattiness: v })),
        ];
      },

      length: () => {
        const n = effective().length;
        return [
          heading("How long is the session?", isPersonas() ? `With ${n} personalities, Reachy adjusts how long it stays in each.` : "The Beating in Sync protocol has fixed stages (about 15 minutes)."),
          isPersonas() ? optionCards(LENGTHS, state.duration, (v) => set({ duration: v }),
            (o) => h("span", { class: "opt__big" }, `${o.mins}`, h("small", {}, " min"))) : "",
          isPersonas() ? h("p", { class: "muted small" }, `About ${Math.max(2, Math.min(8, Math.round((LENGTHS.find((l) => l.v === state.duration)?.mins || 8) * 60 / Math.max(1, n) / 13)))} replies per personality before it switches.`) : "",
          toggleRow("Wake up with a heartbeat", "Reachy sleeps and snores until the participant rests a finger on a pulse sensor (adds about a minute).",
            state.heart_wake, (v) => set({ heart_wake: v })),
        ];
      },

      activities: () => {
        const on = new Set(state.activities);
        const acts = isPersonas() ? cat.activities : cat.activities.filter((a) => a.key === "music_dance");
        return [
          heading("What will you do together?", isPersonas() ? "Pick any. Reachy brings them up along the way, in the current personality's style." : "Beating in Sync supports the music and dance stage."),
          h("div", { class: "act-grid" }, acts.map((a) => h("button", {
            type: "button", class: `act${on.has(a.key) ? " is-on" : ""}`, "aria-pressed": String(on.has(a.key)),
            onclick: () => { on.has(a.key) ? on.delete(a.key) : on.add(a.key); set({ activities: [...on] }); },
          }, h("span", { class: "act__icon", "aria-hidden": "true" }, a.icon), h("strong", {}, a.label), h("span", {}, a.text)))),
          h("p", { class: "muted small" }, on.size ? `${on.size} selected` : "None selected: just conversation."),
        ];
      },

      ready: () => {
        const p = prof();
        const c = effective();
        const v = voices.find((x) => x.id === state.voice_id);
        const sel = (key, opts) => h("select", { onchange: (ev) => set({ [key]: ev.target.value }) },
          opts.map(([val, label]) => h("option", { value: val, selected: String(state[key]) === String(val) }, label)));
        const field = (label, input) => h("label", { class: "field" }, h("span", { class: "field__label" }, label), input);
        const nameIn = h("input", { placeholder: "Name this setup", "aria-label": "Setup name" });
        const row = (label, value, step) => h("div", { class: "review__row" }, h("span", {}, label), h("strong", {}, value),
          h("button", { type: "button", class: "link-sm", onclick: () => go(step) }, "Change"));
        const mins = isPersonas() ? (LENGTHS.find((l) => l.v === state.duration)?.mins || 8) + (state.heart_wake ? 2 : 0) : 15;
        return [
          heading("Ready to start", "Check the summary, add the participant ID, and start."),
          h("div", { class: "ready" },
            h("div", { class: "ready__stage" }, h("div", { class: "ready__cast" }, c.map((k, i) => {
              const it = info(k);
              return h("div", { class: "ready__actor", style: { "--accent": it.color, "--i": i } }, avatar(it.costume, { size: 72, color: it.color, animate: true }), h("span", {}, it.label));
            })),
            !c.length ? h("p", { class: "muted" }, "No persona moves: a gentle session.") : ""),
            h("div", { class: "ready__side" },
              h("div", { class: "start-grid" },
                field("Participant ID", h("input", { value: state.participant, autocomplete: "off", oninput: (ev) => { state.participant = ev.target.value; persist(); } })),
                field("Reachy starts in", h("select", { onchange: (ev) => set({ language_hint: ev.target.value }) },
                  Object.entries(LANGS).map(([k, l]) => h("option", { value: k, selected: k === state.language_hint }, l))))),
              h("div", { class: "review" },
                row("Experience", p.display_name, 0),
                row("Movement", `${MOTION.find((m) => m.v === state.motion_intensity)?.name || "Expressive"} · ${SPEED.find((s) => s.v === state.motion_speed)?.name?.toLowerCase() || "normal"}${state.camera ? " · follows faces" : ""}`, 2),
                row("Voice", `${v?.name || "Default"} · ${state.tone} · ${CHAT.find((x) => x.v === state.chattiness)?.name.toLowerCase()}`, 3),
                row("Length", `about ${mins} min${state.heart_wake ? " · heartbeat wake-up" : ""}`, 4),
                row("Activities", (isPersonas() ? state.activities : state.activities.filter((a) => a === "music_dance")).map((a) => cat.activities.find((x) => x.key === a)?.label).filter(Boolean).join(", ") || "Conversation only", 5)),
              h("div", { class: "save-row" }, nameIn, h("button", { type: "button", class: "btn btn--small", onclick: async () => {
                const name = nameIn.value.trim();
                if (!name) { nameIn.focus(); return; }
                const { participant, step, _allVoices, ...options } = state;
                options.personas = cast();
                try { await api("/api/presets", { name, description: `${p.display_name} · ${c.length} personalities · ${mins} min`, options }); toast(`Saved “${name}”`); presets = await api("/api/presets"); }
                catch (e) { toast(e.message, "error"); }
              } }, "Save setup")))),
          isDebug() ? h("details", { class: "advanced", open: true }, h("summary", {}, "Hardware & engines (Debug)"),
            h("div", { class: "start-grid" },
              field("Heart", sel("heart", [["arduino", "Arduino pulse sensors"], ["sim", "Simulated heart"], ["arduino-sim", "Arduino pipeline, simulated signal"]])),
              state.heart === "arduino" ? field("Sensor port", sel("heart_port", [["", "Auto-detect"], ...ports.map((x) => [x.device, `${x.device}${x.busy ? " (in use)" : ""}`])])) : "",
              field("Conversation", sel("conversation", [["realtime", "Live (ElevenLabs agent)"], ["scripted", "Scripted / offline"]])),
              field("Participant speech", sel("listener", [["elevenlabs", "Reachy's microphone + typed"], ["web", "Typed only (rehearsal)"], ["mic", "Local Whisper"]])),
              field("Reachy voice output", sel("voice", [["elevenlabs", "ElevenLabs on Reachy"], ["mac", "macOS voice"], ["sim", "Silent (text only)"]])),
              field("Clock", sel("time_scale", [[1, "Real time"], [2, "2×"], [5, "5×"], [10, "10×"]])))) : "",
        ];
      },
    };

    async function start(btn) {
      if (serverState.running) { toast("A session is already running.", "error"); return; }
      if (!state.participant.trim()) { toast("Add a participant ID", "error"); return; }
      const debug = isDebug();
      const body = {
        participant: state.participant.trim(), profile: state.profile, personas: cast(), no_tease: state.no_tease,
        motion_intensity: state.motion_intensity, motion_speed: state.motion_speed, camera: state.camera,
        voice_id: state.voice_id, tone: state.tone, chattiness: state.chattiness,
        duration: isPersonas() ? state.duration : null, activities: isPersonas() ? state.activities : state.activities.filter((a) => a === "music_dance"),
        heart_wake: state.heart_wake, language_hint: state.language_hint, llm: true,
        heart: debug ? state.heart : "arduino", heart_port: (debug && state.heart_port) || null,
        conversation: debug ? state.conversation : "realtime", listener: debug ? state.listener : "elevenlabs",
        voice: debug ? state.voice : "elevenlabs", time_scale: debug ? Number(state.time_scale) : 1,
      };
      btn.disabled = true;
      btn.textContent = "Starting…";
      try { await api("/api/session/start", body); location.hash = "#/session"; }
      catch (e) { toast(e.message, "error"); btn.disabled = false; btn.textContent = "Start session"; }
    }

    function draw(animate) {
      const s = STEPS[state.step];
      root.style.setProperty("--accent", s.color);
      setCrumbs([{ label: "Main menu", href: "#/menu" }, "New session", `${state.step + 1} · ${s.label}`]);
      track.replaceChildren(...STEPS.map((st, i) => h("li", { class: `${i === state.step ? "is-current" : ""}${i < state.step ? " is-done" : ""}`, style: { "--c": st.color } },
        h("button", { type: "button", onclick: () => go(i), "aria-current": i === state.step ? "step" : null },
          h("span", { class: "track-steps__dot", "aria-hidden": "true" }, i < state.step ? "✓" : i + 1), h("span", { class: "track-steps__label" }, st.label)))));
      const nav = h("div", { class: "creator__nav" },
        h("button", { type: "button", class: "btn", onclick: () => (state.step ? go(state.step - 1) : (location.hash = "#/menu")) }, state.step ? "← Back" : "← Menu"),
        state.step < STEPS.length - 1
          ? h("button", { type: "button", class: "btn btn--primary btn--big", onclick: () => go(state.step + 1) }, `Next: ${STEPS[state.step + 1].label} →`)
          : h("button", { type: "button", class: "btn btn--primary btn--big btn--start", onclick: (ev) => start(ev.currentTarget) }, "▶ Start session"));
      const content = h("div", { class: `creator__panel creator__panel--${s.key}` },
        serverState.running ? h("div", { class: "banner banner--warn" }, "A session is running now. ", h("a", { href: "#/session" }, "Go to it")) : "",
        ...SCREENS[s.key]().flat().filter(Boolean), nav);
      if (animate) swap(screen, content); else screen.replaceChildren(content);
    }

    const onKey = (e) => {
      if (e.target.matches("input, select, textarea")) return;
      if (e.key === "Enter" && !e.target.matches("button, a, [role=radio]")) { e.preventDefault(); if (state.step < STEPS.length - 1) go(state.step + 1); }
      else if (e.key === "Escape") { e.preventDefault(); if (state.step) go(state.step - 1); }
    };
    window.addEventListener("keydown", onKey);
    cleanupKeys = () => window.removeEventListener("keydown", onKey);
    draw(false);
  }
  let cleanupKeys = null;
  return () => { alive = false; cleanupKeys?.(); audio?.pause(); };
}
