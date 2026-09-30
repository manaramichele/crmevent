import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { CalendarClock, Lock, ArrowUpRight, CreditCard, CheckCircle2, Sparkles } from "lucide-react";

const PLABEL = { starter: "Starter", professional: "Professional", premium: "Premium", free: "—" };
const eur = (n) => (n == null ? "—" : `${Number(n).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);
const dmy = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4) : "—");

function StatePill({ ev, trial, days }) {
  if (trial) return <StatusBadge color="tiffany" data-testid={`plan-badge-${ev.id}`}>Prova Premium · {days} gg</StatusBadge>;
  if (ev.purchased) return <StatusBadge color="green" data-testid={`plan-badge-${ev.id}`}>Piano {PLABEL[ev.current_plan]}</StatusBadge>;
  return <StatusBadge color="red" data-testid={`plan-badge-${ev.id}`}>Prova scaduta</StatusBadge>;
}

export default function EventPlanManager({ handleReturn = false, compact = false }) {
  const [data, setData] = useState(null);
  const [dlg, setDlg] = useState(null); // event object for the dialog
  const [busy, setBusy] = useState(false);
  const [params, setParams] = useSearchParams();
  const handled = useRef(false);

  const load = () => api.get("/event-plans/status").then((r) => setData(r.data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!handleReturn || handled.current) return;
    const sid = params.get("session_id");
    const purchase = params.get("purchase"); const upgrade = params.get("upgrade");
    if (!purchase && !upgrade) return;
    handled.current = true;
    if ((purchase === "cancel") || (upgrade === "cancel")) {
      toast.info("Pagamento annullato. Nessuna modifica applicata all'evento.");
      setParams({}, { replace: true });
      return;
    }
    if (sid && (purchase === "success" || upgrade === "success")) {
      api.get(`/event-plans/checkout-confirmation?session_id=${sid}`).then(({ data: c }) => {
        if (c.paid) toast.success(`Pagamento completato · il piano ${PLABEL[c.plan] || c.plan} è ora attivo per ${c.event_name || "l'evento"}.`);
        else toast.error("Pagamento non confermato.");
        load();
      }).catch((e) => toast.error(formatApiError(e.response?.data?.detail)))
        .finally(() => setParams({}, { replace: true }));
    }
  }, [params, handleReturn]);

  const go = async (ev, opt) => {
    setBusy(true);
    try {
      const url = opt.kind === "upgrade" ? `/events/${ev.id}/upgrade` : `/events/${ev.id}/checkout`;
      const { data: r } = await api.post(url, { plan: opt.plan, origin_url: window.location.origin });
      window.location.href = r.checkout_url;
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };

  if (!data) return null;
  const { trial, days_left, events } = data;

  return (
    <div data-testid="event-plan-manager">
      <div className="space-y-2">
        {events.length === 0 && <p className="text-sm text-slate-400">Nessun evento ancora.</p>}
        {events.map((ev) => (
          <div key={ev.id} className="flex items-center justify-between gap-3 flex-wrap border border-slate-200 rounded-xl px-4 py-3 bg-white" data-testid={`plan-row-${ev.id}`}>
            <div className="min-w-0">
              <div className="font-medium text-slate-800 truncate flex items-center gap-2">{ev.nome} <StatePill ev={ev} trial={trial} days={days_left} /></div>
              <div className="text-xs text-slate-500 mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                <span>Evento: {dmy(ev.data_inizio)}</span>
                {ev.purchased && ev.snapshot && <>
                  <span>Piano: {PLABEL[ev.snapshot.plan] || PLABEL[ev.current_plan]}</span>
                  <span>Pagato: {eur(ev.snapshot.net)} + IVA</span>
                  <span>Acquisto: {ev.snapshot.purchased_at ? new Date(ev.snapshot.purchased_at).toLocaleDateString("it-IT") : "—"}</span>
                </>}
                {ev.readonly && <span className="text-red-600 inline-flex items-center gap-1"><Lock className="w-3 h-3" />Sola lettura</span>}
              </div>
            </div>
            <div className="shrink-0">
              {trial ? (
                <Button size="sm" onClick={() => setDlg(ev)} data-testid={`choose-plan-${ev.id}`} className="bg-tiffany hover:bg-tiffany-hover text-slate-900"><Sparkles className="w-4 h-4 mr-1" />Attiva un piano</Button>
              ) : ev.current_plan === "premium" && ev.purchased ? (
                <span className="text-xs text-emerald-600 font-semibold inline-flex items-center gap-1"><CheckCircle2 className="w-4 h-4" />Piano completo</span>
              ) : ev.purchased ? (
                <Button size="sm" onClick={() => setDlg(ev)} data-testid={`upgrade-plan-${ev.id}`} className="bg-slate-900 hover:bg-slate-800 text-white"><ArrowUpRight className="w-4 h-4 mr-1" />{ev.current_plan === "starter" ? "Passa a Professional o Premium" : "Passa a Premium"}</Button>
              ) : (
                <Button size="sm" onClick={() => setDlg(ev)} data-testid={`choose-plan-${ev.id}`} className="bg-tiffany hover:bg-tiffany-hover text-slate-900">Attiva piano</Button>
              )}
            </div>
          </div>
        ))}
      </div>

      <Dialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)}>
        <DialogContent className="max-w-lg" data-testid="plan-dialog">
          <DialogHeader>
            <DialogTitle>{dlg?.purchased ? "Upgrade piano" : "Scegli il piano"} · {dlg?.nome}</DialogTitle>
            <DialogDescription>{dlg?.purchased ? "Paghi solo la differenza rispetto a quanto già pagato per questo evento." : "Prezzo per singolo evento. IVA 22% esclusa. Nessun abbonamento."}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {(dlg?.options || []).map((opt) => (
              <div key={opt.plan} className={`border rounded-xl p-4 ${opt.plan === "professional" ? "border-tiffany" : "border-slate-200"}`} data-testid={`plan-opt-${opt.plan}`}>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">{PLABEL[opt.plan]}</div>
                    {opt.kind === "upgrade" ? (
                      <div className="text-xs text-slate-500 mt-1 space-y-0.5">
                        <div>{PLABEL[dlg.current_plan]} → {PLABEL[opt.plan]}</div>
                        <div>Già pagato: {eur(opt.already_paid)} + IVA</div>
                        <div className="text-slate-800 font-medium">Differenza: {eur(opt.diff)} + IVA</div>
                      </div>
                    ) : (
                      <div className="text-xs text-slate-500 mt-1">Imponibile {eur(opt.net)} · IVA {eur(opt.vat)}</div>
                    )}
                  </div>
                  <div className="text-right">
                    <div className="font-display text-xl font-bold text-slate-900">{eur(opt.kind === "upgrade" ? opt.diff * 1.22 : opt.gross)}</div>
                    <div className="text-[11px] text-slate-400">IVA incl.</div>
                  </div>
                </div>
                <Button className="w-full mt-3 bg-slate-900 hover:bg-slate-800 text-white" disabled={busy} onClick={() => go(dlg, opt)} data-testid={`pay-${opt.plan}`}>
                  <CreditCard className="w-4 h-4 mr-2" />{busy ? "Reindirizzamento..." : (opt.kind === "upgrade" ? `Paga ${eur(opt.diff * 1.22)} e passa a ${PLABEL[opt.plan]}` : `Vai al pagamento · ${PLABEL[opt.plan]}`)}
                </Button>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-slate-400 text-center">Pagamento sicuro via Stripe (TEST). Il piano si attiva solo dopo conferma server-side del pagamento.</p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
