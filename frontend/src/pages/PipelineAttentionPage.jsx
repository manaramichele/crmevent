import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AttentionRow } from "@/components/PipelineAttention";
import { ArrowLeft, CalendarClock, CheckCircle2 } from "lucide-react";

export default function PipelineAttentionPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/pipeline/attention", { params: { limit: 1000 } }); setData(data); }
    catch { setData({ items: [], total: 0 }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openItem = (it) => navigate(`/eventi/${it.event_id}/pipeline`);

  return (
    <div className="max-w-3xl space-y-5" data-testid="attention-page">
      <button onClick={() => navigate("/app")} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800" data-testid="attention-back"><ArrowLeft className="w-4 h-4" />Torna alla Dashboard</button>
      <div className="flex items-center gap-2">
        <span className="w-10 h-10 rounded-xl flex items-center justify-center text-amber-600 bg-amber-50"><CalendarClock className="w-5 h-5" /></span>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Cosa richiede attenzione</h1>
          <p className="text-sm text-slate-500">Tutte le attività delle Pipeline attive che richiedono un intervento{data ? ` · ${data.total}` : ""}</p>
        </div>
      </div>
      {!data ? <div className="text-slate-400">Caricamento…</div> : data.items.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-10 text-center text-slate-400 flex flex-col items-center gap-2" data-testid="attention-page-empty">
          <CheckCircle2 className="w-8 h-8 text-emerald-500" />Nessuna attività richiede attenzione. Ottimo lavoro!
        </div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-2xl p-3 divide-y divide-slate-50">
          {data.items.map((it) => <AttentionRow key={it.task_id} it={it} onOpen={openItem} />)}
        </div>
      )}
    </div>
  );
}
