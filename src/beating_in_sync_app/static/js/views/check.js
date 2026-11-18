/**
 * Setup checklist: a guided sequence, one check per screen. Steps unlock in order:
 * finish (or skip) a step to open the next. Every screen draws its controls at once,
 * gives feedback as things happen, and explains what a failure means and how to fix it.
 * (Debug mode unlocks every step.)
 */
import { h, toast, setCrumbs, swap, isDebug } from "../ui.js";
import { api, onEvent } from "../api.js";
import { avatar } from "../components/avatar.js";
import { speak, quiet, shortFix, praise, voiceOn, setVoice } from "../components/voice-guide.js";

const STEPS = [
  { key: "reachy", intro: "Let's make sure I can move. Press Connect Reachy and watch me.", title: "Connect Reachy", costume: "base", color: "#5cc8ff", why: "This app needs to reach the robot, and every motor must respond." },
  { key: "sensors", intro: "Four quick checks: sensor 1 alone, sensor 2 alone, one finger on each, and two different people.", title: "Pulse sensors", costume: "smitten", color: "#ff5a6e", why: "The heartbeat wakes Reachy up and shapes its reactions." },
  { key: "mic", intro: "Press Record speech and say a sentence to me. Then press Record a performance and clap, sing, or play some music.", title: "Microphone & sounds", costume: "tia", color: "#ff9a4d", why: "Reachy must understand speech, and recognise music, singing, claps and other sounds." },
  { key: "talk", intro: "Press Start the chat. I'll ask you three quick questions.", title: "Talk with Reachy", costume: "diva", color: "#ff6fb1", why: "A short chat: you hear Reachy clearly, and it understands your answers." },
  { key: "mobility", intro: "Clear the space around me, then press Run every move.", title: "Range of motion", costume: "villain", color: "#b98cff", why: "Head, antennas and body move freely, with nothing in the way." },
  { key: "see", intro: "Sit in front of me, about one metre away, and press Start. Then do what I say.", title: "See & follow", costume: "noir", color: "#ffc94d", why: "Reachy sees where you look and turns its head and body to follow you, even beyond its camera's view." },
];
const STORE = "bis.setup.v3";
const loadResults = () => {
  try { const r = JSON.parse(localStorage.getItem(STORE)); return r && Date.now() - r.t < 3 * 3600e3 ? r.results : {}; } catch { return {}; }
};
const saveResults = (results) => { try { localStorage.setItem(STORE, JSON.stringify({ t: Date.now(), results })); } catch { /* private */ } };
const post = (path, body = {}) => api(path, body);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function checkView(outlet, startKey) {
  const results = loadResults();
  const done = (i) => ["pass", "skip"].includes(results[STEPS[i]?.key]);
  // A step opens once every step before it has passed or been skipped, and stays open after that:
  // re-testing an earlier step never locks the later ones again.
  const unlocked = (i) => {
    if (isDebug() || i === 0 || i <= (results._reached || 0)) return true;
    const open = [...Array(i).keys()].every(done);
    if (open) { results._reached = Math.max(results._reached || 0, i); saveResults(results); }
    return open;
  };
  let idx = STEPS.findIndex((s) => s.key === startKey);
  if (idx < 0 || !unlocked(idx)) idx = Math.max(0, [...STEPS.keys()].find((i) => !done(i)) ?? STEPS.length);
  let stopCurrent = null, running = false, navNext = null;

  const map = h("ol", { class: "setup__map" });
  const stage = h("section", { class: "setup__stage" });
  outlet.replaceChildren(h("div", { class: "setup" }, h("aside", { class: "setup__rail" },
    h("p", { class: "setup__kicker" }, "Setup checklist"), map,
    h("button", { type: "button", class: "link-sm", onclick: () => { for (const k in results) delete results[k]; saveResults(results); show(0); } }, "Start over"),
    h("label", { class: "voice-toggle", title: "Reachy says each instruction, progress and problems out loud" },
      h("input", { type: "checkbox", checked: voiceOn(), onchange: (ev) => { setVoice(ev.target.checked); toast(ev.target.checked ? "Reachy's voice guide is on" : "Voice guide off"); } }),
      h("span", { class: "switch__ui", "aria-hidden": "true" }), h("span", {}, "Voice guide", h("small", { class: "voice-toggle__note" }, "Always on in See & follow")))),
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
    if (value === "pass") delete repairs[key];
    results[key] = value; saveResults(results); drawMap(); navNext?.();
    window.dispatchEvent(new Event("refreshstatus"));
  }

  // ------------------------------------------------------------------ building blocks
  const repairs = {};               // how many Repairs were run for each step (to escalate the advice)
  function feedback(isLast = false, always = false) {
    const box = h("div", { class: "feedback", hidden: true, role: "status" });
    const spoken = new Set();
    return {
      el: box,
      set(state, title, meaning = "", fix = "", { silent = false } = {}) {
        // Say results out loud too: progress, what went wrong, what to do next (once per message).
        if (!silent && state !== "wait" && !spoken.has(state + title)) {
          spoken.add(state + title);
          if (state === "pass") speak(`${praise()} ${title}. ${isLast ? "Press Finish." : "Press Next to continue."}`, { important: true, always });
          else speak(`Hmm, there's a problem. ${title}. ${shortFix(fix) || "Press Retry to try again, or Repair if it keeps failing."}`, { important: true, always });
        }
        box.hidden = false;
        box.dataset.state = state;
        box.replaceChildren(h("span", { class: "feedback__icon", "aria-hidden": "true" }, state === "pass" ? "✓" : state === "fail" ? "!" : "…"),
          h("div", {}, h("strong", {}, title), meaning ? h("p", {}, meaning) : "", fix ? h("p", { class: "feedback__fix" }, h("b", {}, "Try this: "), fix) : "",
            state === "fail" ? afterRepair() : "",
            state === "fail" ? h("div", { class: "btn-row feedback__actions" },
              h("button", { type: "button", class: "btn btn--small", title: "Stop this test and start it again from scratch", onclick: () => show(idx) }, "↺ Reset this step"),
              h("button", { type: "button", class: "btn btn--small", onclick: () => window.dispatchEvent(new Event("repair")) }, "🔧 Repair automatically")) : ""));
      },
    };
  }
  function afterRepair() {
    const n = repairs[STEPS[idx]?.key] || 0;
    if (!n) return "";
    return h("p", { class: "feedback__escalate" }, n === 1
      ? "Repair ran, but this still fails. Press ↺ Reset this step to start the test over. If it fails again, run 🔧 Repair once more."
      : `Still failing after ${n} repairs. Reset this step once more; if it keeps failing, unplug that device (USB and power), wait 10 seconds, plug it back in, then Reset again.`);
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
  const say = (text, important = false) => speak(text, { important, always: true });   // used by See & follow only

  /** Live camera picture, fetched one frame at a time (no connection is held open). */
  function liveVideo(vp) {
    const img = h("img", { class: "viewport__video", alt: "" });
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
      const bodyLine = h("li", { hidden: true });
      const slot = h("div");
      const fill = async () => {
        const c = await api("/api/check");
        lines.replaceChildren(
          h("li", { "data-ok": String(c.daemon.ok) }, h("b", {}, "Robot software: "), c.daemon.detail),
          h("li", { "data-ok": String(c.robot.ok) }, h("b", {}, "This app: "), c.robot.detail), bodyLine);
        if (!c.daemon.ok) fb.set("fail", "The robot software isn't running", "Without it nothing can move.", "Open Reachy Mini Control and turn the robot on. Then press Connect Reachy.");
        else if (!c.robot.ok) fb.set("wait", "Press Connect Reachy");
        else if (results.reachy !== "pass") fb.set("wait", "Connected. Press Test the motors and watch Reachy.");
        return c;
      };
      const test = async () => {
        const r = await post("/api/check/move");
        if (!r.ok) { fb.set("fail", "Reachy didn't move", "The app can't send moves to the robot.", r.fix); setResult("reachy", "fail"); return; }
        fb.set("wait", "Reachy nodded. Now checking the body motor…");
        const b = await post("/api/check/body");
        bodyLine.hidden = false;
        bodyLine.dataset.ok = String(!!b.ok);
        bodyLine.replaceChildren(h("b", {}, "Body motor: "), b.detail);
        if (!b.ok) { fb.set("fail", "The head moves, but the body doesn't turn", b.detail, b.fix); setResult("reachy", "fail"); return; }
        slot.replaceChildren(ask("Did Reachy nod, then turn its body left and right?",
          () => { fb.set("pass", "Reachy is connected and every motor responds", b.detail); setResult("reachy", "pass"); slot.replaceChildren(); },
          () => { fb.set("fail", "Not all the movement was seen", "", "Check the robot is switched on with motors enabled in Reachy Mini Control, then press Connect again."); setResult("reachy", "fail"); }));
      };
      area.append(lines, h("div", { class: "btn-row" },
        busyBtn("Connect Reachy", async () => {
          const r = await post("/api/check/connect");
          await fill();
          if (!r.ok) { fb.set("fail", "Couldn't reach Reachy", "The robot software isn't running or the USB cable is unplugged.", "Open Reachy Mini Control and turn the robot on, then press Connect again."); setResult("reachy", "fail"); return; }
          await test();
        }),
        busyBtn("Test the motors", test, false)), slot);
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
      // Guided checks, in order. Each must hold for ~2 s (8 readings) so a flicker doesn't count.
      const CHECKS = [
        { text: "Sensor 1 alone: one finger on sensor 1", how: "Rest one finger on sensor 1 only, and keep still.",
          ok: ([a, b]) => a.bpm && !b.finger },
        { text: "Sensor 2 alone: one finger on sensor 2", how: "Now move that finger to sensor 2 only.",
          ok: ([a, b]) => b.bpm && !a.finger },
        { text: "One person: a finger on each sensor", how: "Put one finger of each hand on the two sensors. Both should show about the same heart rate.",
          ok: ([a, b]) => a.bpm && b.bpm && Math.abs(a.bpm - b.bpm) <= 12 },
        { text: "Two people: one finger each (optional)", how: "Ask a second person to put a finger on one sensor while you keep yours on the other.",
          ok: ([a, b]) => a.bpm && b.bpm, optional: true },
      ];
      const tasks = CHECKS.map((c) => task(c.text));
      const how = h("p", { class: "instruct" });
      const twoNote = h("p", { class: "muted small" });
      let cur = 0, hold = 0, retried = false, gotData = false;
      const setCur = (i) => {
        cur = i;
        tasks.forEach((t, j) => t.el.classList.toggle("is-current", j === i));
        how.textContent = i < CHECKS.length ? CHECKS[i].how : "All sensor checks done.";
      };
      const finish = () => {
        const required = tasks.slice(0, 3).every((t) => t.isDone());
        if (required) {
          fb.set("pass", tasks[3].isDone() ? "Both sensors work, for one person and for two" : "Both sensors work", tasks[3].isDone() ? "" : "The two-people check was skipped.");
          setResult("sensors", "pass");
        }
      };
      const restart = async (why) => {
        fb.set("wait", why, "Restarting the sensor reader…");
        await post("/api/check/sensors", {}).catch((e) => fb.set("fail", "Couldn't start the sensor test", e.message));
      };
      const skipTwo = h("button", { type: "button", class: "chip-btn", onclick: () => { tasks[3].done(false); setCur(4); finish(); } }, "Only one person here: skip");
      area.append(how,
        h("div", { class: "sensor-tiles" }, tiles[0].el, tiles[1].el),
        h("ul", { class: "tasks" }, tasks.map((t) => t.el)), twoNote,
        h("div", { class: "btn-row" },
          h("button", { type: "button", class: "btn", title: "Stop and restart the sensor reader (fixes most 'no signal' problems)", onclick: () => { retried = false; restart("Reconnecting to the sensors…"); } }, "↻ Reconnect sensors"),
          skipTwo));
      setCur(0);
      fb.set("wait", "Connecting to the sensors…", "The Arduino restarts when it's opened: this can take up to 10 seconds.");
      const off = onEvent((e) => {
        if (e.kind !== "probe" || e.done) return;
        if (e.starting) return;
        if (!e.ok) {
          // Self-recovery: the first time the readings stop, restart the reader once by itself.
          if (!retried) { retried = true; restart("The sensors went quiet: reconnecting automatically…"); return; }
          fb.set("fail", e.detail?.includes("not found") ? "A sensor isn't wired correctly" : "No signal from the sensors", e.detail,
            `${e.fix} If the wires are fine, press ↻ Reconnect sensors.`);
          if (results.sensors !== "pass") setResult("sensors", "fail");
          return;
        }
        if (!gotData) { gotData = true; fb.set("wait", "Sensors connected", "Follow the checks below, one at a time."); }
        retried = false;                     // a later dropout gets its own automatic retry
        e.sensors?.forEach((s, i) => tiles[i].set(s));
        const [a, b] = e.sensors || [{}, {}];
        if (a.bpm && b.bpm) twoNote.textContent = `Sensor 1: ${a.bpm} BPM · Sensor 2: ${b.bpm} BPM${Math.abs(a.bpm - b.bpm) <= 12 ? " (about the same heart)" : " (different hearts)"}`;
        if (cur >= CHECKS.length) return;
        hold = CHECKS[cur].ok(e.sensors || [{}, {}]) ? hold + 1 : 0;
        if (hold >= 8) {
          tasks[cur].done(); hold = 0;
          setCur(cur + 1);
          finish();
        }
      });
      post("/api/check/sensors", {}).catch((e) => fb.set("fail", "Couldn't start the sensor test", e.message));
      return () => { off(); post("/api/check/sensors/stop").catch(() => {}); };
    },

    mic(fb, area) {
      const bars = h("div", { class: "levels", "aria-hidden": "true" }, Array.from({ length: 60 }, () => h("i")));
      const t1 = task("Say a sentence to Reachy");
      const t2 = task("Perform: clap, sing, or play music (a phone recording works)");
      const heard = h("div", { class: "heard-chips" });
      const engine = h("p", { class: "muted small" });
      const draw = (r) => {
        [...bars.children].forEach((b, i) => { b.style.height = `${Math.max(4, (r.levels?.[i] || 0) * 100)}%`; });
        heard.replaceChildren(...[r.speech ? h("span", { class: "chip chip--speech" }, `“${r.speech}”`) : "",
          ...(r.events || []).map((e) => h("span", { class: "chip chip--sound" }, e))].filter(Boolean));
        engine.textContent = r.tags?.length ? `Sound classifier: ${r.tags.slice(0, 4).map((t) => `${t.label} ${Math.round(t.score * 100)}%`).join(" · ")}` :
          r.classifier ? `Sound classifier: ${r.classifier}` : "";
      };
      const finish = () => setResult("mic", t1.isDone() && t2.isDone() ? "pass" : "fail");
      const record = async (which) => {
        fb.set("wait", "Listening for 6 seconds…", which === 1 ? "Speak now, from where the participant will sit." : "Clap a rhythm, sing a line, or play a song now.");
        await quiet();                       // never record Reachy's own voice
        speak(which === 1 ? "Okay, go ahead." : "Okay, perform now.", { important: true });
        await quiet();
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
          fb.set(got ? "pass" : "fail", got ? `Reachy recognised: ${r.events.join(", ")}` : "Reachy didn't recognise the performance", r.speech ? `It heard words: “${r.speech}”` : "",
            got ? "" : "Make it longer (3+ seconds) and closer to Reachy: clap at least three times, or play music louder.");
        }
        finish();
      };
      area.append(h("ul", { class: "tasks" }, t1.el, t2.el), bars, heard, engine,
        h("div", { class: "btn-row" }, busyBtn("Record speech", () => record(1)), busyBtn("Record a performance", () => record(2), false)));
    },

    talk(fb, area) {
      // Three short exchanges, each closed by Reachy so the setup keeps moving.
      const log = h("ol", { class: "chatlog" });
      const line = (who, text) => { log.append(h("li", { class: `chatlog__${who}` }, h("b", {}, who === "reachy" ? "Reachy" : "You"), h("span", {}, text))); log.lastChild.scrollIntoView({ block: "nearest" }); };
      const slot = h("div");
      let heardCount = 0;
      const turn = async (text, listen = 7) => {
        line("reachy", text);
        const r = await post("/api/check/chat", { text, listen });
        if (!r.ok) throw new Error(r.detail || "Audio problem");
        if (listen) { if (r.heard) { heardCount += 1; line("you", r.heard); } else line("you", "(Reachy heard nothing)"); }
        return r.heard;
      };
      const firstWord = (t) => (t || "").replace(/^(my name is|i'm|i am|it's|me llamo|soy)\s+/i, "").split(/[\s,.!?]+/)[0];
      area.append(h("p", { class: "instruct" }, "Reachy will ask three quick questions. Answer out loud, from where the participant will sit."), log,
        h("div", { class: "btn-row" }, busyBtn("▶ Start the chat", async () => {
          log.replaceChildren(); slot.replaceChildren(); heardCount = 0;
          fb.set("wait", "Talking with Reachy…", "Answer each question when Reachy stops speaking.");
          const yes = await turn("Hi! Can you hear me okay? Say yes if you can.");
          await turn(yes ? "Great, I heard you. That works! Next question." : "Hmm, I didn't catch that, but let's keep going.", 0);
          const name = await turn("What's your name?");
          await turn(name ? `Nice to meet you, ${firstWord(name)}! Okay, my ears work.` : "That's okay. Let's try one more.", 0);
          const word = await turn("Tell me one word that describes your day.");
          await turn(word ? `${firstWord(word)}. I like that. Well, now you know this works. Let's continue with the next step!` : "Alright. Now you know how this works. Let's continue with the next step!", 0);
          slot.replaceChildren(ask("Was Reachy's voice clear, and did it understand you?",
            () => { const ok = heardCount >= 2; fb.set(ok ? "pass" : "fail", ok ? "Talking with Reachy works" : "Reachy understood too few answers", `It understood ${heardCount} of 3 answers.`, ok ? "" : "Speak a bit louder and closer, and wait until Reachy has finished talking."); setResult("talk", ok ? "pass" : "fail"); slot.replaceChildren(); },
            () => { fb.set("fail", "The conversation wasn't clear", "", "Turn up the Mac's volume for “Reachy Mini Audio” (System Settings › Sound), move closer, or reduce noise in the room."); setResult("talk", "fail"); }));
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
        const it = items[e.step];
        if (!it) return;
        it.el.classList.toggle("is-moving", e.status === "moving");
        it.el.classList.toggle("is-failed", e.status === "failed");
        if (e.status === "done") it.done();
        if (e.measured != null) it.el.title = `Body turned ${e.measured}°`;
      });
      async function run(group) {
        if (running) return;
        moves.filter((m) => !group || m.group === group).forEach((m) => { items[m.key].done(false); items[m.key].el.classList.remove("is-failed"); });
        fb.set("wait", `Reachy is moving${group ? ` (${group})` : ""}…`, "Watch each move as it's ticked off. Body turns are measured.");
        const r = await post("/api/check/mobility", group ? { group } : {});
        if (!r.ok) { fb.set("fail", r.body_stuck ? "The body didn't turn" : r.detail, r.body_stuck ? r.detail : "", r.fix); setResult("mobility", "fail"); return; }
        const all = moves.every((m) => items[m.key].isDone());
        slot.replaceChildren(ask(all ? "Did every move look smooth and complete?" : `Did the ${group} moves look right?`,
          () => { slot.replaceChildren(); fb.set(all ? "pass" : "wait", all ? "Full range of motion" : `${group} moves look good`, all ? r.detail : "Run the other groups, or Run every move, to finish."); if (all) setResult("mobility", "pass"); },
          () => { fb.set("fail", "Something looked off", "", "Make sure nothing touches the head, antennas or base and Reachy sits on a flat surface. Power-cycle the robot if a joint seems stuck."); setResult("mobility", "fail"); }));
      }
      return off;
    },

    see(fb, area) {
      // Part 1: gaze (face it, turn away, look back). Part 2: follow-me game, narrated by Reachy,
      // going beyond the camera's view so the body has to turn.
      const label = h("span", { class: "viewport__label" }, "Starting the camera…");
      const vp = h("div", { class: "viewport viewport--small" }, h("span", { class: "viewport__grid", "aria-hidden": "true" }), label);
      const arc = h("div", { class: "arc", "aria-hidden": "true" },
        h("span", { class: "arc__zone arc__zone--l" }, "your left"), h("span", { class: "arc__zone arc__zone--m" }, "middle"), h("span", { class: "arc__zone arc__zone--r" }, "your right"),
        h("span", { class: "arc__you" }, "you"), h("span", { class: "arc__reachy" }));
      const coachHint = h("p", { class: "coach__hint", role: "status" });
      const coach = h("div", { class: "coach" }, h("span", { class: "coach__arrow", "aria-hidden": "true" }),
        h("div", {}, h("strong", { class: "coach__text" }, "Sit in front of Reachy and look at it"), coachHint));
      const ROUND = [
        { text: "Look straight at Reachy", say: "First, look straight at me.", ok: (e) => e.state === "facing", zone: 0, part: 1 },
        { text: "Turn your head to the side", say: "Now turn your head to the side.", ok: (e) => e.state === "turned" || e.state === "tracking", zone: 0, part: 1 },
        { text: "Look back at Reachy", say: "And look back at me.", ok: (e) => e.state === "facing", zone: 0, part: 1 },
        { text: "Stand up, in front of Reachy", say: "I can see where you look. Now let's play follow me! I'm facing forward: stand up right in front of me.", ok: (e) => e.face && Math.abs(e.angle) < 15, zone: 0, part: 2, center: true },
        { text: "Walk FAR to your left, past the edge of the camera", say: "Now walk far to your left, even out of my view. I'll turn my body to find you.", ok: (e) => e.face && e.angle > 45, zone: -1, part: 2 },
        { text: "Now walk FAR to your right", say: "Found you! Now walk all the way over to your right.", ok: (e) => e.face && e.angle < -45, zone: 1, part: 2 },
        { text: "Come back to the middle", say: "Perfect. Come back to the middle, in front of me.", ok: (e) => e.face && Math.abs(e.angle) < 18, zone: 0, part: 2 },
      ];
      const tasks = ROUND.map((r) => task(r.text));
      const pickerSlot = h("div");
      let step = -1, hold = 0, stopVideo = () => {}, maxBody = 0, following = false;
      let progressT = Date.now(), nudgeT = 0, lastE = null;
      const setStep = (i, cheer = false) => {
        step = i;
        progressT = Date.now();
        tasks.forEach((t, j) => t.el.classList.toggle("is-current", j === i));
        if (i >= ROUND.length) return;
        const r = ROUND[i];
        if (r.center) post("/api/check/track/center").catch(() => {});   // so "in front of me" is unambiguous
        coach.dataset.zone = String(r.zone);
        coach.querySelector(".coach__text").textContent = r.text;
        coachHint.textContent = "";
        arc.dataset.target = String(r.zone);
        fb.set("wait", r.text, r.zone ? "Walk slowly. Reachy turns its head first, then its body. If you leave its view, it keeps turning to find you." : "");
        say(`${cheer ? praise() + " " : ""}${r.say}`, true);
      };
      // Stuck on a step for a while? Say exactly what to change, from what Reachy sees right now.
      const nudge = () => {
        if (step < 0 || step >= ROUND.length || Date.now() - progressT < 12000 || Date.now() - nudgeT < 12000) return;
        nudgeT = Date.now();
        const r = ROUND[step], e = lastE || {};
        let text;
        if (!e.face) text = "I can't see your face. Turn toward me, about one metre away, so I can find you.";
        else if (r.zone === -1) text = e.angle > 25 ? "Almost! A few more steps to your left." : "Keep walking to your left, slowly.";
        else if (r.zone === 1) text = e.angle < -25 ? "Almost! A few more steps to your right." : "Keep walking to your right, slowly.";
        else if (r.part === 2) text = e.angle > 15 ? "You're on your left. Move toward the middle, in front of my base." : e.angle < -15 ? "You're on your right. Move toward the middle, in front of my base." : "Hold still for a second, facing me.";
        else if (step === 1) text = "Turn your head clearly to the side, like you're looking at the wall.";
        else text = "Look straight at me for a second.";
        coachHint.textContent = `Reachy: “${text}”`;
        say(text, true);
      };
      async function start() {
        tasks.forEach((t) => t.done(false)); hold = 0; maxBody = 0; active = true;
        const r = await post("/api/check/track");
        following = r.following;
        if (!following) toast("Reachy isn't connected: only the camera is tested (no turning).", "error");
        stopVideo(); stopVideo = liveVideo(vp);
        setStep(0);
      }
      async function choose() {
        await post("/api/check/track/stop");
        stopVideo(); vp.classList.remove("has-video");
        pickerSlot.replaceChildren(h("p", { class: "muted" }, "Taking a picture with each camera…"));
        pickerSlot.replaceChildren(await cameraPicker(async () => { pickerSlot.replaceChildren(); await start(); }));
      }
      area.append(coach, h("div", { class: "follow-grid" }, h("div", {}, vp, arc),
        h("div", {}, h("ul", { class: "tasks" }, tasks.map((t) => t.el)),
          h("button", { type: "button", class: "link-sm", onclick: () => choose() }, "Wrong camera? Choose another"))),
      h("div", { class: "btn-row" }, busyBtn("▶ Start", start)), pickerSlot,
      h("p", { class: "muted small" }, "Reachy follows people with its camera, and turns its body to search when they walk out of view. Following a voice by sound alone isn't available in this version."));
      let active = false;
      const off = onEvent((e) => {
        if (e.kind !== "track" || step < 0) return;
        if (e.hint) {                       // Reachy's spoken hint, also shown in writing
          coachHint.textContent = `Reachy: “${e.hint_text}”`;
          coach.classList.toggle("coach--warn", e.hint !== "found");
          return;
        }
        if (e.done) {                       // never "time out": if the camera test ends early, carry on
          if (active && step < ROUND.length) { say("One moment, restarting my camera."); post("/api/check/track").catch(() => {}); }
          return;
        }
        lastE = e;
        nudge();
        if (e.ok === false) { fb.set("fail", "The camera didn't start", e.detail, e.fix); setResult("see", "fail"); return; }
        vp.dataset.state = e.state;
        maxBody = Math.max(maxBody, Math.abs(e.body || 0));
        const where = e.angle > 10 ? "your left" : e.angle < -10 ? "your right" : "middle";
        label.textContent = e.state === "search" ? "Looking for you…" :
          e.face ? `${e.state === "facing" ? "Facing Reachy" : e.state === "turned" ? "Turned away" : "Following your shape"} · ${where}${e.following ? ` · body ${e.body}°` : ""}` : "No one in view";
        if (e.face) arc.style.setProperty("--pos", String(Math.max(-1, Math.min(1, -e.angle / 70))));
        arc.classList.toggle("has-you", !!e.face);
        if (step >= ROUND.length) return;
        hold = ROUND[step].ok(e) ? hold + 1 : 0;
        if (hold >= (ROUND[step].part === 1 ? 2 : 4)) {     // hold the position briefly so a glance doesn't count
          tasks[step].done(); hold = 0;
          if (step < ROUND.length - 1) { setStep(step + 1, true); return; }
          setStep(ROUND.length);
          active = false;
          coach.querySelector(".coach__text").textContent = "Done!";
          // The head leads by up to 35 deg, so the body only covers the rest: a person ~45-60 deg to the side
          // needs ~10-25 deg of body turn. 15 deg proves the body joined in; below that it didn't really move.
          const bodyOk = !following || maxBody >= 15;
          if (bodyOk) {
            fb.set("pass", following ? `I followed you the whole way, head and body together (body turned up to ${maxBody}°)` : "Gaze and tracking work",
              following ? "" : "Connect Reachy to test the turning too.");
            setResult("see", "pass");
          } else {
            fb.set("fail", "Reachy's head followed you, but its body barely turned", `The body turned only ${maxBody}°, the head did the rest.`,
              "Walk further to each side (past the edge of the picture) and run it again. If the body still doesn't move, run Range of motion: it measures the body motor.");
            setResult("see", "fail");
          }
        }
      });
      fb.set("wait", "Press Start, then follow Reachy's instructions (it says them out loud).");
      return () => { active = false; off(); stopVideo(); post("/api/check/track/stop").catch(() => {}); };
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
    if (i >= STEPS.length) {
      swap(stage, summary());
      setCrumbs([{ label: "Main menu", href: "#/menu" }, "Setup checklist", "Summary"]);
      const missing = ["reachy", "sensors", "mic", "talk"].filter((k) => results[k] !== "pass").map((k) => STEPS.find((x) => x.key === k).title);
      speak(missing.length ? `Setup finished, but these still need attention: ${missing.join(", ")}.` : "Setup complete! Everything works. Press Create a session when you're ready.", { important: true });
      return;
    }
    const s = STEPS[i];
    setCrumbs([{ label: "Main menu", href: "#/menu" }, "Setup checklist", `${i + 1} · ${s.title}`]);
    const voiceStep = s.key === "see";        // the person watches Reachy here, so Reachy always talks
    const fb = feedback(i === STEPS.length - 1, voiceStep);
    const area = h("div", { class: "screen__area" });
    speak(`Step ${i + 1} of ${STEPS.length}: ${s.title}. ${s.intro}`, { important: true, always: voiceStep });
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
    const critical = ["reachy", "sensors", "mic", "talk"].filter((k) => results[k] !== "pass");
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
  const onRepaired = () => {                    // Repair finished: re-run this step from scratch to see if it's fixed
    if (idx >= STEPS.length) return;
    const k = STEPS[idx].key;
    repairs[k] = (repairs[k] || 0) + 1;
    show(idx);
  };
  window.addEventListener("repairdone", onRepaired);
  show(idx);
  return () => { stopCurrent?.(); window.removeEventListener("debugchange", onDebug); window.removeEventListener("repairdone", onRepaired); };
}
