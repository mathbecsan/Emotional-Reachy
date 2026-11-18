/**
 * Part 2 / stage 7: the participant's heartbeat from stages 0-6 played back
 * as colour and waves (full screen on the projector). Ribbons follow the
 * look of pulse_triple.py: a bright "hero" line with softer ribbons around
 * it, pink -> purple -> blue -> cyan -> green. Colour temperature follows
 * BPM relative to the baseline; every beat makes the ribbons swell.
 *
 * #/projection           live: follows the running session's sensors / heart
 * #/projection/<session> replay: compresses that session into `duration` s
 */
import { h } from "../ui.js";
import { api, onEvent } from "../api.js";
import { STAGES, MODES } from "../constants.js";

const N_LINES = 12, N_POINTS = 120;

function palette(n, reverse) {
  return Array.from({ length: n }, (_, j) => {
    let x = j / (n - 1); if (reverse) x = 1 - x;
    return 330 - 194 * x; // hue: pink (330) -> green (136)
  });
}

export function projectionView(outlet, name) {
  const canvas = h("canvas", { class: "projection__canvas" });
  const caption = h("div", { class: "projection__caption" });
  const hint = h("div", { class: "projection__hint" }, "F fullscreen · Space pause · Esc back");
  const testTag = h("div", { class: "projection__test", hidden: true }, "Projector test · simulated heartbeat");
  const root = h("div", { class: "projection" }, canvas, caption, hint, testTag);
  outlet.replaceChildren(root);
  document.body.classList.add("is-projection");

  const hues = [palette(N_POINTS, false), palette(N_POINTS, true)];
  const st = { bpm: 72, baseline: 72, energy: 0, phase: 0, mode: null, stage: null, paused: false, t0: performance.now(), live: !name };
  let replay = null, raf = 0, offEvents = null, lastFrame = performance.now();
  // Setup checklist link (same browser): this window says what it shows and what it receives.
  const link = { heart: 0, beats: 0, testHeart: 0, testBeats: 0, frames: 0, fps: 0, lastBpm: null, testUntil: 0 };
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("bis-projection") : null;
  const report = () => channel?.postMessage({
    type: "status", live: st.live, w: innerWidth, h: innerHeight, screenW: screen.width, screenH: screen.height,
    fullscreen: !!document.fullscreenElement, fps: link.fps, heart: link.heart, beats: link.beats,
    testHeart: link.testHeart, testBeats: link.testBeats, bpm: link.lastBpm, visible: document.visibilityState === "visible" });
  if (channel) channel.onmessage = (m) => { if (m.data?.type === "ping") report(); };
  const reportTimer = setInterval(() => { link.fps = link.frames; link.frames = 0; report(); }, 1000);

  function key(ev) {
    if (ev.key === "f" || ev.key === "F") (document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen()).catch(() => {});
    if (ev.key === " ") { st.paused = !st.paused; ev.preventDefault(); }
    if (ev.key === "Escape" && !document.fullscreenElement) location.hash = name ? `#/sessions/${name}` : "#/";
  }
  window.addEventListener("keydown", key);

  if (name) {
    api(`/api/sessions/${encodeURIComponent(name)}`).then((log) => {
      const end = log.events.find((e) => e.kind === "stage" && e.stage === 7)?.t ?? log.heart.at(-1)?.[0] ?? 1;
      replay = {
        heart: log.heart.filter(([t]) => t <= end),
        stages: log.events.filter((e) => e.kind === "stage" && e.stage <= 6),
        turns: log.events.filter((e) => e.kind === "turn"),
        baseline: log.events.find((e) => e.kind === "baseline")?.bpm ?? 72,
        end, duration: 120, // protocol: 2 min playback
      };
      st.baseline = replay.baseline;
    });
  } else {
    offEvents = onEvent((e) => {
      if (e.kind === "heart") { st.bpm = e.bpm; link.heart += 1; link.lastBpm = e.bpm; if (e.test) { link.testHeart += 1; link.testUntil = performance.now() + 2500; } }
      if (e.kind === "pulse" && e.beat) { link.beats += 1; if (e.test) link.testBeats += 1; }
      if (e.kind === "baseline" && e.bpm) st.baseline = e.bpm;
      if (e.kind === "stage") st.stage = e.stage;
      if (e.kind === "turn") st.mode = e.mode;
      if (e.kind === "pulse" && e.beat) { st.energy = 1; st.lastRealBeat = performance.now(); }
    });
  }

  function replayAt(sessionT) {
    const hs = replay.heart;
    let lo = 0, hi = hs.length - 1;
    while (lo < hi) { const m = (lo + hi) >> 1; if (hs[m][0] < sessionT) lo = m + 1; else hi = m; }
    st.bpm = hs[lo]?.[1] ?? st.bpm;
    st.stage = replay.stages.filter((s) => s.t <= sessionT).pop()?.stage ?? 0;
    st.mode = replay.turns.filter((s) => s.t <= sessionT).pop()?.mode ?? null;
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    link.frames += 1;
    testTag.hidden = now > link.testUntil;
    const dt = Math.min(0.05, (now - lastFrame) / 1000); lastFrame = now;
    if (st.paused) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, hh = canvas.clientHeight;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(hh * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(hh * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (replay) {
      const p = ((now - st.t0) / 1000 / replay.duration) % 1;
      replayAt(p * replay.end);
    }
    // Beat clock at the current BPM; real sensor beats take over when they arrive.
    st.phase += dt * (st.bpm / 60);
    if (st.phase >= 1) {
      st.phase -= 1;
      if (now - (st.lastRealBeat || -1e9) > 3000) st.energy = Math.max(st.energy, 0.85);
    }
    st.energy *= Math.exp(-dt / 0.35);

    const arousal = Math.max(-1, Math.min(1, (st.bpm - st.baseline) / 25));
    ctx.fillStyle = `rgba(0,0,0,${0.22})`;
    ctx.fillRect(0, 0, w, hh);
    const t = now / 1000;
    const xs = Array.from({ length: N_POINTS }, (_, j) => j / (N_POINTS - 1));
    for (let s = 0; s < 2; s++) {
      for (let i = 0; i < N_LINES; i++) {
        const u = i / (N_LINES - 1), mid = 1 - Math.abs(2 * u - 1);
        const freq = 0.7 + 1.3 * ((i * 0.618 + s * 0.31) % 1);
        const speed = (0.25 + 0.35 * ((i * 0.37) % 1)) * (1 + 0.8 * Math.max(0, arousal));
        const amp = hh * (0.05 + 0.10 * st.energy * (0.4 + 0.6 * mid)) * (1 + 0.6 * Math.max(0, arousal));
        ctx.lineWidth = i === N_LINES >> 1 ? 3 : 1.2;
        for (let j = 0; j < N_POINTS - 1; j++) {
          const x0 = xs[j], x1 = xs[j + 1];
          const y = (x) => {
            const env = Math.pow(Math.sin(Math.PI * x), 0.4);
            const beat = Math.exp(-Math.pow(((x * 3 - t * (st.bpm / 60) * 0.5 + u * 0.4) % 1 + 1) % 1 - 0.15, 2) / 0.004);
            return hh / 2 - env * (amp * Math.sin(2 * Math.PI * freq * x + i * 0.9 + s * 1.7 + t * speed)
              + beat * amp * 1.4 * st.energy + (u - 0.5) * hh * 0.16 + (s ? 1 : -1) * hh * 0.03);
          };
          const hue = (hues[s][j] + arousal * 40 + 360) % 360;
          const light = 45 + 25 * st.energy * mid;
          ctx.strokeStyle = `hsla(${hue}, 85%, ${light}%, ${0.25 + 0.6 * mid})`;
          ctx.beginPath(); ctx.moveTo(x0 * w, y(x0)); ctx.lineTo(x1 * w, y(x1)); ctx.stroke();
        }
      }
    }
    const stage = st.stage != null ? STAGES[st.stage]?.name : "";
    caption.textContent = `${Math.round(st.bpm)} BPM${stage ? " · " + stage : ""}${st.mode ? " · Reachy " + (MODES[st.mode]?.label || "").toLowerCase() : ""}`;
  }
  raf = requestAnimationFrame(frame);

  return () => {
    cancelAnimationFrame(raf);
    clearInterval(reportTimer);
    channel?.postMessage({ type: "closed" });
    channel?.close();
    window.removeEventListener("keydown", key);
    offEvents?.();
    document.body.classList.remove("is-projection");
  };
}
