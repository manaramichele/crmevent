import { Crown, Clock, Ban, AlertTriangle } from "lucide-react";

const PLAN = {
  gold: { cls: "bg-[#FBF1D3] text-[#8A6A12] ring-[#E9D28A]", Icon: Crown },
  silver: { cls: "bg-[#EEF0F3] text-[#3F4652] ring-[#CDD2DA]" },
  bronze: { cls: "bg-[#F6E3D3] text-[#7A4520] ring-[#E3BE9C]" },
};
const STATE = {
  trial: { cls: "bg-[#0ABAB5]/10 text-[#06706D] ring-[#0ABAB5]/40", label: "Prova gratuita", Icon: Clock },
  expired: { cls: "bg-red-50 text-red-700 ring-red-200", label: "Scaduto", Icon: AlertTriangle },
  canceled: { cls: "bg-red-50 text-red-700 ring-red-200", label: "Scaduto", Icon: AlertTriangle },
  suspended: { cls: "bg-slate-100 text-slate-600 ring-slate-300", label: "Sospeso", Icon: Ban },
};

export const badgeFor = (s) => {
  if (!s?.enabled && !s?.mode) return null;
  if (STATE[s.mode]) return STATE[s.mode];
  const p = PLAN[s.plan];
  if (!p) return null;
  return { ...p, label: `Piano ${s.plan_label || s.plan.toUpperCase()}`, extra: s.mode === "past_due" ? "Pagamento in sospeso" : null };
};

export const BILLING = { free: "Gratuito", trial: "Prova gratuita", paid: "Abbonamento a pagamento", none: "Nessun addebito" };

export function FormulaBadge({ plan, testid }) {
  const p = PLAN[plan];
  if (!p) return <span className="text-xs text-slate-500" data-testid={testid}>Nessuna formula</span>;
  const { Icon } = p;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-semibold ring-1 ring-inset whitespace-nowrap text-[11px] px-2 py-0.5 ${p.cls}`} data-testid={testid} data-plan={plan}>
      {Icon && <Icon className="w-3 h-3" aria-hidden="true" />}{plan.toUpperCase()}
    </span>
  );
}

export default function PlanBadge({ s, testid = "plan-badge", size = "md", className = "" }) {
  const b = badgeFor(s);
  if (!b) return <span className="text-slate-400">—</span>;
  const { Icon } = b;
  const sz = size === "sm" ? "text-[11px] px-2 py-0.5 gap-1" : size === "lg" ? "text-sm px-3 py-1.5 gap-1.5" : "text-xs px-2.5 py-1 gap-1.5";
  return (
    <span className={`inline-flex items-center rounded-full font-semibold ring-1 ring-inset whitespace-nowrap ${sz} ${b.cls} ${className}`} data-testid={testid} data-mode={s.mode} data-plan={s.plan || ""}>
      {Icon && <Icon className={size === "sm" ? "w-3 h-3" : size === "lg" ? "w-4 h-4" : "w-3.5 h-3.5"} aria-hidden="true" />}{b.label}{b.extra ? ` · ${b.extra}` : ""}
    </span>
  );
}
