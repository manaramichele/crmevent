import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";

const when = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");
const ST = { ok: ["Sincronizzata", "text-emerald-700 bg-emerald-50"], partial: ["Parziale", "text-amber-800 bg-amber-50"], error: ["Errore", "text-red-700 bg-red-50"] };
const REASON = { notFound: "calendario non trovato o non più condiviso", google_unavailable: "Google Calendar non risponde, nuovo tentativo automatico tra 15 minuti",
  reauthorization_required: "riconnessione dell'account necessaria", insufficient_scope: "autorizzazioni insufficienti: ricollega l'account", key_missing: "configurazione di cifratura mancante", not_connected: "account non collegato" };

// Calendari da controllare per la disponibilità (solo occupato/libero) + stato e "Sincronizza ora".
export function CalendarAvailability({ cal, cals, onSaved }) {
  const [sel, setSel] = useState(cal.availability_calendar_ids || []);
  const [av, setAv] = useState(cal.availability || {});
  const [busy, setBusy] = useState(false);
  useEffect(() => { setSel(cal.availability_calendar_ids || []); setAv(cal.availability || {}); }, [cal]);
  const toggle = (id, v) => setSel((s) => (v ? [...new Set([...s, id])] : s.filter((x) => x !== id)));
  const name = (id) => cals.find((c) => c.id === id)?.summary || id;
  const run = async (fn, ok) => {
    setBusy(true);
    try { const { data } = await fn(); setAv(data.availability || {}); toast.success(ok); onSaved?.(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  const [label, cls] = ST[av.status] || ["Mai sincronizzata", "text-slate-600 bg-slate-100"];
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 p-3 sm:p-4" data-testid="gcal-availability">
      <div>
        <div className="text-sm font-semibold text-slate-800">Calendari da controllare per la disponibilità</div>
        <p className="text-xs text-slate-500 flex items-start gap-1 mt-0.5"><ShieldCheck className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald-600" />Un orario è occupato se almeno un calendario selezionato ha un impegno "Occupato". CRMEvent legge solo occupato/libero: nessun titolo o dettaglio viene letto, mostrato o importato.</p>
      </div>
      <ul className="space-y-1.5">
        {cals.map((c) => (
          <li key={c.id}>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox checked={sel.includes(c.id)} onCheckedChange={(v) => toggle(c.id, !!v)} data-testid={`gcal-avail-${c.id}`} />
              <span className="break-all">{c.summary}{c.primary ? " (principale)" : ""}{c.id === cal.calendar_id ? " · destinazione" : ""}</span>
            </label>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy || sel.length === 0} onClick={() => run(() => api.post("/calendar/availability", { calendar_ids: sel }), "Calendari monitorati salvati")} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="gcal-avail-save">Salva calendari</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.post("/calendar/sync-now"), "Disponibilità aggiornata")} data-testid="gcal-sync-now"><RefreshCw className={`w-4 h-4 mr-1 ${busy ? "animate-spin" : ""}`} />Sincronizza ora</Button>
      </div>
      <div className="text-xs text-slate-600 flex flex-wrap items-center gap-x-3 gap-y-1" data-testid="gcal-sync-status">
        <span className={`rounded-full px-2 py-0.5 font-semibold ${cls}`} data-testid="gcal-sync-state">{label}</span>
        <span data-testid="gcal-sync-last-ok">Ultima sincronizzazione riuscita: {when(av.last_ok_at)}</span>
        <span data-testid="gcal-sync-monitored">Calendari monitorati: {av.monitored ?? sel.length}</span>
      </div>
      {av.errors?.length > 0 && (
        <ul className="text-xs text-red-700 space-y-0.5" data-testid="gcal-sync-errors">
          {av.errors.map((e, i) => <li key={i} className="flex items-start gap-1"><AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />{e.calendar_id === "*" ? "Controllo non riuscito" : name(e.calendar_id)}: {REASON[e.reason] || e.reason}</li>)}
        </ul>
      )}
    </div>
  );
}
