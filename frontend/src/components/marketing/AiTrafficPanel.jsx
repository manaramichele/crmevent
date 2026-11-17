import { useEffect, useState } from "react";
import api from "@/lib/api";

const COLS = [["visits", "Visite"], ["visitors", "Visitatori"], ["registrations", "Registrazioni"], ["trials", "In prova"], ["subscriptions", "Abbonati"]];

export function AiTrafficPanel() {
  const [days, setDays] = useState(90);
  const [d, setD] = useState(null);
  useEffect(() => { setD(null); api.get(`/platform/ai-traffic?days=${days}`).then((r) => setD(r.data)).catch(() => setD({ rows: [], total_ai: {}, other: {} })); }, [days]);
  return (
    <div className="space-y-4" data-testid="ai-traffic-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-3xl text-sm text-slate-500">Visite e registrazioni arrivate da ChatGPT, Perplexity, Gemini, Copilot e Claude (referrer o utm_source). Le visite sono registrate solo per chi ha accettato i cookie analitici; registrazioni, prove e abbonamenti si riferiscono alle organizzazioni create nel periodo.</p>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid="ai-traffic-days">
          {[30, 90, 180, 365].map((n) => <option key={n} value={n}>Ultimi {n} giorni</option>)}
        </select>
      </div>
      {!d ? <div className="text-sm text-slate-400">Caricamento…</div> : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {COLS.map(([k, l]) => <div key={k} className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs font-semibold uppercase text-slate-400">{l} da AI</div><div className="mt-1 text-2xl font-bold" data-testid={`ai-total-${k}`}>{d.total_ai[k] ?? 0}</div></div>)}
          </div>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm" data-testid="ai-traffic-table">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-2">Assistente</th>{COLS.map(([k, l]) => <th key={k} className="px-4 py-2 text-right">{l}</th>)}</tr></thead>
              <tbody>
                {d.rows.map((r) => <tr key={r.ai} className="border-t border-slate-100" data-testid={`ai-row-${r.ai}`}><td className="px-4 py-2 font-medium">{r.name}</td>{COLS.map(([k]) => <td key={k} className="px-4 py-2 text-right">{r[k]}</td>)}</tr>)}
                <tr className="border-t border-slate-200 text-slate-500"><td className="px-4 py-2">Altre provenienze</td><td className="px-4 py-2 text-right">{d.other.visits ?? 0}</td><td className="px-4 py-2 text-right">{d.other.visitors ?? 0}</td><td className="px-4 py-2 text-right">{d.other.registrations ?? 0}</td><td colSpan={2} /></tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
