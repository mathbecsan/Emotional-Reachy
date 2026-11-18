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

function startForm(onStarted) {
  const form = h("form", { class: "start card" });
  const field = (label, input, hint) => h("label", { class: "field" }, h("span", { class: "field__label" }, label), input,
    hint ? h("span", { class: "field__hint" }, hint) : null);
  const participant = h("input", { name: "participant", value: "P01", required: true, autocomplete: "off" });
  const profile = h("select", { name: "profile" });
  const lang = h("select", { name: "language_hint" }, Object.entries(LANGS).map(([k, v]) => h("option", { value: k }, v)));
  const noTease = h("input", { type: "checkbox", name: "no_tease" });
  const llm = h("input", { type: "checkbox", name: "llm", checked: true });
  const heart = h("select", { name: "heart" },
    h("option", { value: "sim" }, "Simulated heart (no hardware)"),
    h("option", { value: "arduino" }, "Arduino pulse sensors"),
    h("option", { value: "arduino-sim" }, "Arduino pipeline, simulated signal"));
  const port = h("select", { name: "heart_port" }, h("option", { value: "" }, "auto-detect"));
  const camera = h("input", { type: "checkbox", name: "camera", checked: true });
  const listener = h("select", { name: "listener" },
    h("option", { value: "elevenlabs" }, "Reachy's microphone (ElevenLabs) + typed"),
    h("option", { value: "web" }, "Typed here only (rehearsal / Wizard-of-Oz)"),
    h("option", { value: "mic" }, "Microphone (local Whisper)"));
  const conversation = h("select", { name: "conversation" },
    h("option", { value: "realtime" }, "Live & fluid (ElevenLabs agent with Reachy's personality)"),
    h("option", { value: "scripted" }, "Scripted (Director + offline lines / Claude)"));
  const voice = h("select", { name: "voice" },
    h("option", { value: "elevenlabs" }, "ElevenLabs, from Reachy's speaker"),
    h("option", { value: "mac" }, "macOS voice"),
    h("option", { value: "sim" }, "Text only (silent)"));
  const scale = h("select", { name: "time_scale" }, [1, 2, 5, 10].map((s) => h("option", { value: s }, s === 1 ? "Real time" : `${s}× faster`)));
  const portRow = field("Serial port", port, "Close the Arduino IDE serial monitor and pulse_triple.py first: only one program can read the port.");
  const syncPort = () => { portRow.hidden = heart.value !== "arduino"; };
  heart.addEventListener("change", syncPort);

  api("/api/profiles").then((ps) => ps.forEach((p) => profile.append(h("option", { value: p.name }, `${p.display_name} — ${p.description}`))));
  api("/api/ports").then((ps) => ps.forEach((p) => port.append(h("option", { value: p.device }, `${p.device}${p.description ? " · " + p.description : ""}`)))).catch(() => {});
  syncPort();

  form.append(
    h("h2", { class: "card__title" }, "New session"),
    h("p", { class: "start__lede" }, "Run the pre-interview first. Reachy starts asleep; the participant's heartbeat wakes it."),
    h("div", { class: "start__grid" },
      field("Participant ID", participant),
      field("Personality", profile),
      field("Start language", lang, "Reachy switches to the participant's language in stage 2."),
      field("Heart", heart),
      portRow,
      field("Conversation", conversation, "Live: Reachy listens continuously, answers anything, asks its own questions."),
      field("Participant speech", listener),
      field("Reachy voice", voice),
      field("Clock", scale, "Faster clocks are for rehearsals only."),
      h("label", { class: "check" }, noTease, " Would rather not be teased (skips stage 4)"),
      h("label", { class: "check" }, llm, " Claude writes Reachy's lines (otherwise offline templates)"),
      h("label", { class: "check" }, camera, " Camera: face emotion + attention")),
    h("button", { class: "btn btn--primary", type: "submit" }, "Start session"));

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api("/api/session/start", {
        participant: participant.value.trim(), profile: profile.value, language_hint: lang.value,
        no_tease: noTease.checked, llm: llm.checked, heart: heart.value, heart_port: port.value || null,
        camera: camera.checked, listener: listener.value, voice: voice.value, time_scale: Number(scale.value),
        conversation: conversation.value,
      });
      onStarted();
    } catch (e) { toast(e.message, "error"); }
  });
  return form;
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
  const who = h("dl", { class: "who" });
  const ctl = controls();
  const banner = h("div", { class: "banner", hidden: true });

  const layout = h("div", { class: "live" },
    timeline.el,
    banner,
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
    startWrap.replaceChildren(startForm(() => toast("Session started")));
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
          chart.reset(); log.reset(); timeline.reset(); sensors.reset(); baseline = null;
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
      case "baseline": baseline = e.bpm; chart.setBaseline(e.bpm); bpmMeta.textContent = `baseline ${Math.round(e.bpm || 0)}`; break;
      case "turn":
        log.turn(e);
        chart.addTurn(e);
        face.setMode(e.mode);
        modeName.textContent = MODES[e.mode]?.label || e.mode;
        modeAct.textContent = ` · ${e.act}`;
        modeWhy.textContent = e.why;
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
