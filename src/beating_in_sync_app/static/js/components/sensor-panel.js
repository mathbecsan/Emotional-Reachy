/**
 * The two MAX30102 pulse sensors (Arduino Nano): finger on/off, signal lock,
 * per-sensor BPM, and the live normalised waveform -- the same quantities
 * pulse_triple.py shows in its signal panels, for checking the hardware
 * before and during a session.
 */
import { h } from "../ui.js";

export function sensorPanel() {
  const rows = [0, 1].map((i) => {
    const canvas = h("canvas", { class: "sensor__wave", height: 46 });
    const status = h("span", { class: "sensor__status" }, "no data");
    const bpm = h("span", { class: "sensor__bpm" }, "––");
    const row = h("div", { class: "sensor" },
      h("span", { class: "sensor__name" }, `Sensor ${i + 1}`), status, bpm, canvas);
    return { row, canvas, status, bpm };
  });
  const source = h("span", { class: "card__aside" }, "");
  const root = h("section", { class: "card sensors", hidden: true },
    h("div", { class: "card__head" }, h("h2", { class: "card__title" }, "Pulse sensors"), source),
    ...rows.map((r) => r.row));

  function drawWave(canvas, wave, color) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, hh = 46;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(hh * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, hh);
    if (!wave?.length) return;
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    wave.forEach((v, j) => {
      const x = (j / (wave.length - 1)) * w, y = hh - 4 - Math.min(1.1, v) * (hh - 8);
      j ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
  }

  return {
    el: root,
    reset() { root.hidden = true; },
    update(e) {
      root.hidden = false;
      source.textContent = e.source || "";
      (e.sensors || []).forEach((s, i) => {
        const r = rows[i]; if (!r) return;
        r.status.textContent = !s.finger ? "no finger" : s.signal ? (s.bpm ? "locked" : "finding beat…") : "settling…";
        r.row.dataset.state = !s.finger ? "off" : s.signal && s.bpm ? "ok" : "wait";
        r.bpm.textContent = s.bpm ? `${Math.round(s.bpm)} BPM` : "––";
        if (s.spikes) r.status.textContent += ` · ${s.spikes} spikes`;
        drawWave(r.canvas, s.wave, i ? "#5cc8ff" : "#ff6fb1");
      });
    },
  };
}
