/** Hash router, the header's setup status and the Debug switch. */
import { connect, onConnection, onEvent, api } from "./api.js";
import { isDebug, setDebug, h } from "./ui.js";
import { homeView } from "./views/home.js";
import { checkView } from "./views/check.js";
import { builderView } from "./views/builder.js";
import { liveView } from "./views/live.js";
import { sessionsView, replayView } from "./views/sessions.js";
import { projectionView } from "./views/projection.js";
import { personasView } from "./views/personas.js";
import { loadPersonas } from "./personas.js";

const outlet = document.getElementById("view-outlet");
let cleanup = null;
const ALIAS = { "": "home", build: "new", live: "session", sessions: "results", personas: "personalities" };

function route() {
  cleanup?.();
  cleanup = null;
  window.scrollTo(0, 0);
  const [, raw, arg] = (location.hash || "#/").split("/");
  const view = ALIAS[raw ?? ""] ?? raw;
  const a = arg && decodeURIComponent(arg);
  document.querySelectorAll("[data-nav]").forEach((el) => el.classList.toggle("is-active", el.dataset.nav === view));
  document.body.classList.toggle("is-projection", view === "projection");
  if (view === "check") cleanup = checkView(outlet);
  else if (view === "new") cleanup = builderView(outlet, a);
  else if (view === "session") cleanup = liveView(outlet);
  else if (view === "results" && a) cleanup = replayView(outlet, a);
  else if (view === "results") cleanup = sessionsView(outlet);
  else if (view === "projection") cleanup = projectionView(outlet, a);
  else if (view === "personalities") cleanup = personasView(outlet, a);
  else cleanup = homeView(outlet);
}

// ---- header status: Reachy / Sensors / Voice + "session running"
const statusEl = document.querySelector("[data-component=status]");
let running = false;
async function refreshStatus() {
  try {
    const [c, st] = await Promise.all([api("/api/check"), api("/api/state")]);
    running = st.running;
    const pill = (ok, label) => h("span", { class: `pill ${ok ? "pill--ok" : "pill--bad"}` }, h("i", { "aria-hidden": "true" }), label);
    statusEl.replaceChildren(...[
      running ? h("span", { class: "pill pill--live" }, h("i", { "aria-hidden": "true" }), "Session running") : null,
      pill(c.daemon?.ok && c.robot?.ok, "Reachy"), pill(c.sensors?.ok, "Sensors"), pill(c.voice?.ok && c.audio?.ok, "Voice"),
    ].filter(Boolean));
  } catch { /* offline: the connection indicator covers it */ }
}

onConnection((ok) => {
  document.body.classList.toggle("is-offline", !ok);
  if (ok) refreshStatus();
});
onEvent((e) => { if (e.kind === "session") { refreshStatus(); } });
setInterval(refreshStatus, 15000);

const dbg = document.querySelector("[data-component=debug]");
dbg.checked = isDebug();
document.body.classList.toggle("is-debug", dbg.checked);
dbg.addEventListener("change", () => setDebug(dbg.checked));

window.addEventListener("hashchange", route);
connect();
loadPersonas().catch(() => {}).finally(route);
