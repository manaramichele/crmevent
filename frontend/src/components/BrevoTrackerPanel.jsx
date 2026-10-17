import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Activity, RefreshCw } from "lucide-react";

const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");
const TONE = { inviato: "bg-emerald-50 text-emerald-700", errore: "bg-red-50 text-red-700", non_configurato: "bg-amber-50 text-amber-800" };

export function BrevoTrackerPanel() {
  const [d, setD] = useState(null);
  const load = useCallback(() => api.get("/platform/brevo-tracker").then(({ data }) => setD(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), []);
  useEffect(() => { load(); }, [load]);
  if (!d) return <p className="text-sm text-slate-400">Caricamento...</p>;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 space-y-4" data-testid="brevo-tracker-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2"><Activity className="w-4 h-4 text-[#0ABAB5]" /><h2 className="font-semibold text-slate-800">Brevo Tracker · eventi personalizzati</h2></div>
        <Button size="sm" variant="outline" onClick={load} data-testid="brevo-tracker-refresh"><RefreshCw className="w-4 h-4 mr-1" />Aggiorna</Button>
      </div>
      <p className="text-sm text-slate-600">Tracker di navigazione attivo su crmevent.it solo con consenso Marketing (banner cookie CRMEvent). Gli eventi sono inviati dal server tramite API Brevo Events; quelli "primo" una sola volta per organizzazione, gli abbonamenti solo da pagamenti Stripe confermati.</p>
      {!d.configured && <p className="text-sm rounded-lg bg-amber-50 border border-amber-200 text-amber-900 p-3" data-testid="brevo-tracker-not-configured">Brevo non configurato in questo ambiente: gli eventi vengono registrati come "non configurato" e non inviati.</p>}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2" data-testid="brevo-tracker-counts">
        {d.events.map((ev) => {
          const c = d.counts_30d[ev] || {};
          return (
            <div key={ev} className="rounded-lg bg-slate-50 border border-slate-200 p-3" data-testid={`brevo-tracker-count-${ev}`}>
              <div className="text-xs font-mono text-slate-500 break-all">{ev}</div>
              <div className="font-semibold text-slate-900">{c.inviato || 0} inviati</div>
              {(c.errore || c.non_configurato) ? <div className="text-xs text-slate-500">{c.errore || 0} errori · {c.non_configurato || 0} non config.</div> : null}
            </div>
          );
        })}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm" data-testid="brevo-tracker-log">
          <thead><tr className="text-left text-xs text-slate-500 border-b"><th className="py-2 pr-3">Data</th><th className="pr-3">Evento</th><th className="pr-3">Email</th><th>Stato</th></tr></thead>
          <tbody>
            {d.recent.length === 0 && <tr><td colSpan={4} className="py-4 text-slate-400">Nessun evento negli ultimi 90 giorni.</td></tr>}
            {d.recent.map((r, i) => (
              <tr key={i} className="border-b last:border-0">
                <td className="py-2 pr-3 whitespace-nowrap">{dt(r.created_at)}</td>
                <td className="pr-3 font-mono text-xs">{r.event}</td>
                <td className="pr-3 break-all">{r.email}</td>
                <td><span className={`text-xs px-2 py-0.5 rounded-full ${TONE[r.status] || ""}`} title={r.error || ""}>{r.status.replace("_", " ")}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
