import { useEffect, useMemo, useState } from "react";
import * as Slider from "@radix-ui/react-slider";
import api, { eurN } from "@/lib/api";

const CYCLES = [["semester", "Semestrale", 6], ["yearly", "Annuale", 12]];

function Range({ value, onChange, testid }) {
  return (
    <Slider.Root className="relative flex items-center h-6 w-full touch-none select-none" min={0} max={50} step={1} value={[value]} onValueChange={([v]) => onChange(v)} data-testid={testid}>
      <Slider.Track className="relative h-1.5 grow rounded-full bg-slate-200"><Slider.Range className="absolute h-full rounded-full bg-tiffany" /></Slider.Track>
      <Slider.Thumb className="block w-5 h-5 rounded-full bg-white border-2 border-tiffany shadow transition-transform hover:scale-110 focus:outline-none focus:ring-4 focus:ring-tiffany/25" aria-label="Clienti" />
    </Slider.Root>
  );
}

export default function Simulator({ dark = false }) {
  const [cfg, setCfg] = useState(null);
  const [n, setN] = useState({ bronze: 5, silver: 3, gold: 1 });
  const [cycle, setCycle] = useState("yearly");
  useEffect(() => { api.get("/partner/public-config").then(({ data }) => setCfg(data)).catch(() => setCfg(false)); }, []);
  const res = useMemo(() => {
    if (!cfg) return null;
    const months = CYCLES.find((c) => c[0] === cycle)[2];
    const payments = Math.ceil(cfg.duration_months / months);
    const rows = cfg.plans.map((p) => ({ ...p, count: n[p.key] || 0, total: (n[p.key] || 0) * (p[cycle] || 0) * payments * cfg.commission_pct / 100 }));
    return { rows, payments, total: rows.reduce((s, r) => s + r.total, 0) };
  }, [cfg, n, cycle]);
  if (cfg === false) return <p className="text-sm text-red-600" data-testid="simulator-error">Simulatore non disponibile al momento.</p>;
  if (!res) return <p className="text-sm text-slate-400">Caricamento simulatore...</p>;
  const card = dark ? "bg-white/5 border-white/10 text-white" : "bg-white border-slate-200";
  return (
    <div className={`rounded-3xl border p-5 sm:p-7 ${card}`} data-testid="commission-simulator">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className={`text-sm ${dark ? "text-slate-300" : "text-slate-500"}`}>Commissione {cfg.commission_pct}% per {cfg.duration_months} mesi</div>
        <div className={`inline-flex rounded-full p-1 ${dark ? "bg-white/10" : "bg-slate-100"}`} role="tablist">
          {CYCLES.map(([k, l]) => <button key={k} type="button" onClick={() => setCycle(k)} data-testid={`simulator-cycle-${k}`} className={`h-8 px-4 rounded-full text-sm font-medium transition-colors ${cycle === k ? "bg-tiffany text-ink" : dark ? "text-slate-300" : "text-slate-600"}`}>{l}</button>)}
        </div>
      </div>
      <div className="space-y-5">
        {res.rows.map((p) => (
          <div key={p.key} data-testid={`simulator-plan-${p.key}`}>
            <div className="flex items-baseline justify-between text-sm mb-2">
              <span className="font-semibold"><span className="inline-block w-2.5 h-2.5 rounded-full mr-2" style={{ background: p.color }} />{p.label} <span className={dark ? "text-slate-400" : "text-slate-500"}>· {eurN(p[cycle])}</span></span>
              <span className="tabular-nums"><b data-testid={`simulator-count-${p.key}`}>{p.count}</b> clienti</span>
            </div>
            <Range value={p.count} onChange={(v) => setN((s) => ({ ...s, [p.key]: v }))} testid={`simulator-slider-${p.key}`} />
          </div>
        ))}
      </div>
      <div className={`mt-6 pt-5 border-t ${dark ? "border-white/10" : "border-slate-100"} flex flex-wrap items-end justify-between gap-2`}>
        <div className={`text-sm ${dark ? "text-slate-300" : "text-slate-500"}`}>Guadagno stimato nei primi {cfg.duration_months} mesi</div>
        <div className="font-display text-4xl font-extrabold tabular-nums text-tiffany" data-testid="simulator-total">{eurN(res.total)}</div>
      </div>
      <p className={`text-xs mt-3 ${dark ? "text-slate-400" : "text-slate-500"}`}>Stima indicativa: {res.payments} {res.payments === 1 ? "pagamento" : "pagamenti"} per cliente nel periodo, calcolati sull'importo dell'abbonamento effettivamente incassato, imposte escluse, al netto di eventuali rimborsi. Marketplace e crediti esclusi.</p>
    </div>
  );
}
