/**
 * A drawn Reachy Mini (head, two eyes, two antennas) that acts out the
 * current mode -- the "digital twin" when running without the robot, and a
 * glanceable mode indicator when the robot is there.
 */
import { MODES } from "../constants.js";

const NS = "http://www.w3.org/2000/svg";
const POSES = {
  // tilt deg, head dy px, antenna L/R deg (0 = up, + = droop outward), turn px
  sleepy:   { tilt: -6, dy: 14, ant: [62, 62], turn: 0, eyes: 0.15 },
  curious:  { tilt: 14, dy: -2, ant: [-12, -18], turn: 0, eyes: 1 },
  excited:  { tilt: 0, dy: -8, ant: [-28, -28], turn: 0, eyes: 1.1 },
  flirty:   { tilt: 12, dy: 2, ant: [6, -10], turn: 6, eyes: 0.6 },
  teasing:  { tilt: -8, dy: -4, ant: [-30, 10], turn: -6, eyes: 0.7 },
  offended: { tilt: -4, dy: -10, ant: [80, 80], turn: -26, eyes: 0.5 },
  scolding: { tilt: 0, dy: 0, ant: [-38, -38], turn: 0, eyes: 1.2 },
  sincere:  { tilt: 4, dy: 8, ant: [26, 26], turn: 0, eyes: 0.55 },
};

function el(tag, attrs) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

export function reachyFace() {
  const svg = el("svg", { viewBox: "0 0 200 190", class: "reachy-face", role: "img", "aria-label": "Reachy" });
  const head = el("g", { class: "reachy-face__head" });
  const antL = el("g", { class: "reachy-face__ant" });
  const antR = el("g", { class: "reachy-face__ant" });
  for (const [g, x] of [[antL, 70], [antR, 130]]) {
    g.append(el("line", { x1: x, y1: 62, x2: x, y2: 18, stroke: "currentColor", "stroke-width": 4, "stroke-linecap": "round" }));
    g.append(el("circle", { cx: x, cy: 16, r: 6, class: "reachy-face__tip" }));
    g.style.transformOrigin = `${x}px 62px`;
  }
  const shell = el("rect", { x: 42, y: 58, width: 116, height: 86, rx: 40, class: "reachy-face__shell" });
  const eyeL = el("ellipse", { cx: 78, cy: 100, rx: 13, ry: 13, class: "reachy-face__eye" });
  const eyeR = el("ellipse", { cx: 122, cy: 100, rx: 13, ry: 13, class: "reachy-face__eye" });
  head.append(antL, antR, shell, eyeL, eyeR);
  const body = el("path", { d: "M58 186 Q60 150 100 148 Q140 150 142 186 Z", class: "reachy-face__body" });
  svg.append(body, head);
  head.style.transformOrigin = "100px 140px";

  let speaking = null;
  function setMode(mode) {
    const p = POSES[mode] || POSES[MODES[mode]?.pose] || POSES.curious;
    svg.style.setProperty("--mode", MODES[mode]?.color || "#fff");
    head.style.transform = `translate(${p.turn}px, ${p.dy}px) rotate(${p.tilt}deg)`;
    antL.style.transform = `rotate(${-p.ant[0]}deg)`;
    antR.style.transform = `rotate(${p.ant[1]}deg)`;
    for (const e of [eyeL, eyeR]) e.setAttribute("ry", String(Math.max(1.5, 13 * p.eyes)));
    svg.dataset.mode = mode;
  }
  function speak(on) {
    clearTimeout(speaking);
    svg.classList.toggle("reachy-face--speaking", on);
    if (on) speaking = setTimeout(() => svg.classList.remove("reachy-face--speaking"), 4000);
  }
  function listen(on) { svg.classList.toggle("reachy-face--listening", on); }
  setMode("sleepy");
  return { el: svg, setMode, speak, listen };
}
