/** Act rail (session flow v2): the five acts, the current one highlighted, and the session's
 *  total time. No per-stage countdowns: the interview ends when the cast is done, not on a timer. */
import { h, fmtTime } from "../ui.js";
import { ACTS, ACT_OF_STAGE } from "../constants.js";

export function stageTimeline() {
  const cells = ACTS.map((a) =>
    h("li", { class: "timeline__stage", dataset: { act: a.n } },
      h("span", { class: "timeline__num" }, a.n),
      h("span", { class: "timeline__name" }, a.name),
      h("span", { class: "timeline__bar" }, h("span", { class: "timeline__fill" }))));
  const clock = h("span", { class: "timeline__clock", title: "Time since the session started" }, "–:––");
  const root = h("div", { class: "timeline" }, h("ol", { class: "timeline__list timeline__list--acts" }, cells), clock);
  let startedAt = null, timer = 0;

  function tick() {
    if (startedAt == null) return;
    clock.textContent = fmtTime(Math.max(0, Date.now() / 1000 - startedAt));
  }

  return {
    el: root,
    set(stage, startedTs) {
      const act = ACT_OF_STAGE[stage] ?? 1;
      if (startedAt == null && startedTs) startedAt = startedTs;
      cells.forEach((c, i) => {
        const n = i + 1;
        c.classList.toggle("is-done", n < act);
        c.classList.toggle("is-current", n === act);
        c.querySelector(".timeline__fill").style.width = n < act ? "100%" : n === act ? "50%" : "0";
      });
      clearInterval(timer);
      timer = setInterval(tick, 1000);
      tick();
    },
    skip() {},
    reset() {
      clearInterval(timer); startedAt = null; clock.textContent = "–:––";
      cells.forEach((c) => { c.className = "timeline__stage"; c.querySelector(".timeline__fill").style.width = "0"; });
    },
  };
}
