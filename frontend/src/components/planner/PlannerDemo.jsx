import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { MousePointer2, MapPin, Spline, Pentagon, Square, Check, Maximize2, Minimize2, RotateCcw, Shapes, X, Undo2 } from "lucide-react";
import PlannerMap from "./PlannerMap";
import { LibraryPanel, PropsPanel } from "./Panels";
import { makeFeature, translate, uid } from "./features";
import useHistory from "./useHistory";
import { SCENARIOS } from "./demoScenarios";
import { trackDemo, saveDemoProject } from "@/lib/plannerDemo";

const TOOLS = [["select", MousePointer2, "Seleziona e sposta"], ["point", MapPin, "Punto di interesse"], ["line", Spline, "Percorso"], ["polygon", Pentagon, "Area"], ["rect", Square, "Area rettangolare"]];
const TIPS = {
  select: "Tocca un elemento per vederne le proprietà. Quando è selezionato puoi trascinarlo.",
  point: "Tocca la mappa per aggiungere un punto di interesse.",
  line: "Tocca la mappa punto per punto per disegnare un percorso, poi premi Termina.",
  polygon: "Tocca almeno 3 punti per delimitare un'area, poi premi Termina.",
  rect: "Tocca due angoli opposti per disegnare un'area rettangolare.",
};
const MAX = 200;

// Demo pubblica: stesso motore cartografico e pannelli dell'Event Planner, dati solo nel browser del visitatore.
export default function PlannerDemo({ cfg, onClose }) {
  const nav = useNavigate();
  const sc = SCENARIOS[cfg.scenario_default] || SCENARIOS.running;
  const h = useHistory(sc.features);
  const [layers] = useState(sc.layers);
  const [sel, setSel] = useState(null);
  const [mode, setMode] = useState("select");
  const [placing, setPlacing] = useState(null);
  const [linePreset, setLinePreset] = useState(null);
  const [draftN, setDraftN] = useState(0);
  const [lib, setLib] = useState(() => window.innerWidth >= 1024);
  const [full, setFull] = useState(() => window.innerWidth < 768);
  const [count, setCount] = useState(0);
  const [nudge, setNudge] = useState("no");
  const [mapErr, setMapErr] = useState(false);
  const view = useRef({ center: sc.center, zoom: sc.zoom });

  useEffect(() => { trackDemo("start"); trackDemo("scenario", sc.id); }, [sc.id]);
  useEffect(() => {
    if (!full) return undefined;
    const o = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = o; };
  }, [full]);
  useEffect(() => {
    if (count > 0) saveDemoProject({ scenario: sc.id, features: h.features, layers, center: view.current.center, zoom: view.current.zoom });
    if (count >= (cfg.soglia_interazioni || 4) && nudge === "no") { setNudge("on"); trackDemo("nudge"); }
  }, [count, h.features]); // eslint-disable-line react-hooks/exhaustive-deps

  const bump = () => setCount((x) => x + 1);
  const change = (next, transient, before) => { h.set(next, transient, before); if (!transient) bump(); };
  const create = (spec, c) => {
    if (h.features.length >= MAX) { toast.error(`Nella demo puoi inserire fino a ${MAX} elementi`); return; }
    const f = makeFeature(spec, c, layers, linePreset);
    if (placing) trackDemo("place", placing.nome);
    h.set([...h.features, f]); bump(); setSel(f.properties.id); setPlacing(null); setLinePreset(null); setMode("select");
  };
  const selected = h.features.find((f) => f.properties.id === sel);
  const patch = (p) => change(h.features.map((f) => (f.properties.id === sel ? { ...f, properties: { ...f.properties, ...p } } : f)));
  const duplicate = () => { const c = translate({ ...selected, properties: { ...selected.properties, id: uid() } }, 0.00005, -0.00003); change([...h.features, c]); setSel(c.properties.id); };
  const remove = () => { change(h.features.filter((f) => f.properties.id !== sel)); setSel(null); };
  const pickTool = (k) => { setMode(k); setPlacing(null); setLinePreset(null); trackDemo("tool", k); };
  const pick = (x) => {
    if (x?.tipo === "line") { setLinePreset(x); setPlacing(null); setMode("line"); } else { setPlacing(x); setLinePreset(null); setMode("select"); }
    if (x && window.innerWidth < 1024) setLib(false);
  };
  const register = () => {
    saveDemoProject({ scenario: sc.id, features: h.features, layers, center: view.current.center, zoom: view.current.zoom });
    trackDemo("cta_register");
    nav("/registrati?da=event-planner");
  };
  const toggleFull = () => { if (!full) trackDemo("fullscreen"); setFull(!full); };
  const tip = placing ? `Tocca la mappa per posizionare "${placing.nome}".` : linePreset ? `Disegna "${linePreset.nome}" punto per punto, poi premi Termina.` : TIPS[mode];
  const sheet = "absolute inset-x-0 bottom-0 z-20 max-h-[55%] overflow-y-auto overscroll-contain rounded-t-2xl border-t border-slate-200 bg-white p-3 shadow-2xl lg:static lg:max-h-none lg:rounded-none lg:border-t-0 lg:shadow-none";

  return (
    <div className={full ? "fixed inset-0 z-[70] flex flex-col bg-white" : "relative flex h-[600px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl"} data-testid="planner-demo">
      <div className="flex items-center gap-1.5 border-b border-slate-200 px-3 py-2 pt-[max(0.5rem,env(safe-area-inset-top))]">
        <div className="min-w-0 flex-1"><div className="text-[11px] text-slate-500">Demo Event Planner · dati dimostrativi</div>
          <div className="truncate text-sm font-semibold" data-testid="demo-scenario-name">{sc.nome}</div></div>
        <button type="button" onClick={() => setLib(!lib)} className={`inline-flex h-10 items-center gap-1 rounded-lg px-3 text-sm font-medium ${lib ? "bg-slate-900 text-white" : "bg-slate-100"}`} data-testid="demo-toggle-library"><Shapes className="h-4 w-4" /><span className="hidden sm:inline">Oggetti</span></button>
        <button type="button" disabled={!h.canUndo} onClick={() => { h.undo(); bump(); }} className="h-10 rounded-lg px-2.5 hover:bg-slate-100 disabled:opacity-40" aria-label="Annulla" data-testid="demo-undo"><Undo2 className="h-4 w-4" /></button>
        <button type="button" onClick={() => { h.reset(sc.features); setSel(null); }} className="h-10 rounded-lg px-2.5 hover:bg-slate-100" aria-label="Ricomincia" title="Ricomincia" data-testid="demo-reset"><RotateCcw className="h-4 w-4" /></button>
        <button type="button" onClick={toggleFull} className="h-10 rounded-lg px-2.5 hover:bg-slate-100" aria-label="Schermo intero" data-testid="demo-fullscreen">{full ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}</button>
        <button type="button" onClick={onClose} className="h-10 rounded-lg px-2.5 hover:bg-slate-100" aria-label="Chiudi demo" data-testid="demo-close"><X className="h-4 w-4" /></button>
      </div>
      <div className="relative flex min-h-0 flex-1">
        {lib && <aside className={`${sheet} lg:w-64 lg:border-r`} data-testid="demo-library">
          <div className="mb-2 flex items-center justify-between"><span className="text-xs font-semibold">Strutture, servizi e presidi</span>
            <button type="button" onClick={() => setLib(false)} className="p-1 text-xs text-slate-500 lg:hidden" data-testid="demo-library-close">Chiudi</button></div>
          <LibraryPanel library={cfg.library || []} placing={placing} onPick={pick} />
        </aside>}
        <main className="relative min-w-0 flex-1">
          {mapErr ? <div className="flex h-full items-center justify-center bg-slate-100 p-6 text-center text-sm text-slate-600" data-testid="demo-map-error">La mappa è momentaneamente non disponibile. Riprova tra qualche minuto.</div> : (
            <PlannerMap apiKey={cfg.maptiler_key} stile="strade" center={sc.center} zoom={sc.zoom} bounds={sc.bounds} minZoom={13} cooperative={!full}
              features={h.features} layers={layers} selectedId={sel} mode={mode} placing={placing} onSelect={setSel} onCreate={create} onChange={change}
              onDraft={(p) => setDraftN(p.length)} onView={(c, z) => { view.current = { center: c, zoom: z }; }} onError={() => setMapErr(true)}
              emptyText="La mappa è momentaneamente non disponibile. Riprova tra qualche minuto." />)}
          <div className="absolute left-2 top-2 z-10 flex flex-col gap-1 rounded-xl bg-white/95 p-1 shadow-md backdrop-blur" data-testid="demo-toolbar">
            {TOOLS.map(([k, Icon, t]) => <button key={k} type="button" title={t} aria-label={t} onClick={() => pickTool(k)} data-testid={`demo-tool-${k}`}
              className={`rounded-lg p-2.5 transition-colors ${mode === k && !placing ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}><Icon className="h-5 w-5" /></button>)}
          </div>
          <div className="pointer-events-none absolute left-16 right-2 top-2 z-10 flex justify-center"><div className="max-w-md rounded-xl bg-slate-900/85 px-3 py-1.5 text-center text-xs text-white" data-testid="demo-tip">{tip}</div></div>
          {["line", "polygon"].includes(mode) && draftN > 0 && <button type="button" onClick={() => window.__plannerFinish && window.__plannerFinish()} className="absolute bottom-10 left-1/2 z-10 inline-flex h-11 -translate-x-1/2 items-center rounded-full bg-slate-900 px-5 text-sm font-semibold text-white shadow-lg" data-testid="demo-finish"><Check className="mr-1 h-4 w-4" />Termina ({draftN} punti)</button>}
          {nudge === "on" && <div className="absolute bottom-3 left-3 right-3 z-30 rounded-2xl border border-tiffany/50 bg-white p-4 shadow-2xl sm:right-auto sm:w-80" data-testid="demo-nudge">
            <button type="button" onClick={() => setNudge("off")} className="absolute right-2 top-2 p-1 text-slate-400" aria-label="Chiudi" data-testid="demo-nudge-close"><X className="h-4 w-4" /></button>
            <div className="pr-5 font-display font-bold text-slate-900">{cfg.nudge_titolo}</div>
            <p className="mt-1 text-xs text-slate-600">{cfg.nudge_testo}</p>
            <button type="button" onClick={register} className="mt-3 h-10 w-full rounded-lg bg-tiffany text-sm font-semibold text-slate-900 hover:bg-tiffany-hover" data-testid="demo-nudge-register">{cfg.nudge_cta}</button>
          </div>}
        </main>
        {selected && <aside className={`${sheet} lg:w-72 lg:border-l`} data-testid="demo-props">
          <div className="mb-2 flex items-center justify-between"><span className="text-xs font-semibold">Proprietà</span>
            <button type="button" onClick={() => setSel(null)} className="p-1 text-xs text-slate-500" data-testid="demo-props-close">Chiudi</button></div>
          <PropsPanel f={selected} layers={layers} onPatch={patch} onDuplicate={duplicate} onDelete={remove} />
        </aside>}
      </div>
    </div>
  );
}
