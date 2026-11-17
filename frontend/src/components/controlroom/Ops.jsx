import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { WifiOff, Maximize2, Minimize2, PanelRightClose, PanelRightOpen, Layers } from "lucide-react";
import { distance } from "@/lib/geo";
import { useOps } from "./useOps";
import { TopBar } from "./TopBar";
import OpsMap from "./OpsMap";
import { SidePanel } from "./SidePanel";
import { DetailDialog } from "./DetailDialog";
import { FormDialog } from "./FormDialog";
import { StaffImport, SettingsDialog } from "./Dialogs";
import { sectorFields, postFields, resourceFields, interventionFields, toForm } from "./forms";

const TITLES = { sectors: "settore", posts: "postazione", resources: "risorsa", interventions: "intervento" };
const DEFAULTS = { posts: { categoria: "volontari", previsti: 0, presenti_manuali: 0, attiva: true }, resources: { kind: "persona", stato: "disponibile" },
  interventions: { priorita: "normale", stato: "aperto" }, sectors: { colore: "#7C3AED" } };

function nearestKm(route, c) {
  const pts = route?.coordinates;
  if (!pts?.length) return null;
  let best = Infinity, at = 0, acc = 0;
  pts.forEach((p, i) => { if (i) acc += distance(pts[i - 1], p); const dd = distance(p, c); if (dd < best) { best = dd; at = acc; } });
  return best < 500 ? Math.round(at / 100) / 10 : null;
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

// Schermo intero tramite portal: nessun antenato con transform limita il riquadro
function MapShell({ full, children }) {
  const box = <div className={full ? "fixed inset-0 z-[60] bg-white" : "relative h-[55vh] min-h-[360px] flex-1 overflow-hidden rounded-2xl border border-slate-200 lg:h-[calc(100vh-330px)] lg:min-h-[520px]"} data-testid="cr-map-wrap">{children}</div>;
  return full ? createPortal(box, document.body) : box;
}

export default function Ops({ eventId }) {
  const { data: d, error, offline, call, base } = useOps(eventId);
  const [cfg, setCfg] = useState(null);
  const [route, setRoute] = useState(null);
  const [hidden, setHidden] = useState(new Set());
  const [tab, setTab] = useState("resources");
  const [sel, setSel] = useState(null);
  const [form, setForm] = useState(null);
  const [placing, setPlacing] = useState(false);
  const [panel, setPanel] = useState(true);
  const [full, setFull] = useState(false);
  const [fly, setFly] = useState(null);
  const [hl, setHl] = useState(null);
  const [staffOpen, setStaffOpen] = useState(false);
  const [setOpen, setSetOpen] = useState(false);
  const [shifts, setShifts] = useState([]);
  useEffect(() => { api.get("/planner/config").then((r) => setCfg(r.data)).catch(() => setCfg({})); }, []);
  const routeKey = d ? `${d.settings.route_map_id || ""}|${d.routes.map((r) => r.version).join(",")}` : null;
  useEffect(() => {
    if (routeKey === null) return;
    api.get(`${base}/route`, { params: { map_id: d.settings.route_map_id || undefined } }).then((r) => setRoute(r.data.route)).catch(() => setRoute(null));
  }, [routeKey]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (d?.perms.edit) api.get(`${base}/staff`).then((r) => setShifts(r.data.shifts)).catch(() => {}); }, [base, d?.perms.edit]);
  const fields = useMemo(() => d && form && { sectors: sectorFields(d), posts: postFields(d), resources: resourceFields(d, shifts), interventions: interventionFields(d) }[form.kind], [d, form, shifts]);
  if (error) return <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="cr-ops-error">{error}</div>;
  if (!d) return <div className="text-sm text-slate-400" data-testid="cr-ops-loading">Caricamento Control Room…</div>;

  const toggle = (k) => setHidden((h) => { const n = new Set(h); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const open = (kind, id) => {
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
    focus: (c) => { setSel(null); setFly({ c, t: Date.now() }); },
    closeIntervention: (i) => call("put", `/interventions/${i.id}`, { ...i, stato: "chiuso" }, "Intervento chiuso"),
  };
  const place = (c) => { setPlacing(false); setForm({ kind: "posts", initial: { ...DEFAULTS.posts, lng: c[0], lat: c[1], km: nearestKm(route, c) } }); };
  const add = (kind) => setForm({ kind, initial: DEFAULTS[kind] });
  const panelProps = { d, tab, setTab, open, placing, highlight: hl, setHighlight: setHl, onPlace: () => { setPlacing(!placing); setFull(false); }, onImport: () => setStaffOpen(true), onAdd: () => add(tab) };

  return (
    <div className="space-y-3" data-testid="cr-ops">
      {offline && <div className="flex items-center gap-2 rounded-xl bg-red-600 px-4 py-3 text-sm font-semibold text-white" data-testid="cr-offline"><WifiOff className="h-4 w-4" />Connessione persa: i dati mostrati potrebbero non essere aggiornati. Nuovo tentativo in corso…</div>}
      <TopBar d={d} onStatus={(s) => call("put", "/settings", { status: s, version: d.settings.version }, "Stato evento aggiornato")} onNewIntervention={() => add("interventions")} onSettings={() => setSetOpen(true)} />
      {!route && <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="cr-no-route">Nessun percorso GPX collegato all'evento in Percorsi Eventi: la mappa resta utilizzabile per posizionare le risorse.</div>}
      <Filters d={d} hidden={hidden} toggle={toggle} />
      <div className="flex flex-col gap-3 lg:flex-row">
        <MapShell full={full}>
          <OpsMap apiKey={cfg?.maptiler_key} route={route} data={d} hidden={hidden} highlight={hl} placing={placing} onPlace={place} onOpen={open} flyTo={fly} canEdit={d.perms.edit}
            onMove={(p, c) => call("patch", `/posts/${p.id}/position`, { lng: c[0], lat: c[1], version: p.version }, "Posizione salvata")} />
          <div className="absolute right-2 top-2 flex gap-1.5">
            <Button size="icon" variant="secondary" className="h-10 w-10 rounded-full bg-white shadow" onClick={() => setFull(!full)} title={full ? "Esci da schermo intero" : "Mappa a schermo intero"} data-testid="cr-map-fullscreen">{full ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}</Button>
            <Button size="icon" variant="secondary" className="hidden h-10 w-10 rounded-full bg-white shadow lg:inline-flex" onClick={() => setPanel(!panel)} title="Pannello operativo" data-testid="cr-panel-toggle">{panel ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}</Button>
          </div>
          {placing && <div className="absolute left-1/2 top-2 -translate-x-1/2 rounded-full bg-amber-500 px-4 py-2 text-xs font-bold text-slate-900 shadow" data-testid="cr-placing-hint">Clicca sulla mappa per creare la postazione</div>}
        </MapShell>
        {panel && <div className="h-[60vh] overflow-hidden rounded-2xl border border-slate-200 bg-white lg:h-[calc(100vh-330px)] lg:min-h-[520px] lg:w-[380px]">
          <SidePanel {...panelProps} /></div>}
        {!panel && <div className="lg:hidden"><SidePanel {...panelProps} /></div>}
      </div>
      <DetailDialog d={d} sel={sel} onClose={() => setSel(null)} act={act} />
      {form && <FormDialog open onOpenChange={(o) => !o && setForm(null)} title={`${form.initial.id ? "Modifica" : "Nuova"} ${TITLES[form.kind]}`} fields={fields} initial={form.initial}
        testid={`cr-form-${form.kind}`} onSubmit={(v) => save(form.kind, v)} />}
      <StaffImport open={staffOpen} onOpenChange={setStaffOpen} d={d} base={base} onSubmit={(b) => call("post", "/resources/from-staff", b, "Persone assegnate")} />
      <SettingsDialog open={setOpen} onOpenChange={setSetOpen} d={d} onSubmit={(b) => call("put", "/settings", b, "Impostazioni salvate")} />
    </div>
  );
}
