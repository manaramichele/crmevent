import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FileSpreadsheet, FileText, Printer, Plus, Trash2, Layers, X } from "lucide-react";

const n = (x) => (Number.isInteger(x) ? x : Math.round(x * 100) / 100);

async function getFile(url, name, print) {
  const w = print ? window.open("", "_blank") : null;
  try {
    const { data } = await api.get(url, { params: print ? { inline: 1 } : {}, responseType: "blob" });
    const u = URL.createObjectURL(data);
    if (w) { w.location.href = u; return; }
    const a = document.createElement("a");
    a.href = u; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 60000);
  } catch { if (w) w.close(); toast.error("Esportazione non riuscita"); }
}

function Cell({ value, onSave, type = "text", disabled, testid, w = "w-28" }) {
  const [v, setV] = useState(value ?? "");
  useEffect(() => { setV(value ?? ""); }, [value]);
  const commit = () => { const out = type === "number" ? Number(String(v).replace(",", ".")) || 0 : String(v).trim(); if (out !== (value ?? (type === "number" ? 0 : ""))) onSave(out); };
  return <Input value={v} type={type === "number" ? "text" : "text"} inputMode={type === "number" ? "decimal" : undefined} disabled={disabled} onChange={(e) => setV(e.target.value)} onBlur={commit}
    onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()} className={`h-8 ${w} text-xs`} data-testid={testid} />;
}

function Row({ r, statuses, ro, save, onComps, onDelete }) {
  const s = (p) => save(r.key, p);
  const tid = r.key.replace(/[^A-Za-z0-9]+/g, "-");
  return (
    <tr className="border-b border-slate-100 align-top" data-testid={`bom-row-${tid}`}>
      <td className="p-1">{r.source === "manual" ? <Cell value={r.categoria} onSave={(v) => s({ categoria: v })} disabled={ro} testid={`bom-cat-${tid}`} w="w-24" /> : <span className="text-xs">{r.categoria}</span>}</td>
      <td className="p-1"><Cell value={r.code} onSave={(v) => s({ code: v })} disabled={ro} testid={`bom-code-${tid}`} w="w-28" /></td>
      <td className="p-1"><Cell value={r.description} onSave={(v) => s({ description: v })} disabled={ro} testid={`bom-desc-${tid}`} w="w-48" />
        {r.source === "component" && <div className="mt-0.5 text-[10px] text-slate-400">componente</div>}</td>
      <td className="p-1"><Cell value={r.unit} onSave={(v) => s({ unit: v })} disabled={ro} testid={`bom-unit-${tid}`} w="w-14" /></td>
      <td className="p-1 text-right text-xs font-semibold" data-testid={`bom-map-${tid}`}>{n(r.map_qty)}</td>
      <td className="p-1"><Cell type="number" value={r.adjust} onSave={(v) => s({ adjust: v })} disabled={ro} testid={`bom-adj-${tid}`} w="w-16" /></td>
      <td className="p-1 text-right text-sm font-bold" data-testid={`bom-total-${tid}`}>{n(r.total)}</td>
      <td className="p-1"><Cell value={r.supplier} onSave={(v) => s({ supplier: v })} disabled={ro} testid={`bom-sup-${tid}`} w="w-28" /></td>
      <td className="p-1"><Cell value={r.notes} onSave={(v) => s({ notes: v })} disabled={ro} testid={`bom-notes-${tid}`} w="w-36" /></td>
      <td className="p-1"><select value={r.status} disabled={ro} onChange={(e) => s({ status: e.target.value })} className="h-8 rounded-md border border-slate-200 px-1 text-xs" data-testid={`bom-status-${tid}`}>
        {Object.entries(statuses).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></td>
      <td className="p-1 whitespace-nowrap">
        {r.source !== "manual" && !ro && <button type="button" title="Componenti" onClick={() => onComps(r.parent || r.key)} className="p-1 text-slate-500 hover:text-slate-900" data-testid={`bom-comps-${tid}`}><Layers className="h-4 w-4" /></button>}
        {r.source === "manual" && !ro && <button type="button" title="Elimina" onClick={() => onDelete(r.key.slice(2))} className="p-1 text-slate-500 hover:text-red-600" data-testid={`bom-del-${tid}`}><Trash2 className="h-4 w-4" /></button>}
      </td>
    </tr>
  );
}

function CompEditor({ type, items, onSave, onClose }) {
  const [list, setList] = useState(items.map((c) => ({ ...c })));
  const set = (i, p) => setList(list.map((c, j) => (j === i ? { ...c, ...p } : c)));
  return (
    <div className="rounded-xl border border-tiffany/50 bg-tiffany-light/40 p-3 space-y-2" data-testid="bom-comp-editor">
      <div className="flex items-center gap-2 text-sm font-semibold"><Layers className="h-4 w-4" />Componenti per 1 × {type.nome}
        <button type="button" onClick={onClose} className="ml-auto p-1" data-testid="bom-comp-close"><X className="h-4 w-4" /></button></div>
      <p className="text-xs text-slate-600">Ogni oggetto «{type.nome}» sulla mappa genera questi componenti al posto dell'oggetto stesso. Lascia vuoto per contare l'oggetto intero.</p>
      {list.map((c, i) => <div key={i} className="flex flex-wrap gap-2" data-testid={`bom-comp-${i}`}>
        <Input value={c.qty} inputMode="decimal" onChange={(e) => set(i, { qty: e.target.value })} className="h-8 w-16 text-xs" data-testid={`bom-comp-qty-${i}`} />
        <Input value={c.description} placeholder="Es. Zavorra" onChange={(e) => set(i, { description: e.target.value })} className="h-8 w-48 text-xs" data-testid={`bom-comp-desc-${i}`} />
        <Input value={c.unit} onChange={(e) => set(i, { unit: e.target.value })} className="h-8 w-14 text-xs" data-testid={`bom-comp-unit-${i}`} />
        <Input value={c.code || ""} placeholder="Codice" onChange={(e) => set(i, { code: e.target.value })} className="h-8 w-28 text-xs" data-testid={`bom-comp-code-${i}`} />
        <button type="button" onClick={() => setList(list.filter((_, j) => j !== i))} className="p-1 text-slate-500 hover:text-red-600" data-testid={`bom-comp-del-${i}`}><Trash2 className="h-4 w-4" /></button></div>)}
      <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => setList([...list, { qty: 1, description: "", unit: "pz", code: "" }])} data-testid="bom-comp-add"><Plus className="mr-1 h-4 w-4" />Aggiungi componente</Button>
        <Button size="sm" onClick={() => onSave(list.filter((c) => c.description.trim() && Number(String(c.qty).replace(",", ".")) > 0).map((c) => ({ ...c, qty: Number(String(c.qty).replace(",", ".")) })))} className="bg-tiffany text-slate-900 hover:bg-tiffany-hover" data-testid="bom-comp-save">Salva componenti</Button>
      </div>
    </div>
  );
}

function Filters({ rows, f, setF, statuses }) {
  const cats = [...new Set(rows.map((r) => r.categoria))].sort();
  const sups = [...new Set(rows.map((r) => r.supplier).filter(Boolean))].sort();
  const sel = "h-8 rounded-md border border-slate-200 px-1 text-xs";
  return (
    <div className="flex flex-wrap gap-2" data-testid="bom-filters">
      <select value={f.cat} onChange={(e) => setF({ ...f, cat: e.target.value })} className={sel} data-testid="bom-filter-cat"><option value="">Tutte le categorie</option>{cats.map((c) => <option key={c}>{c}</option>)}</select>
      <select value={f.sup} onChange={(e) => setF({ ...f, sup: e.target.value })} className={sel} data-testid="bom-filter-sup"><option value="">Tutti i fornitori</option>{sups.map((c) => <option key={c}>{c}</option>)}</select>
      {statuses && <select value={f.st} onChange={(e) => setF({ ...f, st: e.target.value })} className={sel} data-testid="bom-filter-status"><option value="">Tutti gli stati</option>{Object.entries(statuses).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}
    </div>
  );
}

const Exports = ({ base, name }) => (
  <div className="flex flex-wrap gap-2">
    <Button size="sm" variant="outline" onClick={() => getFile(`${base}/export.xlsx`, `${name}.xlsx`)} data-testid="bom-export-xlsx"><FileSpreadsheet className="mr-1 h-4 w-4" />Esporta Excel</Button>
    <Button size="sm" variant="outline" onClick={() => getFile(`${base}/export.pdf`, `${name}.pdf`)} data-testid="bom-export-pdf"><FileText className="mr-1 h-4 w-4" />Esporta PDF</Button>
    <Button size="sm" variant="outline" onClick={() => getFile(`${base}/export.pdf`, `${name}.pdf`, true)} data-testid="bom-print"><Printer className="mr-1 h-4 w-4" />Stampa</Button>
  </div>
);

function ProjectBom({ proj, refresh }) {
  const [d, setD] = useState(null);
  const [f, setF] = useState({ cat: "", sup: "", st: "" });
  const [comp, setComp] = useState(null);
  const base = `/planner/projects/${proj.id}/bom`;
  const load = useCallback(() => api.get(base).then(({ data }) => setD(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), [base]);
  useEffect(() => { load(); }, [load, refresh]);
  const call = async (p) => { try { const { data } = await p; setD(data); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  if (!d) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const rows = d.rows.filter((r) => (!f.cat || r.categoria === f.cat) && (!f.sup || r.supplier === f.sup) && (!f.st || r.status === f.st));
  const type = comp && (d.types.find((t) => t.key === comp) || { key: comp, nome: comp.split("|").slice(1).join("|") });
  return (
    <div className="space-y-3" data-testid="bom-project">
      <div className="flex flex-wrap items-center gap-2"><Filters rows={d.rows} f={f} setF={setF} statuses={d.statuses} /><div className="ml-auto"><Exports base={base} name={`distinta-${proj.nome}`} /></div></div>
      {type && <CompEditor key={type.key} type={type} items={d.components[type.key] || []} onClose={() => setComp(null)} onSave={(items) => { call(api.put(`${base}/components/${encodeURIComponent(type.key)}`, { items })); setComp(null); }} />}
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[1100px] text-left">
          <thead className="bg-slate-50 text-[11px] uppercase text-slate-500"><tr>{["Categoria", "Codice materiale", "Descrizione", "Unità", "Q.tà da mappa", "Rettifica", "Q.tà totale", "Fornitore", "Note", "Stato", ""].map((h) => <th key={h} className="p-2 font-semibold">{h}</th>)}</tr></thead>
          <tbody>{rows.map((r) => <Row key={r.key} r={r} statuses={d.statuses} ro={d.read_only} save={(k, p) => call(api.put(`${base}/rows/${encodeURIComponent(k)}`, p))} onComps={setComp} onDelete={(mid) => call(api.delete(`${base}/manual/${mid}`))} />)}</tbody>
        </table>
        {!rows.length && <p className="p-4 text-sm text-slate-500" data-testid="bom-empty">Nessun materiale: inserisci oggetti dalla libreria sulla mappa oppure aggiungi un materiale manuale.</p>}
      </div>
      {!d.read_only && <Button size="sm" variant="outline" onClick={() => call(api.post(`${base}/manual`, { description: "Nuovo materiale", categoria: f.cat || "Altro", adjust: 1 }))} data-testid="bom-add-manual"><Plus className="mr-1 h-4 w-4" />Aggiungi materiale non presente sulla mappa</Button>}
      <p className="text-xs text-slate-500">Quantità totale = quantità da mappa + rettifica manuale (mai sotto zero). La quantità da mappa si aggiorna da sola quando inserisci, duplichi, modifichi o elimini oggetti.</p>
    </div>
  );
}

function EventBom({ eid, evName }) {
  const [d, setD] = useState(null);
  const [f, setF] = useState({ cat: "", sup: "", st: "" });
  useEffect(() => { api.get(`/planner/events/${eid}/bom`).then(({ data }) => setD(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))); }, [eid]);
  if (!d) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const rows = d.rows.filter((r) => !f.cat || r.categoria === f.cat);
  return (
    <div className="space-y-3" data-testid="bom-event">
      <div className="flex flex-wrap items-center gap-2"><Filters rows={d.rows} f={f} setF={setF} /><div className="ml-auto"><Exports base={`/planner/events/${eid}/bom`} name={`riepilogo-materiali-${evName}`} /></div></div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[700px] text-left text-xs">
          <thead className="bg-slate-50 text-[11px] uppercase text-slate-500"><tr><th className="p-2">Categoria</th><th className="p-2">Codice</th><th className="p-2">Descrizione</th><th className="p-2">Unità</th>
            {d.projects.map((p) => <th key={p.id} className="p-2 text-right">{p.nome}</th>)}<th className="p-2 text-right">Totale evento</th></tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-slate-100" data-testid={`bom-event-row-${i}`}><td className="p-2">{r.categoria}</td><td className="p-2">{r.code}</td><td className="p-2">{r.description}</td><td className="p-2">{r.unit}</td>
            {d.projects.map((p) => <td key={p.id} className="p-2 text-right">{r.by_project[p.id] ? n(r.by_project[p.id]) : "–"}</td>)}<td className="p-2 text-right text-sm font-bold" data-testid={`bom-event-total-${i}`}>{n(r.total)}</td></tr>)}</tbody>
        </table>
        {!rows.length && <p className="p-4 text-sm text-slate-500">Nessun materiale nei progetti dell'evento.</p>}
      </div>
      <p className="text-xs text-slate-500">Somma delle distinte di tutti i progetti attivi dell'evento: ogni materiale è contato una volta per progetto, con la suddivisione per progetto.</p>
    </div>
  );
}

export default function BomPanel({ open, onClose, proj, eid, evName, refresh }) {
  const [tab, setTab] = useState("project");
  const cls = (t) => `rounded-md px-3 py-1.5 text-sm font-semibold ${tab === t ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[92dvh] w-[96vw] max-w-[1280px] overflow-y-auto" data-testid="bom-panel">
        <DialogHeader><DialogTitle>Distinta materiali</DialogTitle></DialogHeader>
        <div className="flex flex-wrap gap-1"><button type="button" className={cls("project")} onClick={() => setTab("project")} data-testid="bom-tab-project">Progetto: {proj?.nome}</button>
          <button type="button" className={cls("event")} onClick={() => setTab("event")} data-testid="bom-tab-event">Riepilogo materiali evento</button></div>
        {tab === "project" ? proj && <ProjectBom proj={proj} refresh={refresh} /> : <EventBom eid={eid} evName={evName} />}
      </DialogContent>
    </Dialog>
  );
}
