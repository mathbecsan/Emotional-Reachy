/** Stage 0-7 strip with the current stage's countdown (protocol timing). */
import { h, fmtTime } from "../ui.js";
import { STAGES } from "../constants.js";

export function stageTimeline() {
  const cells = STAGES.map((s) =>
    h("li", { class: "timeline__stage", dataset: { stage: s.n } },
      h("span", { class: "timeline__num" }, s.n),
      h("span", { class: "timeline__name" }, s.name),
      h("span", { class: "timeline__bar" }, h("span", { class: "timeline__fill" }))));
  const clock = h("span", { class: "timeline__clock" }, "–:––");
  const root = h("div", { class: "timeline" }, h("ol", { class: "timeline__list" }, cells), clock);
  let current = null, startedAt = 0, seconds = 0, timer = 0;

  function tick() {
    if (current == null) return;
    const elapsed = (Date.now() / 1000) - startedAt;
    const left = seconds - elapsed;
    clock.textContent = left >= 0 ? `${fmtTime(left)} left` : `+${fmtTime(-left)} over`;
    clock.classList.toggle("timeline__clock--over", left < 0);
    const fill = cells[current]?.querySelector(".timeline__fill");
    if (fill) fill.style.width = `${Math.min(100, (elapsed / seconds) * 100)}%`;
  }

  return {
    el: root,
    set(stage, startedTs, secs) {
      current = stage; startedAt = startedTs; seconds = secs || STAGES[stage]?.secs || 60;
      cells.forEach((c, i) => {
        c.classList.toggle("is-done", i < stage);
        c.classList.toggle("is-current", i === stage);
        if (i > stage) c.querySelector(".timeline__fill").style.width = "0";
        if (i < stage) c.querySelector(".timeline__fill").style.width = "100%";
      });
      clearInterval(timer);
      timer = setInterval(tick, 500);
      tick();
    },
    skip(stage) { cells[stage]?.classList.add("is-skipped"); },
    reset() {
      clearInterval(timer); current = null; clock.textContent = "–:––";
      cells.forEach((c) => { c.className = "timeline__stage"; c.querySelector(".timeline__fill").style.width = "0"; });
    },
  };
}
