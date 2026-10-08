import { Link } from "react-router-dom";
import { Users, UserCog, CalendarClock, Mail, UserCheck, AlertTriangle, ClipboardList } from "lucide-react";

function Stat({ icon: Icon, label, value, tone = "slate", testid }) {
  const c = { slate: "text-slate-800", red: "text-red-600", green: "text-emerald-600", orange: "text-amber-600" }[tone];
  return (
    <div className="flex items-center gap-2 min-w-0" data-testid={testid}>
      <Icon className="w-4 h-4 text-slate-400 shrink-0" />
      <span className="text-xs text-slate-500 truncate">{label}</span>
      <span className={`ml-auto font-semibold ${c}`}>{value}</span>
    </div>
  );
}

function TeamCard({ t }) {
  const miss = t.volontari_mancanti;
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4 space-y-3" data-testid={`my-team-${t.id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-display font-bold uppercase tracking-wide text-slate-900 break-words" data-testid={`my-team-name-${t.id}`}>{t.nome}</div>
          {t.evento_nome && <div className="text-xs text-slate-500 mt-0.5">{t.evento_nome}</div>}
        </div>
        {miss > 0 ? <span className="shrink-0 rounded-full bg-red-100 text-red-700 px-2 py-0.5 text-xs font-semibold" data-testid={`my-team-missing-${t.id}`}>{miss} mancanti</span>
          : miss === 0 ? <span className="shrink-0 rounded-full bg-emerald-100 text-emerald-700 px-2 py-0.5 text-xs font-semibold">Completo</span> : null}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
        <Stat icon={Users} label="Componenti" value={t.componenti} testid={`my-team-componenti-${t.id}`} />
        <Stat icon={UserCog} label="Staff · Volontari" value={`${t.staff} · ${t.volontari}`} testid={`my-team-split-${t.id}`} />
        <Stat icon={Users} label="Volontari richiesti / assegnati" value={t.volontari_richiesti == null ? `— / ${t.volontari_assegnati}` : `${t.volontari_richiesti} / ${t.volontari_assegnati}`} testid={`my-team-vol-${t.id}`} />
        <Stat icon={CalendarClock} label="Turni (scoperti)" value={`${t.turni_totali} (${t.turni_scoperti})`} tone={t.turni_scoperti ? "orange" : "slate"} testid={`my-team-turni-${t.id}`} />
        <Stat icon={ClipboardList} label="Disponibilità ricevute" value={t.disponibilita} testid={`my-team-disp-${t.id}`} />
        <Stat icon={Mail} label="Inviti inviati" value={t.inviti_inviati} testid={`my-team-inviti-${t.id}`} />
        <Stat icon={UserCheck} label="Registrazioni completate" value={`${t.registrati} / ${t.componenti}`} tone="green" testid={`my-team-registrati-${t.id}`} />
      </div>
    </div>
  );
}

export default function MyTeams({ teams }) {
  if (!teams?.length) return null;
  return (
    <div data-testid="dash-my-teams">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">I miei Team</h2>
        <Link to="/staff-volontari" className="text-xs font-semibold text-tiffany-active hover:underline" data-testid="my-teams-open-staff">Apri Staff / Volontari</Link>
      </div>
      {teams.some((t) => t.volontari_mancanti > 0) && <div className="mb-3 flex items-center gap-2 text-xs text-amber-700"><AlertTriangle className="w-4 h-4" />Alcuni Team hanno ancora volontari mancanti.</div>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">{teams.map((t) => <TeamCard key={t.id} t={t} />)}</div>
    </div>
  );
}
