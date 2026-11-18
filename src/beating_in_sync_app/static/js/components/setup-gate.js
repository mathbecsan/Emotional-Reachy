/** "Have you done the setup checklist?" pop-up, shown before a new session starts. */
import { h } from "../ui.js";
import { setupStatus } from "../views/check.js";

export function setupGate(href = "#/new") {
  document.querySelector(".gate")?.remove();
  const st = setupStatus();
  const go = (to) => { dlg.close(); dlg.remove(); location.hash = to; };
  const mark = (s) => (s === "pass" ? "✓" : s === "fail" ? "!" : s === "skip" ? "–" : "·");
  const list = h("ul", { class: "gate__list" }, st.steps.map((s) =>
    h("li", { "data-state": s.state }, h("span", { class: "setup__mark" }, mark(s.state)), s.title)));
  const recent = st.minutesAgo != null ? ` (${st.minutesAgo < 1 ? "just now" : `${st.minutesAgo} min ago`})` : "";
  const lead = st.done
    ? h("p", {}, `✓ The setup checklist is done${recent}: ${st.passed} of ${st.steps.length} checks passed.`)
    : h("p", {}, st.minutesAgo == null
      ? "Before starting, make sure Reachy, the sensors, camera, microphone, speaker and projector all work. Have you completed the setup checklist?"
      : `The setup checklist isn't finished yet${recent}. Have you checked everything?`);
  const dlg = h("dialog", { class: "gate", "aria-labelledby": "gate-title" },
    h("h2", { id: "gate-title", class: "gate__title" }, st.done ? "Ready for a new session" : "Setup checklist first?"),
    lead, st.minutesAgo != null ? list : "",
    h("div", { class: "btn-row gate__actions" },
      st.done
        ? h("button", { type: "button", class: "btn btn--primary", onclick: () => go(href) }, "Start a new session →")
        : h("button", { type: "button", class: "btn btn--primary", onclick: () => go("#/check") }, "Open the setup checklist"),
      st.done
        ? h("button", { type: "button", class: "btn", onclick: () => go("#/check") }, "Check the setup again")
        : h("button", { type: "button", class: "btn", onclick: () => go(href) }, "Yes, it's all checked: continue"),
      h("button", { type: "button", class: "link-sm", onclick: () => { dlg.close(); dlg.remove(); } }, "Cancel")));
  dlg.addEventListener("cancel", () => dlg.remove());
  document.body.append(dlg);
  dlg.showModal();
  dlg.querySelector(".btn--primary").focus();
}
