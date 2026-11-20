import api from "@/lib/api";

// Heartbeat leggero: conta solo il tempo con interazioni reali; una sola scheda invia per volta.
const KEY_CLIENT = "acc_client_id";
const KEY_INTERACT = "acc_last_interaction";
const KEY_SENT = "acc_last_hb";
const INTERVAL = 60000;
const EVENTS = ["mousedown", "keydown", "touchstart", "wheel", "scroll", "mousemove"];

export function clientId() {
  let id = localStorage.getItem(KEY_CLIENT);
  if (!id) { id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`; localStorage.setItem(KEY_CLIENT, id); }
  return id;
}

let lastMark = 0;
const mark = () => {
  const now = Date.now();
  if (now - lastMark < 5000 || document.visibilityState !== "visible") return;
  lastMark = now;
  localStorage.setItem(KEY_INTERACT, String(now));
};

const beat = (force = false) => {
  const now = Date.now();
  const last = Number(localStorage.getItem(KEY_SENT) || 0);
  if (!force && now - last < INTERVAL - 2000) return;
  const interacted = now - Number(localStorage.getItem(KEY_INTERACT) || 0) < INTERVAL;
  if (!interacted) return;
  localStorage.setItem(KEY_SENT, String(now));
  api.post("/access/heartbeat", { client_id: clientId(), interacted: true }).catch(() => {});
};

export function startHeartbeat() {
  EVENTS.forEach((e) => window.addEventListener(e, mark, { passive: true }));
  mark();
  const first = setTimeout(() => beat(true), 1500);
  const timer = setInterval(() => beat(), 15000);
  return () => {
    clearTimeout(first);
    clearInterval(timer);
    EVENTS.forEach((e) => window.removeEventListener(e, mark));
  };
}

export async function endAccessSession() {
  try { await api.post("/access/end", { client_id: clientId(), reason: "logout" }); } catch {}
}
