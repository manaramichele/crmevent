import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { RechargeDialog } from "@/components/CreditsSection";
import { Coins, Zap, AlertTriangle, CheckCircle2, CalendarClock, Wallet } from "lucide-react";

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("it-IT", { day: "2-digit", month: "long", year: "numeric" }) : "—");
const STATE = {
  preparazione: ["In preparazione", "text-slate-600 bg-slate-100"],
  attivo: ["Attivo", "text-emerald-700 bg-emerald-50"],
  sospeso: ["Sospeso", "text-red-700 bg-red-50"],
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
      toast.success(`Evento attivo · ${data.cost} crediti utilizzati · nuovo saldo ${data.balance}`);
    } catch (e) {
      if (e.response?.status === 402) toast.error("Crediti insufficienti per attivare l'evento");
      else toast.error(formatApiError(e.response?.data?.detail));
      load();
    }
    setBusy(false);
  };

  const [label, cls] = STATE[st?.credit_state] || ["—", "text-slate-500 bg-slate-100"];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="event-credit-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Coins className="w-5 h-5 text-tiffany-active" />Crediti evento</DialogTitle>
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

            {st.credit_state === "preparazione" && (
              <div className="rounded-lg border border-tiffany-border bg-tiffany-light/30 p-4 text-sm space-y-2" data-testid="event-activate-box">
                <div className="font-semibold text-slate-800 flex items-center gap-1.5"><Zap className="w-4 h-4 text-tiffany-active" />Attiva questo evento</div>
                <p className="text-slate-600">L'attivazione costa <b>{st.cost} crediti</b> e ti permette di usare tutte le funzioni operative per i prossimi <b>{st.period_days} giorni</b>. Il rinnovo avverrà ogni {st.period_days} giorni fino alla data dell'evento.</p>
                <Button onClick={activate} disabled={busy || st.balance < st.cost} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-activate-btn">
                  <Zap className="w-4 h-4 mr-1.5" />Attiva evento · {st.cost} crediti
                </Button>
                {st.balance < st.cost && <Button variant="outline" className="w-full" onClick={() => setRecharge(true)} data-testid="event-recharge-prep"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>}
              </div>
            )}

            {st.credit_state === "attivo" && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm space-y-1" data-testid="event-active-box">
                <div className="font-semibold text-emerald-800 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" />Evento attivo</div>
                <div className="flex items-center gap-1.5 text-slate-600"><CalendarClock className="w-4 h-4" />Prossimo rinnovo: <b>{fmtDate(st.next_renewal_at)}</b> · {st.cost} crediti</div>
                {st.low_balance && (
                  <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-amber-800">
                    <div className="font-semibold flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" />Crediti in esaurimento</div>
                    <p>Il rinnovo richiederà {st.cost} crediti.</p>
                    <Button size="sm" variant="outline" className="mt-1" onClick={() => setRecharge(true)} data-testid="event-recharge-low"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>
                  </div>
                )}
              </div>
            )}

            {st.credit_state === "sospeso" && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm space-y-2" data-testid="event-suspended-box">
                <div className="font-semibold text-red-800 flex items-center gap-1.5"><AlertTriangle className="w-4 h-4" />Evento sospeso per crediti insufficienti</div>
                <p className="text-slate-600">Non ci sono crediti sufficienti per mantenere attivo questo evento. Servono {st.cost} crediti · saldo {st.balance}.</p>
                {st.can_reactivate
                  ? <Button onClick={activate} disabled={busy} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-reactivate-btn"><Zap className="w-4 h-4 mr-1.5" />Riattiva evento · {st.cost} crediti</Button>
                  : <Button onClick={() => setRecharge(true)} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-recharge-suspended"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>}
              </div>
            )}

            {st.credit_state === "concluso" && (
              <p className="text-sm text-slate-500" data-testid="event-concluded-box">Evento concluso. I dati restano consultabili; non sono previsti ulteriori rinnovi.</p>
            )}
          </div>
        )}
      </DialogContent>
      <RechargeDialog open={recharge} onClose={() => { setRecharge(false); load(); }} />
    </Dialog>
  );
}
