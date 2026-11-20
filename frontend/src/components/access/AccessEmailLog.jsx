import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { fmtDate, STEP_LABELS, REM_STATUS } from "./accessShared";

export function AccessEmailLog() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get("/platform/access/reminders").then(({ data }) => setItems(data)).catch((e) => { setItems([]); toast.error(formatApiError(e.response?.data?.detail)); });
  }, []);
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
      <table className="w-full text-sm" data-testid="access-email-log">
        <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider text-left">
          {["Utente", "Organizzazione", "Tipologia", "Giorni", "Invio", "Template", "Stato Brevo", "Errore", "Login successivo"].map((h) => <th key={h} className="font-semibold px-3 py-3 whitespace-nowrap">{h}</th>)}
        </tr></thead>
        <tbody>
          {items === null ? <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400">Caricamento…</td></tr>
            : items.length === 0 ? <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400" data-testid="access-email-log-empty">Nessuna comunicazione automatica inviata.</td></tr>
              : items.map((r) => (
                <tr key={r.id} className="border-t border-slate-100" data-testid={`access-email-row-${r.id}`}>
                  <td className="px-3 py-3"><div className="font-medium text-slate-800">{r.name || "—"}</div><div className="text-xs text-slate-400">{r.email}</div></td>
                  <td className="px-3 py-3 text-slate-600">{(r.org_names || []).join(", ")}</td>
                  <td className="px-3 py-3">{STEP_LABELS[r.step] || r.step}<div className="text-[11px] text-slate-400">{r.kind === "promotional" ? "Promozionale" : "Servizio"}</div></td>
                  <td className="px-3 py-3">{r.days}</td>
                  <td className="px-3 py-3 whitespace-nowrap">{fmtDate(r.sent_at || r.created_at)}</td>
                  <td className="px-3 py-3">#{r.template_id}</td>
                  <td className="px-3 py-3"><StatusBadge color={(REM_STATUS[r.status] || {}).color || "gray"}>{(REM_STATUS[r.status] || {}).label || r.status}</StatusBadge>
                    {r.brevo_message_id && <div className="text-[11px] text-slate-400 break-all max-w-[180px]">{r.brevo_message_id}</div>}</td>
                  <td className="px-3 py-3 text-xs text-red-600 max-w-[200px]">{r.error || "—"}</td>
                  <td className="px-3 py-3 whitespace-nowrap">{fmtDate(r.next_login_at)}</td>
                </tr>))}
        </tbody>
      </table>
    </div>
  );
}
