import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/crm";
import { PlayCircle } from "lucide-react";
import { STEP_LABELS } from "./accessShared";

export function AccessSimulation() {
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { const { data } = await api.post("/platform/access/simulate"); setRes(data); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4" data-testid="access-simulation">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h3 className="font-semibold text-slate-900">Anteprima destinatari</h3><p className="text-sm text-slate-500">La simulazione non invia email e non segna nulla come inviato.</p></div>
        <Button onClick={run} disabled={busy} data-testid="access-simulate-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900"><PlayCircle className="w-4 h-4 mr-1" />{busy ? "Simulazione…" : "Simula automazione"}</Button>
      </div>
      {res && (
        <>
          <div className="flex flex-wrap gap-2 text-sm" data-testid="access-sim-counts">
            {Object.entries(res.counts).map(([k, n]) => <span key={k} className="rounded-full bg-slate-100 px-3 py-1">{STEP_LABELS[k]}: <b>{n}</b></span>)}
            <span className="rounded-full bg-amber-50 text-amber-800 px-3 py-1">Esclusi: <b>{res.excluded}</b></span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="access-sim-table">
              <thead><tr className="text-xs text-slate-500 text-left"><th className="py-2">Utente</th><th>Organizzazione</th><th>Promemoria</th><th>Giorni</th><th>Template</th><th>Esito</th></tr></thead>
              <tbody>{res.items.length === 0 ? <tr><td colSpan={6} className="py-6 text-center text-slate-400" data-testid="access-sim-empty">Nessun utente da contattare oggi.</td></tr> : res.items.map((i) => (
                <tr key={`${i.cycle_id}-${i.step}`} className="border-t border-slate-100" data-testid={`access-sim-row-${i.user_id}`}>
                  <td className="py-2"><div className="font-medium">{i.name || "—"}</div><div className="text-xs text-slate-400">{i.email}</div></td>
                  <td>{i.org_names.join(", ")}</td><td>{STEP_LABELS[i.step]}</td><td>{i.days}</td><td>{i.template_id ? `#${i.template_id}` : "—"}</td>
                  <td>{i.excluded ? <StatusBadge color="orange">{i.excluded}</StatusBadge> : <StatusBadge color="green">Riceverebbe</StatusBadge>}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
