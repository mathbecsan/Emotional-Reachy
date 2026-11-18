/**
 * Personalities: the Off-Brand cast as a browsable catalog. Each persona shows its
 * mood, delivery, script (opener, questions, reactions, silence lines) and its
 * gestures, which can be tried on the robot. Filter, then jump to the builder.
 */
import { h, toast } from "../ui.js";
import { api } from "../api.js";
import { loadPersonas } from "../personas.js";
import { avatar } from "../components/avatar.js";
import { setCrumbs } from "../ui.js";

export function personasView(outlet, focus) {
  setCrumbs([{ label: "Main menu", href: "#/menu" }, "Personalities"]);
  const root = h("div", { class: "personas page" }, h("p", { class: "muted" }, "Loading…"));
  outlet.replaceChildren(root);
  let filter = "all", query = "";

  loadPersonas().then((cat) => {
    const grid = h("div", { class: "catalog" });
    const detail = h("section", { class: "card persona-detail", hidden: true });
    const chips = [["all", "All"], ["core", "Core cast"], ["high", "High energy"], ["low", "Low energy"], ["kind", "Never teases"], ["idea", "Idea bank"]];
    const chipRow = h("div", { class: "filter-row", role: "group", "aria-label": "Filter personalities" });
    const search = h("input", { class: "search", type: "search", placeholder: "Search mood, line, gesture…", "aria-label": "Search personalities",
      oninput: (ev) => { query = ev.target.value.toLowerCase(); draw(); } });

    const match = (p) => (filter === "all" || (filter === "core" && !p.experimental) || (filter === "idea" && p.experimental)
      || (filter === "high" && p.energy === "high") || (filter === "low" && p.energy === "low") || (filter === "kind" && !p.teases))
      && (!query || JSON.stringify(p).toLowerCase().includes(query));

    function tryGesture(g) {
      api(`/api/gesture/${g}`, {}).then(() => toast(`Reachy: ${g.replace(/_/g, " ")}`)).catch((e) => toast(e.message, "error"));
    }

    function show(p) {
      history.replaceState(null, "", `#/personas/${p.key}`);
      const block = (title, ...kids) => h("div", { class: "pd__block" }, h("h3", { class: "card__sub" }, title), ...kids);
      const lines = (arr) => h("ul", { class: "pd__lines" }, arr.map((x) => h("li", {}, x)));
      const gestures = [...new Set([p.entrance, ...p.gestures, ...Object.values(p.camera).map((v) => v.split("|")[0])])];
      detail.hidden = false;
      detail.style.setProperty("--accent", p.color);
      detail.replaceChildren(
        h("div", { class: "pd__head" },
          h("div", { class: "pd__who" }, avatar(p.key, { size: 96, color: p.color, animate: true }),
            h("div", {}, h("h2", { class: "pd__name" }, p.name), h("p", { class: "pd__mood" }, p.mood))),
          h("button", { class: "icon-btn", type: "button", "aria-label": "Close", onclick: () => { detail.hidden = true; history.replaceState(null, "", "#/personas"); } }, "×")),
        h("blockquote", { class: "pd__sample" }, p.sample),
        h("dl", { class: "pd__facts" },
          h("dt", {}, "Goal"), h("dd", {}, p.goal),
          h("dt", {}, "Voice"), h("dd", {}, p.delivery),
          h("dt", {}, "Body"), h("dd", {}, p.body),
          h("dt", {}, "Sound"), h("dd", {}, p.sound)),
        block("Try a gesture on Reachy", h("div", { class: "btn-row" }, gestures.map((g) =>
          h("button", { type: "button", class: `btn btn--small${g === p.entrance ? " btn--accent" : ""}`, onclick: () => tryGesture(g) },
            g.replace(/_/g, " "))))),
        h("div", { class: "pd__cols" },
          block("Switching in", lines([`Glitch: “${p.glitch_in}”`, `Opener: “${p.opener}”`])),
          block("Questions", lines(p.questions)),
          block("Reactions ({slot} = their words)", lines(Object.entries(p.reactions).map(([k, v]) => `${k}: ${v}`))),
          block("Never stuck", lines([`Bridges: ${p.bridges.join(" · ")}`, `Silence: “${p.poke}”`, `Rescue: “${p.rescue}”`,
            `Interrupted: “${p.barge_in}”`, `“I don't know”: “${p.dont_know}”`])),
          block("Reacting to what it sees", lines(Object.entries(p.camera).map(([k, v]) => `${k}: ${v.split("|")[0].replace(/_/g, " ")} + “${v.split("|")[1]}”`)))),
        h("div", { class: "btn-row pd__foot" },
          h("a", { class: "btn btn--primary", href: "#/new" }, "Create a session"),
          p.teases ? h("span", { class: "chip chip--warn" }, "teases: skipped for participants who opt out") : null,
          p.fragile ? h("span", { class: "chip" }, "switches to Base Reachy if someone shares a real problem") : null));
      detail.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function draw() {
      chipRow.replaceChildren(...chips.map(([k, label]) => h("button", {
        type: "button", class: `filter${filter === k ? " is-on" : ""}`, "aria-pressed": String(filter === k),
        onclick: () => { filter = k; draw(); },
      }, label)));
      const items = cat.personas.filter(match);
      grid.replaceChildren(...items.map((p) => h("button", {
        type: "button", class: "persona-card", style: { "--accent": p.color }, onclick: () => show(p),
      },
      avatar(p.key, { size: 84, color: p.color }),
      h("span", { class: "persona-card__top" }, h("strong", {}, p.name), p.key === cat.base ? h("span", { class: "chip" }, "default") : null),
      h("span", { class: "persona-card__mood" }, p.mood),
      h("q", { class: "persona-card__line" }, p.sample),
      h("span", { class: "persona-pick__tags" },
        h("span", { class: "chip" }, p.energy === "high" ? "high energy" : "low energy"),
        p.teases ? h("span", { class: "chip chip--warn" }, "teases") : null,
        p.experimental ? h("span", { class: "chip chip--dim" }, "idea bank") : null))));
      if (!items.length) grid.append(h("p", { class: "muted" }, "No personality matches."));
    }

    root.replaceChildren(
      h("div", { class: "builder__head" },
        h("div", {}, h("h1", { class: "page__title" }, "Personalities"),
          h("p", { class: "muted page__lede" }, "One robot, one voice, many moods. Every switch starts with a glitch line; “Reachy, reset” always brings back Base Reachy.")),
        h("a", { class: "btn btn--primary", href: "#/new" }, "Create a session →")),
      h("div", { class: "catalog-tools" }, chipRow, search), detail, grid);
    draw();
    if (focus && cat.byKey[focus]) show(cat.byKey[focus]);
  }).catch((e) => root.replaceChildren(h("p", { class: "muted" }, `Could not load personalities: ${e.message}`)));

  return () => {};
}
