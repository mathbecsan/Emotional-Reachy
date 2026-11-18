/** The session's cast in order: done, current (big), upcoming. Click a persona to jump
 * to it; buttons glitch into the next one, reset to Base Reachy, or close the interview. */
import { h, toast } from "../ui.js";
import { command } from "../api.js";
import { MODES } from "../constants.js";

export function personaStrip() {
  const name = h("span", { class: "pstrip__name" }, "Not awake yet");
  const why = h("span", { class: "pstrip__why" });
  const list = h("ol", { class: "pstrip__list" });
  const send = (cmd, msg) => command(cmd).then(() => msg && toast(msg)).catch((e) => toast(e.message, "error"));
  const root = h("section", { class: "card pstrip", hidden: true, "aria-label": "Personalities" },
    h("div", { class: "pstrip__head" },
      h("div", {}, h("h2", { class: "card__title" }, "Personality now"), h("div", {}, name, why)),
      h("div", { class: "btn-row" },
        h("button", { class: "btn", type: "button", title: "Glitch into the next persona", onclick: () => send("/next", "Switching…") }, "Next personality →"),
        h("button", { class: "btn", type: "button", title: "Back to Base Reachy for the rest of the session", onclick: () => send("/reset", "Back to Base Reachy") }, "Reset to Base"),
        h("button", { class: "btn btn--danger", type: "button", title: "Close as Base Reachy, then goodbye", onclick: () => send("/close", "Closing the interview") }, "Close interview"))),
    list);
  let cast = [], current = null, index = 0, reset = false;

  function draw() {
    list.replaceChildren(...cast.map((k, i) => {
      const m = MODES[k] || { label: k, color: "#888" };
      const state = reset ? (k === "base" && i === 0 ? "is-current" : "is-dim") : i < index ? "is-done" : i === index ? "is-current" : "";
      return h("li", {},
        h("button", { type: "button", class: `pstrip__chip ${state}`, style: { "--accent": m.color }, title: `Jump to ${m.label}`,
          onclick: () => send(`/persona ${k}`, `Switching to ${m.label}…`) }, h("span", { class: "pstrip__n" }, i + 1), m.label));
    }));
    const m = MODES[current] || {};
    name.textContent = m.label || "Not awake yet";
    root.style.setProperty("--accent", m.color || "#888");
  }

  return {
    el: root,
    setCast(c) { if (!c?.length) return; cast = c; root.hidden = false; draw(); },
    setPersona(e) {
      if (e.cast) cast = e.cast;
      current = e.persona; index = e.index ?? cast.indexOf(e.persona); reset = !!e.reset;
      why.textContent = e.reason ? ` · ${e.reason}` : "";
      root.hidden = !cast.length;
      draw();
    },
    reset() { cast = []; current = null; index = 0; reset = false; root.hidden = true; list.replaceChildren(); },
  };
}
