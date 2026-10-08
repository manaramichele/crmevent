import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Rocket, Wallet } from "lucide-react";

// Prompt globale di attivazione evento: si apre quando il backend risponde 403 event_not_operational.
// Il costo NON è hardcoded: viene letto da /events/{id}/credit-status (servizio configurato in Super Admin).
export default function ActivationGate() {
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const handler = async (e) => {
      const d = e.detail || {};
      if (!d.event_id) return;
      try { const { data } = await api.get(`/events/${d.event_id}/credit-status`); setInfo(data); }
      catch { /* ignora */ }
    };
    window.addEventListener("crmevent:event-not-operational", handler);
    return () => window.removeEventListener("crmevent:event-not-operational", handler);
  }, []);

  const close = () => setInfo(null);
  const suspended = info?.credit_state === "sospeso";
  const cost = suspended ? info?.maintenance_cost : info?.activation_cost;
  const sufficient = suspended ? info?.sufficient_maintenance : info?.sufficient_activation;

  const activate = async () => {
    setBusy(true);
    try {
      await api.post(`/events/${info.event_id}/activate`);
      toast.success(suspended ? "Evento riattivato" : "Evento attivato");
      close();
      setTimeout(() => window.location.reload(), 400);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };

  if (!info) return null;
  return (
    <Dialog open onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-w-sm" data-testid="activation-gate-dialog">
        <DialogHeader>
          <DialogTitle>{suspended ? "Riattiva il tuo evento" : "Attiva il tuo evento"}</DialogTitle>
          <DialogDescription>
            {suspended
              ? "L'evento è sospeso. Riattivalo per gestire di nuovo staff, volontari, sponsor, turni, attività, briefing e le altre funzioni operative."
              : `Per iniziare a gestire staff, volontari, sponsor, turni, attività, briefing e le altre funzioni operative devi prima attivare l'evento${info.nome ? ` "${info.nome}"` : ""}.`}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-slate-500">{suspended ? "Costo riattivazione" : "Attivazione"}</span><span className="font-semibold">{cost ?? "—"} crediti</span></div>
          {!suspended && info.maintenance_cost != null && <div className="flex justify-between"><span className="text-slate-500">Mantenimento</span><span className="font-semibold">{info.maintenance_cost} crediti/mese fino alla data evento</span></div>}
          <div className="flex justify-between border-t pt-2"><span className="text-slate-500">Saldo disponibile</span><span className="font-semibold" data-testid="activation-gate-balance">{info.balance} crediti</span></div>
        </div>
        {!sufficient && <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800 mt-2">Crediti insufficienti: servono {cost} crediti.</div>}
        <DialogFooter className="mt-3">
          <Button variant="outline" onClick={close}>Annulla</Button>
          {sufficient
            ? <Button onClick={activate} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="activation-gate-confirm"><Rocket className="w-4 h-4 mr-1.5" />{suspended ? `Riattiva · ${cost} crediti` : `Attiva evento · ${cost} crediti`}</Button>
            : <Button onClick={() => { close(); window.location.href = "/profilo?tab=crediti"; }} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="activation-gate-recharge"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
