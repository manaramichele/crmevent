import { useEffect, useState, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { HelpCircle, CheckCircle2, Circle, ArrowRight, X, Rocket, MinusCircle } from "lucide-react";

const STEP_TEXT = {
  event: { title: "Crea il tuo primo evento", desc: "Partiamo dalle informazioni principali: nome, data, luogo e dettagli dell'evento.", cta: "Crea evento" },
  people: { title: "Aggiungi staff e volontari", desc: "Inserisci le persone coinvolte: potrai assegnare ruoli, qualifiche e informazioni utili.", cta: "Vai a Persone" },
  team: { title: "Crea il tuo primo team", desc: "Raggruppa le persone per area operativa e assegna i responsabili (Partenza, Ristori, Segreteria…).", cta: "Vai a Team" },
  shifts: { title: "Organizza i turni", desc: "Definisci quando servono le persone e assegna lo staff. CRMEvent evidenzia i turni scoperti.", cta: "Vai ai Turni" },
  activities: { title: "Inserisci le attività", desc: "Crea le cose da fare, assegna i responsabili e tieni sotto controllo le scadenze.", cta: "Vai alle Attività" },
  briefing: { title: "Prepara il briefing", desc: "Raccogli le informazioni operative e genera il briefing da condividere con il team.", cta: "Vai al Briefing" },
  sponsor: { title: "Gestisci Sponsor e Partner", desc: "Gestisci aziende, contatti, trattative e attività commerciali collegate all'evento.", cta: "Vai a Sponsor & Partner" },
  hospitality: { title: "Devi gestire ospitalità o pasti?", desc: "Organizza strutture, camere, pernottamenti e pasti delle persone coinvolte.", cta: "Configura ospitalità e pasti" },
};

// ---- shared lightweight store ----
const refreshAll = () => window.dispatchEvent(new Event("onboarding:refresh"));

export function useOnboarding(eventId) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const isSuper = user?.role === "superadmin";
  const load = useCallback(async () => {
    if (isSuper) { setData({ superadmin: true, show: false }); return; }
    try {
      const params = (eventId && eventId !== "all") ? { event_id: eventId } : {};
      const { data } = await api.get("/onboarding/status", { params });
      setData(data);
    } catch {}
  }, [isSuper, eventId]);
  useEffect(() => {
    load();
    const h = () => load();
    window.addEventListener("onboarding:refresh", h);
    window.addEventListener("focus", h);
    return () => { window.removeEventListener("onboarding:refresh", h); window.removeEventListener("focus", h); };
  }, [load]);
  const patch = useCallback(async (body) => {
    try { await api.post("/onboarding/state", body); } catch {}
    refreshAll();
  }, []);
  return { data, reload: load, patch };
}

function ProgressBar({ done, total }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden" data-testid="onboarding-progress">
      <div className="h-full rounded-full bg-tiffany transition-all duration-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

function StepRow({ s, onGo, onSkip }) {
  const t = STEP_TEXT[s.key] || { title: s.label };
  return (
    <div className="flex items-start gap-3 py-2.5" data-testid={`onboarding-step-${s.key}`}>
      {s.completed
        ? <CheckCircle2 className="w-5 h-5 text-tiffany-active shrink-0 mt-0.5" />
        : s.skipped
          ? <MinusCircle className="w-5 h-5 text-slate-300 shrink-0 mt-0.5" />
          : <Circle className="w-5 h-5 text-slate-300 shrink-0 mt-0.5" />}
      <div className="min-w-0 flex-1">
        <div className={`text-sm font-medium ${s.completed ? "text-slate-400 line-through" : "text-slate-800"}`}>{t.title}</div>
        {!s.completed && !s.skipped && (
          <div className="mt-1 flex items-center gap-3">
            <button onClick={() => onGo(s)} data-testid={`onboarding-go-${s.key}`}
              className="text-xs font-semibold text-tiffany-active hover:underline inline-flex items-center gap-1">
              {t.cta} <ArrowRight className="w-3 h-3" />
            </button>
            {s.optional && (
              <button onClick={() => onSkip(s)} data-testid={`onboarding-skip-${s.key}`}
                className="text-xs text-slate-400 hover:text-slate-600">Non mi serve</button>
            )}
          </div>
        )}
        {s.skipped && <span className="text-xs text-slate-400">Saltato</span>}
      </div>
    </div>
  );
}

// ---- side panel (desktop right / mobile full) ----
export function TutorialPanel({ open, onClose }) {
  const { data, patch } = useOnboarding();
  const navigate = useNavigate();
  if (!open || !data || data.superadmin) return null;
  const go = (s) => { onClose(); navigate(`${s.route}?tutorial=${s.key}`); };
  const skip = (s) => patch({ skip: s.key });

  return (
    <div className="fixed inset-0 z-[60]" data-testid="tutorial-panel">
      <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={onClose} data-testid="tutorial-panel-overlay" />
      <aside className="absolute right-0 top-0 h-[100dvh] w-full sm:w-[400px] bg-white shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
        <div className="h-16 flex items-center justify-between px-5 border-b border-slate-100">
          <div className="font-display font-bold text-slate-900">Configura il tuo evento</div>
          <button onClick={onClose} data-testid="tutorial-panel-close" className="w-9 h-9 rounded-lg hover:bg-slate-100 flex items-center justify-center"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 overflow-y-auto flex-1">
          {data.returning_user && (
            <div className="mb-4 text-xs text-slate-500 bg-slate-50 rounded-lg p-3" data-testid="tutorial-returning-note">
              Checklist dell'evento attivo{data.event_name ? `: ${data.event_name}` : ""}.
            </div>
          )}
          <div className="text-sm text-slate-500 mb-1">{data.main_done} di {data.main_total} passaggi completati</div>
          <ProgressBar done={data.main_done} total={data.main_total} />
          <div className="mt-4 divide-y divide-slate-100">
            {(data.steps || []).map((s) => <StepRow key={s.key} s={s} onGo={go} onSkip={skip} />)}
          </div>
          {(data.optional || []).length > 0 && (
            <>
              <div className="mt-5 mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Funzioni opzionali</div>
              <div className="divide-y divide-slate-100">
                {data.optional.map((s) => <StepRow key={s.key} s={s} onGo={go} onSkip={skip} />)}
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

// ---- header button + welcome + completion, self-contained ----
export function TutorialLauncher() {
  const { data, patch } = useOnboarding();
  const [open, setOpen] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!data || data.superadmin) return;
    const st = data.state || {};
    if (!st.seen && !data.returning_user && !data.all_main_completed) setWelcome(true);
    // mark 'seen' once auto-welcome has had a chance to show (returning users too)
    if (!st.seen) patch({ seen: true });
    if (data.all_main_completed && !st.completed) { setDone(true); patch({ completed: true }); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.state?.seen, data?.all_main_completed, data?.superadmin, data?.returning_user]);

  if (!data || data.superadmin) return null;

  return (
    <>
      <button data-testid="tutorial-button" onClick={() => setOpen(true)} title="Tutorial"
        className="relative h-10 px-3 rounded-lg hover:bg-tiffany-light text-slate-600 hover:text-tiffany-fg flex items-center gap-1.5 transition-colors">
        <HelpCircle className="w-5 h-5" />
        <span className="hidden md:block text-sm font-medium">Tutorial</span>
        {!data.all_main_completed && <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-tiffany ring-2 ring-white" />}
      </button>

      <TutorialPanel open={open} onClose={() => setOpen(false)} />

      <Dialog open={welcome} onOpenChange={(o) => { if (!o) setWelcome(false); }}>
        <DialogContent data-testid="onboarding-welcome">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl">Benvenuto in CRMEvent 👋</DialogTitle>
            <DialogDescription className="text-base text-slate-600 pt-1">
              CRMEvent ti aiuta a organizzare persone, attività e informazioni del tuo evento in un unico posto.
              Ti guidiamo nella configurazione del tuo primo evento, passo dopo passo.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-2">
            <button onClick={() => { setWelcome(false); }} data-testid="onboarding-later"
              className="px-4 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100">Lo farò più tardi</button>
            <button onClick={() => { patch({ started: true }); setWelcome(false); setOpen(true); }} data-testid="onboarding-start"
              className="px-4 py-2.5 rounded-lg text-sm font-semibold bg-tiffany text-white hover:bg-tiffany-hover">Inizia il tutorial</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={done} onOpenChange={(o) => { if (!o) setDone(false); }}>
        <DialogContent data-testid="onboarding-complete">
          <DialogHeader>
            <div className="mx-auto w-14 h-14 rounded-2xl bg-tiffany-light flex items-center justify-center mb-2"><Rocket className="w-7 h-7 text-tiffany-active" /></div>
            <DialogTitle className="font-display text-2xl text-center">Il tuo evento è pronto 🚀</DialogTitle>
            <DialogDescription className="text-base text-slate-600 text-center pt-1">
              Hai configurato le funzioni principali di CRMEvent. Ora puoi continuare a organizzare il tuo evento e aggiungere tutti i dettagli che ti servono.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <button onClick={() => setDone(false)} data-testid="onboarding-complete-cta"
              className="w-full px-4 py-2.5 rounded-lg text-sm font-semibold bg-tiffany text-white hover:bg-tiffany-hover">Vai alla Dashboard</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---- dashboard card ----
export function OnboardingCard({ eventId }) {
  const { data, patch } = useOnboarding(eventId);
  const navigate = useNavigate();
  if (!data || data.superadmin || data.all_main_completed) return null;
  if (data.state?.card_hidden) return null;
  const next = data.next_step;
  return (
    <div className="bg-white border border-tiffany-border rounded-xl shadow-sm p-5 mb-6" data-testid="onboarding-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-display font-bold text-slate-900">Configura il tuo evento</div>
          <div className="text-sm text-slate-500 mt-0.5">{data.main_done} di {data.main_total} passaggi completati</div>
        </div>
        <button onClick={() => patch({ card_hidden: true })} data-testid="onboarding-card-hide"
          className="text-xs text-slate-400 hover:text-slate-600 shrink-0">Nascondi dalla Dashboard</button>
      </div>
      <div className="mt-3"><ProgressBar done={data.main_done} total={data.main_total} /></div>
      {next && <div className="mt-3 text-sm text-slate-600">Prossimo passaggio: <span className="font-semibold text-slate-800">{(STEP_TEXT[next.key] || {}).title || next.label}</span></div>}
      {next && (
        <button onClick={() => navigate(`${next.route}?tutorial=${next.key}`)} data-testid="onboarding-card-continue"
          className="mt-4 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-tiffany text-white hover:bg-tiffany-hover">
          Continua configurazione <ArrowRight className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}

// ---- contextual hint (non invasive top banner when arriving via tutorial) ----
export function TutorialHint() {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const params = new URLSearchParams(location.search);
  const step = params.get("tutorial");
  const [closed, setClosed] = useState(false);
  useEffect(() => { setClosed(false); }, [step]);
  if (!step || closed || user?.role === "superadmin") return null;
  const t = STEP_TEXT[step];
  if (!t) return null;
  return (
    <div className="mx-4 lg:mx-8 mt-4 rounded-lg bg-tiffany-light border border-tiffany-border px-4 py-3 flex items-start gap-3" data-testid="tutorial-hint">
      <span className="mt-0.5 shrink-0 inline-flex items-center justify-center w-6 h-6 rounded-full bg-tiffany text-white text-xs font-bold">1</span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-tiffany-fg">Inizia da qui</div>
        <div className="text-sm text-slate-600">{t.cta} per completare: <span className="font-medium">{t.title}</span></div>
      </div>
      <button onClick={() => { setClosed(true); const p = new URLSearchParams(location.search); p.delete("tutorial"); navigate(`${location.pathname}${p.toString() ? `?${p}` : ""}`, { replace: true }); }}
        data-testid="tutorial-hint-close" className="shrink-0 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
    </div>
  );
}
