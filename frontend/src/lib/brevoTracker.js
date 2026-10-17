// Brevo Tracker (SDK 2.0): comandi inviati SOLO con consenso Marketing (lo script è caricato da index.html).
// Nessuna chiave API riservata qui; gli eventi di automazione partono dal backend.
import api from "@/lib/api";
import { hasConsent } from "@/lib/consent";

const push = (cmd) => { window.Brevo = window.Brevo || []; window.Brevo.push(cmd); };

let lastPath = null;
export function brevoPage(path) {
  if (!hasConsent("marketing") || path === lastPath) return;
  lastPath = path;
  push(["page", path, { ma_title: document.title, ma_url: window.location.origin + path, ma_path: window.location.pathname }]);
}

let identified = null;
export function brevoReset() { identified = null; }

export async function brevoIdentify(user) {
  if (!hasConsent("marketing") || !user || user.support || ["superadmin", "volunteer", "staff"].includes(user.role) || identified === user.user_id) return;
  identified = user.user_id;
  try {
    const { data } = await api.get("/brevo-tracker/identity");
    if (data.identify) push(["identify", { identifiers: { email_id: data.email }, attributes: data.attributes }]);
  } catch {
    identified = null;
  }
}
