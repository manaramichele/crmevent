import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2 } from "lucide-react";

const inp = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";

export default function CoverageNeeds({ eventoId, date, mansioni, pct, onChanged }) {
  const [items, setItems] = useState([]);
  const [f, setF] = useState({ mansione: "", start: "08:00", end: "10:00", needed: 1 });
  const [margin, setMargin] = useState(pct);
  const load = () => api.get("/staff-coverage/needs", { params: { evento_id: eventoId } }).then(({ data }) => setItems(data)).catch(() => {});
  useEffect(() => { load(); }, [eventoId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setMargin(pct); }, [pct]);
  const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
  const add = async () => {
    if (!f.mansione.trim()) { toast.error("Indica la mansione"); return; }
    try { await api.post("/staff-coverage/needs", { ...f, evento_id: eventoId, date, needed: Number(f.needed) }); toast.success("Fabbisogno aggiunto"); load(); onChanged(); } catch (e) { err(e); }
  };
  const del = async (id) => { try { await api.delete(`/staff-coverage/needs/${id}`); load(); onChanged(); } catch (e) { err(e); } };
  const saveMargin = async () => { try { await api.put("/staff-coverage/config", { yellow_margin_pct: Number(margin) }); toast.success("Soglia salvata"); onChanged(); } catch (e) { err(e); } };
  const today = items.filter((n) => n.date === date);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3" data-testid="cov-needs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-slate-900">Fabbisogno minimo del giorno</h3>
        <label className="text-xs text-slate-500 flex items-center gap-2">Giallo se il margine sul minimo è sotto il
          <Input type="number" min={0} max={100} value={margin} onChange={(e) => setMargin(e.target.value)} className="h-8 w-16" data-testid="cov-margin" />%
          <Button size="sm" variant="outline" onClick={saveMargin} data-testid="cov-margin-save">Salva</Button></label>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <input list="cov-mansioni" className={`${inp} w-48`} placeholder="Mansione (es. Segreteria)" value={f.mansione} onChange={(e) => setF({ ...f, mansione: e.target.value })} data-testid="cov-need-mansione" />
        <datalist id="cov-mansioni">{mansioni.map((m) => <option key={m} value={m} />)}</datalist>
        <input type="time" className={inp} value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} data-testid="cov-need-start" />
        <span className="text-slate-400">–</span>
        <input type="time" className={inp} value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} data-testid="cov-need-end" />
        <input type="number" min={1} className={`${inp} w-24`} value={f.needed} onChange={(e) => setF({ ...f, needed: e.target.value })} data-testid="cov-need-n" />
        <Button size="sm" onClick={add} className="bg-tiffany hover:bg-tiffany-hover text-slate-900" data-testid="cov-need-add"><Plus className="w-4 h-4 mr-1" />Aggiungi</Button>
      </div>
      {today.length === 0 ? <p className="text-sm text-slate-400" data-testid="cov-needs-empty">Nessun fabbisogno impostato: vengono mostrate solo le disponibilità.</p> : (
        <ul className="divide-y divide-slate-100 text-sm">{today.map((n) => (
          <li key={n.id} className="flex items-center justify-between py-1.5" data-testid={`cov-need-${n.id}`}>
            <span><b>{n.mansione}</b> · {n.start}–{n.end} · servono {n.needed}</span>
            <button type="button" onClick={() => del(n.id)} className="text-slate-400 hover:text-red-500" data-testid={`cov-need-del-${n.id}`}><Trash2 className="w-4 h-4" /></button>
          </li>))}</ul>)}
    </div>
  );
}
