import { useEffect, useMemo, useState } from "react";
import * as Slider from "@radix-ui/react-slider";
import api, { eurN } from "@/lib/api";

const CYCLES = [["semester", "6 mesi", 6], ["yearly", "12 mesi", 12]];

function Range({ value, onChange, max = 50, testid, label }) {
  return (
    <Slider.Root className="relative flex items-center h-6 w-full touch-none select-none" min={0} max={max} step={1} value={[value]} onValueChange={([v]) => onChange(v)} data-testid={testid}>
      <Slider.Track className="relative h-1.5 grow rounded-full bg-slate-200"><Slider.Range className="absolute h-full rounded-full bg-tiffany" /></Slider.Track>
      <Slider.Thumb className="block w-5 h-5 rounded-full bg-white border-2 border-tiffany shadow transition-transform hover:scale-110 focus:outline-none focus:ring-4 focus:ring-tiffany/25" aria-label={label} />
    </Slider.Root>
  );
}

export function simulate(cfg, n, cycle, renewal) {
  const months = CYCLES.find((c) => c[0] === cycle)[2];
  const r = renewal / 100, pct = cfg.commission_pct / 100;
  let first = 0, second = 0;
  for (const p of cfg.plans) {
    for (let k = 0; k * months < Math.min(cfg.duration_months, 24); k++) {
      const v = (n[p.key] || 0) * Math.pow(r, k) * (p[cycle] || 0) * pct;
      if (k * months < 12) first += v; else second += v;
    }
  }
  return { first, second, total: first + second };
}

export default function Simulator() {
  const [cfg, setCfg] = useState(null);
  const [n, setN] = useState({ bronze: 5, silver: 3, gold: 1 });
  const [cycle, setCycle] = useState("yearly");
  const [renewal, setRenewal] = useState(70);
  useEffect(() => { api.get("/partner/public-config").then(({ data }) => setCfg(data)).catch(() => setCfg(false)); }, []);
  const res = useMemo(() => (cfg ? simulate(cfg, n, cycle, renewal) : null), [cfg, n, cycle, renewal]);
  if (cfg === false) return <p className="text-sm text-red-600" data-testid="simulator-error">Simulatore non disponibile al momento.</p>;
  if (!res) return <p className="text-sm text-slate-400">Caricamento simulatore...</p>;
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-5 sm:p-7 shadow-[0_20px_60px_-30px_rgba(10,186,181,.45)]" data-testid="commission-simulator">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="text-sm text-slate-500">Commissione {cfg.commission_pct}% per {cfg.duration_months} mesi</div>
        <div className="inline-flex rounded-full p-1 bg-slate-100" role="tablist">
          {CYCLES.map(([k, l]) => <button key={k} type="button" onClick={() => setCycle(k)} data-testid={`simulator-cycle-${k}`} className={`h-8 px-4 rounded-full text-sm font-medium transition-colors ${cycle === k ? "bg-tiffany text-ink" : "text-slate-600"}`}>{l}</button>)}
        </div>
      </div>
      <div className="space-y-5">
        {cfg.plans.map((p) => (
          <div key={p.key} data-testid={`simulator-plan-${p.key}`}>
            <div className="flex items-baseline justify-between text-sm mb-2">
              <span className="font-semibold"><span className="inline-block w-2.5 h-2.5 rounded-full mr-2" style={{ background: p.color }} />{p.label} <span className="text-slate-500">· {eurN(p[cycle])}</span></span>
              <span className="tabular-nums"><b data-testid={`simulator-count-${p.key}`}>{n[p.key]}</b> clienti</span>
            </div>
            <Range value={n[p.key]} onChange={(v) => setN((s) => ({ ...s, [p.key]: v }))} testid={`simulator-slider-${p.key}`} label={`Clienti ${p.label}`} />
          </div>
        ))}
        <div>
          <div className="flex justify-between text-sm mb-2"><span className="font-semibold">Rinnovi previsti</span><b data-testid="simulator-renewal">{renewal}%</b></div>
          <Range value={renewal} onChange={setRenewal} max={100} testid="simulator-slider-renewal" label="Percentuale di rinnovo" />
        </div>
      </div>
      <div className="mt-6 pt-5 border-t border-slate-100 grid grid-cols-3 gap-2 text-center">
        <div><div className="text-xs text-slate-500">Primi 12 mesi</div><div className="font-display text-lg sm:text-xl font-bold tabular-nums" data-testid="simulator-first">{eurN(res.first)}</div></div>
        <div><div className="text-xs text-slate-500">Successivi 12 mesi</div><div className="font-display text-lg sm:text-xl font-bold tabular-nums" data-testid="simulator-second">{eurN(res.second)}</div></div>
        <div><div className="text-xs text-slate-500">Totale 24 mesi</div><div className="font-display text-lg sm:text-xl font-extrabold tabular-nums text-tiffany" data-testid="simulator-total">{eurN(res.total)}</div></div>
      </div>
      <p className="text-xs mt-4 text-slate-500" data-testid="simulator-disclaimer">Valori puramente indicativi: è una simulazione, non un guadagno garantito. Calcolata sui prezzi del catalogo CRMEvent e sull'importo dell'abbonamento effettivamente incassato, imposte escluse, al netto di rimborsi. Marketplace escluso.</p>
    </div>
  );
}
