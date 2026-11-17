/** REST helpers + one shared, auto-reconnecting event websocket (/ws). */

const WS_URL = `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;
const listeners = new Set();
const connListeners = new Set();
let socket = null;

export async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `${res.status} ${res.statusText}`);
  return data;
}

export const command = (cmd) => api("/api/command", { cmd });
export const say = (text, lang) => api("/api/say", { text, lang });

/** Subscribe to every server event; returns an unsubscribe function. */
export function onEvent(cb) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function onConnection(cb) {
  connListeners.add(cb);
  cb(socket?.readyState === WebSocket.OPEN);
  return () => connListeners.delete(cb);
}

export function connect() {
  if (socket && socket.readyState <= WebSocket.OPEN) return;
  socket = new WebSocket(WS_URL);
  socket.onopen = () => connListeners.forEach((cb) => cb(true));
  socket.onmessage = (ev) => {
    const event = JSON.parse(ev.data);
    listeners.forEach((cb) => cb(event));
  };
  socket.onclose = () => {
    connListeners.forEach((cb) => cb(false));
    setTimeout(connect, 1000);
  };
}
