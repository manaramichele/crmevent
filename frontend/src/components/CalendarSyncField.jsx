import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { CalendarCheck, CalendarPlus, Lock, Link2, AlertTriangle, CheckCircle2 } from "lucide-react";

// Campo condiviso "Aggiungi a Google Calendar" per Attività e Follow-up.
// Mostra: stato sync (se record già collegato), checkbox, prompt sblocco (20 crediti) e collegamento account.
export default function CalendarSyncField({ kind, form, value, onChange }) {
  const [feat, setFeat] = useState(null);     // {configured, unlocked, cost, balance}
  const [conn, setConn] = useState(null);     // {configured, connected}
  const [synced, setSynced] = useState(false);
  const [busy, setBusy] = useState(false);
  const recId = form?.id;

  const refresh = useCallback(async () => {
    try {
      const [f, s] = await Promise.all([api.get("/calendar/feature"), api.get("/calendar/status")]);
      setFeat(f.data); setConn(s.data);
    } catch { /* noop */ }
    if (recId) {
      try { const { data } = await api.get(`/${kind === "activity" ? "activities" : "followups"}/${recId}/calendar-status`); setSynced(!!data.synced); }
      catch { setSynced(false); }
    }
  }, [recId, kind]);
  useEffect(() => { refresh(); }, [refresh]);

  const unlock = async () => {
    if (!feat) return;
    if ((feat.balance || 0) < feat.cost) { toast.error("Crediti insufficienti per attivare Google Calendar"); return; }
    if (!window.confirm(`Attivare Google Calendar per questa organizzazione?\n\nCosto: ${feat.cost} crediti (una tantum)\nSaldo attuale: ${feat.balance}\nSaldo dopo: ${feat.balance - feat.cost}`)) return;
    setBusy(true);
    try { await api.post("/calendar/unlock"); toast.success("Google Calendar attivato"); await refresh(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const connect = async () => {
    setBusy(true);
    try { const { data } = await api.get("/calendar/connect"); window.location.href = data.authorization_url; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };

  if (synced) {
    return (
      <div className="flex items-center gap-2 text-sm font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2.5" data-testid="gcal-synced">
        <CalendarCheck className="w-4 h-4" />Presente su Google Calendar <span className="text-xs text-emerald-600 font-normal">(salvando aggiorni anche l'evento)</span>
      </div>
    );
  }
  if (!feat) return null;

  return (
    <div className="rounded-lg border border-slate-200 p-3 space-y-2 bg-slate-50/50">
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} className="w-4 h-4 accent-tiffany" data-testid="gcal-checkbox" />
        <span className="text-sm font-medium text-slate-700 inline-flex items-center gap-1.5"><CalendarPlus className="w-4 h-4 text-tiffany-active" />Aggiungi a Google Calendar</span>
      </label>
      {value && !feat.unlocked && (
        <div className="text-xs text-slate-600 pl-6 space-y-2" data-testid="gcal-unlock-prompt">
          <div className="flex items-start gap-1.5"><Lock className="w-3.5 h-3.5 mt-0.5 text-amber-600" /><span>Funzione premium. Costo attivazione: <b>{feat.cost} crediti</b> (una tantum per organizzazione). Saldo: {feat.balance}.</span></div>
          {(feat.balance || 0) < feat.cost
            ? <div className="flex items-center gap-2 text-red-600"><AlertTriangle className="w-3.5 h-3.5" />Crediti insufficienti. <a href="/account" className="underline font-semibold">Acquista crediti</a></div>
            : <Button type="button" size="sm" onClick={unlock} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="gcal-unlock-btn">Attiva con {feat.cost} crediti</Button>}
        </div>
      )}
      {value && feat.unlocked && conn && !conn.connected && (
        <div className="text-xs text-slate-600 pl-6 space-y-2" data-testid="gcal-connect-prompt">
          <div>Collega Google Calendar per aggiungere questo appuntamento.</div>
          <Button type="button" size="sm" variant="outline" onClick={connect} disabled={busy} data-testid="gcal-connect-btn"><Link2 className="w-3.5 h-3.5 mr-1.5" />Collega Google Calendar</Button>
        </div>
      )}
      {value && feat.unlocked && conn?.connected && (
        <div className="text-xs text-emerald-700 pl-6 inline-flex items-center gap-1.5" data-testid="gcal-ready"><CheckCircle2 className="w-3.5 h-3.5" />Verrà creato sul tuo Google Calendar ({conn.google_email})</div>
      )}
    </div>
  );
}
