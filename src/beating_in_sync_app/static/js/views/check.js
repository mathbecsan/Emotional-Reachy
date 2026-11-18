/**
 * Check setup: one row per part of the installation, each with a status, a test
 * button, and what to do when it fails. Ends with "Start a session".
 */
import { h, toast } from "../ui.js";
import { api, onEvent } from "../api.js";

const post = (path, body = {}) => api(path, body);

export function checkView(outlet) {
  const rows = {};
  let running = false;

  function row(id, title, what, actions = [], extra = null) {
    const dot = h("span", { class: "check__dot", "aria-hidden": "true" });
    const detail = h("span", { class: "check__detail" }, "Checking…");
    const fix = h("span", { class: "check__fix", hidden: true });
    const el = h("li", { class: "check", dataset: { state: "wait" } },
      dot,
      h("div", { class: "check__body" }, h("strong", {}, title), h("span", { class: "check__what" }, what), detail, fix, extra),
      h("div", { class: "check__actions" }, actions));
    rows[id] = {
      el,
      set(r) {
        el.dataset.state = r.busy ? "wait" : r.ok ? "ok" : "bad";
        detail.textContent = r.detail || "";
        fix.hidden = !r.fix || r.ok;
        fix.textContent = r.fix || "";
      },
    };
    return el;
  }

  const action = (label, fn, primary = false) => {
    const b = h("button", { type: "button", class: `btn btn--small${primary ? " btn--primary" : ""}` }, label);
    b.addEventListener("click", async () => {
      if (running) { toast("A session is running: tests are available once it ends.", "error"); return; }
      b.disabled = true;
      const old = b.textContent;
      b.textContent = "Testing…";
      try { await fn(); } catch (e) { toast(e.message, "error"); }
      b.disabled = false;
      b.textContent = old;
    });
    return b;
  };

  // live sensor tiles
  const sensorTile = (n) => {
    const state = h("span", { class: "sensor-tile__state" }, "—");
    const bpm = h("span", { class: "sensor-tile__bpm" }, "––");
    const el = h("div", { class: "sensor-tile" }, h("span", { class: "sensor-tile__name" }, `Sensor ${n}`), state, h("span", {}, bpm, h("small", {}, " BPM")));
    return { el, set(s) { el.dataset.on = s.finger ? "1" : "0"; state.textContent = s.finger ? "Finger detected" : "No finger"; bpm.textContent = s.bpm ?? "––"; } };
  };
  const tiles = [sensorTile(1), sensorTile(2)];
  const probeBox = h("div", { class: "sensor-tiles", hidden: true }, tiles[0].el, tiles[1].el,
    h("p", { class: "muted sensor-tiles__hint" }, "Rest a finger lightly on each sensor and keep still. The heart rate appears after about 5 seconds."));

  const heard = h("p", { class: "check__heard", hidden: true });
  const list = h("ol", { class: "checks" },
    row("reachy", "Reachy", "The robot is on and this app is connected to it.",
      [action("Connect Reachy", async () => { const r = await post("/api/check/connect"); rows.reachy.set(r); toast(r.ok ? "Reachy connected" : r.detail, r.ok ? "info" : "error"); }),
        action("Test movement", async () => { const r = await post("/api/check/move"); rows.reachy.set(r); })]),
    row("sensors", "Pulse sensors", "The Arduino streams both sensors and a finger gives a heart rate.",
      [action("Test sensors", async () => { await post("/api/check/sensors", {}); probeBox.hidden = false; rows.sensors.set({ busy: true, detail: "Connecting to the Arduino (a few seconds)…" }); }, true)], probeBox),
    row("speaker", "Speaker", "Reachy's voice plays through its own speaker.",
      [action("Play a hello", async () => rows.speaker.set(await post("/api/check/speaker")))]),
    row("mic", "Microphone", "Reachy hears and understands speech.",
      [action("Record 4 seconds", async () => {
        rows.mic.set({ busy: true, detail: "Recording… say something to Reachy" });
        const r = await post("/api/check/mic");
        rows.mic.set(r);
      })], heard),
    row("camera", "Camera", "Reachy can see the participant's face.",
      [action("Test camera", async () => rows.camera.set(await post("/api/check/camera")))]),
    row("voice", "Voice service", "Internet connection to ElevenLabs (speech and hearing).", []));

  outlet.replaceChildren(h("div", { class: "page page--narrow" },
    h("header", { class: "page__head" },
      h("div", {}, h("h1", { class: "page__title" }, "Check setup"),
        h("p", { class: "page__lede" }, "Run these tests before each participant. Green means ready.")),
      h("button", { class: "btn", type: "button", onclick: refresh }, "Re-check")),
    h("div", { class: "banner banner--warn", hidden: true, dataset: { role: "running" } }, "A session is running. Tests that use the hardware are paused until it ends."),
    list,
    h("div", { class: "page__next" }, h("a", { class: "btn btn--primary btn--big", href: "#/new" }, "Next: New session →"))));

  async function refresh() {
    try {
      const [c, st] = await Promise.all([api("/api/check"), api("/api/state")]);
      running = st.running;
      outlet.querySelector("[data-role=running]").hidden = !running;
      const reachyOk = c.daemon.ok && c.robot.ok;
      rows.reachy.set({ ok: reachyOk, detail: !c.daemon.ok ? `Robot software: ${c.daemon.detail}` : c.robot.detail,
        fix: !c.daemon.ok ? c.daemon.fix : c.robot.fix });
      rows.sensors.set(c.sensors);
      rows.voice.set(c.voice);
      rows.speaker.set({ ok: c.audio.ok && c.voice.ok, detail: c.audio.detail, fix: c.audio.ok ? "Press Play a hello to hear it." : c.audio.fix });
      rows.mic.set({ ok: c.audio.ok, detail: c.audio.ok ? "Press Record to test hearing." : c.audio.detail, fix: c.audio.fix });
      rows.camera.set({ ok: true, detail: "Press Test camera to take a picture.", fix: "" });
      rows.camera.el.dataset.state = "idle";
      if (c.audio.ok) { rows.speaker.el.dataset.state = "idle"; rows.mic.el.dataset.state = "idle"; }
    } catch (e) { toast(`Can't reach the app: ${e.message}`, "error"); }
  }

  const off = onEvent((e) => {
    if (e.kind !== "probe") return;
    if (e.done) { rows.sensors.set({ ok: true, detail: "Sensor test finished. Press Test sensors to run it again." }); return; }
    if (e.sensors) e.sensors.forEach((s, i) => tiles[i]?.set(s));
    const any = e.sensors?.some((s) => s.bpm);
    rows.sensors.set({ ok: e.ok, detail: e.ok ? (any ? `Heartbeat detected on ${e.port}` : `Streaming from ${e.port} · ${e.left}s left`) : e.detail, fix: e.fix });
  });

  refresh();
  return () => { off(); post("/api/check/sensors/stop").catch(() => {}); };
}
