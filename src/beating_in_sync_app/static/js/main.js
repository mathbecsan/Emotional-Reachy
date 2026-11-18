/** Router with wipe transitions, the header status pills and the Debug switch. */
import { connect, onConnection, onEvent, api } from "./api.js";
import { isDebug, setDebug, h, setCrumbs } from "./ui.js";
import { titleView, menuView } from "./views/menu.js";
import { checkView } from "./views/check.js";
import { builderView } from "./views/builder.js";
import { liveView } from "./views/live.js";
import { sessionsView, replayView } from "./views/sessions.js";
import { projectionView } from "./views/projection.js";
import { personasView } from "./views/personas.js";
import { loadPersonas } from "./personas.js";
import { openRepair } from "./components/repair.js";
import { reconnectReachy } from "./components/reconnect.js";

const outlet = document.getElementById("view-outlet");
const wipe = document.querySelector(".wipe");
let cleanup = null, first = true;
const ALIAS = { build: "new", live: "session", sessions: "results", personas: "personalities", home: "menu" };

function render() {
  cleanup?.();
  cleanup = null;
  window.scrollTo(0, 0);
  const [, raw, arg] = (location.hash || "#/").split("/");
  const view = ALIAS[raw] ?? (raw || "title");
  const a = arg && decodeURIComponent(arg);
  document.body.dataset.view = view;
  document.body.classList.toggle("is-projection", view === "projection");
  setCrumbs([]);
  if (view === "check") cleanup = checkView(outlet, a);
  else if (view === "new") cleanup = builderView(outlet, a);
  else if (view === "session") cleanup = liveView(outlet);
  else if (view === "results" && a) cleanup = replayView(outlet, a);
  else if (view === "results") cleanup = sessionsView(outlet);
  else if (view === "projection") cleanup = projectionView(outlet, a);
  else if (view === "personalities") cleanup = personasView(outlet, a);
  else if (view === "menu") cleanup = menuView(outlet);
  else cleanup = titleView(outlet);
}

function route() {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (first || reduce) { first = false; render(); return; }
  wipe.classList.remove("wipe--out");
  wipe.classList.add("wipe--in");
  setTimeout(() => {
    render();
    wipe.classList.remove("wipe--in");
    wipe.classList.add("wipe--out");
  }, 330);
}

// ---- header status pills
const statusEl = document.querySelector("[data-component=status]");
export let lastCheck = null;
async function refreshStatus() {
  try {
    const [c, st] = await Promise.all([api("/api/check"), api("/api/state")]);
    lastCheck = c;
    const pill = (ok, label) => h("span", { class: `pill ${ok ? "pill--ok" : "pill--bad"}` }, h("i", { "aria-hidden": "true" }), label);
    statusEl.replaceChildren(...[
      st.running ? h("span", { class: "pill pill--live" }, h("i", { "aria-hidden": "true" }), "Session running") : null,
      c.daemon?.ok && c.robot?.ok ? pill(true, "Reachy")
        : h("button", { type: "button", class: "pill pill--bad pill--action", title: `${c.daemon?.ok ? c.robot?.detail : c.daemon?.detail || "Reachy isn't connected"}. Click to reconnect.`,
            onclick: (e) => { e.currentTarget.disabled = true; e.currentTarget.lastChild.textContent = "Reconnecting…"; reconnectReachy(); } },
          h("i", { "aria-hidden": "true" }), "Reachy · Reconnect"),
      pill(c.sensors?.ok, "Sensors"), pill(c.voice?.ok && c.audio?.ok, "Voice"),
    ].filter(Boolean));
    window.dispatchEvent(new CustomEvent("statuschange", { detail: { check: c, state: st } }));
  } catch { /* offline: the brand shows it */ }
}
onConnection((ok) => { document.body.classList.toggle("is-offline", !ok); if (ok) refreshStatus(); });
onEvent((e) => { if (e.kind === "session" || (e.kind === "robot" && e.status !== "reconnecting")) refreshStatus(); });
window.addEventListener("refreshstatus", refreshStatus);
setInterval(refreshStatus, 15000);

document.querySelector("[data-component=repair]").addEventListener("click", openRepair);
window.addEventListener("repair", openRepair);

const dbg = document.querySelector("[data-component=debug]");
dbg.checked = isDebug();
document.body.classList.toggle("is-debug", dbg.checked);
dbg.addEventListener("change", () => setDebug(dbg.checked));

window.addEventListener("hashchange", route);
connect();
loadPersonas().catch(() => {}).finally(route);
