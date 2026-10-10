import { useEffect, useMemo, useState } from "react";
import { Minus, Plus } from "lucide-react";
import api, { eurN } from "@/lib/api";

const CYCLES = [["semester", "Semestrale", 6], ["yearly", "Annuale", 12]];
const MAX_N = 500;

export function simulate(cfg, n, cycle) {
  const months = CYCLES.find((c) => c[0] === cycle)[2];
  const dur = Math.min(cfg.duration_months, 24), pct = cfg.commission_pct / 100;
  let first = 0, second = 0;
  for (const p of cfg.plans) {
    for (let m = 0; m < dur; m += months) {
      const v = (n[p.key] || 0) * (p[cycle] || 0) * pct;
      if (m < 12) first += v; else second += v;
    }
  }
  return { first, second, total: first + second };
}

function Counter({ value, onChange, plan }) {
  const set = (v) => onChange(Math.max(0, Math.min(MAX_N, Number.isFinite(v) ? Math.round(v) : 0)));
  const btn = "h-10 w-10 grid place-items-center rounded-full border border-slate-200 hover:bg-slate-50 active:scale-95 transition-transform";
  return (
    <div className="flex items-center gap-1.5">
      <button type="button" className={btn} onClick={() => set(value - 1)} aria-label={`Meno ${plan}`} data-testid={`simulator-minus-${plan}`}><Minus className="w-4 h-4" /></button>
      <input type="number" inputMode="numeric" min={0} max={MAX_N} value={value} onChange={(e) => set(parseInt(e.target.value, 10))} aria-label={`Organizzatori ${plan}`}
        className="h-10 w-16 rounded-xl border border-slate-200 text-center text-sm font-semibold tabular-nums outline-none focus:border-tiffany focus:ring-2 focus:ring-tiffany/25" data-testid={`simulator-input-${plan}`} />
      <button type="button" className={btn} onClick={() => set(value + 1)} aria-label={`Più ${plan}`} data-testid={`simulator-plus-${plan}`}><Plus className="w-4 h-4" /></button>
    </div>
  );
}

const Out = ({ label, value, testid, strong }) => (
  <div className="min-w-0"><div className="text-xs text-slate-500">{label}</div><div className={`font-display text-lg sm:text-xl tabular-nums break-words ${strong ? "font-extrabold text-tiffany-fg" : "font-bold"}`} data-testid={testid}>{eurN(value)}</div></div>
);

export default function Simulator() {
  const [cfg, setCfg] = useState(null);
  const [n, setN] = useState({ bronze: 5, silver: 3, gold: 1 });
  const [cycle, setCycle] = useState("yearly");
  const load = () => { setCfg(null); api.get("/partner/public-config").then(({ data }) => setCfg(data)).catch(() => setCfg(false)); };
  useEffect(load, []);
  const res = useMemo(() => (cfg ? simulate(cfg, n, cycle) : null), [cfg, n, cycle]);
  if (cfg === false) return <p className="text-sm text-red-600" data-testid="simulator-error">Simulatore non disponibile al momento. <button type="button" onClick={load} className="underline font-semibold" data-testid="simulator-retry">Riprova</button></p>;
  if (!res) return <p className="text-sm text-slate-400" data-testid="simulator-loading">Caricamento simulatore...</p>;
  const months = CYCLES.find((c) => c[0] === cycle)[2];
  const totN = cfg.plans.reduce((s, p) => s + (n[p.key] || 0), 0);
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7 shadow-[0_20px_60px_-30px_rgba(10,186,181,.45)] min-w-0" data-testid="commission-simulator">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="text-sm text-slate-600">Commissione <b>{cfg.commission_pct}%</b> per <b>{Math.min(cfg.duration_months, 24)} mesi</b></div>
        <div className="inline-flex rounded-full p-1 bg-slate-100" role="tablist" aria-label="Durata abbonamento">
          {CYCLES.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={cycle === k} onClick={() => setCycle(k)} data-testid={`simulator-cycle-${k}`} className={`h-8 px-4 rounded-full text-sm font-medium transition-colors ${cycle === k ? "bg-tiffany text-ink" : "text-slate-600 hover:text-ink"}`}>{l}</button>)}
        </div>
      </div>
      <div className="divide-y divide-slate-100">
        {cfg.plans.map((p) => (
          <div key={p.key} className="py-3 flex flex-wrap items-center justify-between gap-3" data-testid={`simulator-plan-${p.key}`}>
            <div className="min-w-0">
              <div className="font-semibold text-sm"><span className="inline-block w-2.5 h-2.5 rounded-full mr-2" style={{ background: p.color }} />{p.label}</div>
              <div className="text-xs text-slate-500" data-testid={`simulator-price-${p.key}`}>{eurN(p[cycle])} ogni {months} mesi · commissione {eurN(p[cycle] * cfg.commission_pct / 100)}</div>
            </div>
            <Counter value={n[p.key] || 0} onChange={(v) => setN((s) => ({ ...s, [p.key]: v }))} plan={p.key} />
          </div>
        ))}
      </div>
      <div className="mt-2 text-xs text-slate-500" data-testid="simulator-total-orgs">{totN} organizzatori acquisiti</div>
      <div className="mt-5 pt-5 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Out label="Primo anno" value={res.first} testid="simulator-first" />
        <Out label="Secondo anno" value={res.second} testid="simulator-second" />
        <Out label="Totale 24 mesi" value={res.total} testid="simulator-total" strong />
      </div>
      <p className="text-xs mt-4 text-slate-500 leading-relaxed" data-testid="simulator-disclaimer">Stima indicativa, non un guadagno garantito. Calcolata sui prezzi attuali CRMEvent, ipotizzando che ogni organizzatore resti abbonato e rinnovi per 24 mesi. La commissione reale è il {cfg.commission_pct}% degli importi effettivamente incassati, al netto dell'IVA e di eventuali rimborsi, per un massimo di 24 mesi dal primo pagamento. Acquisti Marketplace esclusi.</p>
    </div>
  );
}
