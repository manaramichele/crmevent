import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { CalendarClock, AlertTriangle } from "lucide-react";
import { usePlans, eur } from "@/components/PlansSection";

const DESC = { bronze: "Gestione essenziale.", silver: "Gestione avanzata.", gold: "Gestione completa." };

// Stato prova letto dal backend (/saas/me): aggiornato all'apertura, al ritorno sulla scheda e ogni 15 minuti.
function useTrialState(initial) {
  const [s, setS] = useState(initial);
  const load = useCallback(() => api.get("/saas/me").then(({ data }) => setS(data)).catch(() => {}), []);
  useEffect(() => { setS(initial); }, [initial]);
  useEffect(() => {
    if (!initial?.enabled) return undefined;
    const t = setInterval(load, 15 * 60 * 1000);
    window.addEventListener("focus", load);
    return () => { clearInterval(t); window.removeEventListener("focus", load); };
  }, [initial?.enabled, load]);
  return [s, load];
}

function PlansSummary() {
  const data = usePlans();
  if (!data) return null;
  return (
    <div className="space-y-2" data-testid="trial-dialog-plans">
      {data.plans.map((p) => (
        <div key={p.key} className="flex items-center gap-3 rounded-xl border border-slate-200 px-3 py-2.5" style={{ borderLeft: `5px solid ${p.color}` }} data-testid={`trial-dialog-plan-${p.key}`}>
          <span className="font-extrabold tracking-wide w-16" style={{ color: p.color }}>{p.label}</span>
          <span className="text-sm text-slate-600 flex-1">{DESC[p.key]}</span>
          <span className="text-sm font-bold text-slate-900 whitespace-nowrap">€{eur(p.monthly).replace(",00", "")}/mese</span>
        </div>
      ))}
    </div>
  );
}

export default function TrialButton({ saas }) {
  const navigate = useNavigate();
  const [s, reload] = useTrialState(saas);
  const [open, setOpen] = useState(false);
  if (!s?.enabled) return null;
  const trial = s.mode === "trial" && !s.purchased;
  const ended = s.mode === "expired" || s.mode === "canceled" || s.mode === "suspended";
  if (!trial && !ended) return null;
  const n = s.days_left;
  const label = s.mode === "suspended" ? "Abbonamento sospeso" : ended ? "Prova terminata" : n === 1 ? "1 giorno rimasto" : `${n} giorni rimasti`;
  const short = s.mode === "suspended" ? "Sospeso" : ended ? "Terminata" : `${n} gg`;
  const tone = ended ? "bg-red-600 text-white hover:bg-red-700" : "bg-white text-[#0ABAB5] border-[1.5px] border-[#0ABAB5] hover:bg-[#0ABAB5]/10";
  const Icon = ended ? AlertTriangle : CalendarClock;
  const go = () => { setOpen(false); navigate("/profilo?tab=abbonamento"); };
  return (
    <>
      <button type="button" onClick={() => { reload(); setOpen(true); }} data-testid="trial-days-button" aria-label={`Prova gratuita: ${label}`}
        className={`shrink-0 inline-flex items-center gap-1.5 h-9 px-2.5 sm:px-3 rounded-lg text-xs sm:text-sm font-semibold transition-[background-color,transform] active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 ${tone}`}>
        <Icon className="w-4 h-4" /><span className="hidden sm:inline" data-testid="trial-days-label">{label}</span><span className="sm:hidden">{short}</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto rounded-2xl p-6" data-testid="trial-dialog">
          <div className="w-11 h-11 rounded-full bg-[#0ABAB5]/15 flex items-center justify-center"><Icon className="w-5 h-5 text-[#088F8A]" /></div>
          <DialogTitle className="font-display text-2xl font-bold text-slate-900">{ended ? "La tua prova gratuita è terminata" : "La tua prova gratuita è attiva!"}</DialogTitle>
          <DialogDescription className="text-slate-600 text-sm" data-testid="trial-dialog-text">
            {ended ? "I tuoi dati restano consultabili. Scegli il piano più adatto alla tua organizzazione per continuare a creare e modificare."
              : `Hai ancora ${n} ${n === 1 ? "giorno" : "giorni"} di prova gratuita. Durante questo periodo puoi utilizzare tutte le funzionalità di CRMEvent.`}
          </DialogDescription>
          {!ended && <p className="text-sm text-slate-500 -mt-1">Al termine della prova potrai scegliere il piano più adatto alla tua organizzazione.</p>}
          <PlansSummary />
          <button type="button" onClick={go} data-testid="trial-dialog-plans-cta" className="h-11 w-full rounded-xl bg-[#0ABAB5] text-slate-900 font-semibold transition-colors hover:bg-[#09A8A3] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900">Scopri i piani</button>
        </DialogContent>
      </Dialog>
    </>
  );
}
