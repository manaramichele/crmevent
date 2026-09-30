import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { RechargeDialog } from "@/components/CreditsSection";
import { Coins, Zap, Gift, AlertTriangle, CheckCircle2, CalendarClock, Wallet } from "lucide-react";

const fmtDate = (s) => (s ? new Date(s + "T00:00:00").toLocaleDateString("it-IT", { day: "2-digit", month: "long", year: "numeric" }) : "—");
const STATE = {
  preparazione: ["In preparazione", "text-slate-600 bg-slate-100"],
  attivo: ["Attivo", "text-emerald-700 bg-emerald-50"],
  concluso: ["Concluso", "text-slate-500 bg-slate-100"],
};

export function EventCreditDialog({ eventId, open, onOpenChange }) {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const [recharge, setRecharge] = useState(false);

  const load = useCallback(async () => {
    if (!eventId) return;
    try { const { data } = await api.get(`/events/${eventId}/credit-status`); setSt(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [eventId]);
  useEffect(() => { if (open) load(); }, [open, load]);

  const activate = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/events/${eventId}/activate`);
      setSt(data);
      if (data.activation_free) toast.success("Primo evento attivato gratuitamente · saldo invariato");
      else toast.success(`Evento attivo · ${data.cost} crediti utilizzati · nuovo saldo ${data.balance}`);
    } catch (e) {
      if (e.response?.status === 402) toast.error("Crediti insufficienti per attivare l'evento");
      else toast.error(formatApiError(e.response?.data?.detail));
      load();
    }
    setBusy(false);
  };

  const disp = st?.display_state || "preparazione";
  const [label, cls] = STATE[disp] || STATE.preparazione;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="event-credit-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Coins className="w-5 h-5 text-tiffany-active" />Attivazione evento</DialogTitle>
          <DialogDescription>{st?.nome}</DialogDescription>
        </DialogHeader>
        {!st ? <p className="text-sm text-slate-400">Caricamento…</p> : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">Stato evento</span>
              <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${cls}`} data-testid="event-credit-state">{label}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-500">Saldo disponibile</span>
              <span className="font-semibold text-slate-900" data-testid="event-credit-balance">{st.balance} crediti</span>
            </div>

            {disp === "preparazione" && st.welcome_free_available && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm space-y-2" data-testid="event-welcome-box">
                <div className="font-semibold text-emerald-800 flex items-center gap-1.5"><Gift className="w-4 h-4" />Il tuo primo evento è gratuito</div>
                <p className="text-emerald-700">Attiva gratuitamente il tuo primo evento CRMEvent {st.event_date ? <>fino al <b>{fmtDate(st.event_date)}</b></> : "fino alla sua data"}. I tuoi <b>{st.balance} crediti di benvenuto</b> restano interamente disponibili.</p>
                <Button onClick={activate} disabled={busy} className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold" data-testid="event-activate-free-btn">
                  <Gift className="w-4 h-4 mr-1.5" />Attiva gratuitamente
                </Button>
              </div>
            )}

            {disp === "preparazione" && !st.welcome_free_available && (
              <div className="rounded-lg border border-tiffany-border bg-tiffany-light/30 p-4 text-sm space-y-2" data-testid="event-activate-box">
                <div className="font-semibold text-slate-800 flex items-center gap-1.5"><Zap className="w-4 h-4 text-tiffany-active" />Attiva il tuo evento</div>
                <p className="text-slate-600">Attiva tutte le funzioni operative di CRMEvent per questo evento {st.event_date ? <>fino al <b>{fmtDate(st.event_date)}</b></> : "fino alla sua data"}. Costo: <b>{st.cost} crediti</b> una tantum. Nessun rinnovo.</p>
                {st.balance < st.cost ? (
                  <div className="rounded border border-amber-200 bg-amber-50 p-2 text-amber-800" data-testid="event-insufficient-box">
                    <div className="font-semibold flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" />Crediti insufficienti</div>
                    <p>Servono {st.cost} crediti per attivare questo evento. Saldo disponibile: {st.balance} crediti.</p>
                    <Button size="sm" variant="outline" className="mt-1" onClick={() => setRecharge(true)} data-testid="event-recharge-prep"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>
                  </div>
                ) : (
                  <Button onClick={activate} disabled={busy} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-activate-btn">
                    <Zap className="w-4 h-4 mr-1.5" />Attiva evento · {st.cost} crediti
                  </Button>
                )}
              </div>
            )}

            {disp === "attivo" && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm space-y-1" data-testid="event-active-box">
                <div className="font-semibold text-emerald-800 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" />Evento attivo</div>
                <div className="flex items-center gap-1.5 text-slate-600"><CalendarClock className="w-4 h-4" />Attivo fino al <b>{fmtDate(st.event_date)}</b></div>
                {st.activation_free && <div className="text-xs text-emerald-700">Attivato gratuitamente (bonus benvenuto).</div>}
                <p className="text-xs text-slate-500 pt-1">Nessun altro consumo per mantenere attivo questo evento.</p>
              </div>
            )}

            {disp === "concluso" && (
              <p className="text-sm text-slate-500" data-testid="event-concluded-box">Evento concluso. I dati restano consultabili; nessun ulteriore addebito.</p>
            )}
          </div>
        )}
      </DialogContent>
      <RechargeDialog open={recharge} onClose={() => { setRecharge(false); load(); }} />
    </Dialog>
  );
}
