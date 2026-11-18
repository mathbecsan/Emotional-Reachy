/**
 * Live view: what the facilitator and observer keep in front of them.
 * Left: Reachy (mode / act / why), heart, sensors. Right: conversation,
 * participant model, controls. A start form replaces it when idle.
 */
import { h, toast } from "../ui.js";
import { api, command, say, onEvent } from "../api.js";
import { MODES, LANGS, BPM_STOP } from "../constants.js";
import { heartChart } from "../components/heart-chart.js";
import { stageTimeline } from "../components/stage-timeline.js";
import { transcript } from "../components/transcript.js";
import { sensorPanel } from "../components/sensor-panel.js";
import { personaStrip } from "../components/persona-strip.js";
import { avatar } from "../components/avatar.js";
import { setCrumbs } from "../ui.js";

// Beating in Sync modes shown as the closest costume
const MODE_COSTUME = { sleepy: "grumpy", curious: "base", excited: "hype_bro", flirty: "smitten", teasing: "bored_teen",
  offended: "melodramatic", scolding: "villain", sincere: "base" };

function avatarFace() {
  const el = h("div", { class: "live-avatar" });
  let current = null;
  const setMode = (mode) => {
    const key = MODE_COSTUME[mode] || mode || "grumpy";
    if (key === current) return;
    current = key;
    el.replaceChildren(avatar(key, { size: 150, color: MODES[mode]?.color || "#8a8fbf", animate: mode !== "sleepy" }));
    el.classList.remove("live-avatar--pop"); void el.offsetWidth; el.classList.add("live-avatar--pop");
  };
  setMode("sleepy");
  return { el, setMode, speak(on) { el.classList.toggle("is-speaking", on); }, listen(on) { el.classList.toggle("is-listening", on); } };
}

function idlePanel() {
  return h("section", { class: "card idle" },
    h("h2", { class: "idle__title" }, "No session running"),
    h("p", { class: "muted" }, "Check the setup, then start a new session."),
    h("div", { class: "btn-row" },
      h("a", { class: "btn btn--primary btn--big", href: "#/new" }, "New session"),
      h("a", { class: "btn btn--big", href: "#/check" }, "Setup checklist")));
}

const STATUS = {
  0: "Asleep · ask the participant to rest a finger on a pulse sensor",
  1: "Waking up…", 2: "Getting to know the participant", 3: "In conversation", 4: "In conversation",
  5: "Music and dance", 6: "Saying goodbye", 7: "Finished",
};

function controls(getLang) {
  const btn = (label, cmd, cls = "", title = "") => h("button", {
    class: `btn ${cls}`, type: "button", title,
    onclick: () => command(cmd).catch((e) => toast(e.message, "error")),
  }, label);
  const text = h("input", { class: "say__input", placeholder: "What the participant says…", autocomplete: "off" });
  const lang = h("select", { class: "say__lang", "aria-label": "Language" },
    Object.entries(LANGS).map(([k, v]) => h("option", { value: k }, v)));
  const sayForm = h("form", { class: "say" }, lang, text, h("button", { class: "btn btn--primary", type: "submit" }, "Say"));
  sayForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    if (!text.value.trim()) return;
    say(text.value.trim(), lang.value).then(() => { text.value = ""; }).catch((e) => toast(e.message, "error"));
  });
  const root = h("section", { class: "card controls" },
    h("h2", { class: "card__title" }, "Facilitator"),
    h("div", { class: "btn-row" },
      btn("Next stage", "/next", "", "Advance if Reachy stalls"),
      btn("Scold now", "/scold", "", "Manual attention trigger if the camera check is unreliable"),
      btn("Pause", "/pause", "btn--danger", "Stop word: Reachy drops the act, says a sincere goodbye, sleeps")),
    h("h3", { class: "card__sub" }, "Pulse sensor (simulated)"),
    h("div", { class: "btn-row" },
      btn("♥ Finger on sensor", "/finger on", "btn--primary", "Participant puts their finger on the sensor: Reachy snores, then wakes"),
      btn("Finger off", "/finger off", "", "Participant lets go: mid-session Reachy asks for their heartbeat back"),
      btn("♥ +15 BPM", "/bpm 15", "", "Simulate a heart-rate jump")),
    h("div", { class: "controls__say" },
      h("h3", { class: "card__sub" }, "Participant (typed — works alongside the mic)"), sayForm),
    h("details", { class: "controls__sim" },
      h("summary", {}, "Simulate senses"),
      h("div", { class: "btn-row" },
        btn("Sensor 2 on", "/hand on"), btn("Sensor 2 off", "/hand off"), btn("Look away", "/look away 4"), btn("Look back", "/look back"),
        btn("2 people", "/people 2"), btn("1 person", "/people 1"),
        btn("Face: happy", "/face happy 0.8"), btn("Face: sad", "/face sad 0.8"), btn("Dancing", "/move 0.7"))));
  return { el: root, setLang(l) { if (l && LANGS[l]) lang.value = l; } };
}

export function liveView(outlet) {
  setCrumbs([{ label: "Main menu", href: "#/menu" }, "Current session"]);
  const face = avatarFace();
  const modeName = h("span", { class: "mode__name" }, "Asleep");
  const modeAct = h("span", { class: "mode__act" });
  const modeWhy = h("p", { class: "mode__why" }, "Waiting for a session.");
  const bpmNow = h("span", { class: "heart__bpm" }, "––");
  const bpmMeta = h("span", { class: "heart__meta" }, "no baseline yet");
  const safety = h("div", { class: "heart__safety", hidden: true });
  const chart = heartChart({ windowSecs: 180 });
  const timeline = stageTimeline();
  const log = transcript();
  const sensors = sensorPanel();
  const strip = personaStrip();
  const who = h("dl", { class: "who" });
  const ctl = controls();
  const banner = h("div", { class: "banner", hidden: true });
  const status = h("p", { class: "live__status" }, "Waiting for a session");
  const actions = h("div", { class: "btn-row live__actions" },
    h("button", { class: "btn", type: "button", title: "Skip ahead (next personality, or next stage)",
      onclick: () => command("/next").catch((e) => toast(e.message, "error")) }, "Skip ahead"),
    h("button", { class: "btn btn--danger", type: "button", title: "Reachy says goodbye kindly and goes to sleep",
      onclick: () => { if (confirm("End the session now? Reachy will say goodbye and go to sleep.")) command("/pause").catch((e) => toast(e.message, "error")); } }, "End session"));
  timeline.el.classList.add("debug-only");
  sensors.el.classList.add("debug-only");
  chart.el.classList.add("debug-only");
  modeWhy.classList.add("debug-only");
  modeAct.classList.add("debug-only");
  bpmMeta.classList.add("debug-only");
  ctl.el.classList.add("debug-only");

  const layout = h("div", { class: "live" },
    timeline.el,
    banner,
    strip.el,
    h("div", { class: "live__cols" },
      h("div", { class: "live__left" },
        h("section", { class: "card mode" }, face.el,
          h("div", { class: "mode__text" }, h("div", {}, modeName, modeAct), status, modeWhy, actions)),
        h("section", { class: "card heart" },
          h("div", { class: "heart__head" }, h("h2", { class: "card__title" }, "Heart"), h("div", {}, bpmNow, h("span", { class: "heart__unit" }, " BPM")), bpmMeta),
          chart.el, safety),
        sensors.el),
      h("div", { class: "live__right" }, log.el,
        h("section", { class: "card debug-only" }, h("h2", { class: "card__title" }, "What Reachy knows"), who),
        ctl.el)));

  const startWrap = h("div", { class: "start-wrap" });
  let running = false, baseline = null, overSince = null;

  function showStart() {
    startWrap.replaceChildren(idlePanel());
    outlet.replaceChildren(startWrap, layout);
    layout.classList.add("live--idle");
  }

  function setRunning(on) {
    running = on;
    startWrap.hidden = on;
    layout.classList.toggle("live--idle", !on);
  }

  function renderUser(u) {
    if (!u) return;
    const row = (k, v) => [h("dt", {}, k), h("dd", {}, v ?? "—")];
    who.replaceChildren(
      ...row("Name", u.name ? `${u.name}${u.name_confirmed ? " ✓" : " ?"}` : null),
      ...row("Language", `${LANGS[u.language] || u.language}${u.language_confirmed ? " ✓" : ""}`),
      ...row("Loves", (u.loves || []).join(" · ") || null),
      ...row("Remembers", (u.facts || []).join(" · ") || null),
      ...row("Talks", u.talkativeness),
      ...row("Laughed / silent", `${u.laughed} / ${u.silences}`),
      ...row("Discomfort", u.discomfort_count ? `${u.discomfort_count} (provocation off at 2)` : "0"),
      ...row("Teasing", u.no_tease ? "off (pre-interview)" : "allowed"),
      ...row("Heart moments", (u.heart_moments || []).join(" · ") || null));
  }

  function handle(e) {
    switch (e.kind) {
      case "snapshot": {
        setRunning(!!e.running);
        const st = e.state || {};
        if (st.stage != null) { timeline.set(st.stage, st.stage_started, st.stage_seconds); if (e.running) status.textContent = STATUS[st.stage] || ""; }
        if (st.mode) { face.setMode(st.mode); modeName.textContent = MODES[st.mode]?.label || st.mode; modeAct.textContent = ` · ${st.act}`; modeWhy.textContent = st.why; }
        renderUser(st.user);
        for (const ev of e.recent || []) replayInto(ev);
        break;
      }
      case "session":
        if (e.status === "running") {
          chart.reset(); log.reset(); timeline.reset(); sensors.reset(); strip.reset(); baseline = null;
          banner.hidden = true; ctl.setLang(e.language_hint);
          setRunning(true);
        } else {
          setRunning(false);
          banner.hidden = false;
          banner.replaceChildren(h("span", {}, "Session ended. "), h("a", { href: `#/results/${(e.log || "").split("/").pop().replace(".jsonl", "")}` }, "Open the replay"),
            h("span", {}, " · "), h("a", { href: "#/projection" }, "Projection"));
          face.setMode("sleepy"); modeName.textContent = "Asleep"; modeAct.textContent = "";
          status.textContent = "Session finished";
          showStart();
        }
        break;
      case "heart":
        chart.addSample(e.t, e.bpm);
        bpmNow.textContent = Math.round(e.bpm);
        bpmNow.classList.toggle("heart__bpm--high", e.bpm >= BPM_STOP);
        if (e.bpm >= BPM_STOP) {
          overSince ??= e.t;
          safety.hidden = false;
          safety.textContent = `Above ${BPM_STOP} BPM for ${Math.round(e.t - overSince)} s (auto-stop at 30 s)`;
        } else { overSince = null; safety.hidden = true; }
        if (baseline) {
          const d = e.bpm - baseline;
          bpmMeta.textContent = `baseline ${Math.round(baseline)} · ${d >= 0 ? "+" : ""}${Math.round(d)}`;
        }
        document.querySelector("[data-component=pulse-dot]")?.animate(
          [{ transform: "scale(1.6)" }, { transform: "scale(1)" }], { duration: 300 });
        break;
      case "pulse": sensors.update(e); break;
      default: replayInto(e);
    }
  }

  function replayInto(e) {
    switch (e.kind) {
      case "stage":
        timeline.set(e.stage, e.ts, e.seconds);
        status.textContent = STATUS[e.stage] || "";
        if (e.skipped) timeline.skip(e.stage);
        chart.addStage(e.t, e.stage);
        log.note(`Stage ${e.stage}${e.skipped ? " skipped" : ""}`, "line--stage line--debug");
        break;
      case "stage_clock": timeline.set(e.stage, e.ts, e.seconds); break;
      case "cast": strip.setCast(e.cast); break;
      case "persona":
        strip.setPersona(e);
        if (e.reason !== "start") log.note(`${e.reset ? "Back to" : "Glitch →"} ${MODES[e.persona]?.label || e.persona} (${e.reason})`, "line--stage");
        break;
      case "baseline": baseline = e.bpm; chart.setBaseline(e.bpm); bpmMeta.textContent = `baseline ${Math.round(e.bpm || 0)}`; break;
      case "turn":
        log.turn(e);
        chart.addTurn(e);
        face.setMode(e.mode);
        modeName.textContent = MODES[e.mode]?.label || e.mode;
        modeAct.textContent = ` · ${e.act}`;
        modeWhy.textContent = e.why || "";
        layout.style.setProperty("--mode", MODES[e.mode]?.color || "#fff");
        break;
      case "say": log.reachy(e); face.speak(true); face.listen(false); break;
      case "listening": face.listen(true); break;
      case "heard": face.listen(false); log.participant(e); break;
      case "user": renderUser(e.user); break;
      case "prompt": log.note(e.text, "line--prompt"); break;
      case "command": log.note(`facilitator: ${e.cmd}`, "line--cmd"); break;
      case "stop": log.note(`STOP — ${e.reason}`, "line--stop"); toast(`Stopped: ${e.reason}`, "error"); break;
      case "sound": log.note(`♫ ${e.text}`, "line--stage"); break;
      case "sensor":
        log.note(e.text, "line--prompt");
        if (/starts snoring/.test(e.text)) status.textContent = "Snoring · learning their resting heartbeat (about a minute)";
        if (/unavailable|not found/i.test(e.text)) toast(e.text, "error");
        break;
      case "error": toast(e.message, "error"); break;
    }
  }

  showStart();
  const off = onEvent(handle);
  api("/api/state").then((s) => handle({ kind: "snapshot", ...s })).catch(() => {});
  return () => off();
}
