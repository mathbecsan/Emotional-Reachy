/**
 * Past sessions and the debrief replay: heart chart with every Reachy turn,
 * the moves the participant actually saw (for the post-interview questions),
 * and which reactions were triggered by their heartbeat vs. pre-scripted.
 */
import { setCrumbs } from "../ui.js";
import { h, fmtTime } from "../ui.js";
import { api } from "../api.js";
import { MODES, STAGES, PROVOCATIONS } from "../constants.js";
import { heartChart } from "../components/heart-chart.js";

export function sessionsView(outlet) {
  setCrumbs([{ label: "Main menu", href: "#/menu" }, "Results"]);
  const list = h("ul", { class: "sessions__list" });
  outlet.replaceChildren(h("div", { class: "page page--narrow" },
    h("header", { class: "page__head" }, h("div", {}, h("h1", { class: "page__title" }, "Results"),
      h("p", { class: "page__lede" }, "Open a session to replay the conversation and the heartbeat."))),
    h("section", { class: "card sessions" }, list)));
  api("/api/sessions").then((items) => {
    if (!items.length) list.append(h("li", { class: "muted" }, "No sessions yet."));
    for (const s of items) {
      const [date, time, pid] = s.name.split(/[-_]/);
      list.append(h("li", {}, h("a", { href: `#/results/${s.name}`, class: "sessions__item" },
        h("strong", {}, pid || s.name), h("span", { class: "muted" }, `${date} ${time?.replace(/(\d\d)(\d\d)(\d\d)/, "$1:$2:$3")}`),
        h("span", { class: "muted" }, `${s.turns} turns`),
        h("a", { href: `#/projection/${s.name}`, class: "btn btn--small" }, "Project"))));
    }
  });
}

export function replayView(outlet, name) {
  setCrumbs([{ label: "Main menu", href: "#/menu" }, { label: "Results", href: "#/results" }, name.split("_").pop()]);
  const chart = heartChart({ windowSecs: 0, height: 260 });
  const turns = h("ol", { class: "replay__turns" });
  const summary = h("div", { class: "replay__summary" });
  outlet.replaceChildren(h("div", { class: "replay" },
    h("div", { class: "card" },
      h("div", { class: "card__head" }, h("h2", { class: "card__title" }, name),
        h("a", { class: "btn btn--small", href: `#/projection/${name}` }, "Play as projection")),
      chart.el, summary),
    h("section", { class: "card" }, h("h2", { class: "card__title" }, "Turn by turn"), turns)));

  api(`/api/sessions/${encodeURIComponent(name)}`).then((log) => {
    log.heart.forEach(([t, b]) => chart.addSample(t, b));
    const baseline = log.events.find((e) => e.kind === "baseline")?.bpm;
    if (baseline) chart.setBaseline(baseline);
    const stageStart = {};
    for (const e of log.events) {
      if (e.kind === "stage") { chart.addStage(e.t, e.stage); stageStart[e.stage] = e.t; }
      if (e.kind === "turn") {
        chart.addTurn(e);
        const m = MODES[e.mode] || {};
        turns.append(h("li", { class: "replay__turn", style: { "--mode": m.color } },
          h("span", { class: "replay__t" }, fmtTime(e.t)),
          h("span", { class: "chip chip--mode" }, m.label || e.mode),
          h("span", { class: "chip" }, e.act),
          e.heart_jump ? h("span", { class: "chip chip--heart" }, `♥ +${Math.round(e.heart_jump)}`) : null,
          e.heard ? h("p", { class: "replay__heard" }, `“${e.heard}”`) : null,
          h("p", { class: "replay__said" }, e.said),
          h("p", { class: "line__why" }, e.why)));
      }
    }
    const t = log.events.filter((e) => e.kind === "turn");
    const seen = [...new Set(t.map((e) => e.mode).filter((m) => PROVOCATIONS.has(m) || m === "flirty"))];
    const heartTurns = t.filter((e) => e.heart_jump);
    const stop = log.events.find((e) => e.kind === "stop");
    const peak = log.heart.reduce((a, c) => (c[1] > a[1] ? c : a), [0, 0]);
    const peakStage = Object.entries(stageStart).filter(([, s]) => s <= peak[0]).pop()?.[0];
    // Off-Brand: one row per persona stint (spec: log switches and stop-word use to see which
    // personas produced the strongest reactions) -- replies, laughs and peak BPM while it was on.
    const switches = log.events.filter((e) => e.kind === "persona");
    const stints = switches.map((e, i) => {
      const end = switches[i + 1]?.t ?? Infinity;
      const heard = log.events.filter((x) => x.kind === "heard" && x.text && x.t >= e.t && x.t < end);
      const bpm = log.heart.filter(([ht]) => ht >= e.t && ht < end).map(([, b]) => b);
      return `${MODES[e.persona]?.label || e.persona} (${e.reason}): ${heard.length} replies` +
        `${heard.filter((x) => (x.cues || []).includes("laugh")).length ? `, ${heard.filter((x) => (x.cues || []).includes("laugh")).length} laughs` : ""}` +
        `${bpm.length ? `, peak ${Math.round(Math.max(...bpm))} BPM` : ""}`;
    });
    const resets = switches.filter((e) => e.reset && e.reason !== "close").length;
    summary.replaceChildren(
      h("dl", { class: "who" },
        ...(switches.length ? [h("dt", {}, "Personalities"), h("dd", {}, h("ol", { class: "pd__lines" }, stints.map((x) => h("li", {}, x)))),
          h("dt", {}, "Resets to Base"), h("dd", {}, String(resets))] : []),
        h("dt", {}, "Baseline"), h("dd", {}, baseline ? `${Math.round(baseline)} BPM` : "—"),
        h("dt", {}, "Peak"), h("dd", {}, peak[1] ? `${Math.round(peak[1])} BPM at ${fmtTime(peak[0])} (stage ${peakStage}: ${STAGES[peakStage]?.name})` : "—"),
        h("dt", {}, "Persona moves seen"), h("dd", {}, seen.map((m) => MODES[m].label).join(", ") || "none"),
        h("dt", {}, "Heart-triggered reactions"), h("dd", {}, heartTurns.length
          ? heartTurns.map((e) => `${fmtTime(e.t)} +${Math.round(e.heart_jump)} → ${e.mode}`).join(" · ") : "none"),
        h("dt", {}, "Stopped"), h("dd", {}, stop ? `${stop.reason} (stage ${stop.stage})` : "no")),
      h("p", { class: "muted" }, "Use “Persona moves seen” to pick which post-interview personality questions to ask, and “Heart-triggered reactions” for the debrief."));
  }).catch((e) => summary.replaceChildren(h("p", { class: "muted" }, e.message)));
}
