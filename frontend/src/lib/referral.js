import api from "@/lib/api";

// Codice partner (?ref=&cmp=): conservato e tracciato SOLO dopo il consenso iubenda (misurazione o marketing).
// Senza consenso resta in memoria per la sola visita corrente.
const KEY = "crmevent_ref";
const DAYS = 30;
let pending = null;

function consentGiven() {
  try {
    const prefs = window._iub?.cs?.api?.getPreferences?.();
    if (prefs?.purposes) return !!(prefs.purposes["4"] || prefs.purposes["5"]);
    const c = document.cookie.split("; ").find((x) => x.startsWith("_iub_cs-"));
    if (!c) return false;
    const v = JSON.parse(decodeURIComponent(c.split("=").slice(1).join("=")));
    return !!(v.purposes ? v.purposes["4"] || v.purposes["5"] : v.consent);
  } catch { return false; }
}

function persist() {
  if (!pending || !consentGiven()) return false;
  try { localStorage.setItem(KEY, JSON.stringify(pending)); } catch {}
  api.post("/partner/track", { ref: pending.code, cmp: pending.cmp || null }).catch(() => {});
  pending = null;
  return true;
}

export function captureReferral() {
  const qs = new URLSearchParams(window.location.search);
  const code = (qs.get("ref") || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 12).toUpperCase();
  if (!code) return;
  pending = { code, cmp: (qs.get("cmp") || "").slice(0, 60) || null, at: new Date().toISOString() };
  if (persist()) return;
  const t = setInterval(() => { if (!pending || persist()) clearInterval(t); }, 1500);
  setTimeout(() => clearInterval(t), 10 * 60 * 1000);
}

export function getReferral() {
  if (pending) return pending;
  try {
    const v = JSON.parse(localStorage.getItem(KEY));
    if (v?.code && Date.now() - new Date(v.at).getTime() < DAYS * 86400000) return v;
    localStorage.removeItem(KEY);
  } catch {}
  return null;
}

export function clearReferral() {
  pending = null;
  try { localStorage.removeItem(KEY); } catch {}
}
