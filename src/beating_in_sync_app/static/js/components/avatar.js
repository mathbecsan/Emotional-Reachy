/**
 * Reachy Mini drawn in costume for each personality (original artwork, inline SVG).
 * avatar("diva", { size: 120, animate: true }) -> <svg>
 * The base drawing: dark body, white head with two big round eyes, two antennas.
 * Each costume adds a few shapes on top and can change the eyes / antennas.
 */
const NS = "http://www.w3.org/2000/svg";

// eyes: [shape] "open" | "half" | "happy" | "angry" | "sad" | "hearts" | "glasses" | "shades" | "wide" | "narrow"
// ant: antenna angles [left, right] in degrees (0 = straight up, + = outward/droop)
const COSTUMES = {
  base:          { eyes: "open", ant: [-8, 8], extra: "" },
  bored_teen:    { eyes: "half", ant: [-20, 55],
    extra: `<path d="M30 40 Q60 14 90 40 L90 46 L30 46 Z" fill="#5b3fa8"/><rect x="28" y="43" width="64" height="8" rx="4" fill="#7d5fd0"/><circle cx="60" cy="18" r="5" fill="#b98cff"/>` },
  burned_out:    { eyes: "sad", ant: [55, 60],
    extra: `<path d="M57 92 L63 92 L66 112 L60 118 L54 112 Z" fill="#3b5ba5"/><path d="M52 88 L68 88 L60 95 Z" fill="#2c4480"/><rect x="88" y="84" width="14" height="16" rx="3" fill="#e9e3d8"/><path d="M102 88 q6 4 0 8" stroke="#e9e3d8" stroke-width="2.5" fill="none"/><path d="M92 80 q2 -4 0 -7 M97 80 q2 -4 0 -7" stroke="#aaa" stroke-width="1.5" fill="none"/>` },
  noir:          { eyes: "narrow", ant: [-35, 30],
    extra: `<ellipse cx="60" cy="40" rx="42" ry="6" fill="#2a2620"/><path d="M38 40 Q40 16 60 16 Q80 16 82 40 Z" fill="#3a342b"/><rect x="38" y="33" width="44" height="5" fill="#8a7650"/><path d="M34 86 L52 98 L60 90 L68 98 L86 86 L86 112 L34 112 Z" fill="#9a8460"/>` },
  diva:          { eyes: "shades", ant: [-25, 25],
    extra: `<path d="M42 38 L48 24 L54 34 L60 20 L66 34 L72 24 L78 38 Z" fill="#ffd34d" stroke="#e0a800" stroke-width="1.5"/><circle cx="60" cy="22" r="3" fill="#ff6fb1"/><path d="M28 92 Q40 84 50 94 Q60 86 70 94 Q80 84 92 92 Q86 104 60 104 Q34 104 28 92 Z" fill="#ff6fb1" opacity="0.9"/>` },
  hype_bro:      { eyes: "happy", ant: [-30, 30],
    extra: `<rect x="31" y="44" width="58" height="9" rx="4" fill="#ffc94d"/><path d="M84 44 L98 38 L96 50 Z" fill="#ffc94d"/><path d="M20 100 l8 -10 M100 100 l-8 -10" stroke="#ffc94d" stroke-width="4" stroke-linecap="round"/>` },
  villain:       { eyes: "angry", ant: [-15, 15],
    extra: `<path d="M24 88 Q60 80 96 88 L104 118 L16 118 Z" fill="#7a0f1c"/><path d="M24 88 Q60 96 96 88" stroke="#c21f33" stroke-width="3" fill="none"/><path d="M48 80 Q54 76 60 80 Q66 76 72 80" stroke="#1c1c1c" stroke-width="3" fill="none" stroke-linecap="round"/>` },
  tia:           { eyes: "wide", ant: [-20, 20],
    extra: `<path d="M30 46 Q60 18 90 46 Q86 36 60 32 Q34 36 30 46 Z" fill="#ff9a4d"/><circle cx="40" cy="38" r="5" fill="#ffd0a8"/><circle cx="52" cy="32" r="5" fill="#ffd0a8"/><circle cx="68" cy="32" r="5" fill="#ffd0a8"/><circle cx="80" cy="38" r="5" fill="#ffd0a8"/><circle cx="30" cy="70" r="4" fill="#ffd34d"/><circle cx="90" cy="70" r="4" fill="#ffd34d"/>` },
  hypochondriac: { eyes: "wide", ant: [-5, 5], shake: true,
    extra: `<rect x="40" y="70" width="40" height="16" rx="5" fill="#cfeee0"/><path d="M40 74 L30 68 M80 74 L90 68" stroke="#cfeee0" stroke-width="2"/><path d="M44 76 h32 M44 81 h32" stroke="#9dd6bd" stroke-width="1.5"/><rect x="92" y="54" width="5" height="26" rx="2.5" fill="#fff" stroke="#aaa"/><circle cx="94.5" cy="80" r="4" fill="#ff4d4d"/>` },
  smitten:       { eyes: "hearts", ant: [-15, 15],
    extra: `<path d="M18 40 c0 -6 8 -6 8 0 c0 -6 8 -6 8 0 c0 6 -8 10 -8 12 c0 -2 -8 -6 -8 -12 Z" fill="#ff8fc8"/><path d="M88 30 c0 -5 6 -5 6 0 c0 -5 6 -5 6 0 c0 5 -6 8 -6 10 c0 -2 -6 -5 -6 -10 Z" fill="#ff8fc8"/>` },
  jealous:       { eyes: "narrow", ant: [-40, 10], tint: "#e4f5c4", extra: "" },
  smug:          { eyes: "glasses", ant: [-10, 10],
    extra: `<path d="M44 80 Q60 86 76 78" stroke="#1c1c1c" stroke-width="3" fill="none" stroke-linecap="round"/><rect x="40" y="16" width="40" height="8" rx="2" fill="#1c1c1c"/><rect x="56" y="10" width="8" height="8" fill="#1c1c1c"/><path d="M64 14 L84 22" stroke="#ffd34d" stroke-width="2"/>` },
  passive_aggressive: { eyes: "half", ant: [0, 0],
    extra: `<path d="M46 80 L74 80" stroke="#1c1c1c" stroke-width="3" stroke-linecap="round"/><path d="M36 50 L50 54 M84 50 L70 54" stroke="#1c1c1c" stroke-width="2.5" stroke-linecap="round"/>` },
  grumpy:        { eyes: "half", ant: [50, 45],
    extra: `<path d="M34 44 Q60 10 86 44 Z" fill="#4a5a9a"/><path d="M84 40 Q100 44 100 60" stroke="#4a5a9a" stroke-width="6" fill="none"/><circle cx="100" cy="62" r="6" fill="#e9e3d8"/><text x="92" y="30" font-size="12" font-weight="700" fill="#8a8fbf">z</text><text x="100" y="20" font-size="9" font-weight="700" fill="#8a8fbf">z</text>` },
  melodramatic:  { eyes: "sad", ant: [60, 40],
    extra: `<path d="M44 74 q-3 8 0 10 q3 -2 0 -10 Z" fill="#7ac8ff"/><path d="M92 76 l10 -16 l4 4 Z" fill="#c21f33"/><circle cx="104" cy="58" r="6" fill="#ff4d6a"/>` },
};

function eyesSvg(kind) {
  const L = 46, R = 74, Y = 62;
  const pair = (fn) => fn(L) + fn(R);
  switch (kind) {
    case "half": return pair((x) => `<circle cx="${x}" cy="${Y}" r="10" fill="#141418"/><rect x="${x - 12}" y="${Y - 13}" width="24" height="11" fill="#f2f1f7"/><path d="M${x - 11} ${Y - 2} h22" stroke="#141418" stroke-width="2"/>`);
    case "happy": return pair((x) => `<path d="M${x - 9} ${Y + 2} Q${x} ${Y - 10} ${x + 9} ${Y + 2}" stroke="#141418" stroke-width="5" fill="none" stroke-linecap="round"/>`);
    case "angry": return pair((x) => `<circle cx="${x}" cy="${Y + 2}" r="9" fill="#141418"/><circle cx="${x + 2}" cy="${Y}" r="2.5" fill="#ff4d4d"/>`) +
      `<path d="M36 48 L54 54 M84 48 L66 54" stroke="#141418" stroke-width="4" stroke-linecap="round"/>`;
    case "sad": return pair((x) => `<circle cx="${x}" cy="${Y + 3}" r="9" fill="#141418"/><circle cx="${x - 2}" cy="${Y}" r="2.5" fill="#fff"/>`) +
      `<path d="M37 52 L53 48 M83 52 L67 48" stroke="#141418" stroke-width="3" stroke-linecap="round"/>`;
    case "hearts": return pair((x) => `<path d="M${x} ${Y + 9} C${x - 14} ${Y - 1} ${x - 8} ${Y - 12} ${x} ${Y - 4} C${x + 8} ${Y - 12} ${x + 14} ${Y - 1} ${x} ${Y + 9} Z" fill="#ff4d8d"/>`);
    case "glasses": return pair((x) => `<circle cx="${x}" cy="${Y}" r="8" fill="#141418"/><circle cx="${x}" cy="${Y}" r="12" fill="none" stroke="#c9a54a" stroke-width="2.5"/>`) +
      `<path d="M58 ${Y} h4" stroke="#c9a54a" stroke-width="2.5"/>`;
    case "shades": return `<path d="M32 54 H88 L84 70 Q74 76 64 68 L60 62 L56 68 Q46 76 36 70 Z" fill="#141418"/><path d="M38 58 l8 0" stroke="#ff6fb1" stroke-width="2" stroke-linecap="round"/>`;
    case "wide": return pair((x) => `<circle cx="${x}" cy="${Y}" r="12" fill="#141418"/><circle cx="${x - 3}" cy="${Y - 3}" r="3.5" fill="#fff"/>`);
    case "narrow": return pair((x) => `<ellipse cx="${x}" cy="${Y}" rx="10" ry="4" fill="#141418"/>`) +
      `<path d="M36 52 L54 56 M84 52 L66 56" stroke="#141418" stroke-width="3" stroke-linecap="round"/>`;
    default: return pair((x) => `<circle cx="${x}" cy="${Y}" r="11" fill="#141418"/><circle cx="${x - 3}" cy="${Y - 3}" r="3" fill="#fff"/>`);
  }
}

export function avatar(key, { size = 120, color = "#8a8fbf", animate = false, label = null } = {}) {
  const c = COSTUMES[key] || COSTUMES.base;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 120 120");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("class", `avatar${animate ? " avatar--animate" : ""}${c.shake ? " avatar--shake" : ""}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", label || `Reachy as ${key.replace(/_/g, " ")}`);
  svg.style.setProperty("--accent", color);
  const ant = (x, deg) => `<g class="avatar__ant" style="transform-origin:${x}px 40px;transform:rotate(${deg}deg)"><line x1="${x}" y1="40" x2="${x}" y2="12" stroke="#d9d8e6" stroke-width="3" stroke-linecap="round"/><circle cx="${x}" cy="10" r="4.5" fill="var(--accent)"/></g>`;
  svg.innerHTML = `
    <ellipse cx="60" cy="116" rx="34" ry="3" fill="#000" opacity="0.25"/>
    <path d="M34 118 Q34 90 60 88 Q86 90 86 118 Z" fill="#2b2b38"/>
    <g class="avatar__head">
      ${ant(44, c.ant[0])}${ant(76, c.ant[1])}
      <rect x="26" y="38" width="68" height="50" rx="24" fill="${c.tint || "#f2f1f7"}"/>
      ${eyesSvg(c.eyes)}
      ${c.extra}
    </g>`;
  return svg;
}
