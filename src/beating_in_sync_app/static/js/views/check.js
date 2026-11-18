/**
 * Setup checklist: a guided sequence, one check per screen. Steps unlock in order:
 * finish (or skip) a step to open the next. Every screen draws its controls at once,
 * gives feedback as things happen, and explains what a failure means and how to fix it.
 * (Debug mode unlocks every step.)
 */
import { h, toast, setCrumbs, swap, isDebug } from "../ui.js";
import { api, onEvent } from "../api.js";
import { avatar } from "../components/avatar.js";

const STEPS = [
  { key: "reachy", title: "Connect Reachy", costume: "base", color: "#5cc8ff", why: "This app needs to reach the robot to move it." },
  { key: "sensors", title: "Pulse sensors", costume: "smitten", color: "#ff5a6e", why: "The heartbeat wakes Reachy up and shapes its reactions." },
  { key: "camera", title: "Camera & gaze", costume: "noir", color: "#c9b28a", why: "Reachy notices where you look and whether you face it." },
  { key: "mic", title: "Microphone & sounds", costume: "tia", color: "#ff9a4d", why: "Reachy must understand speech, and notice claps, music and singing." },
  { key: "speaker", title: "Speaker", costume: "diva", color: "#ff6fb1", why: "The participant must hear Reachy clearly." },
  { key: "follow", title: "Follow me", costume: "hype_bro", color: "#ffc94d", why: "Reachy turns to keep the person in view as they move around." },
  { key: "mobility", title: "Range of motion", costume: "villain", color: "#b98cff", why: "Every joint moves freely, with nothing in the way." },
];
const STORE = "bis.setup.v2";
const loadResults = () => {
  try { const r = JSON.parse(localStorage.getItem(STORE)); return r && Date.now() - r.t < 3 * 3600e3 ? r.results : {}; } catch { return {}; }
};
const saveResults = (results) => { try { localStorage.setItem(STORE, JSON.stringify({ t: Date.now(), results })); } catch { /* private */ } };
const post = (path, body = {}) => api(path, body);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function checkView(outlet, startKey) {
  const results = loadResults();
  const done = (i) => ["pass", "skip"].includes(results[STEPS[i]?.key]);
  const unlocked = (i) => isDebug() || i === 0 || (i <= STEPS.length && [...Array(i).keys()].every(done));
  let idx = STEPS.findIndex((s) => s.key === startKey);
  if (idx < 0 || !unlocked(idx)) idx = Math.max(0, [...STEPS.keys()].find((i) => !done(i)) ?? STEPS.length);
  let stopCurrent = null, running = false, navNext = null;

  const map = h("ol", { class: "setup__map" });
  const stage = h("section", { class: "setup__stage" });
  outlet.replaceChildren(h("div", { class: "setup" }, h("aside", { class: "setup__rail" },
    h("p", { class: "setup__kicker" }, "Setup checklist"), map,
    h("button", { type: "button", class: "link-sm", onclick: () => { for (const k in results) delete results[k]; saveResults(results); show(0); } }, "Start over")),
  stage));

  function drawMap() {
    map.replaceChildren(...STEPS.map((s, i) => {
      const r = results[s.key], open = unlocked(i);
      return h("li", {}, h("button", {
        type: "button", class: `setup__node${i === idx ? " is-current" : ""}${r ? ` is-${r}` : ""}${open ? "" : " is-locked"}`, style: { "--accent": s.color },
        "aria-current": i === idx ? "step" : null, disabled: !open, title: open ? "" : `Finish step ${i} first`, onclick: () => show(i),
      }, h("span", { class: "setup__mark", "aria-hidden": "true" }, !open ? "🔒" : r === "pass" ? "✓" : r === "fail" ? "!" : r === "skip" ? "–" : i + 1),
      h("span", {}, s.title), h("span", { class: "sr-only" }, open ? (r ? ` (${r})` : "") : " (locked)")));
    }), h("li", {}, h("button", { type: "button", class: `setup__node setup__node--end${idx === STEPS.length ? " is-current" : ""}${unlocked(STEPS.length) ? "" : " is-locked"}`,
      disabled: !unlocked(STEPS.length), onclick: () => show(STEPS.length) },
    h("span", { class: "setup__mark", "aria-hidden": "true" }, unlocked(STEPS.length) ? "★" : "🔒"), h("span", {}, "Summary"))));
  }

  function setResult(key, value) {
    results[key] = value; saveResults(results); drawMap(); navNext?.();
    window.dispatchEvent(new Event("refreshstatus"));
  }

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
    };
  }
  function task(label) {
    const el = h("li", { class: "task" }, h("span", { class: "task__box", "aria-hidden": "true" }), h("span", {}, label));
    return { el, done(v = true) { el.classList.toggle("is-done", v); }, isDone: () => el.classList.contains("is-done") };
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
  const say = (text) => post("/api/check/say", { text }).catch(() => ({}));

  /** Live camera picture, fetched one frame at a time (no connection is held open). */
  function liveVideo(vp) {
    const img = h("img", { class: "viewport__video", alt: "Live view from the camera" });
    vp.prepend(img);
    let on = true, misses = 0;
    const next = () => { if (on) img.src = `/api/check/track/frame.jpg?t=${Date.now()}`; };
    img.onload = () => { misses = 0; vp.classList.add("has-video"); setTimeout(next, 120); };
    img.onerror = () => { misses += 1; setTimeout(next, misses > 20 ? 1500 : 300); };
    setTimeout(next, 500);
    return () => { on = false; img.removeAttribute("src"); };
  }

  // ------------------------------------------------------------------ the steps
  const SCREENS = {
    reachy(fb, area) {
      const lines = h("ul", { class: "facts" }, h("li", {}, "Checking the robot…"));
      const slot = h("div");
      const fill = async () => {
        const c = await api("/api/check");
        lines.replaceChildren(
          h("li", { "data-ok": String(c.daemon.ok) }, h("b", {}, "Robot software: "), c.daemon.detail),
          h("li", { "data-ok": String(c.robot.ok) }, h("b", {}, "This app: "), c.robot.detail));
        if (!c.daemon.ok) fb.set("fail", "The robot software isn't running", "Without it nothing can move.", "Open Reachy Mini Control and turn the robot on. Then press Connect Reachy.");
        else if (!c.robot.ok) fb.set("wait", "Press Connect Reachy");
        else if (results.reachy !== "pass") fb.set("wait", "Connected. Press Test a nod and watch Reachy.");
        return c;
      };
      const nod = async () => {
        const r = await post("/api/check/move");
        if (!r.ok) { fb.set("fail", "Reachy didn't move", "The app can't send moves to the robot.", r.fix); setResult("reachy", "fail"); return; }
        slot.replaceChildren(ask("Did Reachy nod?",
          () => { fb.set("pass", "Reachy is connected", "Moves reach the robot."); setResult("reachy", "pass"); slot.replaceChildren(); },
          () => { fb.set("fail", "No movement seen", "The command was sent but Reachy didn't move.", "Check the robot is switched on and its motors are enabled in Reachy Mini Control, then press Connect again."); setResult("reachy", "fail"); }));
      };
      area.append(lines, h("div", { class: "btn-row" },
        busyBtn("Connect Reachy", async () => {
          const r = await post("/api/check/connect");
          await fill();
          if (!r.ok) { fb.set("fail", "Couldn't reach Reachy", "The robot software isn't running or the USB cable is unplugged.", "Open Reachy Mini Control and turn the robot on, then press Connect again."); setResult("reachy", "fail"); return; }
          await nod();
        }),
        busyBtn("Test a nod", nod, false)), slot);
      if (results.reachy === "pass") fb.set("pass", "Reachy is connected", "Passed earlier. Test again any time.");
      fill().catch((e) => fb.set("fail", "Couldn't check the robot", e.message));
    },

    async sensors(fb, area) {
      const tile = (n) => {
        const st = h("span", { class: "sensor-tile__state" }, "Waiting…");
        const bpm = h("span", { class: "sensor-tile__bpm" }, "––");
        const el = h("div", { class: "sensor-tile" }, h("span", { class: "sensor-tile__name" }, `Sensor ${n}`), h("span", { class: "sensor-tile__heart", "aria-hidden": "true" }, "♥"), st, h("span", {}, bpm, h("small", {}, " BPM")));
        return { el, set(s) { el.dataset.on = s.finger ? "1" : "0"; st.textContent = s.finger ? (s.bpm ? "Heartbeat found" : "Finger detected… keep still") : "No finger"; bpm.textContent = s.bpm ?? "––"; } };
      };
      const tiles = [tile(1), tile(2)];
      area.append(h("p", { class: "instruct" }, "Rest a finger lightly on a sensor and keep still. Try both."), h("div", { class: "sensor-tiles" }, tiles[0].el, tiles[1].el));
      fb.set("wait", "Connecting to the sensors…");
      const seen = new Set();
      const off = onEvent((e) => {
        if (e.kind !== "probe") return;
        if (e.done) return;
        if (!e.ok) { fb.set("fail", e.detail?.includes("not found") ? "A sensor isn't wired correctly" : "No signal from the sensors", e.detail, e.fix); setResult("sensors", "fail"); return; }
        e.sensors?.forEach((s, i) => { tiles[i].set(s); if (s.bpm) seen.add(i); });
        if (seen.size) { fb.set("pass", `Heartbeat detected on sensor ${[...seen].map((i) => i + 1).join(" and ")}`, seen.size < 2 ? "Try the other sensor too if you'll use both." : "Both sensors work."); if (results.sensors !== "pass") setResult("sensors", "pass"); }
        else fb.set("wait", "Sensors connected. Waiting for a finger…", `${e.left}s left in this test.`);
      });
      post("/api/check/sensors", {}).catch((e) => fb.set("fail", "Couldn't start the sensor test", e.message));
      return () => { off(); post("/api/check/sensors/stop").catch(() => {}); };
    },

    camera(fb, area) {
      const label = h("span", { class: "viewport__label" }, "Starting the camera…");
      const vp = h("div", { class: "viewport" }, h("span", { class: "viewport__grid", "aria-hidden": "true" }), label);
      const tasks = [task("Look straight at Reachy"), task("Turn your head to the side"), task("Look back at Reachy")];
      const pickerSlot = h("div");
      let stopVideo = liveVideo(vp), step = 0;
      area.append(h("p", { class: "instruct" }, "Sit about an arm's length in front of Reachy, facing it."),
        h("div", { class: "track" }, vp, h("div", {}, h("ul", { class: "tasks" }, tasks.map((t) => t.el)),
          h("button", { type: "button", class: "link-sm", onclick: () => choose() }, "Wrong camera? Choose another"))), pickerSlot);
      const start = async () => {
        step = 0; tasks.forEach((t) => t.done(false));
        try { await post("/api/check/track"); } catch (e) { fb.set("fail", "Couldn't start the camera", e.message); }
      };
      async function choose() {
        await post("/api/check/track/stop");
        stopVideo(); vp.classList.remove("has-video");
        pickerSlot.replaceChildren(h("p", { class: "muted" }, "Taking a picture with each camera…"));
        pickerSlot.replaceChildren(await cameraPicker(async () => { pickerSlot.replaceChildren(); stopVideo = liveVideo(vp); await start(); }));
      }
      fb.set("wait", "Look straight at Reachy");
      const off = onEvent((e) => {
        if (e.kind !== "track") return;
        if (e.done) { if (step < 3) fb.set("fail", "The camera test timed out", "", "Press Retry and follow the three steps."); return; }
        if (e.ok === false) { fb.set("fail", "The camera didn't start", e.detail, e.fix); setResult("camera", "fail"); return; }
        vp.dataset.state = e.state;
        label.textContent = e.state === "facing" ? "Facing Reachy" : e.state === "turned" ? "Turned away" : "No one in view";
        if (step === 0 && e.state === "facing") { tasks[0].done(); step = 1; }
        else if (step === 1 && e.state === "turned") { tasks[1].done(); step = 2; }
        else if (step === 2 && e.state === "facing") { tasks[2].done(); step = 3; }
        if (step === 3) { if (results.camera !== "pass") { fb.set("pass", "Reachy sees where you look"); setResult("camera", "pass"); } }
        else fb.set("wait", tasks[step].el.textContent, e.face ? "" : "Make sure your face is lit and Reachy's camera points at you.");
      });
      start();
      return () => { off(); stopVideo(); post("/api/check/track/stop").catch(() => {}); };
    },

    follow(fb, area) {
      // A short game Reachy narrates out loud: stand in front, go to your left, to your right, back to the middle.
      const ROUND = [
        { key: "front", text: "Stand in front of Reachy", say: "Let's play follow me! Stand right in front of me, and I'll keep my eyes on you.", ok: (a) => Math.abs(a) < 12, zone: 0 },
        { key: "left", text: "Walk slowly to your LEFT", say: "Now take two slow steps to your left. I'll follow you.", ok: (a) => a > 22, zone: -1 },
        { key: "right", text: "Now walk to your RIGHT", say: "Great! Now walk all the way over to your right.", ok: (a) => a < -22, zone: 1 },
        { key: "back", text: "Come back to the middle", say: "Perfect. Come back to the middle.", ok: (a) => Math.abs(a) < 12, zone: 0 },
      ];
      const tasks = ROUND.map((r) => task(r.text));
      const big = h("div", { class: "coach" }, h("span", { class: "coach__arrow", "aria-hidden": "true" }), h("strong", { class: "coach__text" }, "Press Start the game"));
      const label = h("span", { class: "viewport__label" }, "Camera off");
      const vp = h("div", { class: "viewport viewport--small" }, h("span", { class: "viewport__grid", "aria-hidden": "true" }), label);
      const arc = h("div", { class: "arc", "aria-hidden": "true" },
        h("span", { class: "arc__zone arc__zone--l" }, "your left"), h("span", { class: "arc__zone arc__zone--m" }, "middle"), h("span", { class: "arc__zone arc__zone--r" }, "your right"),
        h("span", { class: "arc__you" }, "you"), h("span", { class: "arc__reachy" }));
      let step = -1, hold = 0, stopVideo = () => {}, following = false;
      const setStep = (i) => {
        step = i;
        tasks.forEach((t, j) => t.el.classList.toggle("is-current", j === i));
        if (i >= ROUND.length) return;
        const r = ROUND[i];
        big.dataset.zone = String(r.zone);
        big.querySelector(".coach__text").textContent = r.text;
        arc.dataset.target = String(r.zone);
        fb.set("wait", r.text, r.zone ? "Reachy should turn its head to keep you in view." : "");
        say(r.say);
      };
      area.append(big, h("div", { class: "follow-grid" }, h("div", {}, arc, vp), h("ul", { class: "tasks" }, tasks.map((t) => t.el))),
        h("div", { class: "btn-row" }, busyBtn("▶ Start the game", async () => {
          tasks.forEach((t) => t.done(false)); hold = 0;
          const r = await post("/api/check/track");
          following = r.following;
          if (!following) toast("Reachy isn't connected: the camera is tested, but Reachy won't turn.", "error");
          stopVideo(); stopVideo = liveVideo(vp);
          setStep(0);
        })),
        h("p", { class: "muted small" }, "Reachy follows people with its camera. Following a voice by sound alone isn't available in this version."));
      const off = onEvent((e) => {
        if (e.kind !== "track" || step < 0) return;
        if (e.done) { if (step < ROUND.length) fb.set("fail", "The game timed out", "", "Press Start the game and follow Reachy's instructions."); return; }
        if (e.ok === false) { fb.set("fail", "The camera didn't start", e.detail, e.fix); setResult("follow", "fail"); return; }
        label.textContent = e.face ? `${e.angle > 8 ? "To your left" : e.angle < -8 ? "To your right" : "In the middle"}${e.following ? " · Reachy follows" : ""}` : "No one in view";
        if (e.face) arc.style.setProperty("--pos", String(Math.max(-1, Math.min(1, -e.angle / 45))));
        arc.classList.toggle("has-you", !!e.face);
        if (step >= ROUND.length || !e.face) return;
        hold = ROUND[step].ok(e.angle) ? hold + 1 : 0;
        if (hold >= 4) {                       // stay in the zone briefly so a passing glance doesn't count
          tasks[step].done(); hold = 0;
          if (step === ROUND.length - 1) {
            setStep(ROUND.length);
            big.querySelector(".coach__text").textContent = "Done!";
            fb.set("pass", following ? "Reachy followed you all the way" : "Tracking works", following ? "" : "Connect Reachy to test the turning too.");
            say("I followed you the whole way. Nice moves!");
            setResult("follow", "pass");
          } else setStep(step + 1);
        }
      });
      return () => { off(); stopVideo(); post("/api/check/track/stop").catch(() => {}); };
    },

    mic(fb, area) {
      const bars = h("div", { class: "levels", "aria-hidden": "true" }, Array.from({ length: 60 }, () => h("i")));
      const t1 = task("Say a sentence to Reachy");
      const t2 = task("Perform: clap, sing, or play music from your phone");
      const heard = h("div", { class: "heard-chips" });
      const draw = (r) => {
        [...bars.children].forEach((b, i) => { b.style.height = `${Math.max(4, (r.levels?.[i] || 0) * 100)}%`; });
        heard.replaceChildren(...[r.speech ? h("span", { class: "chip chip--speech" }, `“${r.speech}”`) : "", ...(r.events || []).map((e) => h("span", { class: "chip chip--sound" }, e))].filter(Boolean));
      };
      const finish = () => setResult("mic", t1.isDone() && t2.isDone() ? "pass" : "fail");
      const record = async (which) => {
        fb.set("wait", "Listening for 6 seconds…", which === 1 ? "Speak now, from where the participant will sit." : "Clap a rhythm, sing a line, or play a song now.");
        bars.classList.add("is-live");
        const r = await post("/api/check/sounds");
        bars.classList.remove("is-live");
        draw(r);
        if (which === 1) {
          t1.done(!!r.speech);
          if (r.speech) fb.set("pass", "Reachy understood you", `Background noise ${r.noise_db} dB.`, r.noise_db > -35 ? r.fix : (t2.isDone() ? "" : "Now test a performance: press Record a performance."));
          else fb.set("fail", r.ok ? "Sound arrived, but no words were recognised" : "Nothing reached the microphone", r.detail, r.ok ? "Speak a little louder and closer, in one clear sentence." : "Check Reachy's USB cable, then try again.");
        } else {
          const got = (r.events || []).length > 0;
          t2.done(got);
          fb.set(got ? "pass" : "fail", got ? `Reachy noticed: ${r.events.join(", ")}` : "Reachy didn't notice the performance", r.speech ? `It heard words: “${r.speech}”` : "",
            got ? "" : "Make it longer (3+ seconds) and closer to Reachy: clap at least three times, or play music louder.");
        }
        finish();
      };
      area.append(h("ul", { class: "tasks" }, t1.el, t2.el), bars, heard,
        h("div", { class: "btn-row" }, busyBtn("Record speech", () => record(1)), busyBtn("Record a performance", () => record(2), false)));
    },

    speaker(fb, area) {
      const slot = h("div");
      area.append(h("p", { class: "instruct" }, "Stand where the participant will sit."), h("div", { class: "btn-row" }, busyBtn("Play Reachy's voice", async () => {
        const r = await post("/api/check/speaker");
        if (!r.ok) { fb.set("fail", "No sound could be played", r.detail, r.fix); setResult("speaker", "fail"); return; }
        fb.set("wait", r.detail);
        slot.replaceChildren(ask("Did you hear Reachy clearly?",
          () => { fb.set("pass", "Reachy can be heard", r.detail); setResult("speaker", "pass"); slot.replaceChildren(); },
          () => { fb.set("fail", "The voice wasn't clear", "", r.detail.includes("Reachy") ? "Turn up the Mac's volume for “Reachy Mini Audio” (System Settings › Sound), or reduce noise in the room." : "Reachy's speaker wasn't found, so this computer played it. Check Reachy's USB cable."); setResult("speaker", "fail"); }));
      })), slot);
    },

    async mobility(fb, area) {
      const slot = h("div");
      const groupsBox = h("div", { class: "move-groups" }, h("p", { class: "muted" }, "Loading the moves…"));
      area.append(h("p", { class: "instruct" }, "Clear the space around Reachy. Its body turns up to 150° each way (the limit is 160°, so a full 360° isn't possible)."), groupsBox,
        h("div", { class: "btn-row" }, busyBtn("▶ Run every move", () => run(null))), slot);
      const moves = await api("/api/check/moves").catch(() => []);
      const items = {};
      const groups = [...new Set(moves.map((m) => m.group))];
      groupsBox.replaceChildren(...groups.map((g) => h("section", { class: "move-group" },
        h("div", { class: "move-group__head" }, h("strong", {}, g), h("button", { type: "button", class: "chip-btn", onclick: () => run(g) }, "▶ Run")),
        h("ul", { class: "tasks" }, moves.filter((m) => m.group === g).map((m) => { items[m.key] = task(m.label); return items[m.key].el; })))));
      const off = onEvent((e) => {
        if (e.kind !== "mobility" || !e.step) return;
        items[e.step]?.el.classList.toggle("is-moving", e.status === "moving");
        if (e.status === "done") items[e.step]?.done();
      });
      async function run(group) {
        if (running) return;
        moves.filter((m) => !group || m.group === group).forEach((m) => items[m.key].done(false));
        fb.set("wait", `Reachy is moving${group ? ` (${group})` : ""}…`, "Watch each move as it's ticked off.");
        const r = await post("/api/check/mobility", group ? { group } : {});
        if (!r.ok) { fb.set("fail", r.detail, "", r.fix); setResult("mobility", "fail"); return; }
        const all = moves.every((m) => items[m.key].isDone());
        slot.replaceChildren(ask(all ? "Did every move look smooth and complete?" : `Did the ${group} moves look right?`,
          () => { slot.replaceChildren(); fb.set(all ? "pass" : "wait", all ? "Full range of motion" : `${group} moves look good`, all ? r.detail : "Run the other groups, or Run every move, to finish."); if (all) setResult("mobility", "pass"); },
          () => { fb.set("fail", "Something looked off", "", "Make sure nothing touches the head or antennas and Reachy sits on a flat surface. Restart the robot in Reachy Mini Control if a joint seems stuck."); setResult("mobility", "fail"); }));
      }
      return off;
    },
  };

  /** Snapshots of each camera so the right one (Reachy's) can be picked by sight. */
  async function cameraPicker(onChange) {
    let info = { current: 0, names: [], indices: [0, 1, 2] };
    try { info = await api("/api/check/cameras"); } catch { /* defaults */ }
    const row = h("div", { class: "cam-picker__row" });
    const box = h("div", { class: "cam-picker" }, h("p", { class: "creator__label" }, "Which camera is Reachy's?"), row,
      info.names.length ? h("p", { class: "muted small" }, `This Mac has: ${info.names.join(", ")}. Pick the picture taken from Reachy's point of view.`) : "");
    for (const i of info.indices) {
      const img = h("img", { alt: `Camera ${i + 1}` });
      const ok = await new Promise((res) => { img.onload = () => res(true); img.onerror = () => res(false); img.src = `/api/check/camera/${i}.jpg?t=${Date.now()}`; });
      if (!ok) continue;
      row.append(h("button", { type: "button", class: `cam${i === info.current ? " is-on" : ""}`,
        onclick: async () => { await post("/api/check/camera/use", { index: i }); toast(`Using camera ${i + 1}`); await onChange(); } },
      img, h("span", {}, `Camera ${i + 1}${i === info.current ? " · in use" : ""}`)));
    }
    return box;
  }

  // ------------------------------------------------------------------ screens
  async function show(i) {
    if (!unlocked(i)) { toast(`Finish step ${i} first`); return; }
    stopCurrent?.();
    stopCurrent = null;
    navNext = null;
    idx = i;
    drawMap();
    if (i >= STEPS.length) { swap(stage, summary()); setCrumbs([{ label: "Main menu", href: "#/menu" }, "Setup checklist", "Summary"]); return; }
    const s = STEPS[i];
    setCrumbs([{ label: "Main menu", href: "#/menu" }, "Setup checklist", `${i + 1} · ${s.title}`]);
    const fb = feedback();
    const area = h("div", { class: "screen__area" });
    const next = h("button", { type: "button", class: "btn btn--primary" }, i === STEPS.length - 1 ? "Finish →" : "Next →");
    next.addEventListener("click", () => show(i + 1));
    navNext = () => { const ok = done(i); next.disabled = !ok && !isDebug(); next.title = next.disabled ? "Pass this check, or press Skip" : ""; };
    navNext();
    const screen = h("div", { class: "screen", style: { "--accent": s.color } },
      h("div", { class: "screen__head" },
        h("div", { class: "screen__avatar" }, avatar(s.costume, { size: 120, color: s.color, animate: true })),
        h("div", {}, h("p", { class: "screen__step" }, `Step ${i + 1} of ${STEPS.length}`), h("h1", { class: "screen__title" }, s.title), h("p", { class: "screen__why" }, s.why))),
      area, fb.el,
      h("div", { class: "screen__nav" },
        h("button", { type: "button", class: "btn", disabled: i === 0, onclick: () => show(i - 1) }, "← Back"),
        h("span", { class: "btn-row" },
          h("button", { type: "button", class: "btn", onclick: () => show(i) }, "Retry"),
          h("button", { type: "button", class: "btn", title: "Mark as skipped and continue", onclick: () => { if (results[s.key] !== "pass") setResult(s.key, "skip"); show(i + 1); } }, "Skip"),
          next)));
    swap(stage, screen);
    await sleep(180);                       // let the swap animation put the screen in place
    if (idx !== i) return;
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
  const onDebug = () => { drawMap(); navNext?.(); };
  window.addEventListener("debugchange", onDebug);
  show(idx);
  return () => { stopCurrent?.(); window.removeEventListener("debugchange", onDebug); };
}
