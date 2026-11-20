export function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

export function fmtDur(sec) {
  const s = Math.max(Number(sec) || 0, 0);
  if (s < 60) return s ? `${s} s` : "0 min";
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

export const STATUS = {
  online: { label: "Online", color: "green" },
  offline: { label: "Offline", color: "gray" },
  never: { label: "Mai effettuato accesso", color: "orange" },
};

export const STEP_LABELS = {
  inactive_1: "Inattivo · 1° promemoria", inactive_2: "Inattivo · 2° promemoria",
  never_1: "Mai entrato · 1° promemoria", never_2: "Mai entrato · 2° promemoria",
};

export const REM_STATUS = {
  sent: { label: "Inviato", color: "green" }, test_sent: { label: "Inviato (prova)", color: "tiffany" },
  failed: { label: "Errore", color: "red" }, sending: { label: "In invio", color: "blue" }, canceled: { label: "Annullato", color: "gray" },
};

export const ROLE_OPTIONS = [
  { value: "admin_org", label: "Amministratore" }, { value: "user", label: "Utente" },
  { value: "member", label: "Membro" }, { value: "staff", label: "Staff" }, { value: "volunteer", label: "Volontario" },
];

export const inputCls = "h-10 px-3 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 transition-colors";
