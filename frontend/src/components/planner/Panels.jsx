import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Eye, EyeOff, Lock, Unlock, Plus, Copy, Trash2, Navigation, Link2 } from "lucide-react";
import { measures, anchorOf } from "./features";
import { fmtM, fmtM2 } from "@/lib/geo";

export function LibraryPanel({ library, placing, onPick }) {
  const [q, setQ] = useState("");
  const cats = [...new Set(library.map((x) => x.categoria))];
  const list = library.filter((x) => !q || x.nome.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="space-y-2" data-testid="planner-library">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca oggetti..." className="h-9" data-testid="planner-lib-search" />
      {cats.map((c) => { const items = list.filter((x) => x.categoria === c); return !items.length ? null : (
        <div key={c}><div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{c}</div>
          <div className="grid grid-cols-1 gap-1">{items.map((x) => (
            <button key={x.id} type="button" onClick={() => onPick(placing?.id === x.id ? null : x)} data-testid={`planner-lib-${x.id}`}
              className={`flex items-center gap-2 rounded-md border px-2 py-2 text-left text-xs transition-colors ${placing?.id === x.id ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white hover:border-tiffany"}`}>
              <span className="h-3 w-3 shrink-0 rounded-sm" style={{ background: x.colore }} />{x.nome}
            </button>))}</div></div>); })}
      {placing && <p className="text-[11px] text-slate-500">Tocca la mappa per posizionare "{placing.nome}".</p>}
    </div>
  );
}

export function LayersPanel({ layers, setLayers }) {
  const [n, setN] = useState("");
  const upd = (id, patch) => setLayers(layers.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  const add = () => { if (!n.trim()) return; setLayers([...layers, { id: Math.random().toString(36).slice(2, 10), nome: n.trim(), colore: "#0EA5E9", visibile: true, bloccato: false, ordine: layers.length }]); setN(""); };
  return (
    <div className="space-y-1" data-testid="planner-layers">
      {layers.map((l) => (
        <div key={l.id} className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs" data-testid={`planner-layer-${l.id}`}>
          <input type="color" value={l.colore} onChange={(e) => upd(l.id, { colore: e.target.value })} className="h-5 w-5 cursor-pointer rounded border-0 p-0" />
          <span className="flex-1 truncate">{l.nome}</span>
          <button type="button" onClick={() => upd(l.id, { visibile: !l.visibile })} className="p-1.5" aria-label="Visibilità" data-testid={`planner-layer-vis-${l.id}`}>{l.visibile ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4 text-slate-400" />}</button>
          <button type="button" onClick={() => upd(l.id, { bloccato: !l.bloccato })} className="p-1.5" aria-label="Blocco" data-testid={`planner-layer-lock-${l.id}`}>{l.bloccato ? <Lock className="h-4 w-4 text-amber-600" /> : <Unlock className="h-4 w-4 text-slate-400" />}</button>
        </div>))}
      <div className="flex gap-1 pt-1"><Input value={n} onChange={(e) => setN(e.target.value)} placeholder="Nuovo livello" className="h-8 text-xs" data-testid="planner-layer-new" />
        <Button size="sm" variant="outline" onClick={add} data-testid="planner-layer-add"><Plus className="h-4 w-4" /></Button></div>
    </div>
  );
}

const Num = ({ label, value, onChange, step = 0.5, testid }) => (
  <label className="block text-[11px] text-slate-500">{label}<Input type="number" step={step} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : +e.target.value)} className="h-9" data-testid={testid} /></label>
);

export function PropsPanel({ f, layers, onPatch, onDuplicate, onDelete }) {
  if (!f) return <p className="text-xs text-slate-500" data-testid="planner-props-empty">Seleziona un oggetto sulla mappa per vederne le proprietà.</p>;
  const p = f.properties, m = measures(f), a = anchorOf(f);
  const set = (k) => (v) => onPatch({ [k]: v });
  return (
    <div className="space-y-2 text-sm" data-testid="planner-props">
      <Input value={p.nome || ""} onChange={(e) => onPatch({ nome: e.target.value })} placeholder="Nome" className="h-9 font-medium" data-testid="planner-prop-nome" />
      <div className="text-[11px] text-slate-500">{p.categoria || p.tipo}</div>
      <label className="block text-[11px] text-slate-500">Livello
        <select className="mt-0.5 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" value={p.layer_id} onChange={(e) => onPatch({ layer_id: e.target.value })} data-testid="planner-prop-layer">
          {layers.map((l) => <option key={l.id} value={l.id}>{l.nome}</option>)}</select></label>
      {p.tipo === "box" && <div className="grid grid-cols-2 gap-2"><Num label="Larghezza (m)" value={p.larghezza} onChange={set("larghezza")} testid="planner-prop-w" /><Num label="Lunghezza (m)" value={p.lunghezza} onChange={set("lunghezza")} testid="planner-prop-l" /></div>}
      {p.tipo === "circle" && <Num label="Raggio (m)" value={p.raggio && +p.raggio.toFixed(1)} onChange={set("raggio")} testid="planner-prop-r" />}
      {p.tipo === "box" && <label className="block text-[11px] text-slate-500">Rotazione {Math.round(p.rotazione || 0)}°<input type="range" min="-180" max="180" value={p.rotazione || 0} onChange={(e) => onPatch({ rotazione: +e.target.value })} className="w-full accent-tiffany" data-testid="planner-prop-rot" /></label>}
      {p.tipo === "line" && p.passo && <Num label="Elemento (m)" value={p.passo} onChange={set("passo")} testid="planner-prop-passo" />}
      <div className="rounded-md bg-slate-50 p-2 text-xs text-slate-600" data-testid="planner-prop-measures">
        {m.lunghezza != null && <div>Lunghezza: <b>{fmtM(m.lunghezza)}</b>{m.pezzi ? <> · quantità indicativa: <b data-testid="planner-prop-pezzi">{m.pezzi}</b> (senza sovrapposizioni o aperture)</> : null}</div>}
        {m.area != null && <div>Superficie: <b data-testid="planner-prop-area">{fmtM2(m.area)}</b> · perimetro {fmtM(m.perimetro)}</div>}
        <div>Coordinate: {a[1].toFixed(6)}, {a[0].toFixed(6)}</div>
      </div>
      {p.collegamenti?.length > 0 && <div className="space-y-1 rounded-md border border-tiffany/40 bg-tiffany-light/40 p-2 text-xs" data-testid="planner-prop-links">
        <div className="flex items-center gap-1 font-semibold text-slate-700"><Link2 className="h-3.5 w-3.5" />Collegato in CRMEvent</div>
        {p.collegamenti.map((c) => <div key={c.area + c.testo}><b className="text-slate-700">{c.area}:</b> <span className="text-slate-600">{c.testo}</span></div>)}
      </div>}
      {p.tipo !== "measure" && <><Num label="Quantità" value={p.quantita} onChange={set("quantita")} step={1} testid="planner-prop-qty" />
        <label className="block text-[11px] text-slate-500">Colore <input type="color" value={p.colore || "#0ABAB5"} onChange={(e) => onPatch({ colore: e.target.value })} className="ml-1 h-6 w-8 align-middle" data-testid="planner-prop-color" /></label>
        <textarea value={p.note || ""} onChange={(e) => onPatch({ note: e.target.value })} placeholder="Note / descrizione" rows={2} className="w-full rounded-md border border-slate-200 p-2 text-sm" data-testid="planner-prop-note" /></>}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button size="sm" variant="outline" onClick={onDuplicate} data-testid="planner-prop-dup"><Copy className="mr-1 h-4 w-4" />Duplica</Button>
        <a href={`https://www.google.com/maps/dir/?api=1&destination=${a[1]},${a[0]}`} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center rounded-md border border-slate-200 px-3 text-xs" data-testid="planner-prop-nav"><Navigation className="mr-1 h-4 w-4" />Naviga</a>
        <Button size="sm" variant="ghost" className="text-red-600" onClick={() => window.confirm("Eliminare l'oggetto?") && onDelete()} data-testid="planner-prop-del"><Trash2 className="mr-1 h-4 w-4" />Elimina</Button>
      </div>
    </div>
  );
}
