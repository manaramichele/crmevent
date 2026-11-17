import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import api from "@/lib/api";

// Importa in Control Room i punti e le strutture già disegnati in Event Planner, collegandoli all'elemento originale.
export function PlannerImport({ open, onOpenChange, d, base, call }) {
  const [data, setData] = useState(null);
  const [pid, setPid] = useState("");
  const [sel, setSel] = useState([]);
  const [cats, setCats] = useState({});
  const [opt, setOpt] = useState({ with_staff: true, update_positions: false });
  useEffect(() => {
    if (!open) return;
    setData(null); setSel([]); setCats({});
    api.get(`${base}/planner`).then((r) => { setData(r.data.projects); const p = r.data.projects[0]; if (p) { setPid(p.id); setSel(p.features.filter((f) => !f.imported_post_id).map((f) => f.id)); } })
      .catch(() => setData([]));
  }, [open, base]);
  const pr = (data || []).find((p) => p.id === pid);
  const pick = (id) => { setPid(id); const p = data.find((x) => x.id === id); setSel(p.features.filter((f) => !f.imported_post_id).map((f) => f.id)); };
  const tog = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const submit = async () => {
    const r = await call("post", "/planner/import", { project_id: pid, feature_ids: sel, categories: cats, ...opt });
    if (r) { onOpenChange(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[96vw] max-w-2xl overflow-y-auto" data-testid="cr-planner-import">
        <DialogHeader><DialogTitle className="font-display">Importa postazioni da Event Planner</DialogTitle></DialogHeader>
        {!data ? <div className="text-sm text-slate-400">Caricamento progetti…</div> : !data.length ? <div className="text-sm text-slate-500" data-testid="cr-planner-empty">Nessun progetto Event Planner per questo evento.</div> : <>
          <select value={pid} onChange={(e) => pick(e.target.value)} className="h-10 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="cr-planner-project">{data.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.features.length} elementi)</option>)}</select>
          <div className="flex gap-3 text-xs"><button type="button" className="underline" onClick={() => setSel(pr.features.filter((f) => !f.imported_post_id).map((f) => f.id))}>Seleziona nuove</button><button type="button" className="underline" onClick={() => setSel([])}>Nessuna</button></div>
          <div className="max-h-[45vh] space-y-1 overflow-y-auto rounded-lg border border-slate-100 p-1">
            {pr?.features.map((f) => (
              <div key={f.id} className="flex flex-wrap items-center gap-2 rounded px-2 py-1.5 text-xs hover:bg-slate-50" data-testid={`cr-planner-row-${f.id}`}>
                <input type="checkbox" className="h-4 w-4 accent-[#0ABAB5]" checked={sel.includes(f.id)} onChange={() => tog(f.id)} data-testid={`cr-planner-check-${f.id}`} />
                <div className="min-w-0 flex-1"><b className="text-sm">{f.nome}</b> <span className="text-slate-400">{[f.livello, f.categoria, f.persone ? `${f.persone} persone assegnate` : null].filter(Boolean).join(" · ")}</span>
                  {f.imported_post_id && <span className="ml-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">GIÀ IMPORTATA</span>}</div>
                {!f.imported_post_id && <select value={cats[f.id] || f.suggested} onChange={(e) => setCats({ ...cats, [f.id]: e.target.value })} className="h-8 rounded-md border border-slate-200 px-1 text-xs" data-testid={`cr-planner-cat-${f.id}`}>
                  {d.settings.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select>}
              </div>))}
            {pr && !pr.features.length && <div className="p-2 text-xs text-slate-400">Nessun punto o struttura nel progetto.</div>}
          </div>
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={opt.with_staff} onChange={(e) => setOpt({ ...opt, with_staff: e.target.checked })} data-testid="cr-planner-with-staff" />Assegna anche le persone già collegate alle postazioni in Event Planner (con il loro turno)</label>
          <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={opt.update_positions} onChange={(e) => setOpt({ ...opt, update_positions: e.target.checked })} data-testid="cr-planner-update-pos" />Per quelle già importate, aggiorna la posizione con quella attuale di Event Planner</label>
        </>}
        <DialogFooter><Button disabled={!sel.length} onClick={submit} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-planner-submit">Importa {sel.length || ""}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
