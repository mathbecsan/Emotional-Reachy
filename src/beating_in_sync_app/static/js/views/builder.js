/**
 * Session builder: pick the script, choose which personalities take part (and
 * in what order), set the flow and the hardware, save it as a preset, start.
 * Usable by facilitators and, on the Personalities step, by participants.
 */
import { h, toast } from "../ui.js";
import { api } from "../api.js";
import { LANGS } from "../constants.js";
import { loadPersonas, personaColor } from "../personas.js";

const STORE = "bis.builder.v1";
const MODE_INFO = {
  flirty: { label: "Flirty", text: "Charm about their voice and words, a little French.", color: "#ff6fb1" },
  teasing: { label: "Teasing", text: "Mock-bored and cheeky; invites them to talk back.", color: "#b98cff", teases: true },
  offended: { label: "Offended", text: "Theatrical sulk, wounded pride, turns away.", color: "#ff9a4d", teases: true },
  scolding: { label: "Scolding", text: "Short and sharp, only about attention: “Eyes on me.”", color: "#ff4d4d", teases: true },
};
const SECONDS_PER_EXCHANGE = 13;

const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch { return {}; } };
const save = (s) => { try { localStorage.setItem(STORE, JSON.stringify(s)); } catch { /* private window */ } };

export function builderView(outlet, presetId) {
  const root = h("div", { class: "builder" }, h("p", { class: "muted" }, "Loading…"));
  outlet.replaceChildren(root);
  let alive = true;

  Promise.all([api("/api/profiles"), loadPersonas(), api("/api/presets").catch(() => []), api("/api/ports").catch(() => []),
    api("/api/state").catch(() => ({}))])
    .then(([profiles, cat, presets, ports, st]) => { if (alive) render(profiles, cat, presets, ports, st, presetId); })
    .catch((e) => root.replaceChildren(h("p", { class: "muted" }, `Could not load: ${e.message}`)));

  function render(profiles, cat, presets, ports, serverState, presetId) {
    const byName = Object.fromEntries(profiles.map((p) => [p.name, p]));
    const defaults = {
      participant: "P01", profile: byName.off_brand_reachy ? "off_brand_reachy" : profiles[0].name,
      personas: null, switch_every: null, heart_wake: true, music: null, no_tease: false, language_hint: "en",
      heart: "arduino", heart_port: "", conversation: "realtime", listener: "elevenlabs", voice: "elevenlabs",
      camera: true, llm: true, time_scale: 1,
    };
    const state = { ...defaults, ...load() };
    if (!byName[state.profile]) state.profile = defaults.profile;
    const prof = () => byName[state.profile];
    const cast = () => state.personas ?? prof().default_selection;
    const persist = () => save({ ...state, participant: state.participant });

    const sections = h("div", { class: "builder__main" });
    const side = h("aside", { class: "builder__side card" });
    root.replaceChildren(h("div", { class: "builder__head" },
      h("div", {}, h("h1", { class: "page__title" }, "Build a session"),
        h("p", { class: "muted page__lede" }, "Choose the script, the personalities that take part and their order, then start. Saved presets make test conditions repeatable.")),
      h("a", { class: "btn", href: "#/personas" }, "Browse personalities →")),
    h("div", { class: "builder__cols" }, sections, side));

    function applyPreset(p) {
      Object.assign(state, defaults, { participant: state.participant }, p.options);
      persist(); draw();
      toast(`Loaded “${p.name}”`);
    }

    // ------------------------------------------------------------- 1. script
    function scriptCard() {
      return h("section", { class: "card step" },
        h("h2", { class: "step__title" }, h("span", { class: "step__n" }, "1"), "Script"),
        h("div", { class: "choice-grid" }, profiles.map((p) => h("button", {
          type: "button", class: `choice${p.name === state.profile ? " is-on" : ""}`, style: { "--accent": p.accent },
          "aria-pressed": String(p.name === state.profile),
          onclick: () => { state.profile = p.name; state.personas = null; state.switch_every = null; state.music = null; persist(); draw(); },
        }, h("strong", {}, p.display_name), h("span", { class: "choice__text" }, p.description),
        h("span", { class: "chip" }, p.kind === "personas" ? "persona interview" : "protocol stages 0–7")))));
    }

    // ------------------------------------------------------------- 2. personalities
    function personaStep() {
      const p = prof();
      const box = h("section", { class: "card step" },
        h("h2", { class: "step__title" }, h("span", { class: "step__n" }, "2"), "Personalities"));
      if (p.kind !== "personas") {
        const on = new Set(cast());
        box.append(h("p", { class: "muted" }, "Persona moves Reachy may use in the provocation stage. Leave all off for a gentle session (stage 4 is skipped)."),
          h("div", { class: "toggle-grid" }, p.selectable.map((k) => {
            const m = MODE_INFO[k];
            const disabled = state.no_tease && m.teases;
            return h("button", {
              type: "button", class: `toggle-card${on.has(k) && !disabled ? " is-on" : ""}`, style: { "--accent": m.color },
              disabled, "aria-pressed": String(on.has(k)),
              onclick: () => { on.has(k) ? on.delete(k) : on.add(k); state.personas = p.selectable.filter((x) => on.has(x)); persist(); draw(); },
            }, h("strong", {}, m.label), h("span", { class: "toggle-card__text" }, disabled ? "Off: participant prefers no teasing" : m.text));
          })));
        return box;
      }
      const list = cast().filter((k) => cat.byKey[k]);
      if (list[0] !== cat.base) list.unshift(cat.base);
      const setCast = (next) => { state.personas = next; persist(); draw(); };
      const move = (i, d) => { const n = [...list]; const j = i + d; if (j < 1 || j >= n.length) return; [n[i], n[j]] = [n[j], n[i]]; setCast(n); };
      let dragFrom = null;
      const castList = h("ol", { class: "cast" }, list.map((k, i) => {
        const pp = cat.byKey[k];
        const locked = i === 0;
        const blocked = state.no_tease && pp.teases;
        const li = h("li", {
          class: `cast__item${locked ? " is-locked" : ""}${blocked ? " is-blocked" : ""}`, style: { "--accent": pp.color },
          draggable: locked ? null : "true",
          ondragstart: (ev) => { dragFrom = i; ev.dataTransfer.effectAllowed = "move"; li.classList.add("is-drag"); },
          ondragend: () => li.classList.remove("is-drag"),
          ondragover: (ev) => { if (!locked && dragFrom != null) ev.preventDefault(); },
          ondrop: (ev) => { ev.preventDefault(); if (dragFrom == null || locked) return; const n = [...list]; const [x] = n.splice(dragFrom, 1); n.splice(i, 0, x); dragFrom = null; setCast(n); },
        },
        h("span", { class: "cast__n" }, i + 1),
        h("span", { class: "cast__dot", "aria-hidden": "true" }),
        h("span", { class: "cast__name" }, pp.name, blocked ? h("small", {}, " · skipped (no teasing)") : null),
        h("span", { class: "cast__mood" }, locked ? "opens, closes, and catches resets" : pp.mood),
        locked ? h("span", { class: "chip" }, "always on") : h("span", { class: "cast__btns" },
          h("button", { type: "button", class: "icon-btn", title: "Move up", "aria-label": `Move ${pp.name} up`, disabled: i <= 1, onclick: () => move(i, -1) }, "↑"),
          h("button", { type: "button", class: "icon-btn", title: "Move down", "aria-label": `Move ${pp.name} down`, disabled: i === list.length - 1, onclick: () => move(i, 1) }, "↓"),
          h("button", { type: "button", class: "icon-btn", title: "Remove", "aria-label": `Remove ${pp.name}`, onclick: () => setCast(list.filter((x) => x !== k)) }, "×")));
        return li;
      }));
      const available = cat.personas.filter((pp) => !list.includes(pp.key));
      const card = (pp) => h("button", {
        type: "button", class: "persona-pick", style: { "--accent": pp.color },
        title: `Add ${pp.name}`, onclick: () => setCast([...list, pp.key]),
      },
      h("span", { class: "persona-pick__top" }, h("strong", {}, pp.name), h("span", { class: "persona-pick__add" }, "+ Add")),
      h("span", { class: "persona-pick__mood" }, pp.mood),
      h("q", { class: "persona-pick__line" }, pp.sample),
      h("span", { class: "persona-pick__tags" },
        h("span", { class: "chip" }, pp.energy === "high" ? "high energy" : "low energy"),
        pp.teases ? h("span", { class: "chip chip--warn" }, "teases") : null,
        pp.fragile ? h("span", { class: "chip" }, "sad / anxious") : null,
        pp.experimental ? h("span", { class: "chip chip--dim" }, "idea bank") : null));
      const n = state.switch_every ?? p.switch_every;
      const minutes = Math.max(1, Math.round((list.length * n * SECONDS_PER_EXCHANGE + 40) / 60));
      const slider = h("input", { type: "range", min: 2, max: 8, value: n, "aria-label": "Exchanges per persona",
        oninput: (ev) => { state.switch_every = Number(ev.target.value); persist(); draw(); } });
      box.append(
        h("div", { class: "cast-tools" },
          h("span", { class: "muted" }, `${list.length} personalities · about ${minutes} min`),
          h("span", { class: "btn-row" },
            h("button", { type: "button", class: "btn btn--small", onclick: () => setCast([...cat.default_order]) }, "Suggested order"),
            h("button", { type: "button", class: "btn btn--small", onclick: () => setCast([cat.base, ...list.slice(1).sort(() => Math.random() - 0.5)]) }, "Shuffle"),
            h("button", { type: "button", class: "btn btn--small", onclick: () => setCast([cat.base]) }, "Only Base"))),
        h("div", { class: "cast-cols" },
          h("div", {}, h("h3", { class: "card__sub" }, "In this session, in order (drag or use the arrows)"), castList,
            h("label", { class: "slider" }, h("span", {}, `Switch persona every `, h("strong", {}, n), ` exchanges`), slider)),
          h("div", {}, h("h3", { class: "card__sub" }, available.length ? "Add a personality" : "Every personality is in the session"),
            h("div", { class: "pick-grid" }, available.map(card)))));
      return box;
    }

    // ------------------------------------------------------------- 3. participant & flow
    function flowStep() {
      const p = prof();
      const participant = h("input", { value: state.participant, autocomplete: "off", "aria-label": "Participant ID",
        oninput: (ev) => { state.participant = ev.target.value; persist(); summary(); } });
      const lang = h("select", { onchange: (ev) => { state.language_hint = ev.target.value; persist(); } },
        Object.entries(LANGS).map(([k, v]) => h("option", { value: k, selected: k === state.language_hint }, v)));
      const check = (key, label, hint, value) => h("label", { class: "switch" },
        h("input", { type: "checkbox", checked: value ?? state[key], onchange: (ev) => { state[key] = ev.target.checked; persist(); draw(); } }),
        h("span", { class: "switch__ui", "aria-hidden": "true" }),
        h("span", {}, h("strong", {}, label), h("small", {}, hint)));
      return h("section", { class: "card step" },
        h("h2", { class: "step__title" }, h("span", { class: "step__n" }, "3"), "Participant & flow"),
        h("div", { class: "start__grid" },
          h("label", { class: "field" }, h("span", { class: "field__label" }, "Participant ID"), participant),
          h("label", { class: "field" }, h("span", { class: "field__label" }, "Start language"), lang)),
        h("div", { class: "switch-list" },
          check("heart_wake", "Heartbeat wake-up", "Reachy sleeps and snores until a finger is on a pulse sensor."),
          check("no_tease", "Would rather not be teased", p.kind === "personas" ? "Teasing personas are skipped." : "Stage 4 provocations are skipped."),
          check("music", "Music & dance stage", "A song in their language, then Reachy invites them to dance.", state.music ?? p.music)));
    }

    // ------------------------------------------------------------- 4. setup
    function setupStep() {
      const sel = (key, opts) => h("select", { onchange: (ev) => { state[key] = ev.target.value; persist(); draw(); } },
        opts.map(([v, label]) => h("option", { value: v, selected: String(state[key]) === String(v) }, label)));
      const field = (label, input, hint) => h("label", { class: "field" }, h("span", { class: "field__label" }, label), input,
        hint ? h("span", { class: "field__hint" }, hint) : null);
      const portSel = sel("heart_port", [["", "auto-detect"], ...ports.map((p) => [p.device, `${p.device}${p.busy ? " (in use)" : ""}`])]);
      const camera = h("input", { type: "checkbox", checked: state.camera, onchange: (ev) => { state.camera = ev.target.checked; persist(); summary(); } });
      const llm = h("input", { type: "checkbox", checked: state.llm, onchange: (ev) => { state.llm = ev.target.checked; persist(); } });
      return h("details", { class: "card step step--setup", open: state._setupOpen || null,
        ontoggle: (ev) => { state._setupOpen = ev.target.open; persist(); } },
      h("summary", { class: "step__title" }, h("span", { class: "step__n" }, "4"), "Hardware & engines",
        h("span", { class: "muted step__peek" }, `${state.heart} · ${state.conversation} · ${state.voice}${state.camera ? " · camera" : ""}`)),
      h("div", { class: "start__grid" },
        field("Heart", sel("heart", [["arduino", "Arduino pulse sensors"], ["sim", "Simulated heart (no hardware)"], ["arduino-sim", "Arduino pipeline, simulated signal"]])),
        state.heart === "arduino" ? field("Serial port", portSel, "Close the Arduino IDE serial monitor first.") : null,
        field("Conversation", sel("conversation", [["realtime", "Live & fluid (ElevenLabs agent)"], ["scripted", "Scripted / offline lines"]]),
          "Live: Reachy listens continuously and improvises in persona."),
        field("Participant speech", sel("listener", [["elevenlabs", "Reachy's microphone + typed"], ["web", "Typed here only (rehearsal)"], ["mic", "Microphone (local Whisper)"]])),
        field("Reachy voice", sel("voice", [["elevenlabs", "ElevenLabs, from Reachy's speaker"], ["mac", "macOS voice"], ["sim", "Text only (silent)"]])),
        field("Clock", sel("time_scale", [[1, "Real time"], [2, "2× faster"], [5, "5× faster"], [10, "10× faster"]]), "Faster clocks are for rehearsals only."),
        h("label", { class: "check" }, camera, " Camera: face emotion + attention"),
        h("label", { class: "check" }, llm, " Claude writes scripted lines (needs ANTHROPIC_API_KEY)")));
    }

    // ------------------------------------------------------------- sidebar
    const summaryBox = h("div", { class: "summary" });
    function summary() {
      const p = prof();
      const list = cast().filter((k) => p.kind !== "personas" || cat.byKey[k]);
      const shown = p.kind === "personas"
        ? (list[0] === cat.base ? list : [cat.base, ...list]).filter((k) => !(state.no_tease && cat.byKey[k]?.teases))
        : list.filter((k) => !(state.no_tease && MODE_INFO[k]?.teases));
      summaryBox.replaceChildren(...[
        h("div", { class: "summary__who" }, h("strong", {}, state.participant || "—"), h("span", { class: "muted" }, ` · ${p.display_name}`)),
        h("ol", { class: "summary__cast" }, shown.map((k) => h("li", { style: { "--accent": p.kind === "personas" ? personaColor(k) : MODE_INFO[k].color } },
          p.kind === "personas" ? cat.byKey[k].name : MODE_INFO[k].label))),
        shown.length ? null : h("p", { class: "muted" }, "No persona moves: a gentle session."),
        h("ul", { class: "summary__flags" },
          h("li", {}, state.heart_wake ? "♥ Wakes on the heartbeat" : "Starts awake (no heartbeat wake)"),
          h("li", {}, (state.music ?? p.music) ? "Music & dance stage" : "No music stage"),
          h("li", {}, state.conversation === "realtime" ? "Live conversation" : "Scripted conversation"),
          state.no_tease ? h("li", {}, "No teasing") : null)].filter(Boolean));
    }

    const startBtn = h("button", { class: "btn btn--primary btn--block", type: "button", onclick: start }, "Start session");
    async function start() {
      if (serverState.running) { toast("A session is already running: stop it on the Live page first.", "error"); return; }
      if (!state.participant.trim()) { toast("Add a participant ID", "error"); return; }
      const p = prof();
      const body = {
        participant: state.participant.trim(), profile: state.profile, personas: cast(),
        switch_every: p.kind === "personas" ? (state.switch_every ?? p.switch_every) : null,
        heart_wake: state.heart_wake, music: state.music ?? p.music, no_tease: state.no_tease,
        language_hint: state.language_hint, heart: state.heart, heart_port: state.heart_port || null,
        conversation: state.conversation, listener: state.listener, voice: state.voice, camera: state.camera,
        llm: state.llm, time_scale: Number(state.time_scale),
      };
      startBtn.disabled = true;
      try {
        await api("/api/session/start", body);
        toast("Session started");
        location.hash = "#/";
      } catch (e) { toast(e.message, "error"); startBtn.disabled = false; }
    }

    function presetsBox() {
      const nameIn = h("input", { placeholder: "Preset name, e.g. Pilot A", "aria-label": "Preset name" });
      const saveBtn = h("button", { class: "btn btn--small", type: "button", onclick: async () => {
        const name = nameIn.value.trim();
        if (!name) { nameIn.focus(); return; }
        const p = prof();
        const options = { profile: state.profile, personas: cast(), switch_every: state.switch_every, heart_wake: state.heart_wake,
          music: state.music ?? p.music, no_tease: state.no_tease, language_hint: state.language_hint, conversation: state.conversation };
        try {
          const saved = await api("/api/presets", { name, description: describe(), options });
          presets = [...presets.filter((x) => x.id !== saved.id), saved].sort((a, b) => a.id.localeCompare(b.id));
          toast(`Saved “${name}”`); draw();
        } catch (e) { toast(e.message, "error"); }
      } }, "Save");
      return h("div", { class: "presets" },
        h("h3", { class: "card__sub" }, "Presets"),
        presets.length ? h("ul", { class: "presets__list" }, presets.map((p) => h("li", {},
          h("button", { type: "button", class: "presets__load", title: p.description || "", onclick: () => applyPreset(p) },
            h("strong", {}, p.name), p.description ? h("small", {}, p.description) : null),
          h("button", { type: "button", class: "icon-btn", "aria-label": `Delete ${p.name}`, title: "Delete preset", onclick: async () => {
            if (!confirm(`Delete the preset “${p.name}”?`)) return;
            await fetch(`/api/presets/${encodeURIComponent(p.id)}`, { method: "DELETE" });
            presets = presets.filter((x) => x.id !== p.id); draw();
          } }, "×")))) : h("p", { class: "muted" }, "No presets yet."),
        h("div", { class: "presets__save" }, nameIn, saveBtn));
    }

    function describe() {
      const p = prof();
      const n = cast().length;
      return p.kind === "personas" ? `${p.display_name}: ${n} personalities, switch every ${state.switch_every ?? p.switch_every}` :
        `${p.display_name}: ${n} persona moves`;
    }

    function draw() {
      sections.replaceChildren(scriptCard(), personaStep(), flowStep(), setupStep());
      summary();
      side.replaceChildren(...[h("h2", { class: "card__title" }, "This session"), summaryBox,
        serverState.running ? h("p", { class: "summary__warn" }, "A session is running now. ", h("a", { href: "#/" }, "Go to Live")) : null,
        startBtn, presetsBox()].filter(Boolean));
    }

    if (presetId) {
      const p = presets.find((x) => x.id === presetId);
      if (p) Object.assign(state, defaults, { participant: state.participant }, p.options);
    }
    draw();
  }

  return () => { alive = false; };
}
