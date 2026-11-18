/** Tiny DOM helper: h("div", {class: "x", onclick}, child, "text") */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") {
      for (const [prop, val] of Object.entries(v)) {
        if (prop.startsWith("--")) el.style.setProperty(prop, val);   // custom properties need setProperty
        else el.style[prop] = val;
      }
    }
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function fmtTime(seconds) {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function toast(message, kind = "info") {
  const el = h("div", { class: `toast toast--${kind}`, role: "status" }, message);
  document.body.append(el);
  setTimeout(() => el.classList.add("toast--out"), 3200);
  setTimeout(() => el.remove(), 3800);
}

/** Debug mode: the technical panels (signals, Director reasoning, simulators) are only shown
 * when it is on. Remembered per browser. */
const DEBUG_KEY = "bis.debug";
export function isDebug() { try { return localStorage.getItem(DEBUG_KEY) === "1"; } catch { return false; } }
export function setDebug(on) {
  try { localStorage.setItem(DEBUG_KEY, on ? "1" : "0"); } catch { /* private window */ }
  document.body.classList.toggle("is-debug", on);
  window.dispatchEvent(new CustomEvent("debugchange", { detail: on }));
}
