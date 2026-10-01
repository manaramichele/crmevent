import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AlertTriangle, Flame, Clock, UserX, CheckCircle2, ChevronRight, CalendarClock } from "lucide-react";

const dmy = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");

const REASON = {
  late: { label: "In ritardo", cls: "bg-red-50 text-red-700", icon: AlertTriangle },
  critica: { label: "Critica", cls: "bg-orange-50 text-orange-700", icon: Flame },
  due_soon: { label: "In scadenza", cls: "bg-amber-50 text-amber-700", icon: Clock },
  unassigned: { label: "Senza responsabile", cls: "bg-slate-100 text-slate-600", icon: UserX },
};

const dueHint = (it) => {
  if (it.days_to_due == null) return null;
  if (it.days_to_due < 0) return `${Math.abs(it.days_to_due)}g fa`;
  if (it.days_to_due === 0) return "oggi";
  return `tra ${it.days_to_due}g`;
};

export function AttentionRow({ it, onOpen }) {
  return (
    <button onClick={() => onOpen(it)} className="w-full text-left flex items-center gap-3 py-2.5 px-1 hover:bg-slate-50 rounded-lg transition-colors" data-testid={`attention-item-${it.task_id}`}>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-slate-800 truncate">{it.titolo}</div>
        <div className="text-xs text-slate-400 truncate">{it.event_name}{it.categoria ? ` · ${it.categoria}` : ""}{it.responsabile ? ` · ${it.responsabile}` : ""}</div>
        <div className="flex flex-wrap items-center gap-1 mt-1">
          {it.reasons.map((r) => {
            const R = REASON[r]; if (!R) return null; const Icon = R.icon;
            return <span key={r} className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${R.cls}`}><Icon className="w-3 h-3" />{R.label}</span>;
          })}
        </div>
      </div>
      <div className="text-right shrink-0">
        <div className={`text-xs font-semibold ${it.late ? "text-red-600" : "text-slate-500"}`}>{dmy(it.scadenza)}</div>
        {dueHint(it) && <div className="text-[10px] text-slate-400">{dueHint(it)}</div>}
      </div>
      <ChevronRight className="w-4 h-4 text-slate-300 shrink-0" />
    </button>
  );
}

export default function PipelineAttention() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/pipeline/attention", { params: { limit: 10 } }); setData(data); }
    catch { setData({ items: [], total: 0 }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openItem = (it) => navigate(`/eventi/${it.event_id}/pipeline`);

  if (!data) return null;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-5" data-testid="dashboard-attention">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-9 h-9 rounded-lg flex items-center justify-center text-amber-600 bg-amber-50"><CalendarClock className="w-4.5 h-4.5" /></span>
          <div>
            <h2 className="font-semibold text-slate-800">Cosa richiede attenzione</h2>
            <p className="text-xs text-slate-400">Attività delle Pipeline attive da gestire</p>
          </div>
        </div>
        {data.total > 0 && <span className="text-xs font-semibold text-amber-700 bg-amber-50 px-2 py-1 rounded-full" data-testid="attention-total">{data.total}</span>}
      </div>

      {data.items.length === 0 ? (
        <div className="flex items-center gap-2 text-sm text-slate-400 py-6 justify-center" data-testid="attention-empty">
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />Nessuna attività richiede attenzione. Ottimo lavoro!
        </div>
      ) : (
        <>
          <div className="divide-y divide-slate-50">
            {data.items.map((it) => <AttentionRow key={it.task_id} it={it} onOpen={openItem} />)}
          </div>
          {data.total > data.items.length && (
            <button onClick={() => navigate("/pipeline/attenzione")} className="mt-3 w-full text-center text-sm font-semibold text-tiffany-active hover:underline inline-flex items-center justify-center gap-1" data-testid="attention-see-all">
              Vedi tutte ({data.total}) <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </>
      )}
    </div>
  );
}
