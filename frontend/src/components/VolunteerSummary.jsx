import { teamCounts } from "@/components/TeamMembersDialog";
import { Users, UserCheck, UserX } from "lucide-react";

// Stessa regola del backend (_team_coverage): mancanti per team = MAX(0, richiesti - assegnati).
export function volunteerSummary(teams, staffLinks, eventIds) {
  const out = { req: 0, assigned: 0, assignedReq: 0, missing: 0, noReq: 0 };
  (teams || []).filter((t) => eventIds.has(t.evento_id)).forEach((t) => {
    const n = teamCounts(t, staffLinks).vol.size;
    out.assigned += n;
    if (t.volontari_richiesti == null) { out.noReq += 1; return; }
    out.req += t.volontari_richiesti;
    out.assignedReq += n;
    out.missing += Math.max(t.volontari_richiesti - n, 0);
  });
  return out;
}

function Box({ icon: Icon, label, value, tone, testid }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 sm:px-4 sm:py-3 min-w-0" data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[11px] sm:text-xs uppercase tracking-wide text-slate-500"><Icon className="w-3.5 h-3.5 shrink-0" /><span className="truncate">{label}</span></div>
      <div className={`font-display text-xl sm:text-2xl font-bold mt-0.5 ${tone || "text-slate-900"}`} data-testid={`${testid}-value`}>{value}</div>
    </div>
  );
}

export default function VolunteerSummary({ teams, staffLinks, events, evFilter }) {
  const ids = new Set(evFilter === "all" ? (events || []).map((e) => e.id) : [evFilter]);
  const s = volunteerSummary(teams, staffLinks, ids);
  const pct = s.req > 0 ? Math.round((s.assignedReq / s.req) * 100) : null;
  const done = s.req > 0 && s.missing === 0;
  return (
    <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3 sm:p-4 space-y-3" data-testid="volunteer-summary">
      <div className="grid grid-cols-3 gap-2 sm:gap-3">
        <Box icon={Users} label="Necessari" value={s.req} testid="vol-sum-needed" />
        <Box icon={UserCheck} label="Assegnati" value={s.assigned} testid="vol-sum-assigned" />
        <Box icon={UserX} label="Mancanti" value={s.missing} tone={s.req === 0 ? "text-slate-400" : s.missing > 0 ? "text-red-600" : "text-emerald-600"} testid="vol-sum-missing" />
      </div>
      <div data-testid="vol-sum-coverage">
        <div className="flex justify-between text-xs text-slate-500 mb-1">
          <span>Copertura volontari</span>
          <b className={done ? "text-emerald-600" : "text-slate-700"} data-testid="vol-sum-coverage-pct">{pct === null ? "Fabbisogno non indicato" : `${pct}%`}</b>
        </div>
        <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
          <div className="h-full rounded-full bg-[#0ABAB5] transition-[width] duration-500" style={{ width: `${pct === null ? 0 : Math.min(100, pct)}%` }} />
        </div>
        {s.noReq > 0 && <p className="text-[11px] text-slate-400 mt-1" data-testid="vol-sum-noreq">{s.noReq === 1 ? "1 team senza fabbisogno indicato" : `${s.noReq} team senza fabbisogno indicato`} (esclusi da Necessari e Mancanti).</p>}
      </div>
    </div>
  );
}
