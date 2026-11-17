/**
 * Heart-rate chart on a canvas: BPM line, baseline band (±15 = the jump
 * threshold), stage bands, and a dot per Reachy turn coloured by mode
 * (ringed when that turn was triggered by a heart jump).
 * Live mode shows a sliding window; replay mode shows the whole session.
 */
import { h } from "../ui.js";
import { MODES, BPM_STOP } from "../constants.js";

export function heartChart({ windowSecs = 180, height = 220 } = {}) {
  const canvas = h("canvas", { class: "heart-chart__canvas", height });
  const root = h("div", { class: "heart-chart" }, canvas);
  const state = { samples: [], stages: [], turns: [], baseline: null, window: windowSecs, cursor: null };
  let raf = 0;

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  function draw() {
    raf = 0;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, hh = height;
    if (canvas.width !== Math.round(w * dpr)) canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(hh * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, hh);
    const s = state.samples;
    if (!s.length) {
      ctx.fillStyle = css("--muted");
      ctx.font = "13px system-ui";
      ctx.fillText("Waiting for a heartbeat…", 12, hh / 2);
      return;
    }
    const tEnd = state.cursor ?? s[s.length - 1][0];
    const tStart = state.window ? Math.max(s[0][0], tEnd - state.window) : s[0][0];
    const vis = s.filter(([t]) => t >= tStart && t <= tEnd);
    const bpms = vis.map(([, b]) => b).concat(state.baseline ? [state.baseline - 18, state.baseline + 18] : []);
    const lo = Math.floor(Math.min(...bpms) - 4), hi = Math.ceil(Math.max(...bpms) + 4);
    const pad = { l: 34, r: 8, t: 8, b: 18 };
    const X = (t) => pad.l + ((t - tStart) / Math.max(1, tEnd - tStart)) * (w - pad.l - pad.r);
    const Y = (b) => pad.t + (1 - (b - lo) / Math.max(1, hi - lo)) * (hh - pad.t - pad.b);

    // stage bands
    state.stages.forEach((st, i) => {
      const end = state.stages[i + 1]?.t ?? tEnd;
      if (end < tStart || st.t > tEnd) return;
      ctx.fillStyle = i % 2 ? "rgba(255,255,255,0.025)" : "rgba(255,255,255,0.05)";
      ctx.fillRect(X(Math.max(st.t, tStart)), pad.t, X(Math.min(end, tEnd)) - X(Math.max(st.t, tStart)), hh - pad.t - pad.b);
      ctx.fillStyle = css("--muted");
      ctx.font = "11px system-ui";
      if (st.t >= tStart) ctx.fillText(String(st.stage), X(st.t) + 4, hh - 5);
    });

    // baseline band = no-comment zone
    if (state.baseline) {
      ctx.fillStyle = "rgba(123,224,168,0.08)";
      ctx.fillRect(pad.l, Y(state.baseline + 15), w - pad.l - pad.r, Y(state.baseline - 15) - Y(state.baseline + 15));
      ctx.strokeStyle = "rgba(123,224,168,0.5)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(pad.l, Y(state.baseline)); ctx.lineTo(w - pad.r, Y(state.baseline)); ctx.stroke();
      ctx.setLineDash([]);
    }
    if (hi > BPM_STOP) {
      ctx.strokeStyle = "rgba(255,77,77,0.6)";
      ctx.beginPath(); ctx.moveTo(pad.l, Y(BPM_STOP)); ctx.lineTo(w - pad.r, Y(BPM_STOP)); ctx.stroke();
    }

    // axis labels
    ctx.fillStyle = css("--muted");
    ctx.font = "11px system-ui";
    for (const b of [lo, Math.round((lo + hi) / 2), hi]) ctx.fillText(String(b), 4, Y(b) + 4);

    // BPM line
    ctx.strokeStyle = css("--heart");
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.beginPath();
    vis.forEach(([t, b], i) => (i ? ctx.lineTo(X(t), Y(b)) : ctx.moveTo(X(t), Y(b))));
    ctx.stroke();

    // Reachy turns
    for (const turn of state.turns) {
      if (turn.t < tStart || turn.t > tEnd) continue;
      const near = vis.reduce((a, c) => (Math.abs(c[0] - turn.t) < Math.abs(a[0] - turn.t) ? c : a), vis[0]);
      ctx.fillStyle = MODES[turn.mode]?.color || "#fff";
      ctx.beginPath(); ctx.arc(X(turn.t), Y(near[1]), 4.5, 0, Math.PI * 2); ctx.fill();
      if (turn.heart_jump) {
        ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(X(turn.t), Y(near[1]), 8, 0, Math.PI * 2); ctx.stroke();
      }
    }
  }

  const schedule = () => { if (!raf) raf = requestAnimationFrame(draw); };
  new ResizeObserver(schedule).observe(canvas);

  return {
    el: root,
    reset() { Object.assign(state, { samples: [], stages: [], turns: [], baseline: null, cursor: null }); schedule(); },
    addSample(t, bpm) { state.samples.push([t, bpm]); if (state.samples.length > 4000) state.samples.shift(); schedule(); },
    addStage(t, stage) { state.stages.push({ t, stage }); schedule(); },
    addTurn(turn) { state.turns.push(turn); schedule(); },
    setBaseline(b) { state.baseline = b; schedule(); },
    setWindow(secs) { state.window = secs; schedule(); },
    setCursor(t) { state.cursor = t; schedule(); },
    get samples() { return state.samples; },
  };
}
