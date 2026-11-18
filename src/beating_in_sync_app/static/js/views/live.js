/**
 * Live view: what the facilitator and observer keep in front of them.
 * Left: Reachy (mode / act / why), heart, sensors. Right: conversation,
 * participant model, controls. A start form replaces it when idle.
 */
import { h, toast } from "../ui.js";
import { api, command, say, onEvent } from "../api.js";
import { MODES, LANGS, BPM_STOP } from "../constants.js";
import { heartChart } from "../components/heart-chart.js";
import { reachyFace } from "../components/reachy-face.js";
import { stageTimeline } from "../components/stage-timeline.js";
import { transcript } from "../components/transcript.js";
import { sensorPanel } from "../components/sensor-panel.js";
import { personaStrip } from "../components/persona-strip.js";

function idlePanel() {
  const presets = h("div", { class: "idle__presets" });
  api("/api/presets").then((ps) => presets.replaceChildren(...ps.map((p) => h("a", { class: "idle__preset", href: `#/build/${encodeURIComponent(p.id)}` },
    h("strong", {}, p.name), p.description ? h("small", {}, p.description) : null)))).catch(() => {});
  return h("section", { class: "start card idle" },
    h("div", { class: "idle__head" },
      h("div", {}, h("h2", { class: "card__title" }, "No session running"),
        h("p", { class: "start__lede" }, "Build a session: pick the script, the personalities and their order, the participant and the hardware. Reachy starts asleep; a heartbeat wakes it.")),
      h("a", { class: "btn btn--primary", href: "#/build" }, "Build a session")),
    h("h3", { class: "card__sub" }, "Or start from a preset"), presets);
}

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
  const face = reachyFace();
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

  const layout = h("div", { class: "live" },
    timeline.el,
    banner,
    strip.el,
    h("div", { class: "live__cols" },
      h("div", { class: "live__left" },
        h("section", { class: "card mode" }, face.el,
          h("div", { class: "mode__text" }, h("div", {}, modeName, modeAct), modeWhy)),
        h("section", { class: "card heart" },
          h("div", { class: "heart__head" }, h("h2", { class: "card__title" }, "Heart"), h("div", {}, bpmNow, h("span", { class: "heart__unit" }, " BPM")), bpmMeta),
          chart.el, safety),
        sensors.el),
      h("div", { class: "live__right" }, log.el,
        h("section", { class: "card" }, h("h2", { class: "card__title" }, "What Reachy knows"), who),
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
        if (st.stage != null) timeline.set(st.stage, st.stage_started, st.stage_seconds);
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
          banner.replaceChildren(h("span", {}, "Session ended. "), h("a", { href: `#/sessions/${(e.log || "").split("/").pop().replace(".jsonl", "")}` }, "Open the replay"),
            h("span", {}, " · "), h("a", { href: "#/projection" }, "Projection"));
          face.setMode("sleepy"); modeName.textContent = "Asleep"; modeAct.textContent = "";
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
        if (e.skipped) timeline.skip(e.stage);
        chart.addStage(e.t, e.stage);
        log.note(`Stage ${e.stage}${e.skipped ? " skipped" : ""}`, "line--stage");
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
      case "prompt": log.note(e.text, "line--prompt"); toast(e.text); break;
      case "command": log.note(`facilitator: ${e.cmd}`, "line--cmd"); break;
      case "stop": log.note(`STOP — ${e.reason}`, "line--stop"); toast(`Stopped: ${e.reason}`, "error"); break;
      case "sensor": log.note(e.text, "line--prompt"); break;
      case "error": toast(e.message, "error"); break;
    }
  }

  showStart();
  const off = onEvent(handle);
  api("/api/state").then((s) => handle({ kind: "snapshot", ...s })).catch(() => {});
  return () => off();
}
