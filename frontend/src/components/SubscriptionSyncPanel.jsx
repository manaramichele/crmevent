import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { RefreshCw, CalendarClock } from "lucide-react";

const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");
const Stat = ({ label, value, testid }) => <div className="rounded-lg bg-slate-50 border border-slate-200 p-3"><div className="text-xs text-slate-500">{label}</div><div className="font-semibold text-slate-900" data-testid={testid}>{value}</div></div>;

export function SubscriptionSyncPanel() {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState("");
  const load = useCallback(() => api.get("/platform/brevo/subscription-sync").then(({ data }) => setD(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), []);
  useEffect(() => { load(); }, [load]);
  const run = async (key, url, body) => {
    setBusy(key);
    try { const { data } = await api.post(url, body); (data.ok === false || data.failed ? toast.error : toast.success)(data.total != null ? `Sincronizzate ${data.ok}/${data.total}${data.failed ? ` · ${data.errors?.[0] || ""}` : ""}` : data.ok ? "Organizzazione sincronizzata" : `Errore: ${data.error}`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(""); }
  };
  if (!d) return <p className="text-sm text-slate-400">Caricamento...</p>;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 space-y-4" data-testid="subscription-sync-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2"><CalendarClock className="w-4 h-4 text-[#0ABAB5]" /><h2 className="font-semibold text-slate-800">Sincronizzazione abbonamenti</h2></div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("failed", "/platform/brevo/subscription-sync", { only_failed: true })} data-testid="sub-sync-failed">Riprova errori</Button>
          <Button size="sm" disabled={!!busy} onClick={() => run("all", "/platform/brevo/subscription-sync", { only_failed: false })} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="sub-sync-all"><RefreshCw className={`w-4 h-4 mr-1 ${busy === "all" ? "animate-spin" : ""}`} />Sincronizza tutte</Button>
        </div>
      </div>
      {!d.configured && <p className="text-sm rounded-lg bg-amber-50 border border-amber-200 text-amber-900 p-3" data-testid="sub-sync-not-configured">Brevo non configurato in questo ambiente: le sincronizzazioni restano in errore finché non è presente la chiave API.</p>}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Stato" value={!d.configured ? "Non configurato" : d.errors ? "Con errori" : "Attivo"} testid="sub-sync-status" />
        <Stat label="Organizzazioni sincronizzate" value={`${d.synced_ok} / ${d.total_orgs}`} testid="sub-sync-count" />
        <Stat label="Errori" value={d.errors} testid="sub-sync-errors" />
        <Stat label="Ultima sincronizzazione" value={dt(d.last_sync_at)} testid="sub-sync-last" />
      </div>
      <p className="text-xs text-slate-500">Attributi: {Object.keys(d.attributes).join(", ")}. Solo Admin Organizzatore e utenti con permesso Gestione abbonamento; nessuna lista modificata.</p>
      <div className="divide-y divide-slate-100 max-h-[420px] overflow-y-auto" data-testid="sub-sync-rows">
        {d.rows.length === 0 ? <p className="text-sm text-slate-500 py-2">Nessuna sincronizzazione ancora eseguita.</p> : d.rows.map((x) => (
          <div key={x.org_id} className="py-2 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-sm" data-testid={`sub-sync-row-${x.org_id}`}>
            <div className="min-w-0"><div className="font-medium text-slate-800">{x.org_name || x.org_id} <span className={`ml-1 text-xs rounded px-1.5 py-0.5 ${x.status === "ok" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{x.status === "ok" ? "Sincronizzata" : "Errore"}</span></div>
              <div className="text-xs text-slate-500 break-words">{x.attrs?.CRM_PIANO || "—"} · {x.attrs?.CRM_STATO} · scadenza {x.attrs?.CRM_SCADENZA || "—"} · {x.recipients?.length || 0} destinatari · {dt(x.at)} ({x.source}){x.error ? ` · ${x.error}` : ""}</div></div>
            <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run(x.org_id, `/platform/brevo/subscription-sync/${x.org_id}`)} data-testid={`sub-sync-one-${x.org_id}`}><RefreshCw className="w-3.5 h-3.5 mr-1" />Risincronizza</Button>
          </div>
        ))}
      </div>
    </div>
  );
}
