import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { sortIt } from "@/lib/sortOptions";

const sel = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm w-full";
const TONE = { create: "text-emerald-700", update: "text-emerald-700", already: "text-slate-500", skip: "text-amber-700" };
const fmtD = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "2-digit" });

function Preview({ pv }) {
  return (
    <div className="space-y-2" data-testid="bulk-preview">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-sm">
        {[["Persone trovate", pv.total, "bulk-total"], ["Da aggiornare", pv.to_update, "bulk-to-update"], ["Hanno già la fascia", pv.already, "bulk-already"], ["Escluse", pv.skipped, "bulk-skipped"]].map(([l, n, t]) => (
          <div key={t} className="rounded-lg border border-slate-200 py-2"><div className="text-lg font-semibold tabular-nums" data-testid={t}>{n}</div><div className="text-xs text-slate-500">{l}</div></div>))}
      </div>
      <div className="max-h-64 overflow-y-auto divide-y divide-slate-100 border border-slate-100 rounded-lg">
        {pv.people.map((p) => (
          <div key={p.id} className="px-3 py-1.5 text-sm flex flex-col sm:flex-row sm:items-center gap-1" data-testid={`bulk-person-${p.id}`}>
            <span className="font-medium text-slate-800 sm:w-56">{p.cognome} {p.nome}</span>
            <span className="text-xs text-slate-500 sm:w-40">{p.mansioni.join(", ")}</span>
            <span className={`text-xs ${TONE[p.action]}`}>{p.label}</span>
          </div>))}
        {!pv.people.length && <p className="text-sm text-slate-400 text-center py-4">Nessuna persona con queste mansioni.</p>}
      </div>
      {pv.skipped > 0 && <p className="text-xs text-amber-700">Le persone escluse non vengono modificate: aggiornale dalla loro scheda.</p>}
    </div>
  );
}

export default function CoverageBulkDialog({ open, onClose, eventoId, rows, mansioni, onDone }) {
  const days = useMemo(() => [...new Set(rows.map((r) => r.date))], [rows]);
  const [f, setF] = useState({ date: "", fascia: "mattina", mansioni: [] });
  const [pv, setPv] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setF({ date: days[0] || "", fascia: "mattina", mansioni: [] }); setPv(null); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const slots = rows.filter((r) => r.date === f.date);
  const set = (k, v) => { setF((c) => ({ ...c, [k]: v })); setPv(null); };
  const toggleM = (m) => set("mansioni", f.mansioni.includes(m) ? f.mansioni.filter((x) => x !== m) : [...f.mansioni, m]);
  const body = { evento_id: eventoId, ...f };
  const preview = async () => {
    setBusy(true);
    try { const { data } = await api.post("/staff-coverage/bulk-fascia/preview", body); setPv(data); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  const apply = async () => {
    setBusy(true);
    try { const { data } = await api.post("/staff-coverage/bulk-fascia/apply", { ...body, token: pv.token }); toast.success(`Disponibilità aggiornate: ${data.updated}`); onDone(); onClose(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); if (e.response?.status === 409) setPv(null); }
    setBusy(false);
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="bulk-dialog">
        <DialogHeader><DialogTitle>Assegna una fascia per mansione</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">Aggiunge la fascia scelta a tutte le persone confermate (Staff o Volontari con stato Confermato) con le mansioni selezionate. Le altre disponibilità, i team e le mansioni restano invariati.</p>
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-xs text-slate-600 space-y-1">Giorno<select className={sel} value={f.date} onChange={(e) => set("date", e.target.value)} data-testid="bulk-date">{days.map((d) => <option key={d} value={d}>{fmtD(d)}</option>)}</select></label>
          <label className="text-xs text-slate-600 space-y-1">Fascia<select className={sel} value={f.fascia} onChange={(e) => set("fascia", e.target.value)} data-testid="bulk-fascia">
            {slots.map((s) => <option key={s.fascia} value={s.fascia}>{s.label}{s.start && s.end ? ` (${s.start}–${s.end})` : " (senza orari)"}</option>)}</select></label>
        </div>
        <div className="space-y-1">
          <div className="text-xs text-slate-600">Mansioni ({f.mansioni.length} selezionate)</div>
          <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto">
            {sortIt(mansioni).map((m) => (
              <label key={m} className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm cursor-pointer ${f.mansioni.includes(m) ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 text-slate-700"}`}>
                <input type="checkbox" className="sr-only" checked={f.mansioni.includes(m)} onChange={() => toggleM(m)} data-testid={`bulk-mansione-${m}`} />{m}</label>))}
            {!mansioni.length && <span className="text-sm text-slate-400">Nessuna mansione assegnata nell'evento.</span>}
          </div>
        </div>
        {pv && <Preview pv={pv} />}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} data-testid="bulk-cancel">Annulla</Button>
          {!pv ? <Button onClick={preview} disabled={busy || !f.date || !f.mansioni.length} data-testid="bulk-preview-btn">Anteprima</Button>
            : <Button onClick={apply} disabled={busy || !pv.to_update} data-testid="bulk-apply-btn">Conferma e aggiorna {pv.to_update} persone</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
