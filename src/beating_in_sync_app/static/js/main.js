/** Hash router + shared connection status (same no-build approach as the conversation app). */
import { connect, onConnection } from "./api.js";
import { liveView } from "./views/live.js";
import { sessionsView, replayView } from "./views/sessions.js";
import { projectionView } from "./views/projection.js";
import { builderView } from "./views/builder.js";
import { personasView } from "./views/personas.js";
import { loadPersonas } from "./personas.js";

const outlet = document.getElementById("view-outlet");
let cleanup = null;

function route() {
  cleanup?.();
  cleanup = null;
  const [, view, arg] = (location.hash || "#/").split("/");
  document.querySelectorAll("[data-nav]").forEach((a) =>
    a.classList.toggle("is-active", a.dataset.nav === (view || "live") || (view === "sessions" && a.dataset.nav === "sessions")));
  if (view === "sessions" && arg) cleanup = replayView(outlet, decodeURIComponent(arg));
  else if (view === "sessions") cleanup = sessionsView(outlet);
  else if (view === "projection") cleanup = projectionView(outlet, arg && decodeURIComponent(arg));
  else if (view === "build") cleanup = builderView(outlet, arg && decodeURIComponent(arg));
  else if (view === "personas") cleanup = personasView(outlet, arg && decodeURIComponent(arg));
  else cleanup = liveView(outlet);
}

onConnection((ok) => {
  const el = document.querySelector("[data-component=conn]");
  el.textContent = ok ? "connected" : "offline";
  el.classList.toggle("is-ok", ok);
});

window.addEventListener("hashchange", route);
connect();
loadPersonas().catch(() => {}).finally(route);   // persona colors before the first view renders
