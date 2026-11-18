/**
 * Title screen ("press any key") and the main menu. The menu is a short list on the
 * left; the panel on the right previews whatever is focused (hover, Tab or arrow keys).
 */
import { h, setCrumbs } from "../ui.js";
import { api } from "../api.js";
import { avatar } from "../components/avatar.js";

export function titleView(outlet) {
  const go = () => { location.hash = "#/menu"; };
  const root = h("section", { class: "title", tabindex: "0", "aria-label": "Start screen. Press any key to continue.", onclick: go },
    h("div", { class: "title__bands", "aria-hidden": "true" }, h("span"), h("span"), h("span")),
    h("div", { class: "title__stage" },
      avatar("base", { size: 220, color: "#ff5a6e", animate: true }),
      h("div", { class: "title__ecg", "aria-hidden": "true" }),
      h("h1", { class: "title__name" }, "Beating", h("em", {}, " in "), "Sync"),
      h("p", { class: "title__sub" }, "A robot that listens to your heart"),
      h("p", { class: "title__press" }, "Press any key or tap to start")));
  root.querySelector(".title__ecg").innerHTML = `<svg viewBox="0 0 600 60" preserveAspectRatio="none">
    <path d="M0 30 H170 L185 30 L195 8 L208 52 L220 18 L230 30 H380 L395 30 L405 8 L418 52 L430 18 L440 30 H600" /></svg>`;
  outlet.replaceChildren(root);
  const onKey = (e) => { if (!e.metaKey && !e.ctrlKey && !e.altKey) go(); };
  window.addEventListener("keydown", onKey, { once: true });
  root.focus();
  return () => window.removeEventListener("keydown", onKey);
}

const ITEMS = [
  { key: "new", href: "#/new", label: "New session", color: "#ff5a6e", costume: "hype_bro",
    text: "Choose Reachy's personalities, how it moves and speaks, how long it lasts and what you'll do together." },
  { key: "check", href: "#/check", label: "Setup checklist", color: "#5cc8ff", costume: "hypochondriac",
    text: "Make sure Reachy, the pulse sensors, camera, microphone and speaker all work, one step at a time." },
  { key: "session", href: "#/session", label: "Current session", color: "#7be0a8", costume: "base",
    text: "Follow the conversation and the heartbeat while a session runs." },
  { key: "results", href: "#/results", label: "Results", color: "#ffc94d", costume: "noir",
    text: "Replay past sessions: what was said, which personality was on, and how the heart reacted." },
  { key: "personalities", href: "#/personalities", label: "Meet the personalities", color: "#b98cff", costume: "diva",
    text: "Every personality Reachy can play, with its lines and gestures." },
];

export function menuView(outlet) {
  setCrumbs(["Main menu"]);
  const statusLine = h("p", { class: "menu__status" }, "");
  const prevAvatar = h("div", { class: "menu__avatar" });
  const prevTitle = h("h2", { class: "menu__ptitle" });
  const prevText = h("p", { class: "menu__ptext" });
  const preview = h("aside", { class: "menu__preview", "aria-live": "polite" }, prevAvatar, prevTitle, prevText, statusLine);
  let focused = 0, info = {};

  function focus(i) {
    focused = (i + ITEMS.length) % ITEMS.length;
    const it = ITEMS[focused];
    list.querySelectorAll(".menu__item").forEach((el, j) => el.classList.toggle("is-focus", j === focused));
    root.style.setProperty("--accent", it.color);
    prevAvatar.replaceChildren(avatar(it.costume, { size: 200, color: it.color, animate: true }));
    prevTitle.textContent = it.label;
    prevText.textContent = it.text;
    statusLine.textContent = info[it.key] || "";
    statusLine.className = `menu__status ${info[`${it.key}_cls`] || ""}`;
    preview.classList.remove("menu__preview--pop");
    void preview.offsetWidth;
    preview.classList.add("menu__preview--pop");
  }

  const list = h("ol", { class: "menu__list", role: "menu" }, ITEMS.map((it, i) => h("li", { role: "none" },
    h("a", { class: "menu__item", href: it.href, role: "menuitem", style: { "--accent": it.color },
      onmouseenter: () => focus(i), onfocus: () => focus(i) },
    h("span", { class: "menu__bar", "aria-hidden": "true" }), h("span", { class: "menu__label" }, it.label)))));

  const root = h("section", { class: "menu" },
    h("div", { class: "menu__bands", "aria-hidden": "true" }, h("span"), h("span")),
    h("div", { class: "menu__left" }, h("p", { class: "menu__kicker" }, "Main menu"), list,
      h("p", { class: "menu__hint" }, "↑ ↓ to choose · Enter to open")),
    preview);
  outlet.replaceChildren(root);

  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); focus(focused + 1); list.querySelectorAll("a")[focused].focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); focus(focused - 1); list.querySelectorAll("a")[focused].focus(); }
  };
  window.addEventListener("keydown", onKey);

  Promise.all([api("/api/check").catch(() => null), api("/api/state").catch(() => ({})), api("/api/sessions").catch(() => [])])
    .then(([c, st, ss]) => {
      if (c) {
        const bad = [["Reachy", c.daemon?.ok && c.robot?.ok], ["sensors", c.sensors?.ok], ["voice", c.voice?.ok && c.audio?.ok]].filter(([, ok]) => !ok).map(([n]) => n);
        info.check = bad.length ? `Needs attention: ${bad.join(", ")}` : "Everything is connected";
        info.check_cls = bad.length ? "is-bad" : "is-ok";
        info.new = bad.length ? "Tip: run the setup checklist first." : "Ready when you are.";
      }
      info.session = st.running ? `Running now · ${st.state?.participant || ""}` : "No session running";
      info.session_cls = st.running ? "is-live" : "";
      info.results = ss.length ? `${ss.length} saved session${ss.length > 1 ? "s" : ""}` : "No sessions yet";
      focus(focused);
    });
  focus(0);
  list.querySelector("a").focus({ preventScroll: true });
  return () => window.removeEventListener("keydown", onKey);
}
