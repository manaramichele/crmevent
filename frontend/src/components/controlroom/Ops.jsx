import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { WifiOff, Maximize2, Minimize2, PanelRightClose, PanelRightOpen, Layers, Siren } from "lucide-react";
import { distance } from "@/lib/geo";
import { useOps } from "./useOps";
import { TopBar } from "./TopBar";
import OpsMap from "./OpsMap";
import { SidePanel } from "./SidePanel";
import { DetailDialog } from "./DetailDialog";
import { FormDialog } from "./FormDialog";
import { StaffImport, SettingsDialog } from "./Dialogs";
import { ItvNew } from "./ItvNew";
import { ItvDetail } from "./ItvDetail";
import { ItvList, Comms, Diary } from "./ItvViews";
import { AccessDialog } from "./Access";
import { PlannerImport } from "./PlannerImport";
import { CLOSED } from "./meta";
import { sectorFields, postFields, resourceFields, toForm } from "./forms";

const TITLES = { sectors: "settore", posts: "postazione", resources: "risorsa" };
const DEFAULTS = { posts: { categoria: "volontari", previsti: 0, presenti_manuali: 0, attiva: true }, resources: { kind: "persona", stato: "disponibile" }, sectors: { colore: "#7C3AED" } };
const VIEWS = [["map", "Operativa"], ["itv", "Interventi"], ["comms", "Comunicazioni"], ["diary", "Diario operativo"]];

function nearestKm(route, c) {
  const pts = route?.coordinates;
  if (!pts?.length) return null;
  let best = Infinity, at = 0, acc = 0;
  pts.forEach((p, i) => { if (i) acc += distance(pts[i - 1], p); const dd = distance(p, c); if (dd < best) { best = dd; at = acc; } });
  return best < 500 ? Math.round(at / 100) / 10 : null;
}

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.35, 0.7].forEach((t) => { const o = ctx.createOscillator(), g = ctx.createGain(); o.frequency.value = 880; o.connect(g); g.connect(ctx.destination); g.gain.value = 0.25; o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.2); });
  } catch (e) { /* audio non consentito dal browser */ }
}

function Filters({ d, hidden, toggle }) {
  const vehicles = [...new Set(d.resources.filter((r) => r.kind === "mezzo").map((r) => r.tipologia))];
  const chips = [["route", "Percorso"], ["km", "Chilometri"], ["sectors", "Settori"], ["interventions", "Interventi"], ["squadre", "Squadre"],
    ...d.settings.categories.filter((c) => d.posts.some((p) => p.categoria === c.key)).map((c) => [`post:${c.key}`, c.label, c.color]),
    ...vehicles.map((k) => [`veh:${k}`, `Mezzo: ${d.vehicles.find((v) => v.key === k)?.label || k}`])];
  return (
    <div className="flex gap-1.5 overflow-x-auto pb-1" data-testid="cr-filters">
      <Layers className="mt-1.5 h-4 w-4 shrink-0 text-slate-400" />
      {chips.map(([k, l, col]) => (
        <button key={k} type="button" onClick={() => toggle(k)} className={`flex shrink-0 items-center gap-1 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${hidden.has(k) ? "border-slate-200 bg-white text-slate-400 line-through" : "border-[#0ABAB5]/40 bg-[#0ABAB5]/10 text-slate-800"}`} data-testid={`cr-filter-chip-${k.replace(":", "-")}`}>
          {col && <span className="h-2 w-2 rounded-full" style={{ background: col }} />}{l}
        </button>))}
    </div>
  );
}

function MapShell({ full, children }) {
  const box = <div className={full ? "fixed inset-0 z-[60] bg-white" : "relative h-[55vh] min-h-[360px] flex-1 overflow-hidden rounded-2xl border border-slate-200 lg:h-[calc(100vh-330px)] lg:min-h-[520px]"} data-testid="cr-map-wrap">{children}</div>;
  return full ? createPortal(box, document.body) : box;
}

function CriticalBanner({ list, open }) {
  if (!list.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-red-600/30" data-testid="cr-critical-banner">
      <Siren className="h-5 w-5 animate-pulse" />{list.length} CRITICITÀ ROSS{list.length > 1 ? "E" : "A"} DA GESTIRE
      {list.slice(0, 4).map((i) => <button key={i.id} type="button" onClick={() => open(i.id)} className="rounded-full bg-white/20 px-3 py-0.5 text-xs hover:bg-white/30" data-testid={`cr-critical-${i.codice}`}>{i.codice}</button>)}
    </div>
  );
}

export default function Ops({ eventId }) {
  const { data: d, error, offline, call, base } = useOps(eventId);
  const [cfg, setCfg] = useState(null);
  const [route, setRoute] = useState(null);
  const [hidden, setHidden] = useState(new Set());
  const [view, setView] = useState("map");
  const [tab, setTab] = useState("resources");
  const [sel, setSel] = useState(null);
  const [itvId, setItvId] = useState(null);
  const [newItv, setNewItv] = useState(null);
  const [form, setForm] = useState(null);
  const [placing, setPlacing] = useState(null);
  const [panel, setPanel] = useState(true);
  const [full, setFull] = useState(false);
  const [fly, setFly] = useState(null);
  const [hl, setHl] = useState(null);
  const [staffOpen, setStaffOpen] = useState(false);
  const [setOpen, setSetOpen] = useState(false);
  const [accOpen, setAccOpen] = useState(false);
  const [plOpen, setPlOpen] = useState(false);
  const [msgPreset, setMsgPreset] = useState(null);
  const [shifts, setShifts] = useState([]);
  const [sound, setSound] = useState(() => localStorage.getItem("cr_sound") === "1");
  const [flash, setFlash] = useState(false);
  const seen = useRef(null);
  useEffect(() => { api.get("/planner/config").then((r) => setCfg(r.data)).catch(() => setCfg({})); }, []);
  const routeKey = d ? `${d.settings.route_map_id || ""}|${d.routes.map((r) => r.version).join(",")}` : null;
  useEffect(() => {
    if (routeKey === null) return;
    api.get(`${base}/route`, { params: { map_id: d.settings.route_map_id || undefined } }).then((r) => setRoute(r.data.route)).catch(() => setRoute(null));
  }, [routeKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (d?.perms.edit) api.get(`${base}/staff`).then((r) => setShifts(r.data.shifts)).catch(() => {}); }, [base, d?.perms.edit]);
  const critical = useMemo(() => (d ? d.interventions.filter((i) => ["alta", "critica"].includes(i.priorita) && !CLOSED.includes(i.stato) && i.stato !== "risolto") : []), [d]);
  useEffect(() => {
    if (!d) return;
    const ids = critical.map((i) => i.id);
    if (seen.current && ids.some((id) => !seen.current.has(id))) {
      setFlash(true); setTimeout(() => setFlash(false), 6000);
      if (sound) beep();
    }
    seen.current = new Set([...(seen.current || []), ...ids]);
  }, [critical, d, sound]);
  const fields = useMemo(() => d && form && { sectors: sectorFields(d), posts: postFields(d), resources: resourceFields(d, shifts) }[form.kind], [d, form, shifts]);
  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="cr-ops-error">{error}</div>;
  if (!d) return <div className="text-sm text-slate-400" data-testid="cr-ops-loading">Caricamento Control Room…</div>;

  const canItv = ["responsabile", "coordinatore"].includes(d.perms.role);
  const toggle = (k) => setHidden((h) => { const n = new Set(h); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const flyTo = (c) => { setFull(false); setView("map"); setFly({ c, t: Date.now() }); };
  const open = (kind, id) => {
    if (kind === "interventions") { setItvId(id); const i = d.interventions.find((x) => x.id === id); if (i?.lng != null) setFly({ c: [i.lng, i.lat], t: Date.now() }); return; }
    setSel([kind, id]);
    const it = { posts: d.posts, resources: d.resources }[kind]?.find((x) => x.id === id);
    const p = kind === "posts" ? it : d.posts.find((x) => x.id === it?.post_id);
    const c = it?.lng != null ? [it.lng, it.lat] : p?.lng != null ? [p.lng, p.lat] : null;
    if (c) setFly({ c, t: Date.now() });
  };
  const save = async (kind, v) => {
    const body = { ...v }; delete body.id;
    return v.id ? call("put", `/${kind}/${v.id}`, body, "Salvato") : call("post", `/${kind}`, body, "Creato");
  };
  const act = {
    presence: (r, on) => call("post", `/resources/${r.id}/presence`, { presente: on }),
    status: (r, stato) => call("patch", `/resources/${r.id}/status`, { stato, version: r.version }),
    edit: (kind, it) => { setSel(null); setForm({ kind, initial: kind === "resources" ? toForm(it) : it }); },
    remove: async (kind, it) => { if (await call("delete", `/${kind}/${it.id}`, undefined, "Eliminato")) setSel(null); },
    duplicate: async (p) => { const r = await call("post", `/posts/${p.id}/duplicate`, {}, "Postazione duplicata"); if (r?.id) setSel(["posts", r.id]); },
    focus: (c) => { setSel(null); flyTo(c); },
  };
  const place = (c) => {
    const mode = placing; setPlacing(null);
    if (mode === "itv") { setFull(false); setNewItv({ lng: c[0], lat: c[1], km: nearestKm(route, c), origine: "mappa" }); return; }
    setForm({ kind: "posts", initial: { ...DEFAULTS.posts, lng: c[0], lat: c[1], km: nearestKm(route, c) } });
  };
  const add = (kind) => setForm({ kind, initial: DEFAULTS[kind] });
  const createItv = async (v) => { const r = await call("post", "/interventions", v, "Intervento registrato"); if (r?.id) setItvId(r.id); return r; };
  const itv = itvId && d.interventions.find((i) => i.id === itvId);
  const panelProps = { d, tab, setTab, open, placing: placing === "post", highlight: hl, setHighlight: setHl, onPlace: () => { setPlacing(placing === "post" ? null : "post"); setFull(false); },
    onImport: () => setStaffOpen(true), onPlannerImport: () => setPlOpen(true), onAdd: () => add(tab), onPlaceItv: () => setPlacing(placing === "itv" ? null : "itv") };

  return (
    <div className="space-y-3 pb-20 lg:pb-0" data-testid="cr-ops">
      {offline && <div className="flex items-center gap-2 rounded-xl bg-red-600 px-4 py-3 text-sm font-semibold text-white" data-testid="cr-offline"><WifiOff className="h-4 w-4" />Connessione persa: i dati mostrati NON sono aggiornati e le operazioni non risultano registrate. Riconnessione automatica in corso…</div>}
      {flash && <div className="pointer-events-none fixed inset-0 z-[70] animate-pulse border-[10px] border-red-600" data-testid="cr-critical-flash" />}
      <TopBar d={d} sound={sound} onSound={() => { const n = !sound; setSound(n); localStorage.setItem("cr_sound", n ? "1" : "0"); if (n) beep(); }}
        onStatus={(s) => call("put", "/settings", { status: s, version: d.settings.version }, "Stato evento aggiornato")} onNewIntervention={canItv ? () => setNewItv({}) : null}
        onSettings={() => setSetOpen(true)} onAccess={() => setAccOpen(true)} onReadNotifs={() => call("post", "/notifications/read")} openItv={(id) => open("interventions", id)} />
      <CriticalBanner list={critical} open={(id) => open("interventions", id)} />
      <div className="flex gap-1 overflow-x-auto" data-testid="cr-views">
        {VIEWS.map(([k, l]) => <button key={k} type="button" onClick={() => setView(k)} className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold transition-colors ${view === k ? "bg-slate-900 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`} data-testid={`cr-view-${k}`}>
          {l}{k === "itv" && d.kpi.interventi_aperti > 0 && <span className="ml-1.5 rounded-full bg-red-600 px-1.5 text-[11px] text-white">{d.kpi.interventi_aperti}</span>}{k === "comms" && d.unread_inbound > 0 && <span className="ml-1.5 rounded-full bg-sky-600 px-1.5 text-[11px] text-white">{d.unread_inbound}</span>}</button>)}
      </div>
      {view === "itv" && <ItvList d={d} open={(id) => open("interventions", id)} />}
      {view === "comms" && <Comms key={msgPreset?.t || 0} d={d} call={call} preset={msgPreset} />}
      {view === "diary" && <Diary d={d} base={base} open={(id) => open("interventions", id)} />}
      {view === "map" && <>
        {!route && <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="cr-no-route">Nessun percorso GPX collegato all'evento in Percorsi Eventi: la mappa resta utilizzabile per posizionare le risorse.</div>}
        <Filters d={d} hidden={hidden} toggle={toggle} />
        <div className="flex flex-col gap-3 lg:flex-row">
          <MapShell full={full}>
            <OpsMap apiKey={cfg?.maptiler_key} route={route} data={d} hidden={hidden} highlight={hl} placing={!!placing} onPlace={place} onOpen={open} flyTo={fly} canEdit={d.perms.edit}
              onMove={(p, c) => call("patch", `/posts/${p.id}/position`, { lng: c[0], lat: c[1], version: p.version }, "Posizione salvata")} />
            <div className="absolute right-2 top-2 flex gap-1.5">
              {canItv && <Button size="sm" onClick={() => setPlacing(placing === "itv" ? null : "itv")} className={`h-10 rounded-full font-bold shadow ${placing === "itv" ? "bg-amber-500 text-slate-900" : "bg-white text-red-600 hover:bg-red-50"}`} data-testid="cr-map-new-itv">
                <Siren className="mr-1 h-4 w-4" />{placing === "itv" ? "Annulla" : "Intervento qui"}</Button>}
              <Button size="icon" variant="secondary" className="h-10 w-10 rounded-full bg-white shadow" onClick={() => setFull(!full)} title={full ? "Esci da schermo intero" : "Mappa a schermo intero"} data-testid="cr-map-fullscreen">{full ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}</Button>
              <Button size="icon" variant="secondary" className="hidden h-10 w-10 rounded-full bg-white shadow lg:inline-flex" onClick={() => setPanel(!panel)} title="Pannello operativo" data-testid="cr-panel-toggle">{panel ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}</Button>
            </div>
            {placing && <div className="absolute left-1/2 top-14 -translate-x-1/2 rounded-full bg-amber-500 px-4 py-2 text-xs font-bold text-slate-900 shadow" data-testid="cr-placing-hint">{placing === "itv" ? "Clicca sul punto dell'intervento" : "Clicca sulla mappa per creare la postazione"}</div>}
          </MapShell>
          {panel && <div className="h-[60vh] overflow-hidden rounded-2xl border border-slate-200 bg-white lg:h-[calc(100vh-330px)] lg:min-h-[520px] lg:w-[380px]"><SidePanel {...panelProps} /></div>}
          {!panel && <div className="lg:hidden"><SidePanel {...panelProps} /></div>}
        </div>
      </>}
      {canItv && <Button onClick={() => setNewItv({})} className="fixed bottom-4 right-4 z-40 h-14 rounded-full bg-red-600 px-6 text-base font-bold text-white shadow-xl shadow-red-600/30 hover:bg-red-700 lg:hidden" data-testid="cr-fab-new-itv"><Siren className="mr-2 h-5 w-5" />NUOVO INTERVENTO</Button>}
      <DetailDialog d={d} sel={sel} onClose={() => setSel(null)} act={act} />
      {itv && <ItvDetail d={d} it={itv} base={base} call={call} onClose={() => setItvId(null)} focus={(c) => { setItvId(null); flyTo(c); }}
        openPost={(pid) => { setItvId(null); open("posts", pid); }} message={(rid, iid) => { setItvId(null); setMsgPreset({ to_id: rid, intervention_id: iid, t: Date.now() }); setView("comms"); }} />}
      <ItvNew open={!!newItv} onOpenChange={(o) => !o && setNewItv(null)} d={d} initial={newItv} onSubmit={createItv} />
      {form && <FormDialog open onOpenChange={(o) => !o && setForm(null)} title={`${form.initial.id ? "Modifica" : "Nuova"} ${TITLES[form.kind]}`} fields={fields} initial={form.initial}
        testid={`cr-form-${form.kind}`} onSubmit={(v) => save(form.kind, v)} />}
      <StaffImport open={staffOpen} onOpenChange={setStaffOpen} d={d} base={base} onSubmit={(b) => call("post", "/resources/from-staff", b, "Persone assegnate")} />
      <SettingsDialog open={setOpen} onOpenChange={setSetOpen} d={d} onSubmit={(b) => call("put", "/settings", b, "Impostazioni salvate")} />
      {accOpen && <AccessDialog open onOpenChange={setAccOpen} d={d} base={base} call={call} />}
      <PlannerImport open={plOpen} onOpenChange={setPlOpen} d={d} base={base} call={async (m, p, b) => { const r = await call(m, p, b); if (r) toast.success(`Importazione completata: ${r.created} nuove postazioni, ${r.updated} aggiornate, ${r.people} persone assegnate`); return r; }} />
    </div>
  );
}
