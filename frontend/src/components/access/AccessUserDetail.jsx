import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/crm";
import { fmtDate, fmtDur, STATUS, STEP_LABELS, REM_STATUS } from "./accessShared";

const END = { logout: "Logout", timeout: "Inattività", close: "Chiusura" };

function Info({ label, value, id }) {
  return <div><div className="text-xs text-slate-500">{label}</div><div className="text-sm font-medium text-slate-800" data-testid={`access-detail-${id}`}>{value}</div></div>;
}

function Sessions({ items }) {
  if (!items.length) return <p className="text-sm text-slate-400" data-testid="access-detail-no-sessions">Nessuna sessione registrata dall'attivazione del monitoraggio.</p>;
  return (
    <table className="w-full text-sm" data-testid="access-detail-sessions">
      <thead><tr className="text-xs text-slate-500 text-left"><th className="py-1">Inizio</th><th>Ultima attività</th><th>Durata attiva</th><th>Chiusura</th></tr></thead>
      <tbody>{items.map((s) => (
        <tr key={s.id} className="border-t border-slate-100"><td className="py-1.5">{fmtDate(s.started_at)}</td><td>{fmtDate(s.last_activity_at)}</td>
          <td>{fmtDur(s.active_seconds)}</td><td>{s.ended_at ? END[s.end_reason] || s.end_reason : "In corso"}</td></tr>))}</tbody>
    </table>
  );
}

function Reminders({ items }) {
  if (!items.length) return <p className="text-sm text-slate-400">Nessun promemoria ricevuto.</p>;
  return (
    <ul className="space-y-1.5" data-testid="access-detail-reminders">{items.map((r) => (
      <li key={r.id} className="flex flex-wrap items-center gap-2 text-sm"><span className="text-slate-500">{fmtDate(r.sent_at || r.created_at)}</span>
        <span className="font-medium">{STEP_LABELS[r.step]}</span><StatusBadge color={(REM_STATUS[r.status] || {}).color || "gray"}>{(REM_STATUS[r.status] || {}).label || r.status}</StatusBadge></li>))}</ul>
  );
}

export function AccessUserDetail({ userId, onClose }) {
  const [d, setD] = useState(null);
  useEffect(() => {
    if (!userId) { setD(null); return; }
    api.get(`/platform/access/users/${userId}`).then(({ data }) => setD(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [userId]);
  const u = d?.user;
  return (
    <Dialog open={!!userId} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="access-user-detail">
        <DialogHeader><DialogTitle>{u ? (u.name || u.email) : "Caricamento…"}</DialogTitle></DialogHeader>
        {u && (
          <div className="space-y-5">
            <div className="text-sm text-slate-500">{u.email} · {u.org_names.join(", ") || "nessuna organizzazione"} · <StatusBadge color={STATUS[u.status].color}>{STATUS[u.status].label}</StatusBadge></div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Info id="registered" label="Registrazione" value={fmtDate(u.registered_at)} />
              <Info id="first-login" label="Primo login" value={u.first_login_at ? fmtDate(u.first_login_at) : "Non disponibile"} />
              <Info id="last-login" label="Ultimo login" value={fmtDate(u.last_login_at)} />
              <Info id="last-activity" label="Ultima attività" value={fmtDate(u.last_activity_at)} />
              <Info id="login-count" label="Accessi totali" value={u.login_count} />
              <Info id="avg" label="Durata media sessioni" value={fmtDur(u.avg_session_seconds)} />
              <Info id="total" label="Tempo totale" value={fmtDur(u.total_seconds)} />
              <Info id="days" label="Giorni di inattività" value={u.days_inactive ?? "—"} />
            </div>
            <p className="text-xs text-slate-400">Dati raccolti dal {fmtDate(d.monitoring_started_at)}: nessuno storico precedente viene ricostruito. Non vengono registrate le pagine visitate.</p>
            <section><h3 className="text-sm font-semibold text-slate-800 mb-2">Storico sessioni</h3><Sessions items={d.sessions} /></section>
            <section><h3 className="text-sm font-semibold text-slate-800 mb-2">Promemoria Brevo ricevuti</h3><Reminders items={d.reminders} /></section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
