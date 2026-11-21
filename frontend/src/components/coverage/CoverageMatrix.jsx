import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const fmtDay = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "2-digit" });

export default function CoverageMatrix({ params, version, onPick }) {
  const [m, setM] = useState(null);
  useEffect(() => {
    const { date, ...rest } = params; // eslint-disable-line no-unused-vars
    api.get("/staff-coverage/matrix", { params: rest }).then(({ data }) => setM(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [params, version]);
  if (!m) return <p className="text-sm text-slate-400">Caricamento…</p>;
  if (!m.days.length) return <p className="text-sm text-slate-400" data-testid="cov-matrix-empty">Nessun giorno con disponibilità per questo evento.</p>;
  const max = Math.max(1, ...m.rows.flatMap((r) => r.cells));
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto" data-testid="cov-matrix">
      <table className="text-sm min-w-full">
        <thead><tr className="bg-slate-50 text-xs text-slate-500"><th className="px-3 py-2 text-left sticky left-0 bg-slate-50">Fascia</th>
          {m.days.map((d) => <th key={d} className="px-3 py-2 whitespace-nowrap">{fmtDay(d)}{m.tbc[d] > 0 && <div className="text-[10px] text-amber-600 font-normal">{m.tbc[d]} da confermare</div>}</th>)}</tr></thead>
        <tbody>{m.rows.map((r) => (
          <tr key={r.start} className="border-t border-slate-100">
            <td className="px-3 py-1.5 text-xs font-medium text-slate-600 whitespace-nowrap sticky left-0 bg-white">{r.start}–{r.end}</td>
            {r.cells.map((n, i) => (
              <td key={m.days[i]} className="px-1 py-1 text-center">
                <button type="button" onClick={() => onPick(m.days[i])} className="w-full min-w-[52px] rounded py-1 tabular-nums" style={{ backgroundColor: n ? `rgba(10,186,181,${0.15 + 0.6 * (n / max)})` : "#F8FAFC" }} data-testid={`cov-cell-${m.days[i]}-${r.start}`}>{n}</button>
              </td>))}
          </tr>))}</tbody>
      </table>
      <p className="text-xs text-slate-400 px-3 py-2">Clicca una cella per aprire la giornata e il dettaglio delle persone.</p>
    </div>
  );
}
