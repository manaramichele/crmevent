import { useEffect, useState } from "react";
import { sortIt } from "@/lib/sortOptions";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Trash2, Plus } from "lucide-react";
import api from "@/lib/api";
import { ICON_NAMES } from "./meta";

const S = "h-10 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";

// Seleziona persone già registrate in Staff / Volontari (nessuna anagrafica duplicata) e le assegna.
export function StaffImport({ open, onOpenChange, d, base, onSubmit }) {
  const [rows, setRows] = useState(null);
  const [sel, setSel] = useState([]);
  const [f, setF] = useState({});
  const [q, setQ] = useState("");
  useEffect(() => {
    if (!open) return;
    setSel([]); setF({}); setRows(null);
    api.get(`${base}/staff`).then((r) => setRows(r.data)).catch(() => setRows({ staff: [], shifts: [] }));
  }, [open, base]);
  const list = (rows?.staff || []).filter((x) => !x.in_control_room && (!q || x.nome.toLowerCase().includes(q.toLowerCase())));
  const tog = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const submit = async () => { if (await onSubmit({ staff_ids: sel, ...f })) onOpenChange(false); };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[95vw] max-w-xl overflow-y-auto" data-testid="cr-staff-import">
        <DialogHeader><DialogTitle className="font-display">Assegna da Staff / Volontari</DialogTitle></DialogHeader>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca persona…" data-testid="cr-staff-search" />
        <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-100 p-1">
          {!rows ? <div className="p-3 text-xs text-slate-400">Caricamento…</div> : list.map((x) => (
            <label key={x.staff_id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-50" data-testid={`cr-staff-row-${x.staff_id}`}>
              <input type="checkbox" className="h-4 w-4 accent-[#0ABAB5]" checked={sel.includes(x.staff_id)} onChange={() => tog(x.staff_id)} />
              <span className="flex-1 truncate">{x.nome}</span><span className="text-[11px] text-slate-400">{[x.categoria, x.team].filter(Boolean).join(" · ")}</span>
            </label>))}
          {rows && !list.length && <div className="p-3 text-xs text-slate-400" data-testid="cr-staff-empty">Nessuna persona disponibile per questo evento in Staff / Volontari.</div>}
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <select className={S} value={f.post_id || ""} onChange={(e) => setF({ ...f, post_id: e.target.value || null })} data-testid="cr-staff-post"><option value="">Postazione…</option>{sortIt(d.posts, (p) => p.nome).map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</select>
          <select className={S} value={f.sector_id || ""} onChange={(e) => setF({ ...f, sector_id: e.target.value || null })} data-testid="cr-staff-sector"><option value="">Settore…</option>{sortIt(d.sectors, (s) => s.nome).map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}</select>
          <select className={S} value={f.caposquadra_staff_id || ""} onChange={(e) => setF({ ...f, caposquadra_staff_id: e.target.value || null })} data-testid="cr-staff-leader"><option value="">Caposquadra…</option>
            {(rows?.staff || []).filter((x) => sel.includes(x.staff_id)).map((x) => <option key={x.staff_id} value={x.staff_id}>{x.nome}</option>)}</select>
        </div>
        <DialogFooter><Button disabled={!sel.length} onClick={submit} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-staff-import-submit">Assegna {sel.length || ""}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ItvSettings({ v, setV, d }) {
  const types = v.itv_types || [];
  const setT = (i, k, x) => setV({ ...v, itv_types: types.map((c, j) => (j === i ? { ...c, [k]: x } : c)) });
  const used = new Set(d.interventions.map((i) => i.tipologia));
  return (
    <div className="space-y-2 border-t border-slate-100 pt-3" data-testid="cr-settings-itv">
      <div className="text-xs font-semibold text-slate-600">Interventi</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <Input value={v.centrale_tel || ""} disabled={!d.perms.contacts} onChange={(e) => setV({ ...v, centrale_tel: e.target.value })} placeholder="Telefono Control Room (per gli operatori)" data-testid="cr-settings-centrale-tel" />
        <label className="flex items-center gap-2 text-xs">Avviso se non confermato dopo<Input type="number" min="1" max="60" value={v.confirm_timeout_min || 3} onChange={(e) => setV({ ...v, confirm_timeout_min: e.target.value })} className="h-9 w-16" data-testid="cr-settings-timeout" />min</label>
        <label className="flex items-center gap-2 text-xs sm:col-span-2"><input type="checkbox" checked={!!v.assign_sets_busy} onChange={(e) => setV({ ...v, assign_sets_busy: e.target.checked })} data-testid="cr-settings-busy" />All'assegnazione la risorsa disponibile diventa IMPEGNATA</label>
      </div>
      <div className="text-xs font-semibold text-slate-600">Tipologie di intervento</div>
      {types.map((t, i) => (
        <div key={t.key} className="flex flex-wrap items-center gap-1.5" data-testid={`cr-itvtype-${t.key}`}>
          <input type="color" value={t.color} onChange={(e) => setT(i, "color", e.target.value)} className="h-9 w-9 shrink-0 rounded border border-slate-200" />
          <Input value={t.label} onChange={(e) => setT(i, "label", e.target.value)} className="h-9 min-w-0 flex-1" data-testid={`cr-itvtype-label-${t.key}`} />
          <select value={t.icon} onChange={(e) => setT(i, "icon", e.target.value)} className="h-9 w-24 rounded-md border border-slate-200 px-1 text-xs">{ICON_NAMES.map((n) => <option key={n} value={n}>{n}</option>)}</select>
          <select value={t.priorita} onChange={(e) => setT(i, "priorita", e.target.value)} className="h-9 rounded-md border border-slate-200 px-1 text-xs" data-testid={`cr-itvtype-prio-${t.key}`}>{["bassa", "media", "alta", "critica"].map((p) => <option key={p} value={p}>{p}</option>)}</select>
          <Input value={t.gruppo || ""} onChange={(e) => setT(i, "gruppo", e.target.value)} placeholder="Gruppo operativo" className="h-9 w-28" />
          <Button variant="ghost" size="icon" disabled={used.has(t.key)} onClick={() => setV({ ...v, itv_types: types.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></Button>
        </div>))}
      <Button variant="outline" size="sm" onClick={() => setV({ ...v, itv_types: [...types, { key: `itv_${Date.now().toString(36)}`, label: "Nuova tipologia", icon: "MapPin", color: "#64748B", priorita: "media", gruppo: "" }] })} data-testid="cr-itvtype-add"><Plus className="mr-1 h-4 w-4" />Aggiungi tipologia</Button>
    </div>
  );
}

// Responsabile, percorso e categorie personalizzabili delle postazioni.
export function SettingsDialog({ open, onOpenChange, d, onSubmit }) {
  const [v, setV] = useState({});
  useEffect(() => { if (open) setV({ responsabile: d.settings.responsabile || "", responsabile_tel: d.settings.responsabile_tel || "", route_map_id: d.settings.route_map_id || "", categories: d.settings.categories,
    centrale_tel: d.settings.centrale_tel || "", itv_types: d.itv_types, assign_sets_busy: d.settings.assign_sets_busy ?? true, confirm_timeout_min: d.settings.confirm_timeout_min || 3 }); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const cats = v.categories || [];
  const setCat = (i, k, x) => setV({ ...v, categories: cats.map((c, j) => (j === i ? { ...c, [k]: x } : c)) });
  const used = new Set(d.posts.map((p) => p.categoria));
  const submit = async () => {
    const body = { ...v, route_map_id: v.route_map_id || null, version: d.settings.version };
    if (!d.perms.contacts) { delete body.responsabile_tel; delete body.centrale_tel; }
    body.confirm_timeout_min = Number(body.confirm_timeout_min) || 3;
    if (await onSubmit(body)) onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[95vw] max-w-xl overflow-y-auto" data-testid="cr-settings">
        <DialogHeader><DialogTitle className="font-display">Impostazioni Control Room</DialogTitle></DialogHeader>
        <div className="grid gap-2 sm:grid-cols-2">
          <Input value={v.responsabile || ""} onChange={(e) => setV({ ...v, responsabile: e.target.value })} placeholder="Responsabile Control Room" data-testid="cr-settings-resp" />
          <Input value={v.responsabile_tel || ""} disabled={!d.perms.contacts} onChange={(e) => setV({ ...v, responsabile_tel: e.target.value })} placeholder="Telefono responsabile" data-testid="cr-settings-tel" />
          <select className={`${S} sm:col-span-2`} value={v.route_map_id || ""} onChange={(e) => setV({ ...v, route_map_id: e.target.value })} data-testid="cr-settings-route">
            <option value="">{d.routes.length ? "Percorso: primo GPX disponibile" : "Nessun percorso in Percorsi Eventi"}</option>{d.routes.map((r) => <option key={r.map_id} value={r.map_id}>{r.nome} ({r.format})</option>)}</select>
        </div>
        <div className="text-xs font-semibold text-slate-600">Categorie postazioni</div>
        <div className="space-y-1.5">{cats.map((c, i) => (
          <div key={c.key} className="flex items-center gap-1.5" data-testid={`cr-cat-${c.key}`}>
            <input type="color" value={c.color} onChange={(e) => setCat(i, "color", e.target.value)} className="h-9 w-9 shrink-0 rounded border border-slate-200" />
            <Input value={c.label} onChange={(e) => setCat(i, "label", e.target.value)} className="h-9 min-w-0 flex-1" data-testid={`cr-cat-label-${c.key}`} />
            <select value={c.icon} onChange={(e) => setCat(i, "icon", e.target.value)} className="h-9 w-28 rounded-md border border-slate-200 px-1 text-xs">{ICON_NAMES.map((n) => <option key={n} value={n}>{n}</option>)}</select>
            <Button variant="ghost" size="icon" disabled={used.has(c.key)} title={used.has(c.key) ? "Usata da una postazione" : "Rimuovi"} onClick={() => setV({ ...v, categories: cats.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></Button>
          </div>))}</div>
        <Button variant="outline" size="sm" onClick={() => setV({ ...v, categories: [...cats, { key: `cat_${Date.now().toString(36)}`, label: "Nuova categoria", icon: "MapPin", color: "#64748B" }] })} data-testid="cr-cat-add"><Plus className="mr-1 h-4 w-4" />Aggiungi categoria</Button>
        <ItvSettings v={v} setV={setV} d={d} />
        <DialogFooter><Button onClick={submit} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-settings-submit">Salva</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
