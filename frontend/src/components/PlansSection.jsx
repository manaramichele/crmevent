import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Minus, Video, Mail, Crown, Infinity as InfinityIcon, Gift, Users } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;
export const eur = (n) => Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function supportLabel(p) {
  if (p.video_quota === 0) return { icon: Mail, text: "Assistenza via email" };
  if (p.video_quota < 0) return { icon: Crown, text: "Videochiamate illimitate e prioritarie" };
  return { icon: Video, text: `Email + ${p.video_quota} videochiamate al mese` };
}

export function limitsLabel(p) {
  const ev = p.max_events < 0 ? "Eventi illimitati" : p.max_events === 1 ? "1 evento incluso" : `Fino a ${p.max_events} eventi`;
  const us = p.max_users < 0 ? "Staff e Volontari illimitati" : `Fino a ${p.max_users} Staff e Volontari`;
  return { ev, us };
}

export function usePlans() {
  const [data, setData] = useState(null);
  useEffect(() => { fetch(`${API}/api/saas/plans-public`).then((r) => r.json()).then(setData).catch(() => setData({ plans: [], features: [] })); }, []);
  return data;
}

export function CycleToggle({ cycle, setCycle }) {
  const btn = (k, label) => (
    <button type="button" onClick={() => setCycle(k)} data-testid={`cycle-${k}`}
      className={`h-10 px-4 rounded-full text-sm font-semibold transition-colors ${cycle === k ? "bg-slate-900 text-white" : "text-slate-600 hover:text-slate-900"}`}>{label}</button>
  );
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1 shadow-sm" data-testid="cycle-toggle">
      {btn("monthly", "Mensile")}{btn("yearly", <>Annuale <span className="ml-1 rounded-full bg-[#0ABAB5] text-slate-900 px-2 py-0.5 text-[11px]">−20%</span></>)}
    </div>
  );
}

export function PlanCard({ p, cycle, features, cta, current }) {
  const yearly = cycle === "yearly";
  const perMonth = yearly ? p.yearly / 12 : p.monthly;
  const sup = supportLabel(p);
  const lim = limitsLabel(p);
  return (
    <div className={`relative flex flex-col rounded-2xl bg-white p-6 border transition-[transform,box-shadow] duration-200 hover:-translate-y-1 hover:shadow-lg ${current ? "border-[#0ABAB5] ring-2 ring-[#0ABAB5]/30" : "border-slate-200 shadow-sm"}`}
      style={{ borderTop: `6px solid ${p.color}` }} data-testid={`plan-card-${p.key}`}>
      {current && <span className="absolute -top-3 right-4 rounded-full bg-[#0ABAB5] px-3 py-1 text-[11px] font-bold text-slate-900">Piano attuale</span>}
      <div className="font-display text-2xl font-extrabold tracking-wide" style={{ color: p.color }}>{p.label}</div>
      <p className="text-sm text-slate-500 mt-1 min-h-[40px]">{p.tagline}</p>
      <div className="mt-4 flex items-baseline gap-1">
        <span className="font-display text-4xl font-bold text-slate-900" data-testid={`plan-price-${p.key}`}>€{eur(perMonth)}</span>
        <span className="text-sm text-slate-500">/mese</span>
      </div>
      <div className="text-xs text-slate-500 h-4" data-testid={`plan-billed-${p.key}`}>{yearly ? `Totale annuale addebitato: €${eur(p.yearly)}` : "Fatturazione mensile"}</div>
      <ul className="mt-5 space-y-2 text-sm flex-1">
        <li className="flex gap-2 text-slate-800 font-medium" data-testid={`plan-events-${p.key}`}><InfinityIcon className="w-4 h-4 text-[#0ABAB5] mt-0.5 shrink-0" />{lim.ev}</li>
        <li className="flex gap-2 text-slate-800 font-medium" data-testid={`plan-users-${p.key}`}><Users className="w-4 h-4 text-[#0ABAB5] mt-0.5 shrink-0" />{lim.us}</li>
        <li className="flex gap-2 text-slate-800 font-medium"><sup.icon className="w-4 h-4 text-[#0ABAB5] mt-0.5 shrink-0" />{sup.text}</li>
        {features.filter((f) => p.features.includes(f.key)).map((f) => (
          <li key={f.key} className="flex gap-2 text-slate-600"><Check className="w-4 h-4 text-[#0ABAB5] mt-0.5 shrink-0" />{f.label}</li>
        ))}
      </ul>
      <div className="mt-6">{cta}</div>
    </div>
  );
}

export function ComparisonTable({ plans, features }) {
  const cell = (v, k) => <td key={k} className="px-1 py-1.5 sm:px-2 sm:py-2 text-center align-middle">{v === true ? <Check className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-[#0ABAB5] mx-auto" /> : v === false ? <Minus className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-slate-300 mx-auto" /> : <span className="text-[11px] sm:text-sm leading-tight text-slate-700">{v}</span>}</td>;
  const rows = [
    ...features.map((f) => [f.label, plans.map((p) => p.features.includes(f.key))]),
    ["Eventi", plans.map((p) => (p.max_events < 0 ? "Illimitati" : p.max_events === 1 ? "1" : `Fino a ${p.max_events}`))],
    ["Staff e Volontari", plans.map((p) => (p.max_users < 0 ? "Illimitati" : `Fino a ${p.max_users}`))],
    ["Assistenza email", plans.map(() => true)],
    ["Videochiamate Google Meet", plans.map((p) => (p.video_quota === 0 ? false : p.video_quota < 0 ? "Illimitate e prioritarie" : `${p.video_quota}/mese`))],
  ];
  return (
    <div className="rounded-xl sm:rounded-2xl border border-slate-200 bg-white overflow-hidden max-w-3xl mx-auto" data-testid="plans-comparison">
      <table className="w-full table-fixed text-[11px] sm:text-sm">
        <colgroup><col />{plans.map((p) => <col key={p.key} className="w-[20%] sm:w-[17%]" />)}</colgroup>
        <thead><tr className="border-b border-slate-200 bg-slate-50">
          <th className="px-2 py-2 sm:px-3 sm:py-2.5 text-left font-semibold text-slate-700">Funzionalità</th>
          {plans.map((p) => <th key={p.key} className="px-1 py-2 sm:px-2 sm:py-2.5 text-[11px] sm:text-sm font-extrabold tracking-wide text-center" style={{ color: p.color }} data-testid={`comparison-head-${p.key}`}>{p.label}</th>)}
        </tr></thead>
        <tbody>{rows.map(([label, vals]) => (
          <tr key={label} className="border-b border-slate-100 last:border-0">
            <td className="px-2 py-1.5 sm:px-3 sm:py-2 text-slate-700 leading-snug break-words">{label}</td>{vals.map((v, i) => cell(v, i))}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function PlansSection({ authed, claim }) {
  const data = usePlans();
  const [cycle, setCycle] = useState("monthly");
  if (!data) return <p className="text-center text-sm text-slate-400">Caricamento piani…</p>;
  return (
    <div className="space-y-10" data-testid="plans-section">
      <div className="text-center">
        <div className="inline-flex items-center gap-2 rounded-full bg-[#0ABAB5]/10 text-slate-800 px-3 py-1 text-xs font-semibold mb-4" data-testid="plans-trial-claim">
          <Gift className="w-3.5 h-3.5 text-[#0ABAB5]" />{claim || `${data.trial_days || 14} giorni di prova gratuita. Nessuna carta di credito richiesta.`}
        </div>
        <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight">Scegli il piano per il tuo evento</h2>
        <p className="text-slate-500 mt-3 text-sm md:text-base">Staff e Volontari conteggiati come persone uniche. Durante la prova gratuita hai accesso completo.</p>
        <div className="mt-6"><CycleToggle cycle={cycle} setCycle={setCycle} /></div>
      </div>
      <div className="grid gap-5 md:grid-cols-3">
        {data.plans.map((p) => (
          <PlanCard key={p.key} p={p} cycle={cycle} features={data.features}
            cta={<Link to={authed ? "/profilo?tab=abbonamento" : "/registrati"} data-testid={`plan-cta-${p.key}`}
              className="flex h-11 items-center justify-center rounded-xl bg-[#0ABAB5] text-sm font-semibold text-slate-900 transition-[background-color,transform] hover:bg-[#09A8A3] active:scale-[0.98]">{authed ? "Scegli piano" : "Registrati gratis"}</Link>} />
        ))}
      </div>
      <div>
        <h3 className="font-display text-xl font-bold mb-4">Confronta i piani</h3>
        <ComparisonTable plans={data.plans} features={data.features} />
      </div>
    </div>
  );
}
