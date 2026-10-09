import api, { API } from "@/lib/api";

const ERRORS = {
  denied: "Accesso con Google annullato.",
  state: "Sessione di accesso scaduta o non valida. Riprova.",
  exchange: "Google non ha completato l'accesso. Riprova.",
  invalid: "Identità Google non valida. Riprova.",
  unverified: "L'email del tuo account Google non è verificata.",
  no_account: "Nessun account CRMEvent con questa email Google. Registrati per iniziare.",
  disabled: "Accesso disabilitato per questo account.",
  conflict: "Questa email è già collegata a un altro account Google. Accedi con email e password.",
};
export const googleErrorText = (code) => (code ? ERRORS[code] || "Accesso con Google non riuscito." : "");

// Login Google: flusso CRMEvent (backend) se attivo, altrimenti quello precedente.
// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export async function startGoogle({ intent, next = "", invite = "", legacyRedirect }) {
  let provider = "emergent";
  try { provider = (await api.get("/oauth/google/config")).data.provider; } catch { /* resta il flusso precedente */ }
  if (provider === "crmevent") {
    const q = new URLSearchParams({ intent, ...(next ? { next } : {}), ...(invite ? { invite } : {}) });
    window.location.href = `${API}/oauth/google/start?${q}`;
    return;
  }
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(legacyRedirect)}`;
}
