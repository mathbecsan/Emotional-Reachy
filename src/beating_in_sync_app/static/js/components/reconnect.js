/** One press to get Reachy back: restarts the robot software if it's stuck or stopped, then reconnects. */
import { api } from "../api.js";
import { toast } from "../ui.js";

let busy = null;

export function reconnectReachy() {
  if (busy) return busy;
  toast("Reconnecting Reachy… this can take up to 20 seconds.");
  busy = api("/api/robot/reconnect", {})
    .then((r) => {
      if (r.ok) toast(`${r.detail}${r.note ? ` ${r.note}` : ""}`);
      else toast(`${r.detail} ${r.fix || ""}`, "error");
      return r;
    })
    .catch((e) => { toast(e.message, "error"); return { ok: false, detail: e.message }; })
    .finally(() => { busy = null; window.dispatchEvent(new Event("refreshstatus")); });
  return busy;
}
