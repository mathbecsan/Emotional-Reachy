/**
 * Live view: what the facilitator and observer keep in front of them.
 * Left: Reachy (mode / act / why), heart, sensors. Right: conversation,
 * participant model, controls. A start form replaces it when idle.
 */
import { h, toast } from "../ui.js";
import { api, command, say, onEvent } from "../api.js";
import { MODES, LANGS, BPM_STOP, LATENCY_BUDGET } from "../constants.js";
import { heartChart } from "../components/heart-chart.js";
import { stageTimeline } from "../components/stage-timeline.js";
import { transcript } from "../components/transcript.js";
import { sensorPanel } from "../components/sensor-panel.js";
import { personaStrip } from "../components/persona-strip.js";
import { avatar } from "../components/avatar.js";
import { setCrumbs } from "../ui.js";
import { setupGate } from "../components/setup-gate.js";

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
      h("a", { class: "btn btn--primary btn--big", href: "#/new", onclick: (e) => { e.preventDefault(); setupGate(); } }, "New session"),
      h("a", { class: "btn btn--big", href: "#/check" }, "Setup checklist")));
}

const STATUS = {
  0: "Asleep · waiting for a fingertip on a pulse sensor",
  1: "Waking up…", 2: "Introductions · Base Reachy", 3: "In conversation", 4: "In conversation",
  5: "Music and dance", 6: "Saying goodbye", 7: "Finished",
};

/** Latency card (session flow v2, section 4): how fast Reachy answers, against the budget. */
function latencyCard() {
  const rows = { contact_to_wake: "Fingertip → wake", first_word: "Wake → first word", reply: "Last reply", avg: "Average reply" };
  const cells = {};
  const dl = h("dl", { class: "latency" }, Object.entries(rows).flatMap(([k, label]) => {
    cells[k] = h("dd", {}, "—");
    return [h("dt", {}, label), cells[k]];
  }));
  const el = h("section", { class: "card debug-only" }, h("h2", { class: "card__title" }, "Latency"), dl);
  let replies = [];
  const show = (key, budgetKey, secs) => {
    const [good, ok] = LATENCY_BUDGET[budgetKey];
    cells[key].textContent = `${secs.toFixed(1)} s`;
    cells[key].className = secs <= good ? "is-good" : secs <= ok ? "is-ok" : "is-slow";
  };
  return {
    el,
    add(e) {
      if (!(e.measure in LATENCY_BUDGET)) return;
      if (e.measure === "reply") {
        replies.push(e.seconds);
        show("reply", "reply", e.seconds);
        show("avg", "reply", replies.reduce((a, b) => a + b, 0) / replies.length);
        cells.avg.textContent += ` (${replies.length})`;
      } else show(e.measure, e.measure, e.seconds);
    },
    reset() { replies = []; Object.values(cells).forEach((c) => { c.textContent = "—"; c.className = ""; }); },
  };
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
    h("h3", { class: "card__sub" }, "Pulse sensor (simulated: only in sessions without real sensors)"),
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
  const latency = latencyCard();
  const who = h("dl", { class: "who" });
  const ctl = controls();
  const banner = h("div", { class: "banner", hidden: true });
  const status = h("p", { class: "live__status" }, "Waiting for a session");
  const sensorWarn = h("div", { class: "banner banner--warn", hidden: true, role: "alert" });
  // Planned length reached: Reachy asks whether to keep going; the facilitator can decide too.
  const endingBar = h("div", { class: "banner banner--ending", hidden: true, role: "status" },
    h("span", {}, "⏳ Reachy is about to wrap up: the planned length is reached. It's asking the participant whether to keep talking. "),
    h("button", { class: "btn btn--primary btn--small", type: "button",
      onclick: () => command("/extend").then(() => toast("Another round added")).catch((e) => toast(e.message, "error")) }, "Keep talking"),
    h("button", { class: "btn btn--small", type: "button",
      onclick: () => command("/close").catch((e) => toast(e.message, "error")) }, "Finish now"));
  const actions = h("div", { class: "btn-row live__actions" },
    h("button", { class: "btn", type: "button", title: "Skip ahead: wakes Reachy while it's asleep, then moves on to the next personality",
      onclick: () => command("/next").catch((e) => toast(e.message, "error")) }, "Skip ahead"),
    h("button", { class: "btn btn--danger", type: "button", title: "Reachy says goodbye kindly and goes to sleep",
      onclick: () => { if (confirm("End the session now? Reachy will say goodbye and go to sleep.")) command("/pause").catch((e) => toast(e.message, "error")); } }, "End session"));
  sensors.el.classList.add("debug-only");
  chart.el.classList.add("debug-only");
  modeWhy.classList.add("debug-only");
  modeAct.classList.add("debug-only");
  bpmMeta.classList.add("debug-only");
  ctl.el.classList.add("debug-only");

  const layout = h("div", { class: "live" },
    timeline.el,
    banner,
    sensorWarn,
    endingBar,
    strip.el,
    h("div", { class: "live__cols" },
      h("div", { class: "live__left" },
        h("section", { class: "card mode" }, face.el,
          h("div", { class: "mode__text" }, h("div", {}, modeName, modeAct), status, modeWhy, actions)),
        h("section", { class: "card heart" },
          h("div", { class: "heart__head" }, h("h2", { class: "card__title" }, "Heart"), h("div", {}, bpmNow, h("span", { class: "heart__unit" }, " BPM")), bpmMeta),
          chart.el, safety),
        sensors.el, latency.el),
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

  function clearAll() {
    // Everything on this screen belongs to one session: wipe it so a new session starts from zero.
    chart.reset(); log.reset(); timeline.reset(); sensors.reset(); strip.reset(); latency.reset();
    baseline = null; overSince = null;
    sensorWarn.hidden = true; banner.hidden = true; safety.hidden = true; endingBar.hidden = true;
    bpmNow.textContent = "––"; bpmNow.classList.remove("heart__bpm--high"); bpmMeta.textContent = "no baseline yet";
    who.replaceChildren();
    face.setMode("sleepy"); modeName.textContent = "Asleep"; modeAct.textContent = ""; modeWhy.textContent = "Waiting for a session.";
    status.textContent = "Waiting for a session";
  }

  function handle(e) {
    switch (e.kind) {
      case "snapshot": {
        setRunning(!!e.running);
        const st = e.state || {};
        if (st.stage != null) { timeline.set(st.stage, st.stage_started, st.stage_seconds); if (e.running) status.textContent = STATUS[st.stage] || ""; }
        if (st.mode) { face.setMode(st.mode); modeName.textContent = MODES[st.mode]?.label || st.mode; modeAct.textContent = ` · ${st.act}`; modeWhy.textContent = st.why; }
        if (!e.running) { clearAll(); break; }   // no session: a clean screen (past sessions live in Results)
        renderUser(st.user);
        for (const ev of e.recent || []) replayInto(ev);
        break;
      }
      case "session":
        if (e.status === "starting") {
          clearAll();
          status.textContent = "Starting the session…";
        } else if (e.status === "failed") {
          status.textContent = `Couldn't start the session: ${e.message || "see the server log"}`;
          showStart();
        } else if (e.status === "running") {
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
      case "latency": latency.add(e); break;
      case "ending":
        endingBar.hidden = e.status !== "soon";
        if (e.status === "soon") status.textContent = "Nearly time · asking whether to keep talking";
        if (e.status === "extended") { status.textContent = "Keep talking · another round"; log.note(`Another round added (${e.by})`, "line--stage"); }
        if (e.status === "closing") status.textContent = "Wrapping up";
        break;
      case "tone":
        if ((e.labels || []).length) log.note(`🎙 voice: ${e.labels.join(", ")}${e.mood ? ` (${e.mood})` : ""}`, "line--stage line--debug");
        break;
      case "sensor":
        log.note(e.text, "line--prompt");
        if (/Pulse sensors (unavailable|not answering)/.test(e.text)) {
          const help = /not answering/.test(e.text);
          sensorWarn.hidden = false;
          sensorWarn.replaceChildren(h("strong", {}, help ? "A pulse sensor isn't answering, so Reachy can't feel the heartbeat. "
              : "The pulse sensors aren't connected, so Reachy can't feel the heartbeat yet. "),
            h("span", {}, help ? "Unplug the Arduino's USB for 10 seconds, check that sensor's wires, and plug it back in. Reachy keeps trying meanwhile. "
              : "It keeps retrying by itself. Check the Arduino's USB cable, and close the Arduino IDE if it's open. "),
            h("button", { type: "button", class: "btn btn--small", onclick: () => window.dispatchEvent(new Event("repair")) }, "🔧 Repair"));
        }
        if (/Pulse sensors streaming/.test(e.text)) sensorWarn.hidden = true;
        if (/starts snoring/.test(e.text)) status.textContent = "Snoring · learning their resting heartbeat (about a minute)";
        if (/Fingertip felt/.test(e.text)) status.textContent = "Stirring · reading the heartbeat";
        if (/Reachy wakes up|wake now/.test(e.text)) status.textContent = "Waking up…";
        if (/not answering/.test(e.text)) toast("A pulse sensor isn't answering: see the bar at the top.", "error");
        break;
      case "error": toast(e.message, "error"); break;
    }
  }

  showStart();
  const off = onEvent(handle);
  api("/api/state").then((s) => handle({ kind: "snapshot", ...s })).catch(() => {});
  return () => off();
}
