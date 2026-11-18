/** Home: what this is, and the four steps of a study session. */
import { h } from "../ui.js";
import { api } from "../api.js";

export function homeView(outlet) {
  const setup = h("span", { class: "tile__status muted" }, "Checking…");
  const live = h("span", { class: "tile__status muted" }, "No session running");
  const last = h("span", { class: "tile__status muted" }, "");
  const tile = (n, href, title, text, status, primary) => h("a", { class: `tile${primary ? " tile--primary" : ""}`, href },
    h("span", { class: "tile__n" }, n), h("strong", { class: "tile__title" }, title), h("span", { class: "tile__text" }, text), status);

  outlet.replaceChildren(h("div", { class: "home" },
    h("section", { class: "hero" },
      h("h1", {}, "Reachy reacts to your heartbeat."),
      h("p", {}, "A participant rests a finger on a pulse sensor. Reachy wakes up, talks with them in different personalities, and reacts to their words, face and heart.")),
    h("div", { class: "tiles" },
      tile(1, "#/check", "Check setup", "Make sure Reachy, the pulse sensors, mic and speaker work.", setup),
      tile(2, "#/new", "New session", "Choose personalities and how Reachy behaves, then start.", null, true),
      tile(3, "#/session", "Session", "Follow the conversation and the heartbeat as it happens.", live),
      tile(4, "#/results", "Results", "Replay past sessions and what triggered each reaction.", last)),
    h("p", { class: "home__foot muted" }, "First time here? Read the guide: ",
      h("a", { href: "https://github.com/mathbecsan/Emotional-Reachy/blob/main/GUIDE.md", target: "_blank", rel: "noopener" }, "How to run a session"), ".")));

  api("/api/check").then((c) => {
    const items = [["Reachy", c.daemon?.ok && c.robot?.ok], ["Sensors", c.sensors?.ok], ["Voice", c.voice?.ok && c.audio?.ok]];
    const bad = items.filter(([, ok]) => !ok).map(([n]) => n);
    setup.textContent = bad.length ? `Needs attention: ${bad.join(", ")}` : "Everything connected";
    setup.className = `tile__status ${bad.length ? "is-bad" : "is-ok"}`;
  }).catch(() => { setup.textContent = "App offline"; });
  api("/api/state").then((s) => { if (s.running) { live.textContent = `Running · ${s.state?.participant || ""}`; live.className = "tile__status is-live"; } }).catch(() => {});
  api("/api/sessions").then((ss) => { last.textContent = ss.length ? `${ss.length} saved session${ss.length > 1 ? "s" : ""}` : "No sessions yet"; }).catch(() => {});
  return () => {};
}
