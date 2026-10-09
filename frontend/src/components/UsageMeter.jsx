import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, X } from "lucide-react";

export function usageItems(limits, usage) {
  if (!limits || !usage) return [];
  return [
    { kind: "events", label: "Eventi utilizzati", used: usage.events, limit: limits.max_events },
    { kind: "users", label: "Utenti registrati", used: usage.users + (usage.pending_invites || 0), limit: limits.max_users, pending: usage.pending_invites || 0 },
  ].map((x) => ({ ...x, pct: x.limit > 0 ? Math.min(100, Math.round((x.used / x.limit) * 100)) : 0 }));
}

function Bar({ it }) {
  const full = it.limit > 0 && it.used >= it.limit;
  return (
    <div data-testid={`usage-${it.kind}`}>
      <div className="flex justify-between text-sm"><span className="text-slate-600">{it.label}</span>
        <b className={full ? "text-amber-700" : "text-slate-800"} data-testid={`usage-${it.kind}-value`}>{it.limit < 0 ? `${it.used} · Illimitati` : `${it.used} / ${it.limit}`}</b></div>
      {it.limit > 0 && <div className="mt-1.5 h-2 rounded-full bg-slate-100 overflow-hidden"><div className={`h-full rounded-full transition-[width] duration-500 ${full ? "bg-amber-500" : "bg-[#0ABAB5]"}`} style={{ width: `${it.pct}%` }} /></div>}
      {it.pending > 0 && <div className="text-[11px] text-slate-400 mt-1">di cui {it.pending} {it.pending === 1 ? "invito in attesa" : "inviti in attesa"} (posto riservato)</div>}
      {it.limit > 0 && it.used > it.limit && <div className="text-[11px] text-amber-700 mt-1" data-testid={`usage-${it.kind}-over`}>Limite superato: i dati restano gestibili, nuove aggiunte bloccate.</div>}
    </div>
  );
}

export function UsageBars({ limits, usage }) {
  const items = usageItems(limits, usage);
  if (!items.length) return null;
  return <div className="grid sm:grid-cols-2 gap-4" data-testid="sub-usage">{items.map((it) => <Bar key={it.kind} it={it} />)}</div>;
}

export function UsageNotice({ s, usage, orgId }) {
  const navigate = useNavigate();
  const [, force] = useState(0);
  if (!s?.enabled || !usage) return null;
  const hit = usageItems(s.limits, usage).filter((it) => it.limit > 0 && it.pct >= 80);
  const key = (it) => `usage-notice:${orgId}:${it.kind}:${it.used >= it.limit ? 100 : 80}:${it.limit}`;
  const show = hit.filter((it) => !localStorage.getItem(key(it)));
  if (!show.length) return null;
  const close = () => { show.forEach((it) => localStorage.setItem(key(it), "1")); force((n) => n + 1); };
  return (
    <div className="flex items-center gap-2 px-3 sm:px-6 py-1.5 text-xs bg-amber-50 text-amber-900 border-b border-amber-200" data-testid="usage-notice">
      <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
      <span className="flex-1 min-w-0">{show.map((it) => `${it.kind === "events" ? "Eventi" : "Utenti"}: ${it.used} su ${it.limit}`).join(" · ")} — {show.some((it) => it.used >= it.limit) ? "limite raggiunto." : "stai per raggiungere il limite del piano."}</span>
      <button type="button" onClick={() => navigate("/profilo?tab=abbonamento")} className="font-semibold underline underline-offset-2" data-testid="usage-notice-cta">Vedi piani</button>
      <button type="button" onClick={close} aria-label="Chiudi avviso" className="p-1 rounded hover:bg-amber-100" data-testid="usage-notice-close"><X className="w-3.5 h-3.5" /></button>
    </div>
  );
}
