/**
 * Repair panel: one button that walks through everything that commonly goes wrong
 * (stale link after the laptop slept, leftover tests, robot software, motors), puts
 * Reachy to sleep and wakes it up so the next test starts fresh, and shows each step live.
 */
import { h, toast } from "../ui.js";
import { api, onEvent } from "../api.js";
import { speak } from "./voice-guide.js";

const STEPS = [
  ["session", "No session running"], ["tests", "Stop leftover tests"], ["daemon", "Robot software"],
  ["link", "Connection to Reachy"], ["motors", "Motors switched on"], ["reset", "Sleep and wake up"],
  ["body", "Head and body move"], ["sensors", "Pulse sensors"], ["audio", "Voice and microphone"],
];
let open = false;

export function openRepair() {
  if (open) return;
  open = true;
  const rows = Object.fromEntries(STEPS.map(([k, label]) => [k, h("li", { class: "repair__row", dataset: { status: "pending" } },
    h("span", { class: "repair__icon", "aria-hidden": "true" }), h("div", {}, h("strong", {}, label), h("p", { class: "repair__detail" }), h("p", { class: "repair__fix" })))]));
  const summary = h("p", { class: "repair__summary", role: "status" }, "Checking everything, one step at a time…");
  const closeBtn = h("button", { type: "button", class: "btn", disabled: true, onclick: () => close() }, "Close");
  const again = h("a", { class: "btn btn--primary", href: "#/check", hidden: true, onclick: () => close() }, "Run the setup checklist");
  const note = h("p", { class: "muted small", hidden: true }, "When you close this, the step re-runs. If the problem comes back, press ↺ Reset this step, then Repair once more.");
  const panel = h("div", { class: "repair", role: "dialog", "aria-modal": "true", "aria-label": "Repair" },
    h("div", { class: "repair__card" },
      h("header", {}, h("h2", {}, "🔧 Repair"), h("p", { class: "muted" }, "Fixes what it can and restarts Reachy so the next test starts fresh. Takes about 30 seconds.")),
      h("ol", { class: "repair__list" }, Object.values(rows)), summary, note, h("div", { class: "btn-row repair__nav" }, closeBtn, again)));
  document.body.append(panel);
  speak("Let me check everything and fix what I can. This takes about half a minute.", { important: true });
  let firstFail = null;
  const off = onEvent((e) => {
    if (e.kind !== "repair") return;
    if (e.status === "failed" && !firstFail) firstFail = e;
    if (e.done) {
      speak(e.ok ? "All fixed! Everything is ready. You can run the setup checklist again."
        : `I fixed what I could, but ${firstFail ? firstFail.label.toLowerCase() + " still needs you. " + (firstFail.fix || "").split(/(?<=[.!?])\s/)[0] : "something still needs you."}`, { important: true });
      summary.textContent = e.summary;
      summary.dataset.ok = String(e.ok);
      closeBtn.disabled = false;
      closeBtn.textContent = location.hash.startsWith("#/check") ? "Close and re-test" : "Close";
      again.hidden = !e.ok || location.hash.startsWith("#/check");
      note.hidden = !location.hash.startsWith("#/check");
      window.dispatchEvent(new Event("refreshstatus"));
      return;
    }
    const row = rows[e.step];
    if (!row) return;
    row.dataset.status = e.status;
    row.querySelector(".repair__detail").textContent = e.detail || "";
    row.querySelector(".repair__fix").textContent = e.status === "failed" && e.fix ? `Try this: ${e.fix}` : "";
  });
  function close() {
    off(); panel.remove(); open = false;
    window.dispatchEvent(new Event("repairdone"));   // the step that failed re-runs to check the fix
  }
  panel.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !closeBtn.disabled) close(); });
  api("/api/repair", {}).catch((e) => { summary.textContent = e.message; closeBtn.disabled = false; toast(e.message, "error"); });
}
