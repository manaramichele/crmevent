import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { FasciaPeopleDialog, LegacyDialog } from "./CoverageFasceDialogs";

const DOT = { green: "bg-emerald-500", yellow: "bg-amber-400", red: "bg-red-500" };
export const fmtDayLong = (d) => { const s = new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "2-digit" }); return s.charAt(0).toUpperCase() + s.slice(1); };

function NeedInput({ row, eventoId, onSaved }) {
  const [v, setV] = useState(row.needed ?? "");
  useEffect(() => { setV(row.needed ?? ""); }, [row.needed]);
  const save = async () => {
    const n = v === "" ? 0 : Number(v);
    if (Number.isNaN(n) || n < 0 || n === (row.needed || 0)) return;
    try { await api.put("/staff-coverage/fascia-needs", { evento_id: eventoId, date: row.date, fascia: row.fascia, needed: n }); onSaved(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return <input type="number" min={0} value={v} onChange={(e) => setV(e.target.value)} onBlur={save} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
    placeholder="—" className="w-16 h-8 rounded border border-slate-200 px-2 text-sm tabular-nums" data-testid={`fx-need-${row.date}-${row.fascia}`} />;
}

export default function CoverageFasce({ params, day, version, onOpenPerson }) {
  const [data, setData] = useState(null);
  const [pick, setPick] = useState(null);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    api.get("/staff-coverage/fasce", { params }).then(({ data: d }) => setData(d)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [params, version, tick]);
  if (!data) return <div className="text-sm text-slate-400">Caricamento…</div>;
  const rows = data.rows.filter((r) => !day || r.date === day);
  const open = (fn) => { setPick(null); setLegacyOpen(false); onOpenPerson(fn); };
  return (
    <div className="space-y-3" data-testid="cov-fasce">
      {data.legacy.length > 0 && (
        <button type="button" onClick={() => setLegacyOpen(true)} className="w-full sm:w-auto inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 hover:bg-amber-100" data-testid="cov-legacy-indicator">
          <AlertTriangle className="w-4 h-4" />Disponibilità da aggiornare: <b data-testid="cov-legacy-count">{data.legacy.length}</b>
        </button>)}
      <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
        <table className="w-full text-sm min-w-[640px]" data-testid="cov-fasce-table">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
            <tr>{["Giorno", "Fascia", "Orario", "Disponibili", "Assegnati", "Necessari", ""].map((h) => <th key={h} className="text-left font-medium px-3 py-2">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.date}-${r.fascia}`} className="border-t border-slate-100" data-testid={`fx-row-${r.date}-${r.fascia}`}>
                <td className="px-3 py-2 whitespace-nowrap text-slate-700">{fmtDayLong(r.date)}</td>
                <td className="px-3 py-2"><button type="button" onClick={() => setPick(r)} className="font-medium text-tiffany-fg underline-offset-2 hover:underline" data-testid={`fx-open-${r.date}-${r.fascia}`}>{r.label}</button></td>
                <td className="px-3 py-2 tabular-nums text-slate-600">{r.start && r.end ? `${r.start}–${r.end}` : "Orario non impostato"}</td>
                <td className="px-3 py-2 tabular-nums" data-testid={`fx-avail-${r.date}-${r.fascia}`}><b>{r.available}</b>
                  {r.partial > 0 && <span className="ml-1.5 text-xs text-slate-500">+{r.partial} parziali</span>}
                  {r.tbc > 0 && <span className="ml-1.5 text-xs text-amber-700">+{r.tbc} da verificare</span>}
                  {r.changed > 0 && <span className="ml-1.5 text-xs text-red-600" title="Persone che hanno scelto la fascia con orari diversi da quelli attuali">· {r.changed} con orari superati</span>}</td>
                <td className="px-3 py-2 tabular-nums" data-testid={`fx-assigned-${r.date}-${r.fascia}`}>{r.assigned}</td>
                <td className="px-3 py-2"><NeedInput row={r} eventoId={params.evento_id} onSaved={() => setTick((t) => t + 1)} /></td>
                <td className="px-3 py-2">{r.status && <span className={`inline-block w-2.5 h-2.5 rounded-full ${DOT[r.status]}`} data-testid={`fx-status-${r.date}-${r.fascia}-${r.status}`} />}</td>
              </tr>))}
            {!rows.length && <tr><td colSpan={7} className="px-3 py-8 text-center text-slate-400" data-testid="fx-empty">Nessuna fascia attiva: configura Mattina e Pomeriggio nella scheda dell'evento.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">Disponibili = copertura dell'intera fascia. Le coperture parziali e gli orari da verificare (vecchio modulo) sono indicati a parte e non contano come disponibili. Assegnati = disponibili con mansione o team. Necessari: inserisci il numero per ogni fascia.</p>
      <FasciaPeopleDialog row={pick} onClose={() => setPick(null)} onOpenPerson={open} />
      <LegacyDialog open={legacyOpen} list={data.legacy} onClose={() => setLegacyOpen(false)} onOpenPerson={open} />
    </div>
  );
}
