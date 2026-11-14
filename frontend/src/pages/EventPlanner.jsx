import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { MousePointer2, MapPin, Spline, Pentagon, Square, Circle, Ruler, Undo2, Redo2, Search, PanelLeft, PanelRight, ArrowLeft, Check } from "lucide-react";
import PlannerMap from "@/components/planner/PlannerMap";
import { LibraryPanel, LayersPanel, PropsPanel } from "@/components/planner/Panels";
import { uid, translate, makeFeature } from "@/components/planner/features";
import useHistory from "@/components/planner/useHistory";
import { loadDemoProject, clearDemoProject, trackDemo } from "@/lib/plannerDemo";
import { boxPolygon } from "@/lib/geo";

const TOOLS = [["select", MousePointer2, "Selezione e spostamento"], ["point", MapPin, "Punto"], ["line", Spline, "Linea"], ["polygon", Pentagon, "Poligono"],
  ["rect", Square, "Rettangolo"], ["circle", Circle, "Cerchio"], ["measure", Ruler, "Misura"]];

function DemoImport({ onImport, onDiscard }) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-tiffany/40 bg-tiffany-light/50 px-3 py-2 text-sm" data-testid="planner-demo-import">
      <span className="flex-1">Hai un progetto creato nella demo Event Planner della homepage. Vuoi importarlo in questo evento?</span>
      <Button size="sm" onClick={onImport} className="bg-tiffany text-slate-900 hover:bg-tiffany-hover" data-testid="planner-demo-import-btn">Importa progetto demo</Button>
      <Button size="sm" variant="ghost" onClick={onDiscard} data-testid="planner-demo-discard">Non ora</Button>
    </div>
  );
}

export default function EventPlanner() {
  const { id } = useParams();
  const nav = useNavigate();
  const [cfg, setCfg] = useState(null);
  const [ev, setEv] = useState(null);
  const [projects, setProjects] = useState([]);
  const [proj, setProj] = useState(null);
  const [layers, setLayersRaw] = useState([]);
  const h = useHistory();
  const [sel, setSel] = useState(null);
  const [mode, setMode] = useState("select");
  const [placing, setPlacing] = useState(null);
  const [linePreset, setLinePreset] = useState(null);
  const [draftN, setDraftN] = useState(0);
  const [left, setLeft] = useState(() => window.innerWidth >= 1024);
  const [right, setRight] = useState(() => window.innerWidth >= 1024);
  const [stile, setStile] = useState("strade");
  const [q, setQ] = useState("");
  const [fly, setFly] = useState(null);
  const [save, setSave] = useState("salvato");
  const ver = useRef(1), dirty = useRef(false), timer = useRef(null);
  const [demo, setDemo] = useState(() => loadDemoProject());

  const loadList = useCallback(() => api.get(`/planner/events/${id}/projects`).then(({ data }) => { setEv(data.evento); setProjects(data.projects); return data.projects; }), [id]);
  const open = useCallback(async (pid) => {
    const { data } = await api.get(`/planner/projects/${pid}`);
    setProj(data); ver.current = data.version; setLayersRaw(data.layers); h.reset(data.features); setSel(null); dirty.current = false; setSave("salvato");
  }, [h.reset]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    api.get("/planner/config").then(({ data }) => setCfg(data)).catch(() => setCfg({ library: [] }));
    loadList().then((ps) => { const p = ps.find((x) => !x.archiviato); if (p) open(p.id); }).catch((e) => {
      if (e.response?.data?.detail?.code === "addon_required") { toast.info(e.response.data.detail.message, { id: "addon-required" }); nav("/event-planner", { replace: true }); return; }
      toast.error(formatApiError(e.response?.data?.detail));
    });
  }, [loadList, open]);

  const persist = useCallback(async (features, lys) => {
    if (!proj) return;
    setSave("salvataggio");
    try { const { data } = await api.put(`/planner/projects/${proj.id}/content`, { version: ver.current, features, layers: lys }); ver.current = data.version; dirty.current = false; setSave("salvato"); }
    catch (e) { setSave(e.response?.status === 409 ? "conflitto" : "errore"); toast.error(formatApiError(e.response?.data?.detail)); }
  }, [proj]);
  useEffect(() => {
    if (!dirty.current) return undefined;
    setSave("modificato");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => persist(h.features, layers), 1500);
    return () => clearTimeout(timer.current);
  }, [h.features, layers, persist]);
  const change = (next, transient, before) => { dirty.current = true; h.set(next, transient, before); };
  const setLayers = (l) => { dirty.current = true; setLayersRaw(l); };
  const importDemo = async () => {
    try {
      const { data } = await api.post(`/planner/events/${id}/projects`, { nome: "Progetto dalla demo" });
      await api.put(`/planner/projects/${data.id}/content`, { version: data.version, features: demo.features, layers: demo.layers });
      await api.patch(`/planner/projects/${data.id}`, { center: demo.center, zoom: demo.zoom });
      clearDemoProject(); setDemo(null); trackDemo("import"); toast.success("Progetto della demo importato");
      await loadList(); open(data.id);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const discardDemo = () => { clearDemoProject(); setDemo(null); };

  const create = (spec, c) => {
    const f = makeFeature(spec, c, layers, linePreset);
    change([...h.features, f]); setSel(f.properties.id); setPlacing(null); setLinePreset(null); setMode("select"); if (window.innerWidth >= 1024) setRight(true);
  };
  const selected = h.features.find((f) => f.properties.id === sel);
  const patch = (p) => change(h.features.map((f) => (f.properties.id === sel ? { ...f, properties: { ...f.properties, ...p } } : f)));
  const duplicate = () => { const c = translate({ ...selected, properties: { ...selected.properties, id: uid() } }, 0.00005, -0.00003); change([...h.features, c]); setSel(c.properties.id); };
  const remove = () => { change(h.features.filter((f) => f.properties.id !== sel)); setSel(null); };
  const search = async () => {
    if (!q.trim() || !cfg?.maptiler_key) return;
    try { const r = await fetch(`https://api.maptiler.com/geocoding/${encodeURIComponent(q)}.json?key=${cfg.maptiler_key}&language=it&limit=1`).then((x) => x.json());
      const c = r.features?.[0]?.center; if (c) setFly({ center: c, zoom: 16 }); else toast.error("Località non trovata"); } catch { toast.error("Ricerca non disponibile"); }
  };
  const newProject = async (dup) => {
    const nome = window.prompt(dup ? "Nome della copia" : "Nome del nuovo progetto", dup ? `${proj.nome} (copia)` : "Planimetria generale");
    if (!nome) return;
    try { const { data } = await api.post(`/planner/events/${id}/projects`, { nome, duplica_da: dup ? proj.id : null }); await loadList(); open(data.id); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const rename = async () => { const nome = window.prompt("Nuovo nome", proj.nome); if (!nome) return; await api.patch(`/planner/projects/${proj.id}`, { nome }); setProj({ ...proj, nome }); loadList(); };
  const archive = async () => { if (!window.confirm("Archiviare il progetto?")) return; await api.patch(`/planner/projects/${proj.id}`, { archiviato: true }); setProj(null); const ps = await loadList(); const p = ps.find((x) => !x.archiviato); if (p) open(p.id); };
  const SAVE = { salvato: "Salvato", modificato: "Modifiche non salvate", salvataggio: "Salvataggio...", errore: "Errore di rete: riprova", conflitto: "Modificato da un altro utente: ricarica" };

  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col bg-slate-50" data-testid="event-planner">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-3 py-2">
        <Button size="sm" variant="ghost" onClick={() => nav("/eventi")} data-testid="planner-back"><ArrowLeft className="h-4 w-4" /></Button>
        <div className="min-w-0"><div className="truncate text-xs text-slate-500">{ev?.nome}</div>
          <select className="h-8 max-w-[14rem] rounded-md border border-slate-200 bg-white px-1 text-sm font-semibold" value={proj?.id || ""} onChange={(e) => open(e.target.value)} data-testid="planner-project-select">
            {!proj && <option value="">Nessun progetto</option>}{projects.filter((p) => !p.archiviato).map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</select></div>
        <Button size="sm" variant="outline" onClick={() => newProject(false)} data-testid="planner-new-project">Nuovo</Button>
        {proj && <><Button size="sm" variant="ghost" onClick={() => newProject(true)} data-testid="planner-dup-project">Duplica</Button><Button size="sm" variant="ghost" onClick={rename} data-testid="planner-rename-project">Rinomina</Button><Button size="sm" variant="ghost" onClick={archive} data-testid="planner-archive-project">Archivia</Button></>}
        <span className={`text-xs ${save === "salvato" ? "text-green-700" : save === "modificato" || save === "salvataggio" ? "text-slate-500" : "text-red-600"}`} data-testid="planner-save-state">{SAVE[save]}</span>
        {save === "conflitto" && <Button size="sm" variant="outline" onClick={() => open(proj.id)} data-testid="planner-reload">Ricarica</Button>}
        <div className="ml-auto flex items-center gap-1">
          <Button size="icon" variant="ghost" disabled={!h.canUndo} onClick={() => { dirty.current = true; h.undo(); }} data-testid="planner-undo" aria-label="Annulla"><Undo2 className="h-4 w-4" /></Button>
          <Button size="icon" variant="ghost" disabled={!h.canRedo} onClick={() => { dirty.current = true; h.redo(); }} data-testid="planner-redo" aria-label="Ripristina"><Redo2 className="h-4 w-4" /></Button>
          <select className="h-8 rounded-md border border-slate-200 bg-white px-1 text-xs" value={stile} onChange={(e) => setStile(e.target.value)} data-testid="planner-style"><option value="strade">Strade</option><option value="satellite">Satellite</option></select>
        </div>
      </div>
      {demo && <DemoImport onImport={importDemo} onDiscard={discardDemo} />}
      {!proj ? <div className="p-8 text-sm text-slate-600" data-testid="planner-empty">Nessun progetto per questo evento. <Button size="sm" onClick={() => newProject(false)} className="ml-2 bg-tiffany text-slate-900 hover:bg-tiffany-hover" data-testid="planner-create-first">Crea il primo progetto</Button></div> : (
        <div className="relative flex min-h-0 flex-1">
          {left && <aside className="absolute inset-y-0 left-0 z-20 w-72 space-y-4 overflow-y-auto overscroll-contain border-r border-slate-200 bg-slate-50 p-3 lg:static" data-testid="planner-left">
            <div className="flex gap-1"><Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder="Cerca città, indirizzo, luogo" className="h-9" data-testid="planner-search" />
              <Button size="icon" variant="outline" onClick={search} data-testid="planner-search-btn"><Search className="h-4 w-4" /></Button></div>
            <div><div className="mb-1 text-xs font-semibold">Livelli</div><LayersPanel layers={layers} setLayers={setLayers} /></div>
            <div><div className="mb-1 text-xs font-semibold">Oggetti e strutture</div><LibraryPanel library={cfg?.library || []} placing={placing} onPick={(x) => { if (x?.tipo === "line") { setLinePreset(x); setPlacing(null); setMode("line"); toast.info(`Disegna la linea di "${x.nome}" sulla mappa, poi premi Termina`); } else { setPlacing(x); setLinePreset(null); setMode("select"); } if (x && window.innerWidth < 1024) setLeft(false); }} /></div>
          </aside>}
          <main className="relative min-w-0 flex-1">
            <PlannerMap apiKey={cfg?.maptiler_key} stile={stile} center={proj.center} zoom={proj.zoom} features={h.features} layers={layers} selectedId={sel} mode={mode} placing={placing}
              onSelect={(x) => { setSel(x); if (x) setRight(true); }} onCreate={create} onChange={change} onDraft={(p) => setDraftN(p.length)} flyTo={fly}
              onView={(c, z) => { proj.center = c; proj.zoom = z; }} />
            <div className="absolute left-2 top-2 z-10 flex flex-col gap-1 rounded-xl bg-white/95 p-1 shadow-md backdrop-blur" data-testid="planner-toolbar">
              <button type="button" onClick={() => setLeft(!left)} className="rounded-lg p-2.5 hover:bg-slate-100" aria-label="Pannello sinistro" data-testid="planner-toggle-left"><PanelLeft className="h-5 w-5" /></button>
              {TOOLS.map(([k, Icon, t]) => <button key={k} type="button" title={t} aria-label={t} onClick={() => { setMode(k); setPlacing(null); setLinePreset(null); }} data-testid={`planner-tool-${k}`}
                className={`rounded-lg p-2.5 ${mode === k && !placing ? "bg-slate-900 text-white" : "hover:bg-slate-100"}`}><Icon className="h-5 w-5" /></button>)}
            </div>
            {["line", "polygon", "measure"].includes(mode) && draftN > 0 && <Button onClick={() => window.__plannerFinish && window.__plannerFinish()} className="absolute bottom-10 left-1/2 z-10 -translate-x-1/2 bg-slate-900 text-white" data-testid="planner-finish"><Check className="mr-1 h-4 w-4" />Termina ({draftN} punti)</Button>}
            <button type="button" onClick={() => setRight(!right)} className="absolute right-2 top-2 z-10 rounded-lg bg-white/95 p-2.5 shadow-md" aria-label="Pannello proprietà" data-testid="planner-toggle-right"><PanelRight className="h-5 w-5" /></button>
          </main>
          {right && <aside className="absolute inset-x-0 bottom-0 z-20 max-h-[55dvh] overflow-y-auto overscroll-contain rounded-t-2xl border-t border-slate-200 bg-white p-3 shadow-2xl lg:static lg:max-h-none lg:w-80 lg:rounded-none lg:border-l lg:border-t-0 lg:shadow-none" data-testid="planner-right">
            <div className="mb-2 flex items-center justify-between"><span className="text-xs font-semibold">Proprietà</span><button type="button" className="p-1 text-xs text-slate-500 lg:hidden" onClick={() => setRight(false)} data-testid="planner-close-right">Chiudi</button></div>
            <PropsPanel f={selected} layers={layers} onPatch={patch} onDuplicate={duplicate} onDelete={remove} />
          </aside>}
        </div>)}
    </div>
  );
}

export { boxPolygon };
