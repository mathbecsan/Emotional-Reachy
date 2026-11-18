/** Persona catalog from the server (brain/personas.py), merged into MODES so every
 * view (transcript chips, chart dots, Reachy's face, replays) can color persona turns. */
import { api } from "./api.js";
import { MODES } from "./constants.js";

let cache = null;

export async function loadPersonas() {
  if (cache) return cache;
  cache = await api("/api/personas");
  for (const p of cache.personas) {
    MODES[p.key] = {
      color: p.color, label: p.name, persona: true,
      pose: p.key === "base" ? "curious" : p.energy === "high" ? "excited" : p.fragile ? "sincere" : "teasing",
    };
  }
  cache.byKey = Object.fromEntries(cache.personas.map((p) => [p.key, p]));
  return cache;
}

export const personaColor = (key) => MODES[key]?.color || "#8a8fbf";
