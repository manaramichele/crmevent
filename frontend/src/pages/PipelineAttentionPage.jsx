import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { AttentionRow, CriticalConfirmDialog, useAttention, sortByScadenza } from "@/components/PipelineAttention";
import { ArrowLeft, CalendarClock, CheckCircle2 } from "lucide-react";

export default function PipelineAttentionPage() {
  const navigate = useNavigate();
  const { data, persons, staffLinks, loadStaff, requestComplete, setResponsabile, confirmItem, setConfirmItem, confirmComplete } = useAttention(1000);
  const openItem = (it) => navigate(`/eventi/${it.event_id}/pipeline`);
  // Ordinamento fisso per scadenza crescente (solo nella pagina completa).
  const items = useMemo(() => sortByScadenza(data?.items), [data]);

  return (
    <div className="max-w-3xl space-y-5" data-testid="attention-page">
      <button onClick={() => navigate("/app")} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800" data-testid="attention-back"><ArrowLeft className="w-4 h-4" />Torna alla Dashboard</button>
      <div className="flex items-center gap-2">
        <span className="w-10 h-10 rounded-xl flex items-center justify-center text-amber-600 bg-amber-50"><CalendarClock className="w-5 h-5" /></span>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">To Do List</h1>
          <p className="text-sm text-slate-500">Tutte le attività delle Pipeline attive che richiedono un intervento{data ? ` · ${data.total}` : ""}</p>
        </div>
      </div>
      {!data ? <div className="text-slate-400">Caricamento…</div> : items.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center text-slate-400 flex flex-col items-center gap-2" data-testid="attention-page-empty">
          <CheckCircle2 className="w-8 h-8 text-emerald-500" />Nessuna attività richiede attenzione. Ottimo lavoro!
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-2xl p-3 divide-y divide-slate-50">
          {items.map((it) => <AttentionRow key={it.task_id} it={it} persons={persons} staffLinks={staffLinks} onOpen={openItem} onComplete={requestComplete} onSetResponsabile={setResponsabile} onStaffAdded={loadStaff} />)}
        </div>
      )}
      <CriticalConfirmDialog item={confirmItem} onCancel={() => setConfirmItem(null)} onConfirm={confirmComplete} />
    </div>
  );
}
