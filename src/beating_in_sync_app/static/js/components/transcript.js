/**
 * Conversation log for the observer: Reachy's lines carry mode, act and the
 * Director's reason ("why"); participant lines carry language, detected
 * emotion and cues. Heart-triggered turns are flagged -- that is what the
 * debrief needs ("which reactions came from your heartbeat").
 */
import { h } from "../ui.js";
import { MODES, LANGS } from "../constants.js";

export function transcript() {
  const list = h("ol", { class: "transcript__list" });
  const root = h("section", { class: "transcript card", "aria-label": "Conversation" },
    h("h2", { class: "card__title" }, "Conversation"), list);
  let pendingTurn = null;

  function scroll() { list.lastElementChild?.scrollIntoView({ block: "end", behavior: "smooth" }); }

  function chip(text, cls = "") { return h("span", { class: `chip ${cls}` }, text); }

  return {
    el: root,
    reset() { list.replaceChildren(); },
    turn(e) { pendingTurn = e; },
    reachy(e) {
      const turn = pendingTurn; pendingTurn = null;
      const mode = MODES[e.mode] || { color: "#fff", label: e.mode };
      list.append(h("li", { class: "line line--reachy", style: { "--mode": mode.color } },
        h("div", { class: "line__meta" },
          chip(mode.label, "chip--mode"),
          turn && chip(turn.act),
          turn?.heart_jump ? chip(`♥ +${Math.round(turn.heart_jump)}`, "chip--heart") : null,
          turn?.story ? chip(`story: ${turn.story}`) : null,
          turn?.source === "template" ? chip("offline", "chip--dim") : null),
        h("p", { class: "line__text" }, e.text),
        turn?.why ? h("p", { class: "line__why" }, turn.why) : null));
      scroll();
    },
    participant(e) {
      list.append(e.text == null
        ? h("li", { class: "line line--silence" }, "(silence)")
        : h("li", { class: "line line--participant" },
          h("div", { class: "line__meta" },
            e.lang ? chip(LANGS[e.lang] || e.lang) : null,
            e.emotion && e.emotion !== "neutral" ? chip(e.emotion, "chip--emotion") : null,
            ...(e.cues || []).filter((c) => c !== "ask_robot").map((c) => chip(c.replace("_", " ")))),
          h("p", { class: "line__text" }, e.text)));
      scroll();
    },
    note(text, kind = "") {
      list.append(h("li", { class: `line line--note ${kind}` }, text));
      scroll();
    },
  };
}
