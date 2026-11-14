import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { SOURCE_LABEL, eur } from "@/components/addons/addonInfo";

const PLANS = ["bronze", "silver", "gold"];
const num = (v) => (v === "" || v == null ? null : Number(v));

function IncludedRow({ label, value, onChange, prefix }) {
  return (
    <div className="grid grid-cols-3 gap-2">{PLANS.map((p) => (
      <label key={p} className="text-xs text-slate-500">{label} {p.toUpperCase()}
        <Input type="number" min={0} value={value[p]} onChange={(e) => onChange({ ...value, [p]: Number(e.target.value) })} data-testid={`${prefix}-included-${p}`} /></label>))}
    </div>
  );
}

function PackageRow({ p, onChange, onDel, i }) {
  const set = (k) => (e) => onChange({ ...p, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  return (
    <div className="grid grid-cols-2 md:grid-cols-7 gap-2 items-end rounded-lg border border-slate-200 p-2" data-testid={`em-package-${i}`}>
      <label className="text-xs text-slate-500 col-span-2">Nome<Input value={p.name} onChange={set("name")} data-testid={`em-package-name-${i}`} /></label>
      <label className="text-xs text-slate-500">Prezzo €<Input type="number" min={0} step="0.01" value={p.price ?? ""} onChange={set("price")} data-testid={`em-package-price-${i}`} /></label>
      <label className="text-xs text-slate-500">Video<Input type="number" min={0} value={p.videos} onChange={set("videos")} data-testid={`em-package-videos-${i}`} /></label>
      <label className="text-xs text-slate-500">Eventi<Input type="number" min={1} value={p.events} onChange={set("events")} data-testid={`em-package-events-${i}`} /></label>
      <label className="text-xs text-slate-500">Validità (giorni)<Input type="number" min={1} value={p.validity_days ?? ""} placeholder="Nessuna" onChange={set("validity_days")} data-testid={`em-package-validity-${i}`} /></label>
      <div className="flex items-center gap-2">
        <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={p.active} onChange={set("active")} data-testid={`em-package-active-${i}`} />Attivo</label>
        <button type="button" onClick={onDel} className="text-red-600" data-testid={`em-package-del-${i}`}><Trash2 className="w-4 h-4" /></button>
      </div>
      <label className="text-xs text-slate-500 col-span-2 md:col-span-7">Formati disponibili (separati da virgola)<Input value={(p.formats || []).join(", ")} onChange={(e) => onChange({ ...p, formats: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} placeholder="9:16 verticale, 16:9 orizzontale" data-testid={`em-package-formats-${i}`} /></label>
    </div>
  );
}

function ConfigCard({ onSaved }) {
  const [c, setC] = useState(null);
  useEffect(() => { api.get("/platform/addons/config").then(({ data }) => setC(data)); }, []);
  if (!c) return null;
  const pkgs = c.eventmap.packages || [];
  const setPk = (list) => setC({ ...c, eventmap: { ...c.eventmap, packages: list } });
  const save = async () => {
    try {
      const { data } = await api.put("/platform/addons/config", {
        planner_included: c.planner.included, planner_price: num(c.planner.price),
        eventmap_included: c.eventmap.included, eventmap_included_videos: Number(c.eventmap.included_videos || 0),
        eventmap_packages: pkgs.map((p) => ({ ...p, price: num(p.price), videos: Number(p.videos || 0), events: Number(p.events || 1), validity_days: num(p.validity_days) })),
      });
      setC(data); toast.success("Configurazione salvata"); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-5" data-testid="addon-config">
      <div className="space-y-2"><h3 className="font-semibold text-slate-900">Event Planner</h3>
        <IncludedRow label="Eventi inclusi" value={c.planner.included} prefix="ep" onChange={(v) => setC({ ...c, planner: { ...c.planner, included: v } })} />
        <label className="block text-xs text-slate-500 max-w-xs">Prezzo attivazione per evento aggiuntivo (€)<Input type="number" min={0} step="0.01" value={c.planner.price ?? ""} placeholder="Non configurato" onChange={(e) => setC({ ...c, planner: { ...c.planner, price: e.target.value } })} data-testid="ep-price" /></label>
      </div>
      <div className="space-y-2"><h3 className="font-semibold text-slate-900">Event Map</h3>
        <IncludedRow label="Eventi inclusi" value={c.eventmap.included} prefix="em" onChange={(v) => setC({ ...c, eventmap: { ...c.eventmap, included: v } })} />
        <label className="block text-xs text-slate-500 max-w-xs">Video compresi per ogni evento incluso (Silver/Gold)<Input type="number" min={0} value={c.eventmap.included_videos} onChange={(e) => setC({ ...c, eventmap: { ...c.eventmap, included_videos: e.target.value } })} data-testid="em-included-videos" /></label>
        <div className="space-y-2">{pkgs.map((p, i) => <PackageRow key={p.id || i} i={i} p={p} onChange={(np) => setPk(pkgs.map((x, j) => (j === i ? np : x)))} onDel={() => setPk(pkgs.filter((_, j) => j !== i))} />)}</div>
        <Button variant="outline" size="sm" onClick={() => setPk([...pkgs, { name: "Nuovo pacchetto", price: null, videos: 1, events: 1, validity_days: 365, formats: [], active: true }])} data-testid="em-package-add"><Plus className="w-4 h-4 mr-1" />Aggiungi pacchetto</Button>
      </div>
      <Button onClick={save} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="addon-config-save">Salva configurazione</Button>
    </div>
  );
}

function GrantForm({ org, product, data, packages, onDone }) {
  const [f, setF] = useState({ source: "superadmin", events_total: 1, videos_total: 0, package_id: "", expires_at: "", event_ids: [], note: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const toggleEv = (id) => setF({ ...f, event_ids: f.event_ids.includes(id) ? f.event_ids.filter((x) => x !== id) : [...f.event_ids, id] });
  const submit = async () => {
    try {
      await api.post(`/platform/addons/orgs/${org.id}/grants`, { product, source: f.source, events_total: Number(f.events_total), videos_total: Number(f.videos_total || 0),
        package_id: f.package_id || null, expires_at: f.expires_at || null, event_ids: f.event_ids, note: f.note || null });
      toast.success("Assegnazione gratuita registrata"); onDone();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="rounded-lg bg-slate-50 p-3 space-y-2" data-testid={`grant-form-${product}`}>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-slate-500">Tipo<select value={f.source} onChange={set("source")} className="w-full h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid={`grant-source-${product}`}><option value="superadmin">Omaggio</option><option value="promo">Promozione temporanea</option></select></label>
        <label className="text-xs text-slate-500">Scadenza{f.source === "promo" ? "*" : ""}<Input type="date" value={f.expires_at} onChange={set("expires_at")} data-testid={`grant-expires-${product}`} /></label>
        {product === "eventmap" && <label className="text-xs text-slate-500 col-span-2">Pacchetto<select value={f.package_id} onChange={set("package_id")} className="w-full h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="grant-package"><option value="">Personalizzato</option>{packages.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
        {!f.package_id && <label className="text-xs text-slate-500">Eventi<Input type="number" min={1} value={f.events_total} onChange={set("events_total")} data-testid={`grant-events-${product}`} /></label>}
        {product === "eventmap" && !f.package_id && <label className="text-xs text-slate-500">Video<Input type="number" min={0} value={f.videos_total} onChange={set("videos_total")} data-testid="grant-videos" /></label>}
      </div>
      <div className="text-xs text-slate-500">Attiva subito sugli eventi (facoltativo):</div>
      <div className="flex flex-wrap gap-1.5">{data.events.filter((e) => !e.active).map((e) => (
        <button key={e.id} type="button" onClick={() => toggleEv(e.id)} className={`px-2 py-1 rounded-full text-xs border ${f.event_ids.includes(e.id) ? "bg-[#0ABAB5] border-[#0ABAB5]" : "border-slate-200 bg-white"}`} data-testid={`grant-ev-${product}-${e.id}`}>{e.nome}</button>))}</div>
      <Input value={f.note} onChange={set("note")} placeholder="Nota interna" data-testid={`grant-note-${product}`} />
      <Button size="sm" onClick={submit} className="bg-slate-900 text-white" data-testid={`grant-submit-${product}`}>Assegna gratuitamente</Button>
    </div>
  );
}

function ProductPanel({ org, product, d, packages, reload }) {
  const revoke = async (gid) => {
    try { await api.post(`/platform/addons/grants/${gid}/revoke`); toast.success("Attivazione revocata: i dati restano conservati"); reload(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="space-y-3" data-testid={`sa-addon-${product}`}>
      <h4 className="font-semibold">{d.name}</h4>
      <div className="text-sm text-slate-600">Inclusi {d.included_used}/{d.included} · acquistati {d.purchased} · omaggi/promo {d.granted}{product === "eventmap" && ` · video ${d.videos_used}/${d.videos_total}`}</div>
      <div className="text-xs space-y-1">{d.events.filter((e) => e.assigned).map((e) => <div key={e.id}>{e.nome} · {e.active ? SOURCE_LABEL[e.source] || "attivo" : "non coperto"}</div>)}</div>
      {d.grants.length > 0 && <div className="space-y-1">{d.grants.map((g) => (
        <div key={g.id} className="flex items-center gap-2 text-xs rounded border border-slate-100 p-2" data-testid={`sa-grant-${g.id}`}>
          <span className="flex-1">{SOURCE_LABEL[g.source]} · {g.package_name} · {g.events_total} eventi{product === "eventmap" && ` · ${g.videos_total} video`}{g.price ? ` · ${eur(g.price)} €` : ""}{g.expires_at ? ` · scad. ${g.expires_at.slice(0, 10)}` : ""} · <b>{g.status}</b></span>
          {g.status === "active" && g.source !== "purchase" && <button type="button" onClick={() => revoke(g.id)} className="text-red-600 font-semibold" data-testid={`sa-grant-revoke-${g.id}`}>Revoca</button>}
        </div>))}</div>}
      <GrantForm org={org} product={product} data={d} packages={packages} onDone={reload} />
    </div>
  );
}

function OrgDialog({ org, onClose, onChanged }) {
  const [d, setD] = useState(null);
  const [pk, setPk] = useState([]);
  const load = () => api.get(`/platform/addons/orgs/${org.id}`).then(({ data }) => setD(data));
  useEffect(() => { load(); api.get("/platform/addons/config").then(({ data }) => setPk(data.eventmap.packages || [])); }, [org.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const reload = () => { load(); onChanged(); };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid="sa-addon-org-dialog">
        <DialogTitle>{org.nome} · {org.plan_label || org.mode || "—"}</DialogTitle>
        {!d ? <p className="text-sm text-slate-400">Caricamento...</p> : <div className="grid md:grid-cols-2 gap-6">
          <ProductPanel org={org} product="planner" d={d.planner} packages={pk} reload={reload} />
          <ProductPanel org={org} product="eventmap" d={d.eventmap} packages={pk} reload={reload} />
        </div>}
      </DialogContent>
    </Dialog>
  );
}

export default function AddonAdmin() {
  const [rows, setRows] = useState(null);
  const [open, setOpen] = useState(null);
  const [q, setQ] = useState("");
  const load = () => api.get("/platform/addons/orgs").then(({ data }) => setRows(data));
  useEffect(() => { load(); }, []);
  const list = (rows || []).filter((r) => !q || (r.nome || "").toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="animate-fade-up space-y-6" data-testid="addon-admin-page">
      <PageHeader title="Event Planner & Event Map" subtitle="Eventi inclusi nei piani, prezzi, pacchetti, omaggi e promozioni per organizzazione." />
      <ConfigCard onSaved={load} />
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca organizzazione" className="max-w-sm" data-testid="addon-admin-search" />
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm" data-testid="addon-admin-table">
          <thead className="bg-slate-50 text-xs text-slate-500 text-left"><tr><th className="px-3 py-2">Organizzazione</th><th className="px-3 py-2">Piano</th><th className="px-3 py-2">Event Planner (incl./usati · acquist. · omaggi)</th><th className="px-3 py-2">Event Map (incl./usati · acquist. · omaggi)</th><th className="px-3 py-2">Video (gen./disp.)</th><th className="px-3 py-2">Promo</th><th /></tr></thead>
          <tbody>{list.map((r) => (
            <tr key={r.id} className="border-t border-slate-100" data-testid={`addon-admin-row-${r.id}`}>
              <td className="px-3 py-2 font-medium">{r.nome}</td><td className="px-3 py-2">{r.unrestricted ? "Interna" : r.plan_label || r.mode}</td>
              <td className="px-3 py-2">{r.planner.included_used}/{r.planner.included} · {r.planner.purchased} · {r.planner.granted}</td>
              <td className="px-3 py-2">{r.eventmap.included_used}/{r.eventmap.included} · {r.eventmap.purchased} · {r.eventmap.granted}</td>
              <td className="px-3 py-2">{r.eventmap.videos_used}/{r.eventmap.videos_total}</td><td className="px-3 py-2">{r.promos}</td>
              <td className="px-3 py-2"><Button size="sm" variant="outline" onClick={() => setOpen(r)} data-testid={`addon-admin-manage-${r.id}`}>Gestisci</Button></td>
            </tr>))}</tbody>
        </table>
      </div>
      {open && <OrgDialog org={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}
