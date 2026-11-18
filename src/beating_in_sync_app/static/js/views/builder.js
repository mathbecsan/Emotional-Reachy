/**
 * New session: a four-step wizard.
 *   1 Experience     which interaction (or a saved preset)
 *   2 Personalities  who Reachy becomes, in what order
 *   3 Behaviour      how big and fast it moves, how often it switches, what it reacts to
 *   4 Start          participant, a one-glance summary, start (hardware only in Debug mode)
 */
import { h, toast, isDebug } from "../ui.js";
import { api } from "../api.js";
import { LANGS } from "../constants.js";
import { loadPersonas, personaColor } from "../personas.js";

const STORE = "bis.builder.v2";
const MODE_INFO = {
  flirty: { label: "Flirty", text: "Charming, a little French.", color: "#ff6fb1" },
  teasing: { label: "Teasing", text: "Mock-bored and cheeky.", color: "#b98cff", teases: true },
  offended: { label: "Offended", text: "Sulks and turns away.", color: "#ff9a4d", teases: true },
  scolding: { label: "Scolding", text: "“Hey. Eyes on me.”", color: "#ff4d4d", teases: true },
};
const STEPS = ["Experience", "Personalities", "Behaviour", "Start"];
const SECONDS_PER_EXCHANGE = 13;
const LEVELS = {
  motion_intensity: [[0.5, "Subtle"], [0.8, "Gentle"], [1.0, "Normal"], [1.2, "Dramatic"]],
  motion_speed: [[0.7, "Slow"], [1.0, "Normal"], [1.3, "Fast"]],
};

const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (s) => { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch { /* private window */ } };

export function builderView(outlet, presetId) {
  const root = h("div", { class: "page" }, h("p", { class: "muted" }, "Loading…"));
  outlet.replaceChildren(root);
  let alive = true;
  Promise.all([api("/api/profiles"), loadPersonas(), api("/api/presets").catch(() => []), api("/api/ports").catch(() => []),
    api("/api/state").catch(() => ({}))])
    .then((r) => alive && render(...r))
    .catch((e) => root.replaceChildren(h("p", { class: "muted" }, `Could not load: ${e.message}`)));

  function render(profiles, cat, presets, ports, serverState) {
    const byName = Object.fromEntries(profiles.map((p) => [p.name, p]));
    const defaults = {
      participant: "P01", profile: byName.off_brand_reachy ? "off_brand_reachy" : profiles[0].name,
      personas: null, switch_every: null, heart_wake: true, music: null, no_tease: false, language_hint: "en",
      motion_intensity: 1.0, motion_speed: 1.0, camera: true,
      heart: "arduino", heart_port: "", conversation: "realtime", listener: "elevenlabs", voice: "elevenlabs", llm: true, time_scale: 1,
    };
    const state = { ...defaults, ...load(), step: 0 };
    if (presetId) {
      const p = presets.find((x) => x.id === presetId);
      if (p) Object.assign(state, defaults, { participant: state.participant }, p.options);
    }
    if (!byName[state.profile]) state.profile = defaults.profile;
    const prof = () => byName[state.profile];
    const cast = () => {
      const p = prof();
      if (p.kind !== "personas") return state.personas ?? p.default_selection;
      const list = (state.personas ?? p.default_selection).filter((k) => cat.byKey[k]);
      return list[0] === cat.base ? list : [cat.base, ...list.filter((k) => k !== cat.base)];
    };
    const effectiveCast = () => cast().filter((k) => !(state.no_tease && (cat.byKey[k]?.teases || MODE_INFO[k]?.teases)));
    const persist = () => { const { step, ...rest } = state; save(rest); };
    const set = (patch) => { Object.assign(state, patch); persist(); draw(); };

    const stepper = h("ol", { class: "stepper" });
    const body = h("div", { class: "wizard__body" });
    const nav = h("div", { class: "wizard__nav" });
    root.replaceChildren(
      h("header", { class: "page__head" }, h("div", {}, h("h1", { class: "page__title" }, "New session"),
        h("p", { class: "page__lede" }, "Four quick steps. Your choices are remembered for next time."))),
      serverState.running ? h("div", { class: "banner banner--warn" }, "A session is already running. ", h("a", { href: "#/session" }, "Go to it")) : "",
      stepper, h("section", { class: "card wizard" }, body, nav));

    // ------------------------------------------------------------ steps
    function stepExperience() {
      return [
        h("h2", { class: "wizard__title" }, "What kind of interaction?"),
        h("div", { class: "choice-grid" }, profiles.map((p) => h("button", {
          type: "button", class: `choice${p.name === state.profile ? " is-on" : ""}`, style: { "--accent": p.accent },
          "aria-pressed": String(p.name === state.profile),
          onclick: () => set({ profile: p.name, personas: null, switch_every: null, music: null }),
        }, h("strong", {}, p.display_name), h("span", { class: "choice__text" }, p.description)))),
        presets.length ? h("div", { class: "presets-row" }, h("h3", { class: "wizard__sub" }, "Or start from a saved setup"),
          h("div", { class: "chip-row" }, presets.map((p) => h("button", {
            type: "button", class: "chip-btn", title: p.description || "",
            onclick: () => { Object.assign(state, defaults, { participant: state.participant }, p.options, { step: 3 }); persist(); draw(); toast(`Loaded “${p.name}”`); },
          }, p.name)))) : "",
      ];
    }

    function stepPersonalities() {
      const p = prof();
      if (p.kind !== "personas") {
        const on = new Set(cast());
        return [
          h("h2", { class: "wizard__title" }, "Which persona moves can Reachy use?"),
          h("p", { class: "wizard__hint" }, "Used in the provocation stage. Turn all off for a gentle session."),
          h("div", { class: "toggle-grid" }, p.selectable.map((k) => {
            const m = MODE_INFO[k];
            const blocked = state.no_tease && m.teases;
            return h("button", {
              type: "button", class: `toggle-card${on.has(k) && !blocked ? " is-on" : ""}`, style: { "--accent": m.color }, disabled: blocked,
              "aria-pressed": String(on.has(k)),
              onclick: () => { on.has(k) ? on.delete(k) : on.add(k); set({ personas: p.selectable.filter((x) => on.has(x)) }); },
            }, h("strong", {}, m.label), h("span", { class: "toggle-card__text" }, blocked ? "Off (no teasing)" : m.text));
          })),
        ];
      }
      const list = cast();
      const setCast = (next) => set({ personas: next });
      const move = (i, d) => { const n = [...list]; const j = i + d; if (j < 1 || j >= n.length) return; [n[i], n[j]] = [n[j], n[i]]; setCast(n); };
      let dragFrom = null;
      const items = list.map((k, i) => {
        const pp = cat.byKey[k];
        const locked = i === 0, blocked = state.no_tease && pp.teases;
        return h("li", {
          class: `cast__item${locked ? " is-locked" : ""}${blocked ? " is-blocked" : ""}`, style: { "--accent": pp.color },
          draggable: locked ? null : "true",
          ondragstart: () => { dragFrom = i; }, ondragover: (ev) => { if (!locked && dragFrom != null) ev.preventDefault(); },
          ondrop: (ev) => { ev.preventDefault(); if (dragFrom == null || locked) return; const n = [...list]; const [x] = n.splice(dragFrom, 1); n.splice(i, 0, x); dragFrom = null; setCast(n); },
        },
        h("span", { class: "cast__n" }, i + 1), h("span", { class: "cast__dot", "aria-hidden": "true" }),
        h("span", { class: "cast__name" }, pp.name, blocked ? h("small", {}, " · skipped") : ""),
        h("span", { class: "cast__mood" }, locked ? "Opens and closes every session" : pp.mood),
        locked ? h("span", { class: "chip" }, "always") : h("span", { class: "cast__btns" },
          h("button", { type: "button", class: "icon-btn", "aria-label": `Move ${pp.name} up`, disabled: i <= 1, onclick: () => move(i, -1) }, "↑"),
          h("button", { type: "button", class: "icon-btn", "aria-label": `Move ${pp.name} down`, disabled: i === list.length - 1, onclick: () => move(i, 1) }, "↓"),
          h("button", { type: "button", class: "icon-btn", "aria-label": `Remove ${pp.name}`, onclick: () => setCast(list.filter((x) => x !== k)) }, "×")));
      });
      const available = cat.personas.filter((pp) => !list.includes(pp.key));
      return [
        h("div", { class: "wizard__titlerow" }, h("h2", { class: "wizard__title" }, "Who does Reachy become?"),
          h("a", { class: "link-sm", href: "#/personalities", target: "_blank" }, "About each personality ↗")),
        h("div", { class: "cast-cols" },
          h("div", {},
            h("h3", { class: "wizard__sub" }, `In this session · ${list.length}`),
            h("ol", { class: "cast" }, items),
            h("div", { class: "chip-row" },
              h("button", { type: "button", class: "chip-btn", onclick: () => setCast([...cat.default_order]) }, "Suggested order"),
              h("button", { type: "button", class: "chip-btn", onclick: () => setCast([cat.base, ...list.slice(1).sort(() => Math.random() - 0.5)]) }, "Shuffle"),
              h("button", { type: "button", class: "chip-btn", onclick: () => setCast([cat.base]) }, "Clear"))),
          h("div", {},
            h("h3", { class: "wizard__sub" }, available.length ? "Tap to add" : "All personalities added"),
            h("div", { class: "pick-grid" }, available.map((pp) => h("button", {
              type: "button", class: "persona-pick", style: { "--accent": pp.color }, onclick: () => setCast([...list, pp.key]),
            }, h("span", { class: "persona-pick__top" }, h("strong", {}, pp.name), h("span", { class: "persona-pick__add" }, "+")),
            h("q", { class: "persona-pick__line" }, pp.sample),
            pp.teases ? h("span", { class: "persona-pick__tags" }, h("span", { class: "chip chip--warn" }, "teases")) : ""))))),
      ];
    }

    function segmented(key, label, hint) {
      return h("div", { class: "setting" },
        h("div", { class: "setting__label" }, h("strong", {}, label), h("span", {}, hint)),
        h("div", { class: "segmented", role: "radiogroup", "aria-label": label }, LEVELS[key].map(([v, name]) => h("button", {
          type: "button", role: "radio", "aria-checked": String(Math.abs(state[key] - v) < 0.01),
          class: Math.abs(state[key] - v) < 0.01 ? "is-on" : "", onclick: () => set({ [key]: v }),
        }, name))));
    }

    function toggle(label, hint, checked, onchange) {
      return h("label", { class: "setting setting--toggle" },
        h("div", { class: "setting__label" }, h("strong", {}, label), h("span", {}, hint)),
        h("span", { class: "switch" }, h("input", { type: "checkbox", checked, onchange: (ev) => onchange(ev.target.checked) }),
          h("span", { class: "switch__ui", "aria-hidden": "true" })));
    }

    function stepBehaviour() {
      const p = prof();
      const n = state.switch_every ?? p.switch_every;
      return [
        h("h2", { class: "wizard__title" }, "How does Reachy behave?"),
        h("div", { class: "settings" },
          h("h3", { class: "wizard__sub" }, "Movement"),
          segmented("motion_intensity", "Size of gestures", "How big the head, antenna and body moves are."),
          segmented("motion_speed", "Speed of gestures", "How fast each move plays."),
          p.kind === "personas" ? [
            h("h3", { class: "wizard__sub" }, "Conversation"),
            h("div", { class: "setting" },
              h("div", { class: "setting__label" }, h("strong", {}, "Switch personality every"), h("span", {}, "Participant replies before Reachy glitches into the next one.")),
              h("div", { class: "segmented" }, [2, 3, 4, 5, 6].map((v) => h("button", {
                type: "button", class: v === n ? "is-on" : "", "aria-pressed": String(v === n), onclick: () => set({ switch_every: v }),
              }, String(v))))),
          ] : h("h3", { class: "wizard__sub" }, "Conversation"),
          toggle("Teasing allowed", "Off skips every personality that teases (for participants who opt out).", !state.no_tease, (v) => set({ no_tease: !v })),
          h("h3", { class: "wizard__sub" }, "Senses"),
          toggle("Wake up with a heartbeat", "Reachy sleeps and snores until a finger is on a pulse sensor.", state.heart_wake, (v) => set({ heart_wake: v })),
          toggle("React to the face", "Reachy notices smiles, looking away and moving, using the camera.", state.camera, (v) => set({ camera: v })),
          toggle("Music and dance", "A song in their language, then Reachy invites them to dance.", state.music ?? p.music, (v) => set({ music: v }))),
      ];
    }

    function stepStart() {
      const p = prof();
      const c = effectiveCast();
      const n = state.switch_every ?? p.switch_every;
      const minutes = p.kind === "personas" ? Math.max(2, Math.round((c.length * n * SECONDS_PER_EXCHANGE + (state.heart_wake ? 100 : 20)) / 60)) : 15;
      const level = (key) => LEVELS[key].reduce((a, b) => (Math.abs(b[0] - state[key]) < Math.abs(a[0] - state[key]) ? b : a))[1];
      const sel = (key, opts) => h("select", { onchange: (ev) => set({ [key]: ev.target.value }) },
        opts.map(([v, label]) => h("option", { value: v, selected: String(state[key]) === String(v) }, label)));
      const field = (label, input) => h("label", { class: "field" }, h("span", { class: "field__label" }, label), input);
      const nameIn = h("input", { placeholder: "Name this setup", "aria-label": "Preset name" });
      return [
        h("h2", { class: "wizard__title" }, "Ready to start"),
        h("div", { class: "start-grid" },
          field("Participant ID", h("input", { value: state.participant, autocomplete: "off", oninput: (ev) => { state.participant = ev.target.value; persist(); } })),
          field("Reachy starts in", h("select", { onchange: (ev) => set({ language_hint: ev.target.value }) },
            Object.entries(LANGS).map(([k, v]) => h("option", { value: k, selected: k === state.language_hint }, v))))),
        h("div", { class: "review" },
          h("div", { class: "review__row" }, h("span", {}, "Experience"), h("strong", {}, p.display_name), h("button", { type: "button", class: "link-sm", onclick: () => set({ step: 0 }) }, "Change")),
          h("div", { class: "review__row" }, h("span", {}, "Personalities"),
            h("span", { class: "review__cast" }, c.length ? c.map((k) => h("span", { class: "dot-chip", style: { "--accent": p.kind === "personas" ? personaColor(k) : MODE_INFO[k].color } },
              p.kind === "personas" ? cat.byKey[k].name : MODE_INFO[k].label)) : "None (gentle)"),
            h("button", { type: "button", class: "link-sm", onclick: () => set({ step: 1 }) }, "Change")),
          h("div", { class: "review__row" }, h("span", {}, "Behaviour"),
            h("strong", {}, [`${level("motion_intensity")} gestures`, `${level("motion_speed").toLowerCase()} speed`,
              p.kind === "personas" ? `switch every ${n}` : null, state.no_tease ? "no teasing" : null].filter(Boolean).join(" · ")),
            h("button", { type: "button", class: "link-sm", onclick: () => set({ step: 2 }) }, "Change")),
          h("div", { class: "review__row" }, h("span", {}, "Senses"),
            h("strong", {}, [state.heart_wake ? "heartbeat wake-up" : "starts awake", state.camera ? "face reactions" : "no camera",
              (state.music ?? p.music) ? "music" : null].filter(Boolean).join(" · ")),
            h("button", { type: "button", class: "link-sm", onclick: () => set({ step: 2 }) }, "Change")),
          h("div", { class: "review__row" }, h("span", {}, "Length"), h("strong", {}, `about ${minutes} minutes`), h("span", {}))),
        isDebug() ? h("details", { class: "advanced", open: true },
          h("summary", {}, "Hardware & engines (Debug)"),
          h("div", { class: "start-grid" },
            field("Heart", sel("heart", [["arduino", "Arduino pulse sensors"], ["sim", "Simulated heart"], ["arduino-sim", "Arduino pipeline, simulated signal"]])),
            state.heart === "arduino" ? field("Sensor port", sel("heart_port", [["", "Auto-detect"], ...ports.map((x) => [x.device, `${x.device}${x.busy ? " (in use)" : ""}`])])) : "",
            field("Conversation", sel("conversation", [["realtime", "Live (ElevenLabs agent)"], ["scripted", "Scripted / offline"]])),
            field("Participant speech", sel("listener", [["elevenlabs", "Reachy's microphone + typed"], ["web", "Typed only (rehearsal)"], ["mic", "Local Whisper"]])),
            field("Reachy voice", sel("voice", [["elevenlabs", "ElevenLabs on Reachy"], ["mac", "macOS voice"], ["sim", "Silent (text only)"]])),
            field("Clock", sel("time_scale", [[1, "Real time"], [2, "2×"], [5, "5×"], [10, "10×"]])))) : "",
        h("div", { class: "save-row" }, nameIn, h("button", { type: "button", class: "btn btn--small", onclick: async () => {
          const name = nameIn.value.trim();
          if (!name) { nameIn.focus(); return; }
          const { participant, step, ...options } = state;
          options.personas = cast();
          try { await api("/api/presets", { name, description: `${p.display_name} · ${c.length} personalities`, options }); toast(`Saved “${name}”`); presets = await api("/api/presets"); }
          catch (e) { toast(e.message, "error"); }
        } }, "Save setup")),
      ];
    }

    async function start(btn) {
      if (serverState.running) { toast("A session is already running.", "error"); return; }
      if (!state.participant.trim()) { toast("Add a participant ID", "error"); set({ step: 3 }); return; }
      const p = prof();
      const debug = isDebug();
      const body = {
        participant: state.participant.trim(), profile: state.profile, personas: cast(),
        switch_every: p.kind === "personas" ? (state.switch_every ?? p.switch_every) : null,
        heart_wake: state.heart_wake, music: state.music ?? p.music, no_tease: state.no_tease, language_hint: state.language_hint,
        motion_intensity: state.motion_intensity, motion_speed: state.motion_speed, camera: state.camera,
        heart: debug ? state.heart : "arduino", heart_port: (debug && state.heart_port) || null,
        conversation: debug ? state.conversation : "realtime", listener: debug ? state.listener : "elevenlabs",
        voice: debug ? state.voice : "elevenlabs", llm: true, time_scale: debug ? Number(state.time_scale) : 1,
      };
      btn.disabled = true;
      try { await api("/api/session/start", body); location.hash = "#/session"; }
      catch (e) { toast(e.message, "error"); btn.disabled = false; }
    }

    function draw() {
      stepper.replaceChildren(...STEPS.map((name, i) => h("li", {},
        h("button", { type: "button", class: `stepper__item${i === state.step ? " is-current" : i < state.step ? " is-done" : ""}`,
          "aria-current": i === state.step ? "step" : null, onclick: () => set({ step: i }) },
        h("span", { class: "stepper__n" }, i < state.step ? "✓" : i + 1), name))));
      body.replaceChildren(...[stepExperience, stepPersonalities, stepBehaviour, stepStart][state.step]().flat().filter(Boolean));
      const back = h("button", { type: "button", class: "btn", disabled: state.step === 0, onclick: () => set({ step: state.step - 1 }) }, "← Back");
      const next = state.step < 3
        ? h("button", { type: "button", class: "btn btn--primary", onclick: () => set({ step: state.step + 1 }) }, `Next: ${STEPS[state.step + 1]} →`)
        : h("button", { type: "button", class: "btn btn--primary btn--big", onclick: (ev) => start(ev.currentTarget) }, "Start session");
      nav.replaceChildren(back, next);
    }
    draw();
  }
  return () => { alive = false; };
}
