import { useEffect, useState, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { HelpCircle, ArrowRight, ArrowLeft, X, ChevronRight, ListTree } from "lucide-react";

// Guida informativa (NON una checklist): spiega le funzioni di CRMEvent.
// Ogni sezione ha micro-passaggi testuali; nessuna verifica dati, nessuna mutazione.
// Rotte e nomi = quelli reali dell'interfaccia. Le funzioni interne all'evento puntano a /eventi.
const SECTIONS = [
  { key: "dashboard", label: "Dashboard", route: "/app", steps: [
    { t: "La tua Dashboard", b: "È il punto di partenza: da qui tieni sotto controllo l'evento selezionato con riepiloghi, scadenze e ciò che richiede attenzione." },
    { t: "Seleziona l'evento", b: "Usa il selettore evento in alto per cambiare il contesto: tutti i riepiloghi si aggiornano sull'evento scelto." },
  ]},
  { key: "eventi", label: "Eventi", route: "/eventi", steps: [
    { t: "Crea e gestisci gli eventi", b: "Qui crei un nuovo evento (nome, tipologia, date, logo) e gestisci quelli esistenti: in preparazione, attivo, sospeso o concluso." },
    { t: "Attivazione evento", b: "L'attivazione sblocca le funzioni operative dell'evento. Alcune attivazioni possono utilizzare crediti." },
    { t: "Duplica da edizione precedente", b: "Se disponibile, puoi partire dai dati di un'edizione precedente per risparmiare tempo." },
  ]},
  { key: "checklist", label: "Checklist Evento", route: "/eventi", steps: [
    { t: "Checklist Evento", b: "È lo strumento operativo per pianificare e controllare le attività dell'evento: la apri dalla gestione dell'evento selezionato." },
    { t: "Attività, scadenze e priorità", b: "Le voci hanno stati, scadenze e priorità; CRMEvent evidenzia ciò che è in ritardo o richiede attenzione." },
    { t: "Diversa dal Tutorial", b: "La Checklist misura il lavoro reale dell'evento; questo Tutorial invece spiega soltanto come usare la piattaforma." },
  ]},
  { key: "staff", label: "Staff / Volontari", route: "/staff-volontari", steps: [
    { t: "Aggiungi Staff e Volontari", b: "Da qui inserisci le persone che collaborano all'organizzazione dell'evento." },
    { t: "Ruolo e qualifica", b: "Indica il ruolo nell'evento e la qualifica quando serve, insieme ai recapiti." },
    { t: "Disponibilità", b: "Consulta giorni, orari e preferenze; se disponibile, puoi usare un link pubblico per raccogliere le disponibilità." },
  ]},
  { key: "aziende", label: "Aziende", route: "/aziende", steps: [
    { t: "Aziende", b: "Gestisci le aziende collegate all'evento e i relativi referenti, utili anche per Sponsor & Partner." },
  ]},
  { key: "anagrafiche", label: "Anagrafiche", route: "/persone", steps: [
    { t: "Anagrafiche", b: "L'archivio dei contatti della tua organizzazione: dati anagrafici e recapiti riutilizzabili nei vari moduli." },
  ]},
  { key: "team", label: "Team", route: "/eventi", steps: [
    { t: "Organizza i Team", b: "Dalla gestione dell'evento raggruppi le persone per area operativa (es. Partenza, Ristori, Segreteria)." },
    { t: "Referenti e composizione", b: "Assegni Staff e Volontari a ogni Team e indichi i responsabili." },
  ]},
  { key: "turni", label: "Turni", route: "/eventi", steps: [
    { t: "Organizza i Turni", b: "Definisci giorni e orari e assegni Staff, Volontari o Team ai turni dell'evento." },
    { t: "Turni scoperti", b: "CRMEvent ti aiuta a individuare i turni ancora scoperti, così da completare la copertura." },
  ]},
  { key: "attivita", label: "Attività", route: "/attivita", steps: [
    { t: "Attività", b: "Crea le cose da fare, assegna i responsabili e tieni sotto controllo scadenze, priorità e stati." },
    { t: "In ritardo e sotto controllo", b: "Le attività in ritardo vengono evidenziate e si collegano a Dashboard e Checklist Evento." },
  ]},
  { key: "sponsor", label: "Sponsor & Partner", route: "/sponsor", steps: [
    { t: "Sponsor & Partner", b: "Gestisci aziende, referenti e opportunità commerciali collegate all'evento." },
    { t: "Pipeline commerciale", b: "Segui le trattative in stile Kanban con stato, importi e follow-up." },
  ]},
  { key: "ospitalita", label: "Ospitalità & Pasti", route: "/ospitalita", steps: [
    { t: "Ospitalità", b: "Organizza strutture, pernottamenti e camere delle persone coinvolte; i dati confluiscono nel briefing." },
    { t: "Pasti", b: "Gestisci i pasti e i relativi servizi per le persone dell'evento, con le informazioni operative utili." },
  ]},
  { key: "briefing", label: "Briefing", route: "/eventi", steps: [
    { t: "Briefing operativo", b: "Dalla gestione dell'evento raccogli dati evento, Staff, Team, Turni, attività, ospitalità e pasti in un unico documento." },
    { t: "Generazione e versioni", b: "Puoi generare il briefing e gestirne le versioni/PDF da condividere con il team." },
    { t: "Crediti", b: "Alcune funzioni avanzate del briefing (es. AI) possono utilizzare crediti." },
  ]},
  { key: "mappe", label: "Mappe / GPX", route: "/eventi", steps: [
    { t: "Mappe e tracciati GPX", b: "Se attiva, puoi caricare tracciati GPX e associarli all'evento per la gestione del percorso." },
  ]},
  { key: "file", label: "File / Documenti", route: "/eventi", steps: [
    { t: "File e documenti", b: "Carichi e organizzi i documenti dell'evento per averli sempre a portata di mano e condivisibili." },
  ]},
  { key: "pipeline", label: "Pipeline Evento Pro", route: "/eventi", steps: [
    { t: "Pipeline Evento Pro", b: "Genera automaticamente un modello di attività con scadenze relative alla data dell'evento e priorità." },
    { t: "Collegamento con la Checklist", b: "Le attività generate alimentano la Checklist Evento e la sezione «Cosa richiede attenzione»." },
    { t: "Attivazione a crediti", b: "È una funzione attivabile che può utilizzare crediti; se non attiva per l'evento corrente, puoi comunque attivarla quando vuoi." },
  ]},
];
const SECTION_MAP = Object.fromEntries(SECTIONS.map((s) => [s.key, s]));

const refreshAll = () => window.dispatchEvent(new Event("onboarding:refresh"));
const openIndex = () => window.dispatchEvent(new Event("tutorial:open-index"));

function useTutorial() {
  const { user } = useAuth();
  const [info, setInfo] = useState(null);
  const isSuper = user?.role === "superadmin";
  const load = useCallback(async () => {
    if (isSuper) { setInfo({ superadmin: true }); return; }
    try { const { data } = await api.get("/onboarding/status"); setInfo(data); } catch {}
  }, [isSuper]);
  useEffect(() => {
    load();
    const h = () => load();
    window.addEventListener("onboarding:refresh", h);
    return () => window.removeEventListener("onboarding:refresh", h);
  }, [load]);
  const patch = useCallback(async (body) => {
    try { await api.post("/onboarding/state", body); } catch {}
    refreshAll();
  }, []);
  return { info, patch, isSuper };
}

// ---- Header button + welcome + index drawer ----
export function TutorialLauncher() {
  const { info, patch, isSuper } = useTutorial();
  const [open, setOpen] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const h = () => setOpen(true);
    window.addEventListener("tutorial:open-index", h);
    return () => window.removeEventListener("tutorial:open-index", h);
  }, []);
  useEffect(() => {
    if (!info || info.superadmin) return;
    const st = info.state || {};
    if (!st.seen) { setWelcome(true); patch({ seen: true }); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info?.state?.seen, info?.superadmin]);

  if (!info || info.superadmin || isSuper) return null;

  const goSection = (s) => {
    setOpen(false);
    navigate(`${s.route}?tutorial=${s.key}&tstep=0`);
  };

  return (
    <>
      <button data-testid="tutorial-button" onClick={() => setOpen(true)} title="Tutorial"
        className="h-10 px-3 rounded-lg hover:bg-tiffany-light text-slate-600 hover:text-tiffany-fg flex items-center gap-1.5 transition-colors">
        <HelpCircle className="w-5 h-5" />
        <span className="hidden md:block text-sm font-medium">Tutorial</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-[60]" data-testid="tutorial-index">
          <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={() => setOpen(false)} />
          <aside className="absolute right-0 top-0 h-[100dvh] w-full sm:w-[400px] bg-white shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
            <div className="px-5 pt-5 pb-4 border-b border-slate-100 flex items-start justify-between">
              <div>
                <div className="font-display text-lg font-bold text-slate-900">Scopri CRMEvent</div>
                <div className="text-sm text-slate-500 mt-0.5">Scopri come utilizzare CRMEvent e tutte le funzioni disponibili per organizzare e gestire i tuoi eventi.</div>
              </div>
              <button onClick={() => setOpen(false)} data-testid="tutorial-index-close" className="w-9 h-9 rounded-lg hover:bg-slate-100 flex items-center justify-center shrink-0"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-3 overflow-y-auto flex-1">
              {SECTIONS.map((s) => (
                <button key={s.key} onClick={() => goSection(s)} data-testid={`tutorial-section-${s.key}`}
                  className="w-full text-left px-3 py-3 rounded-lg hover:bg-tiffany-light flex items-center justify-between group">
                  <span className="text-sm font-medium text-slate-800">{s.label}</span>
                  <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-tiffany-active" />
                </button>
              ))}
            </div>
          </aside>
        </div>
      )}

      <Dialog open={welcome} onOpenChange={(o) => { if (!o) setWelcome(false); }}>
        <DialogContent data-testid="onboarding-welcome">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl">Benvenuto in CRMEvent 👋</DialogTitle>
            <DialogDescription className="text-base text-slate-600 pt-1">
              Vuoi scoprire come organizzare il tuo evento con CRMEvent? Ti mostriamo rapidamente le principali funzioni della piattaforma.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-2">
            <button onClick={() => { patch({ later: true }); setWelcome(false); }} data-testid="onboarding-later"
              className="px-4 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100">Lo farò più tardi</button>
            <button onClick={() => { setWelcome(false); setOpen(true); }} data-testid="onboarding-start"
              className="px-4 py-2.5 rounded-lg text-sm font-semibold bg-tiffany text-white hover:bg-tiffany-hover">Inizia il tutorial</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ---- Contextual guide card (reads ?tutorial=key&tstep=n). Non-blocking. ----
export function TutorialHint() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const key = params.get("tutorial");
  const tstep = parseInt(params.get("tstep") || "0", 10);
  const section = key ? SECTION_MAP[key] : null;

  const setStep = (n) => {
    const p = new URLSearchParams(location.search);
    p.set("tutorial", key); p.set("tstep", String(n));
    navigate(`${location.pathname}?${p}`, { replace: true });
  };
  const close = () => {
    const p = new URLSearchParams(location.search);
    p.delete("tutorial"); p.delete("tstep");
    navigate(`${location.pathname}${p.toString() ? `?${p}` : ""}`, { replace: true });
  };

  if (!section || user?.role === "superadmin") return null;
  const steps = section.steps;
  const idx = Math.min(Math.max(tstep, 0), steps.length - 1);
  const step = steps[idx];
  const isFirst = idx === 0;
  const isLast = idx === steps.length - 1;

  return (
    <div className="fixed z-[55] left-1/2 -translate-x-1/2 bottom-4 w-[calc(100%-2rem)] max-w-md" data-testid="tutorial-hint">
      <div className="rounded-xl bg-white border border-tiffany-border shadow-2xl p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-tiffany-active">{section.label} · {idx + 1}/{steps.length}</div>
            <div className="text-sm font-bold text-slate-900 mt-0.5">{step.t}</div>
          </div>
          <button onClick={close} data-testid="tutorial-hint-close" className="shrink-0 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
        </div>
        <p className="text-sm text-slate-600 mt-1.5 leading-relaxed">{step.b}</p>
        <div className="mt-3 flex items-center justify-between">
          <button onClick={openIndex} data-testid="tutorial-hint-index" className="text-xs text-slate-500 hover:text-slate-700 inline-flex items-center gap-1">
            <ListTree className="w-3.5 h-3.5" /> Torna all'indice
          </button>
          <div className="flex items-center gap-2">
            <button onClick={() => setStep(idx - 1)} disabled={isFirst} data-testid="tutorial-hint-prev"
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-40 inline-flex items-center gap-1"><ArrowLeft className="w-3.5 h-3.5" /> Indietro</button>
            {isLast
              ? <button onClick={close} data-testid="tutorial-hint-finish" className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-tiffany text-white hover:bg-tiffany-hover">Ho capito</button>
              : <button onClick={() => setStep(idx + 1)} data-testid="tutorial-hint-next" className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-tiffany text-white hover:bg-tiffany-hover inline-flex items-center gap-1">Avanti <ArrowRight className="w-3.5 h-3.5" /></button>}
          </div>
        </div>
      </div>
    </div>
  );
}
