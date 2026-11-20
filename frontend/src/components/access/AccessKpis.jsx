import { fmtDur } from "./accessShared";

const CARDS = [
  ["users", "Utenti totali"], ["logged", "Almeno un login"], ["active_7", "Attivi ultimi 7 giorni"],
  ["inactive_7", "Inattivi da 7+ giorni"], ["inactive_14", "Inattivi da 14+ giorni"], ["inactive_30", "Inattivi da 30+ giorni"],
  ["never", "Mai entrati"], ["sessions", "Sessioni nel periodo"],
];

export function AccessKpis({ k }) {
  if (!k) return null;
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="access-kpis">
      {CARDS.map(([key, label]) => (
        <div key={key} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`access-kpi-${key}`}>
          <div className="text-xs text-slate-500">{label}</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{k[key]}</div>
        </div>
      ))}
      <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid="access-kpi-avg">
        <div className="text-xs text-slate-500">Durata media sessione</div>
        <div className="text-2xl font-bold text-slate-900 mt-1">{fmtDur(k.avg_session_seconds)}</div>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid="access-kpi-total">
        <div className="text-xs text-slate-500">Tempo complessivo</div>
        <div className="text-2xl font-bold text-slate-900 mt-1">{fmtDur(k.total_seconds)}</div>
      </div>
    </div>
  );
}
