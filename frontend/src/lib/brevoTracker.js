// Brevo Tracker (SDK 2.0): solo coda client. Lo script Brevo parte da index.html dopo il consenso Marketing iubenda;
// senza consenso i comandi restano nella coda locale e non vengono mai inviati. Nessuna chiave API riservata qui.
import api from "@/lib/api";

const push = (cmd) => { if (typeof window !== "undefined") { window.Brevo = window.Brevo || []; window.Brevo.push(cmd); } };

let lastPath = null;
export function brevoPage(path) {
  if (path === lastPath) return;
  lastPath = path;
  push(["page", path, { ma_title: document.title, ma_url: window.location.origin + path, ma_path: window.location.pathname }]);
}

let identified = null;
export async function brevoIdentify(user) {
  if (!user || user.support || ["superadmin", "volunteer", "staff"].includes(user.role) || identified === user.user_id) return;
  identified = user.user_id;
  try {
    const { data } = await api.get("/brevo-tracker/identity");
    if (data.identify) push(["identify", { identifiers: { email_id: data.email }, attributes: data.attributes }]);
  } catch {
    identified = null;
  }
}
