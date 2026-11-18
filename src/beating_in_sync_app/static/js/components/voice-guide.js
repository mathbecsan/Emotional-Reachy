/**
 * Reachy's spoken guide for the setup: what to do, "got it" when a step is done, a nudge
 * when you're stuck, what went wrong and how to fix it. Lines are queued (never overlap),
 * repeats within 10 s are skipped, and the guide can be switched off.
 */
import { api } from "../api.js";

const KEY = "bis.voiceGuide";
let chain = Promise.resolve();
let pending = 0;
let last = { text: "", t: 0 };

export function voiceOn() { try { return localStorage.getItem(KEY) !== "0"; } catch { return true; } }
export function setVoice(on) { try { localStorage.setItem(KEY, on ? "1" : "0"); } catch { /* private */ } }

/** Say `text` through Reachy. `important` lines are never dropped when several are waiting. */
export function speak(text, { important = false } = {}) {
  if (!voiceOn() || !text) return chain;
  const now = Date.now();
  if (text === last.text && now - last.t < 10000) return chain;
  if (!important && pending >= 2) return chain;              // don't pile up chatter
  last = { text, t: now };
  pending += 1;
  chain = chain.then(() => api("/api/check/say", { text }).catch(() => {})).finally(() => { pending -= 1; });
  return chain;
}

/** Resolves once Reachy has finished everything queued (e.g. before recording the microphone). */
export const quiet = () => chain;

export const shortFix = (fix) => (fix || "").split(/(?<=[.!?])\s/)[0];

const PRAISE = ["Got it!", "Perfect!", "Nice!", "Great job!", "That's it!"];
let p = 0;
export const praise = () => PRAISE[p++ % PRAISE.length];
