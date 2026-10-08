import { useEffect, useState, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { HelpCircle, ArrowRight, ArrowLeft, X, ChevronRight, ListTree, CalendarDays, Info } from "lucide-react";

// Guida informativa read-only: spiega le funzioni ed evidenzia gli elementi reali. Nessuna mutazione dati.
const T = (id) => `[data-testid="${id}"]`;
const P = (prefix) => `[data-testid^="${prefix}"]`;

const SECTIONS = [
  { key: "dashboard", label: "Dashboard", route: () => "/app", steps: [
    { t: "La tua Dashboard", b: "È il punto di partenza: riepiloghi di eventi, contatti, trattative, Staff / Volontari e scadenze.", s: [T("kpi-eventi-attivi")] },
    { t: "Filtra per evento", b: "Con questo selettore scegli l'evento da analizzare: tutti i riepiloghi si aggiornano sull'evento scelto.", s: [T("dashboard-event-filter")] },
    { t: "To Do List", b: "Qui trovi le attività in ritardo o critiche della Checklist Evento e i turni ancora scoperti.", s: [T("dashboard-attention"), T("kpi-turni-scoperti")] },
  ]},
  { key: "eventi", label: "Eventi", route: () => "/eventi", steps: [
    { t: "Crea e gestisci gli eventi", b: "Con «Aggiungi» crei un nuovo evento (nome, tipologia, date, logo); dall'elenco gestisci quelli esistenti.", s: [T("add-event-button")] },
    { t: "Stato dell'evento", b: "La colonna «Fase» mostra se l'evento è pianificato, in corso, concluso o annullato. Con l'abbonamento ogni evento è subito operativo, senza attivazioni.", s: (e) => [T(`event-credit-badge-${e}`), P("event-credit-badge-")] },
    { t: "Raccolta disponibilità", b: "Da «Disponibilità» puoi preparare un link pubblico per raccogliere giorni e orari di Staff / Volontari.", s: (e) => [T(`availability-${e}`), T(`actions-menu-${e}`), P("availability-"), P("actions-menu-")] },
    { t: "Altre azioni dell'evento", b: "Da qui accedi anche a Briefing, Pipeline, Percorsi, Calendario, modifica ed eliminazione dell'evento.", s: (e) => [T(`more-actions-${e}`), T(`actions-menu-${e}`), P("more-actions-"), P("actions-menu-")] },
  ]},
  { key: "checklist", label: "Checklist Evento", ev: true, route: (e) => `/eventi/${e}/pipeline`, steps: [
    { t: "Checklist Evento", b: "È lo strumento operativo dell'evento: l'elenco delle attività da svolgere con la percentuale di completamento. Si trova nella Pipeline dell'evento.", s: [T("pipeline-dashboard"), T("pipeline-intro"), T("pipeline-template-chooser")] },
    { t: "Stati, scadenze e priorità", b: "Ogni voce ha stato, scadenza e priorità; puoi filtrarle e CRMEvent evidenzia quelle in ritardo.", s: [T("filter-stato"), T("pipeline-tasks-table"), T("pipeline-intro"), T("pipeline-template-chooser")] },
    { t: "Diversa dal Tutorial", b: "La Checklist misura il lavoro reale dell'evento; questo Tutorial spiega soltanto come usare la piattaforma e non ha avanzamento.", s: [T("pipeline-percent"), T("pipeline-intro"), T("pipeline-template-chooser")] },
  ]},
  { key: "staff", label: "Staff / Volontari", route: () => "/staff-volontari", steps: [
    { t: "Aggiungi Staff e Volontari", b: "Da qui inserisci Staff e Volontari che collaborano all'evento, con ruolo, qualifica e recapiti.", s: [T("add-person-button")] },
    { t: "Staff e Volontari", b: "Le schede separano Staff e Volontari; puoi filtrare per evento e cercare per nome.", s: [T("tab-staff")] },
    { t: "Da classificare", b: "Qui trovi chi non ha ancora un ruolo nell'evento (es. arrivato dal link disponibilità) e va classificato.", s: [T("tab-da-classificare")] },
  ]},
  { key: "team", label: "Team", route: () => "/staff-volontari", steps: [
    { t: "Organizza i Team", b: "Nella scheda Team raggruppi Staff / Volontari per area operativa (es. Partenza, Ristori, Segreteria).", s: [T("tab-team")] },
    { t: "Team Leader e componenti", b: "Per ogni Team indichi il Team Leader e assegni i componenti dell'evento.", s: [T("tab-team")] },
  ]},
  { key: "turni", label: "Turni", route: () => "/staff-volontari", steps: [
    { t: "Organizza i Turni", b: "Nella scheda Turni definisci giorni, orari, luogo e punto di ritrovo, assegnando Staff / Volontari o Team.", s: [T("tab-turni")] },
    { t: "Turni scoperti", b: "Un turno senza persona assegnata risulta scoperto ed è segnalato anche in Dashboard.", s: [T("tab-turni")] },
  ]},
  { key: "aziende", label: "Aziende", route: () => "/aziende", steps: [
    { t: "Aziende", b: "Gestisci le aziende collegate ai tuoi eventi e i relativi referenti, utili anche per Sponsor & Partner.", s: [T("add-company-button")] },
    { t: "Ricerca", b: "Trova rapidamente un'azienda per nome o dati di contatto.", s: [T("search-company-input")] },
  ]},
  { key: "anagrafiche", label: "Anagrafiche", route: () => "/persone", steps: [
    { t: "Anagrafiche", b: "L'archivio dei referenti e contatti della tua organizzazione, riutilizzabili nei vari moduli.", s: [T("add-person-button")] },
  ]},
  { key: "attivita", label: "Attività", route: () => "/attivita", steps: [
    { t: "Attività", b: "Crea le cose da fare, assegna i responsabili e tieni sotto controllo scadenze, priorità e stati.", s: [T("add-activity-button")] },
    { t: "Cerca e filtra", b: "Ritrova le attività per titolo o tipo.", s: [T("search-activity-input")] },
  ]},
  { key: "followup", label: "Follow-up", route: () => "/followup", steps: [
    { t: "Follow-up", b: "Pianifica i ricontatti (telefonate, email, appuntamenti) per non perdere nessuna opportunità.", s: [T("add-followup-button")] },
  ]},
  { key: "sponsor", label: "Sponsor & Partner", route: () => "/sponsor", steps: [
    { t: "Sponsor & Partner", b: "Gestisci le trattative commerciali con aziende e referenti collegate all'evento.", s: [T("add-deal-button")] },
    { t: "Filtra per evento", b: "Visualizza solo le trattative dell'evento che ti interessa, con stato, importi e follow-up.", s: [T("sponsor-event-filter")] },
  ]},
  { key: "ospitalita", label: "Ospitalità & Pasti", route: () => "/ospitalita", steps: [
    { t: "Seleziona l'evento", b: "Ospitalità e pasti si gestiscono per evento: scegli qui l'evento di riferimento.", s: [T("hosp-event-select")] },
    { t: "Strutture e pernottamenti", b: "Registra strutture, camere e pernottamenti di Staff / Volontari; i dati confluiscono nel Briefing.", s: [T("open-structures"), T("hosp-event-select")] },
    { t: "Pasti e assegnazioni", b: "Assegna pasti e servizi a più persone insieme e consulta il riepilogo per persona, giorno o struttura.", s: [T("open-bulk-assign"), T("view-persona"), T("hosp-event-select")] },
  ]},
  { key: "briefing", label: "Briefing", ev: true, route: (e) => `/eventi/${e}/briefing`, steps: [
    { t: "Briefing operativo", b: "Raccoglie dati evento, Staff / Volontari, Team, Turni, mappe, ospitalità e pasti in un unico documento.", s: [T("briefing-cover")] },
    { t: "Completezza", b: "L'indicatore mostra quali informazioni mancano per un briefing completo.", s: [T("briefing-completeness")] },
    { t: "Versioni, PDF e presentazione", b: "Puoi pubblicare versioni, scaricare il PDF o mostrarlo in modalità presentazione al team.", s: [T("briefing-publish-btn"), T("briefing-pdf-btn")] },
  ]},
  { key: "mappe", label: "Mappe / GPX", ev: true, route: () => "/eventi", steps: [
    { t: "Mappe e percorsi", b: "Dal pulsante «Percorsi» dell'evento carichi tracciati GPX, link Google Maps e descrizioni dei percorsi.", s: (e) => [T(`maps-${e}`), T(`actions-menu-${e}`)] },
  ]},
  { key: "pipeline", label: "Pipeline Evento Pro", ev: true, route: (e) => `/eventi/${e}/pipeline`, steps: [
    { t: "Pipeline Evento Pro", b: "Genera da un modello le attività dell'evento con scadenze relative alla data dell'evento e priorità.", s: [T("pipeline-intro"), T("pipeline-template-chooser"), T("pipeline-dashboard")] },
    { t: "Attivazione a crediti", b: "È una funzione attivabile che può utilizzare crediti. Se non è attiva per l'evento selezionato, la attivi solo quando vuoi tu.", s: [T("pipeline-activate-cta"), T("pipeline-create-cta"), T("pipeline-actions-menu")] },
    { t: "Da un'edizione precedente", b: "Puoi anche creare la Pipeline partendo da un'edizione precedente dell'evento.", s: [T("pipeline-dup-intro"), T("pipeline-actions-menu"), T("pipeline-template-chooser")] },
  ]},
];
const SECTION_MAP = Object.fromEntries(SECTIONS.map((s) => [s.key, s]));
const EV_KEY = "crm_tutorial_event";

const refreshAll = () => window.dispatchEvent(new Event("onboarding:refresh"));
const openIndex = () => window.dispatchEvent(new Event("tutorial:open-index"));
const pickEvent = (events) => {
  const saved = localStorage.getItem(EV_KEY);
  return (events || []).find((e) => e.id === saved)?.id || events?.[0]?.id || null;
};
const withQuery = (route, q) => `${route}${route.includes("?") ? "&" : "?"}${q}`;
const sectionUrl = (s, eid, n = 0) => withQuery(s.ev && !eid ? "/eventi" : s.route(eid), `tutorial=${s.key}&tstep=${n}`);

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
    window.addEventListener("onboarding:refresh", load);
    return () => window.removeEventListener("onboarding:refresh", load);
  }, [load]);
  const patch = useCallback(async (body) => {
    try { await api.post("/onboarding/state", body); } catch {}
  }, []);
  return { info, patch, isSuper };
}

function EventPicker({ events, value, onChange, testid }) {
  if (!events || events.length < 2) return null;
  return (
    <label className="flex items-center gap-2 text-xs text-slate-500">
      <CalendarDays className="w-3.5 h-3.5 shrink-0" />
      <select value={value || ""} onChange={(e) => onChange(e.target.value)} data-testid={testid}
        className="flex-1 min-w-0 h-8 rounded-md border border-slate-200 bg-white px-2 text-xs text-slate-700">
        {events.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
      </select>
    </label>
  );
}

// ---- Header button + welcome + index drawer ----
export function TutorialLauncher() {
  const { user } = useAuth();
  const { info, patch, isSuper } = useTutorial();
  const [open, setOpen] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const [eid, setEid] = useState(null);
  const navigate = useNavigate();
  const events = info?.events || [];

  useEffect(() => {
    const h = () => { refreshAll(); setOpen(true); };
    window.addEventListener("tutorial:open-index", h);
    return () => window.removeEventListener("tutorial:open-index", h);
  }, []);
  useEffect(() => { if (info?.events) setEid(pickEvent(info.events)); }, [info?.events]);
  useEffect(() => {
    if (!info || info.superadmin) return;
    if (user?.welcome_demo) return; // nuovi organizzatori: unico benvenuto = WelcomeDemo; tutorial dal pulsante "Tutorial"
    if (!info.state?.seen) { setWelcome(true); patch({ seen: true }); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info?.state?.seen, info?.superadmin, user?.welcome_demo]);

  if (!info || info.superadmin || isSuper) return null;

  const chooseEvent = (id) => { localStorage.setItem(EV_KEY, id); setEid(id); };
  const goSection = (s) => { setOpen(false); navigate(sectionUrl(s, eid)); };

  return (
    <>
      <button data-testid="tutorial-button" onClick={() => { refreshAll(); setOpen(true); }} title="Tutorial"
        className="h-10 px-3 rounded-lg hover:bg-tiffany-light text-slate-600 hover:text-tiffany-fg flex items-center gap-1.5 transition-colors">
        <HelpCircle className="w-5 h-5" />
        <span className="hidden md:block text-sm font-medium">Tutorial</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-[60]" data-testid="tutorial-index">
          <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm" onClick={() => setOpen(false)} data-testid="tutorial-index-overlay" />
          <aside className="absolute right-0 top-0 h-[100dvh] w-full sm:w-[400px] bg-white shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
            <div className="px-5 pt-5 pb-4 border-b border-slate-100 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-display text-lg font-bold text-slate-900">Scopri CRMEvent</div>
                  <div className="text-sm text-slate-500 mt-0.5">Scopri come utilizzare CRMEvent e tutte le funzioni disponibili per organizzare e gestire i tuoi eventi.</div>
                </div>
                <button onClick={() => setOpen(false)} data-testid="tutorial-index-close" className="w-9 h-9 rounded-lg hover:bg-slate-100 flex items-center justify-center shrink-0"><X className="w-5 h-5" /></button>
              </div>
              {events.length === 0 ? (
                <div className="text-xs rounded-lg bg-amber-50 border border-amber-200 text-amber-800 px-3 py-2" data-testid="tutorial-index-noevent">
                  Non hai ancora creato eventi: le sezioni contrassegnate richiedono un evento e ti mostreranno come crearlo.
                </div>
              ) : (
                <div className="space-y-1">
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Evento di riferimento</div>
                  {events.length === 1
                    ? <div className="text-sm text-slate-700" data-testid="tutorial-index-event-name">{events[0].nome}</div>
                    : <EventPicker events={events} value={eid} onChange={chooseEvent} testid="tutorial-index-event-select" />}
                </div>
              )}
            </div>
            <div className="p-3 overflow-y-auto flex-1">
              {SECTIONS.map((s) => (
                <button key={s.key} onClick={() => goSection(s)} data-testid={`tutorial-section-${s.key}`}
                  className="w-full text-left px-3 py-3 rounded-lg hover:bg-tiffany-light flex items-center justify-between group">
                  <span className="text-sm font-medium text-slate-800">{s.label}</span>
                  <span className="flex items-center gap-2">
                    {s.ev && events.length === 0 && <span className="text-[10px] text-amber-700">richiede un evento</span>}
                    <ChevronRight className="w-4 h-4 text-slate-300 group-hover:text-tiffany-active" />
                  </span>
                </button>
              ))}
            </div>
          </aside>
        </div>
      )}

      <Dialog open={welcome} onOpenChange={(o) => { if (!o) setWelcome(false); }}>
        <DialogContent data-testid="onboarding-welcome">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl">Benvenuto in CRMEvent</DialogTitle>
            <DialogDescription className="text-base text-slate-600 pt-1">
              Vuoi scoprire come organizzare il tuo evento con CRMEvent? Ti mostriamo rapidamente le principali funzioni della piattaforma. Puoi riaprire la guida in qualsiasi momento dal pulsante «Tutorial».
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

// ---- Highlight ring on the real UI element (pointer-events: none, non-blocking) ----
function useSpotlight(sels, stepKey) {
  const [rect, setRect] = useState(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setRect(null); setReady(false);
    let scrolled = false;
    const find = () => {
      for (const q of sels) for (const el of document.querySelectorAll(q)) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
      return null;
    };
    const tick = () => {
      const el = find();
      if (!el) { setRect(null); return; }
      if (!scrolled) { el.scrollIntoView({ block: "center", behavior: "smooth" }); scrolled = true; }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top - 6, left: r.left - 6, width: r.width + 12, height: r.height + 12 });
    };
    tick();
    const iv = setInterval(tick, 300);
    const to = setTimeout(() => setReady(true), 1500);
    return () => { clearInterval(iv); clearTimeout(to); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepKey]);
  return { rect, missing: ready && !rect };
}

// ---- Contextual guide card (reads ?tutorial=key&tstep=n). Non-blocking. ----
export function TutorialHint() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const key = params.get("tutorial");
  const section = key ? SECTION_MAP[key] : null;
  const [events, setEvents] = useState(null);
  const isSuper = user?.role === "superadmin";

  useEffect(() => {
    if (!section || isSuper || events) return;
    api.get("/onboarding/status").then(({ data }) => setEvents(data.events || [])).catch(() => setEvents([]));
  }, [section, isSuper, events]);

  const eid = events ? pickEvent(events) : null;
  const steps = section?.steps || [];
  const idx = Math.min(Math.max(parseInt(params.get("tstep") || "0", 10) || 0, 0), Math.max(steps.length - 1, 0));
  const step = steps[idx];
  const noEvent = !!section?.ev && events !== null && !eid;
  const sels = !step ? [] : noEvent ? [`[data-testid="add-event-button"]`] : (typeof step.s === "function" ? step.s(eid) : step.s);
  const { rect, missing } = useSpotlight(sels, `${key}-${idx}-${eid}-${noEvent}-${location.pathname}`);

  if (!section || isSuper || !step) return null;

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
  const changeEvent = (id) => {
    localStorage.setItem(EV_KEY, id);
    navigate(sectionUrl(section, id, idx), { replace: true });
  };
  const isFirst = idx === 0;
  const isLast = idx === steps.length - 1;

  return (
    <>
      {rect && (
        <div data-testid="tutorial-highlight" aria-hidden
          className="fixed z-[54] pointer-events-none rounded-xl ring-4 ring-tiffany/70 shadow-[0_0_0_9999px_rgba(15,23,42,0.18)] transition-[top,left,width,height] duration-300"
          style={rect} />
      )}
      <div className="fixed z-[55] left-1/2 -translate-x-1/2 bottom-4 w-[calc(100%-2rem)] max-w-md" data-testid="tutorial-hint">
        <div className="rounded-xl bg-white border border-tiffany-border shadow-2xl p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-tiffany-active" data-testid="tutorial-hint-progress">{section.label} · {idx + 1}/{steps.length}</div>
              <div className="text-sm font-bold text-slate-900 mt-0.5" data-testid="tutorial-hint-title">{step.t}</div>
            </div>
            <button onClick={close} data-testid="tutorial-hint-close" title="Chiudi tutorial" className="shrink-0 text-slate-400 hover:text-slate-600"><X className="w-4 h-4" /></button>
          </div>
          <p className="text-sm text-slate-600 mt-1.5 leading-relaxed" data-testid="tutorial-hint-body">{step.b}</p>
          {noEvent && (
            <div className="mt-2 text-xs rounded-lg bg-amber-50 border border-amber-200 text-amber-800 px-3 py-2" data-testid="tutorial-hint-noevent">
              Questa funzione si usa all'interno di un evento. Non hai ancora creato eventi: puoi crearne uno con «Aggiungi» quando vuoi.
            </div>
          )}
          {missing && !noEvent && (
            <div className="mt-2 text-xs text-slate-500 flex items-start gap-1.5" data-testid="tutorial-hint-notfound">
              <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" />Questo elemento non è ancora visibile per l'evento selezionato (funzione non attiva o nessun dato): puoi proseguire comunque.
            </div>
          )}
          {section.ev && !noEvent && <div className="mt-2"><EventPicker events={events} value={eid} onChange={changeEvent} testid="tutorial-hint-event-select" /></div>}
          <div className="mt-3 flex items-center justify-between gap-2">
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
    </>
  );
}
