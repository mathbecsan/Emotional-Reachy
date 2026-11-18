/**
 * Setup checklist: a guided sequence, one check per screen. A map on the left shows
 * every step and its result; each screen explains what is tested, gives immediate
 * feedback, and says what it means and how to fix it when something fails.
 */
import { h, toast, setCrumbs, swap } from "../ui.js";
import { api, onEvent } from "../api.js";
import { avatar } from "../components/avatar.js";

const STEPS = [
  { key: "reachy", title: "Connect Reachy", costume: "base", color: "#5cc8ff", why: "This app needs to reach the robot to move it." },
  { key: "sensors", title: "Pulse sensors", costume: "smitten", color: "#ff5a6e", why: "The heartbeat wakes Reachy up and shapes its reactions." },
  { key: "camera", title: "Camera & gaze", costume: "noir", color: "#c9b28a", why: "Reachy notices where you look and whether you face it." },
  { key: "mic", title: "Microphone & sounds", costume: "tia", color: "#ff9a4d", why: "Reachy must understand speech and notice other sounds." },
  { key: "speaker", title: "Speaker", costume: "diva", color: "#ff6fb1", why: "The participant must hear Reachy clearly." },
  { key: "follow", title: "Follow me", costume: "hype_bro", color: "#ffc94d", why: "Reachy turns to follow the person as they move." },
  { key: "mobility", title: "Range of motion", costume: "villain", color: "#b98cff", why: "Every joint moves freely, with nothing in the way." },
];
const STORE = "bis.setup.v1";
const loadResults = () => {
  try { const r = JSON.parse(localStorage.getItem(STORE)); return r && Date.now() - r.t < 3 * 3600e3 ? r.results : {}; } catch { return {}; }
};
const saveResults = (results) => { try { localStorage.setItem(STORE, JSON.stringify({ t: Date.now(), results })); } catch { /* private */ } };
const post = (path, body = {}) => api(path, body);

export function checkView(outlet, startKey) {
  const results = loadResults();
  let idx = Math.max(0, STEPS.findIndex((s) => s.key === startKey));
  if (!startKey) idx = Math.max(0, STEPS.findIndex((s) => results[s.key] !== "pass"));
  let stopCurrent = null;
  let running = false;

  const map = h("ol", { class: "setup__map" });
  const stage = h("section", { class: "setup__stage" });
  const root = h("div", { class: "setup" }, h("aside", { class: "setup__rail" },
    h("p", { class: "setup__kicker" }, "Setup checklist"), map,
    h("button", { type: "button", class: "link-sm", onclick: () => { for (const k in results) delete results[k]; saveResults(results); drawMap(); show(0); } }, "Start over")),
  stage);
  outlet.replaceChildren(root);

  function drawMap() {
    map.replaceChildren(...STEPS.map((s, i) => {
      const r = results[s.key];
      return h("li", {}, h("button", {
        type: "button", class: `setup__node${i === idx ? " is-current" : ""}${r ? ` is-${r}` : ""}`, style: { "--accent": s.color },
        "aria-current": i === idx ? "step" : null, onclick: () => show(i),
      }, h("span", { class: "setup__mark", "aria-hidden": "true" }, r === "pass" ? "✓" : r === "fail" ? "!" : r === "skip" ? "–" : i + 1),
      h("span", {}, s.title), h("span", { class: "sr-only" }, r ? ` (${r})` : "")));
    }), h("li", {}, h("button", { type: "button", class: `setup__node setup__node--end${idx === STEPS.length ? " is-current" : ""}`, onclick: () => show(STEPS.length) },
      h("span", { class: "setup__mark", "aria-hidden": "true" }, "★"), h("span", {}, "Summary"))));
  }

  function setResult(key, value) { results[key] = value; saveResults(results); drawMap(); window.dispatchEvent(new Event("refreshstatus")); }

  // ------------------------------------------------------------------ building blocks
  function feedback() {
    const box = h("div", { class: "feedback", hidden: true, role: "status" });
    return {
      el: box,
      set(state, title, meaning = "", fix = "") {
        box.hidden = false;
        box.dataset.state = state;
        box.replaceChildren(h("span", { class: "feedback__icon", "aria-hidden": "true" }, state === "pass" ? "✓" : state === "fail" ? "!" : "…"),
          h("div", {}, h("strong", {}, title), meaning ? h("p", {}, meaning) : "", fix ? h("p", { class: "feedback__fix" }, h("b", {}, "Try this: "), fix) : ""));
      },
      hide() { box.hidden = true; },
    };
  }
  function task(label) {
    const el = h("li", { class: "task" }, h("span", { class: "task__box", "aria-hidden": "true" }), h("span", {}, label));
    return { el, done(v = true) { el.classList.toggle("is-done", v); } };
  }
  function ask(question, onYes, onNo) {
    return h("div", { class: "ask" }, h("strong", {}, question),
      h("div", { class: "btn-row" }, h("button", { type: "button", class: "btn btn--primary", onclick: onYes }, "Yes"),
        h("button", { type: "button", class: "btn", onclick: onNo }, "No")));
  }
  const busyBtn = (label, fn, primary = true) => {
    const b = h("button", { type: "button", class: `btn btn--big${primary ? " btn--primary" : ""}` }, label);
    b.addEventListener("click", async () => {
      if (running) { toast("A session is running: tests resume once it ends.", "error"); return; }
      b.disabled = true; const t = b.textContent; b.textContent = "Working…";
      try { await fn(); } catch (e) { toast(e.message, "error"); }
      b.disabled = false; b.textContent = t;
    });
    return b;
  };

  // ------------------------------------------------------------------ the steps
  const SCREENS = {
    async reachy(fb, area) {
      const lines = h("ul", { class: "facts" });
      const fill = async () => {
        const c = await api("/api/check");
        lines.replaceChildren(
          h("li", { "data-ok": String(c.daemon.ok) }, h("b", {}, "Robot software: "), c.daemon.detail),
          h("li", { "data-ok": String(c.robot.ok) }, h("b", {}, "This app: "), c.robot.detail));
        return c;
      };
      const c = await fill();
      const nod = async () => {
        const r = await post("/api/check/move");
        if (!r.ok) { fb.set("fail", "Reachy didn't move", "The app can't send moves to the robot.", r.fix); setResult("reachy", "fail"); return; }
        area.querySelector(".ask-slot").replaceChildren(ask("Did Reachy nod?",
          () => { fb.set("pass", "Reachy is connected", "Moves reach the robot."); setResult("reachy", "pass"); },
          () => { fb.set("fail", "No movement seen", "The command was sent but Reachy didn't move.", "Check the robot is switched on and its motors are enabled in Reachy Mini Control, then press Connect again."); setResult("reachy", "fail"); }));
      };
      area.append(lines,
        h("div", { class: "btn-row" },
          busyBtn("Connect Reachy", async () => {
            const r = await post("/api/check/connect");
            await fill();
            if (!r.ok) { fb.set("fail", "Couldn't reach Reachy", "The robot software isn't running or the USB cable is unplugged.", "Open Reachy Mini Control and turn the robot on, then press Connect again."); setResult("reachy", "fail"); return; }
            fb.set("wait", "Connected. Now watch Reachy…"); await nod();
          }),
          c.robot.ok ? busyBtn("Test a nod", nod, false) : ""),
        h("div", { class: "ask-slot" }));
      if (!c.daemon.ok) fb.set("fail", "The robot software isn't running", "Without it nothing can move.", "Open Reachy Mini Control and turn the robot on. Then press Connect Reachy.");
    },

    async sensors(fb, area) {
      const tile = (n) => {
        const st = h("span", { class: "sensor-tile__state" }, "Waiting…");
        const bpm = h("span", { class: "sensor-tile__bpm" }, "––");
        const heart = h("span", { class: "sensor-tile__heart", "aria-hidden": "true" }, "♥");
        const el = h("div", { class: "sensor-tile" }, h("span", { class: "sensor-tile__name" }, `Sensor ${n}`), heart, st, h("span", {}, bpm, h("small", {}, " BPM")));
        return { el, set(s) { el.dataset.on = s.finger ? "1" : "0"; st.textContent = s.finger ? (s.bpm ? "Heartbeat found" : "Finger detected… keep still") : "No finger"; bpm.textContent = s.bpm ?? "––"; } };
      };
      const tiles = [tile(1), tile(2)];
      area.append(h("p", { class: "instruct" }, "Rest a finger lightly on a sensor and keep still. Try both."),
        h("div", { class: "sensor-tiles" }, tiles[0].el, tiles[1].el));
      fb.set("wait", "Connecting to the sensors…");
      const seen = new Set();
      const off = onEvent((e) => {
        if (e.kind !== "probe") return;
        if (e.done) { off(); return; }
        if (!e.ok) { fb.set("fail", e.detail?.includes("not found") ? "A sensor isn't wired correctly" : "No signal from the sensors", e.detail, e.fix); setResult("sensors", "fail"); return; }
        e.sensors?.forEach((s, i) => { tiles[i].set(s); if (s.bpm) seen.add(i); });
        if (seen.size) { fb.set("pass", `Heartbeat detected on sensor ${[...seen].map((i) => i + 1).join(" and ")}`, seen.size < 2 ? "Try the other sensor too if you'll use both." : "Both sensors work."); setResult("sensors", "pass"); }
        else fb.set("wait", "Sensors connected. Waiting for a finger…", `${e.left}s left in this test.`);
      });
      try { await post("/api/check/sensors", {}); } catch (e) { fb.set("fail", "Couldn't start the sensor test", e.message); }
      return () => { off(); post("/api/check/sensors/stop").catch(() => {}); };
    },

    async camera(fb, area) { return trackScreen(fb, area, "camera"); },
    async follow(fb, area) { return trackScreen(fb, area, "follow"); },

    async mic(fb, area) {
      const bars = h("div", { class: "levels", "aria-hidden": "true" }, Array.from({ length: 60 }, () => h("i")));
      const t1 = task("Say a sentence to Reachy");
      const t2 = task("Make another sound: clap, or play a ringtone from your phone");
      const show = (r) => [...bars.children].forEach((b, i) => { b.style.height = `${Math.max(4, (r.levels?.[i] || 0) * 100)}%`; });
      const record = async (which) => {
        fb.set("wait", "Listening for 6 seconds…", which === 1 ? "Speak now, from where the participant will sit." : "Clap, snap, or play a sound now.");
        bars.classList.add("is-live");
        const r = await post("/api/check/sounds");
        bars.classList.remove("is-live");
        show(r);
        if (which === 1) {
          t1.done(!!r.speech);
          if (r.speech) fb.set("pass", `Reachy heard: “${r.speech}”`, `Background noise ${r.noise_db} dB.${r.events?.length ? " Also heard: " + r.events.join(", ") + "." : ""}`, r.noise_db > -35 ? r.fix : "");
          else fb.set("fail", r.ok ? "Sound arrived, but no words were recognised" : "Nothing reached the microphone", r.detail, r.ok ? "Speak a little louder and closer, in one clear sentence." : "Check Reachy's USB cable, then try again.");
        } else {
          const got = r.events?.length || (r.ok && !r.speech);
          t2.done(!!got);
          fb.set(got ? "pass" : "fail", got ? `Reachy noticed: ${r.events?.length ? r.events.join(", ") : "a sound"}` : "No sound stood out", r.detail, got ? "" : "Make the sound closer to Reachy, or louder.");
        }
        setResult("mic", t1.el.classList.contains("is-done") ? "pass" : "fail");
      };
      area.append(h("ul", { class: "tasks" }, t1.el, t2.el), bars,
        h("div", { class: "btn-row" }, busyBtn("Record speech", () => record(1)), busyBtn("Record a sound", () => record(2), false)));
    },

    async speaker(fb, area) {
      const slot = h("div");
      area.append(h("p", { class: "instruct" }, "Stand where the participant will sit."), h("div", { class: "btn-row" }, busyBtn("Play Reachy's voice", async () => {
        const r = await post("/api/check/speaker");
        if (!r.ok) { fb.set("fail", "No sound could be played", r.detail, r.fix); setResult("speaker", "fail"); return; }
        fb.set("wait", r.detail);
        slot.replaceChildren(ask("Did you hear Reachy clearly?",
          () => { fb.set("pass", "Reachy can be heard", r.detail); setResult("speaker", "pass"); },
          () => { fb.set("fail", "The voice wasn't clear", "", r.detail.includes("Reachy") ? "Turn up the Mac's volume for “Reachy Mini Audio” (System Settings › Sound), or reduce noise in the room." : "Reachy's speaker wasn't found, so this computer played it. Check Reachy's USB cable."); setResult("speaker", "fail"); }));
      })), slot);
    },

    async mobility(fb, area) {
      const MOVES = [["look_left", "Look left"], ["look_right", "Look right"], ["look_up", "Look up"], ["look_down", "Look down"], ["tilt", "Tilt the head"],
        ["lift", "Stretch up"], ["turn_left", "Turn the body left"], ["turn_right", "Turn the body right"], ["antennas", "Wave the antennas"]];
      const items = Object.fromEntries(MOVES.map(([k, l]) => [k, task(l)]));
      const slot = h("div");
      const off = onEvent((e) => {
        if (e.kind !== "mobility" || !e.step) return;
        items[e.step]?.el.classList.toggle("is-moving", e.status === "moving");
        if (e.status === "done") items[e.step]?.done();
      });
      area.append(h("p", { class: "instruct" }, "Clear the space around Reachy. It turns its body up to 150° each way (its limit is 160°, so a full 360° turn isn't possible)."),
        h("ul", { class: "tasks tasks--grid" }, Object.values(items).map((t) => t.el)),
        h("div", { class: "btn-row" }, busyBtn("Start the moves", async () => {
          Object.values(items).forEach((t) => t.done(false));
          fb.set("wait", "Reachy is moving…");
          const r = await post("/api/check/mobility");
          if (!r.ok) { fb.set("fail", r.detail, "", r.fix); setResult("mobility", "fail"); return; }
          slot.replaceChildren(ask("Did every move look smooth and complete?",
            () => { fb.set("pass", "Full range of motion", r.detail); setResult("mobility", "pass"); },
            () => { fb.set("fail", "Something looked off", "", "Make sure nothing touches the head or antennas, and that Reachy sits on a flat surface. Restart the robot in Reachy Mini Control if a joint seems stuck."); setResult("mobility", "fail"); }));
        })), slot);
      return off;
    },
  };

  async function trackScreen(fb, area, mode) {
    const dot = h("span", { class: "viewport__dot" });
    const label = h("span", { class: "viewport__label" }, "Starting the camera…");
    const vp = h("div", { class: "viewport" }, h("span", { class: "viewport__grid", "aria-hidden": "true" }), dot, label);
    const tasks = mode === "camera"
      ? [task("Look straight at Reachy"), task("Turn your head to the side"), task("Look back at Reachy")]
      : [task("Move to one side of Reachy"), task("Move to the other side"), task("Come back to the middle")];
    const note = mode === "follow" ? h("p", { class: "muted small" }, "Reachy follows people with its camera. Following a voice by sound alone isn't available in this version.") : "";
    area.append(h("div", { class: "track" }, vp, h("ul", { class: "tasks" }, tasks.map((t) => t.el))), note);
    let step = 0, sideA = null;
    fb.set("wait", "Starting the camera…");
    const off = onEvent((e) => {
      if (e.kind !== "track") return;
      if (e.done) { if (!results[mode] || results[mode] === "wait") fb.set("fail", "Test ended before all steps were done", "", "Press Retry and try the steps again."); off(); return; }
      if (e.ok === false) { fb.set("fail", "The camera didn't start", e.detail, e.fix); setResult(mode, "fail"); return; }
      vp.dataset.state = e.state;
      if (e.face) { dot.style.left = `${50 + e.x * 50}%`; dot.style.top = `${50 + e.y * 50}%`; }
      label.textContent = e.state === "facing" ? "Facing Reachy" : e.state === "turned" ? "Turned away" : "No one in view";
      if (mode === "camera") {
        if (step === 0 && e.state === "facing") { tasks[0].done(); step = 1; }
        else if (step === 1 && e.state === "turned") { tasks[1].done(); step = 2; }
        else if (step === 2 && e.state === "facing") { tasks[2].done(); step = 3; }
      } else if (e.face) {
        if (step === 0 && Math.abs(e.x) > 0.35) { tasks[0].done(); sideA = Math.sign(e.x); step = 1; }
        else if (step === 1 && Math.sign(e.x) === -sideA && Math.abs(e.x) > 0.35) { tasks[1].done(); step = 2; }
        else if (step === 2 && Math.abs(e.x) < 0.2) { tasks[2].done(); step = 3; }
      }
      if (step === 3 && results[mode] !== "pass") {
        fb.set("pass", mode === "camera" ? "Reachy sees where you look" : (e.following ? "Reachy follows you" : "Tracking works"),
          mode === "follow" && !e.following ? "Reachy isn't connected, so only the camera was tested." : "");
        setResult(mode, "pass");
      } else if (step < 3) {
        fb.set("wait", tasks[step].el.textContent, e.face ? "" : "Sit or stand in front of Reachy, about an arm's length away.", e.state === "none" && e.left < 25 ? "Make sure the room is lit and your face isn't backlit by a window." : "");
      }
    });
    try { const r = await post("/api/check/track"); if (mode === "follow" && !r.following) toast("Reachy isn't connected: only the camera will be tested."); }
    catch (e) { fb.set("fail", "Couldn't start the camera test", e.message); }
    return () => { off(); post("/api/check/track/stop").catch(() => {}); };
  }

  // ------------------------------------------------------------------ screens
  async function show(i) {
    stopCurrent?.();
    stopCurrent = null;
    idx = i;
    drawMap();
    if (i >= STEPS.length) { swap(stage, summary()); setCrumbs([{ label: "Main menu", href: "#/menu" }, "Setup checklist", "Summary"]); return; }
    const s = STEPS[i];
    setCrumbs([{ label: "Main menu", href: "#/menu" }, "Setup checklist", `${i + 1} · ${s.title}`]);
    const fb = feedback();
    const area = h("div", { class: "screen__area" });
    const screen = h("div", { class: "screen", style: { "--accent": s.color } },
      h("div", { class: "screen__head" },
        h("div", { class: "screen__avatar" }, avatar(s.costume, { size: 120, color: s.color, animate: true })),
        h("div", {}, h("p", { class: "screen__step" }, `Step ${i + 1} of ${STEPS.length}`), h("h1", { class: "screen__title" }, s.title), h("p", { class: "screen__why" }, s.why))),
      area, fb.el,
      h("div", { class: "screen__nav" },
        h("button", { type: "button", class: "btn", disabled: i === 0, onclick: () => show(i - 1) }, "← Back"),
        h("span", { class: "btn-row" },
          h("button", { type: "button", class: "btn", onclick: () => show(i) }, "Retry"),
          h("button", { type: "button", class: "btn", onclick: () => { if (!results[s.key]) setResult(s.key, "skip"); show(i + 1); } }, "Skip"),
          h("button", { type: "button", class: "btn btn--primary", onclick: () => show(i + 1) }, i === STEPS.length - 1 ? "Finish →" : "Next →"))));
    swap(stage, screen);
    try { stopCurrent = (await SCREENS[s.key](fb, area)) || null; }
    catch (e) { fb.set("fail", "This test couldn't run", e.message); }
  }

  function summary() {
    const pass = STEPS.filter((s) => results[s.key] === "pass").length;
    const critical = ["reachy", "sensors", "mic", "speaker"].filter((k) => results[k] !== "pass");
    return h("div", { class: "screen summary-screen" },
      h("div", { class: "screen__head" }, h("div", { class: "screen__avatar" }, avatar(critical.length ? "hypochondriac" : "hype_bro", { size: 120, color: critical.length ? "#ffc94d" : "#7be0a8", animate: true })),
        h("div", {}, h("p", { class: "screen__step" }, "Summary"), h("h1", { class: "screen__title" }, critical.length ? "Almost ready" : "Ready for a session"),
          h("p", { class: "screen__why" }, `${pass} of ${STEPS.length} checks passed.`))),
      h("ul", { class: "summary-list" }, STEPS.map((s, i) => h("li", { "data-state": results[s.key] || "none" },
        h("span", { class: "setup__mark" }, results[s.key] === "pass" ? "✓" : results[s.key] === "fail" ? "!" : "–"),
        h("span", {}, s.title), h("button", { type: "button", class: "link-sm", onclick: () => show(i) }, results[s.key] === "pass" ? "Test again" : "Open")))),
      critical.length ? h("p", { class: "feedback__fix" }, `Still needed before a real session: ${critical.map((k) => STEPS.find((s) => s.key === k).title).join(", ")}.`) : "",
      h("div", { class: "screen__nav" }, h("a", { class: "btn", href: "#/menu" }, "Main menu"), h("a", { class: "btn btn--primary btn--big", href: "#/new" }, "Create a session →")));
  }

  api("/api/state").then((st) => { running = st.running; if (running) toast("A session is running: hardware tests resume once it ends.", "error"); }).catch(() => {});
  drawMap();
  show(idx);
  return () => stopCurrent?.();
}
