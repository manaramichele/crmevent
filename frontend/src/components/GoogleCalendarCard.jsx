import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { AlertTriangle, CalendarCheck2, Link2, RefreshCw, Unplug } from "lucide-react";

const REASONS = {
  access_denied: "Non hai autorizzato l'accesso a Google Calendar. Puoi riprovare quando vuoi.",
  expired: "La richiesta di collegamento è scaduta. Riprova.",
  exchange_failed: "Non siamo riusciti a completare il collegamento. Riprova tra qualche istante.",
  consent_required: "Google non ha concesso l'accesso continuativo: riprova e conferma le autorizzazioni richieste.",
  identity_failed: "Non siamo riusciti a leggere l'account Google selezionato. Riprova.",
  generic: "Si è verificato un problema durante il collegamento a Google Calendar.",
};
const STATUS = { connected: ["Connesso", "text-emerald-700 bg-emerald-50"], reauthorization_required: ["Riconnessione necessaria", "text-red-700 bg-red-50"],
  temporary_error: ["Errore temporaneo", "text-amber-800 bg-amber-50"], not_connected: ["Non collegato", "text-slate-600 bg-slate-100"] };

export const connectCalendar = async (force) => {
  try { const { data } = await api.get("/calendar/connect", { params: force ? { force_consent: true } : {} }); window.location.href = data.authorization_url; }
  catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
};

export function CalendarReturnHandler() {
  const loc = useLocation();
  const nav = useNavigate();
  useEffect(() => {
    const p = new URLSearchParams(loc.search);
    const c = p.get("calendar");
    if (!c) return;
    const reason = p.get("reason");
    p.delete("calendar"); p.delete("reason");
    nav({ pathname: loc.pathname, search: p.toString() ? `?${p}` : "" }, { replace: true });
    if (c === "connected") {
      api.get("/calendar/status").then(({ data }) => {
        if (data.connected) toast.success("Google Calendar collegato!", { id: "gcal-return", description: `Il tuo account Google Calendar (${data.google_email}) è stato collegato correttamente a CRMEvent.`, duration: 7000, className: "!border-[#0ABAB5]" });
        else toast.error(data.message || REASONS.generic, { id: "gcal-return", duration: 12000, action: { label: "Riprova", onClick: () => connectCalendar(true) } });
        window.dispatchEvent(new Event("calendar:changed"));
      }).catch(() => {});
    } else {
      toast.error(REASONS[reason] || REASONS.generic, { id: "gcal-return", duration: 12000, action: { label: "Riprova", onClick: () => connectCalendar(reason === "consent_required") } });
    }
  }, [loc.search, loc.pathname, nav]);
  return null;
}

const when = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

export function GoogleCalendarCard() {
  const [cal, setCal] = useState(null);
  const [cals, setCals] = useState([]);
  const load = useCallback(async () => {
    try { const { data } = await api.get("/calendar/status"); setCal(data); if (data.connected) { try { const r = await api.get("/calendar/calendars"); setCals(r.data.calendars); } catch { setCals([]); } } }
    catch { setCal({ configured: true, connected: false, status: "temporary_error", message: "Impossibile leggere lo stato del collegamento." }); }
  }, []);
  useEffect(() => { load(); window.addEventListener("calendar:changed", load); return () => window.removeEventListener("calendar:changed", load); }, [load]);
  const disconnect = async () => { if (!window.confirm("Scollegare Google Calendar dal tuo account CRMEvent?")) return; await api.post("/calendar/disconnect"); toast.success("Google Calendar scollegato"); load(); };
  const selectCal = async (id) => { await api.post("/calendar/select", { calendar_id: id }); setCal((c) => ({ ...c, calendar_id: id })); toast.success("Calendario aggiornato"); };
  if (!cal) return <div className="text-sm text-slate-400">Caricamento...</div>;
  if (!cal.configured) return <div className="text-sm text-amber-700 bg-amber-50 ring-1 ring-amber-200 rounded-lg p-3">Google Calendar non è ancora configurato dall'amministratore.</div>;
  const [label, cls] = STATUS[cal.status] || STATUS.not_connected;
  const linked = cal.status !== "not_connected";
  return (
    <div className="space-y-4" data-testid="gcal-card">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`} data-testid="gcal-status">{label}</span>
        {cal.google_email && <span className="text-slate-700 break-all"><CalendarCheck2 className="inline w-4 h-4 mr-1 text-emerald-600" />Account collegato: <b data-testid="gcal-email">{cal.google_email}</b></span>}
        {linked && !cal.google_email && <span className="text-red-700" data-testid="gcal-email-missing">Account da riconnettere</span>}
      </div>
      {cal.message && <p className="text-sm text-red-700 flex items-start gap-1.5" data-testid="gcal-message"><AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />{cal.message}</p>}
      {linked && <p className="text-xs text-slate-500" data-testid="gcal-last-sync">Collegato il {when(cal.connected_at)} · ultima sincronizzazione {when(cal.last_sync_at)}</p>}
      {cal.connected && cals.length > 0 && (
        <div className="max-w-xs space-y-1.5"><Label className="text-xs">Calendario selezionato</Label>
          <Select value={cal.calendar_id} onValueChange={selectCal}><SelectTrigger data-testid="calendar-select"><SelectValue /></SelectTrigger>
            <SelectContent>{cals.map((c) => <SelectItem key={c.id} value={c.id}>{c.summary}</SelectItem>)}</SelectContent></Select>
        </div>
      )}
      {cal.redirect_uri && <p className="text-xs text-slate-400 break-all" data-testid="gcal-redirect-uri">Redirect URI (solo Super Admin): {cal.redirect_uri}{cal.key_configured === false ? " · chiave di cifratura MANCANTE" : ""}</p>}
      <div className="flex flex-wrap gap-2">
        {!linked && <Button onClick={() => connectCalendar(false)} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="calendar-connect"><Link2 className="w-4 h-4 mr-1.5" />Collega Google Calendar</Button>}
        {linked && cal.status !== "connected" && <Button onClick={() => connectCalendar(true)} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="calendar-reconnect"><RefreshCw className="w-4 h-4 mr-1.5" />Ricollega</Button>}
        {cal.status === "connected" && <Button variant="outline" onClick={() => connectCalendar(false)} data-testid="calendar-change-account"><RefreshCw className="w-4 h-4 mr-1.5" />Cambia account Google</Button>}
        {linked && <Button variant="outline" onClick={disconnect} data-testid="calendar-disconnect"><Unplug className="w-4 h-4 mr-1.5" />Scollega Google Calendar</Button>}
      </div>
    </div>
  );
}
