import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { StaffAssignSelect } from "@/components/StaffAssignSelect";
import { AlertTriangle, Flame, Clock, UserX, CheckCircle2, ChevronRight, CalendarClock, Check, UserPlus } from "lucide-react";

const dmy = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");
const pname = (p) => `${p.nome || ""} ${p.cognome || ""}`.trim() || p.email || p.id;

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

// Ordina per scadenza crescente (più vicina → più lontana); le attività senza scadenza sempre in fondo.
export function sortByScadenza(items) {
  return [...(items || [])].sort((a, b) => {
    const sa = a.scadenza || "", sb = b.scadenza || "";
    if (!sa && !sb) return 0;
    if (!sa) return 1;
    if (!sb) return -1;
    return sa < sb ? -1 : sa > sb ? 1 : 0;
  });
}

// Stato + azioni condivisi da widget Dashboard e pagina /pipeline/attenzione.
export function useAttention(limit) {
  const [data, setData] = useState(null);
  const [persons, setPersons] = useState([]);
  const [staffLinks, setStaffLinks] = useState([]);
  const [confirmItem, setConfirmItem] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/pipeline/attention", { params: { limit } }); setData(data); }
    catch { setData({ items: [], total: 0 }); }
  }, [limit]);
  const loadStaff = useCallback(async () => {
    try { const [p, s] = await Promise.all([api.get("/persons"), api.get("/staff")]); setPersons(p.data); setStaffLinks(s.data); }
    catch { /* noop */ }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadStaff(); }, [loadStaff]);

  const removeLocal = (taskId) => setData((d) => d ? { items: d.items.filter((i) => i.task_id !== taskId), total: Math.max(0, d.total - 1) } : d);
  const updateLocal = (taskId, patch) => setData((d) => d ? { ...d, items: d.items.map((i) => i.task_id === taskId ? { ...i, ...patch } : i) } : d);

  const complete = async (it) => {
    try {
      await api.put(`/pipeline/tasks/${it.task_id}`, { stato: "completata" });
      removeLocal(it.task_id);
      toast.success("Attività completata");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const requestComplete = (it) => { if (it.priorita === "critica") setConfirmItem(it); else complete(it); };
  const confirmComplete = () => { if (confirmItem) { complete(confirmItem); setConfirmItem(null); } };

  const setResponsabile = async (it, personId) => {
    try {
      await api.put(`/pipeline/tasks/${it.task_id}`, { responsabile_id: personId });
      const person = personId ? persons.find((p) => p.id === personId) : null;
      const remaining = personId ? it.reasons.filter((r) => r !== "unassigned") : it.reasons;
      if (personId && remaining.length === 0) removeLocal(it.task_id);
      else updateLocal(it.task_id, { responsabile: person ? pname(person) : null, responsabile_id: personId, reasons: remaining });
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return { data, persons, staffLinks, loadStaff, requestComplete, setResponsabile, confirmItem, setConfirmItem, confirmComplete };
}

export function AttentionRow({ it, persons, staffLinks, onOpen, onComplete, onSetResponsabile, onStaffAdded }) {
  const staffPersons = useMemo(() => {
    const ids = new Set((staffLinks || []).filter((l) => l.evento_id === it.event_id && ["staff", "collaboratore"].includes(l.categoria)).map((l) => l.persona_id));
    return (persons || []).filter((p) => ids.has(p.id));
  }, [persons, staffLinks, it.event_id]);
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2 py-2.5 px-1 hover:bg-slate-50 rounded-lg transition-colors" data-testid={`attention-item-${it.task_id}`}>
      <button onClick={() => onOpen(it)} className="flex-1 min-w-0 text-left" data-testid={`attention-open-${it.task_id}`}>
        <div className="font-medium text-slate-800 truncate">{it.titolo}</div>
        <div className="text-xs text-slate-400 truncate">{it.event_name}{it.categoria ? ` · ${it.categoria}` : ""}</div>
        <div className="flex flex-wrap items-center gap-1 mt-1">
          {it.reasons.map((r) => {
            const R = REASON[r]; if (!R) return null; const Icon = R.icon;
            return <span key={r} className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${R.cls}`}><Icon className="w-3 h-3" />{R.label}</span>;
          })}
        </div>
      </button>
      <div className="flex items-center gap-2 shrink-0">
        <div className="text-right">
          <div className={`text-xs font-semibold ${it.late ? "text-red-600" : "text-slate-500"}`}>{dmy(it.scadenza)}</div>
          {dueHint(it) && <div className="text-[10px] text-slate-400">{dueHint(it)}</div>}
        </div>
        {/* Responsabile: stesso selettore della Pipeline (solo Staff dell'evento) */}
        <StaffAssignSelect
          eventoId={it.event_id}
          staffPersons={staffPersons}
          allPersons={persons}
          value={it.responsabile_id || null}
          onChange={(pid) => onSetResponsabile(it, pid)}
          onStaffAdded={onStaffAdded}
          align="end"
          trigger={
            it.responsabile
              ? <button className="text-xs text-slate-600 hover:text-tiffany-active underline underline-offset-2 max-w-[8rem] truncate" title="Cambia responsabile" data-testid={`attention-reassign-${it.task_id}`}>{it.responsabile}</button>
              : <button className="inline-flex items-center gap-1 text-xs font-semibold text-tiffany-active hover:underline" data-testid={`attention-assign-${it.task_id}`}><UserPlus className="w-3.5 h-3.5" />Assegna</button>
          }
        />
        <button onClick={() => onComplete(it)} title="Segna come completata" className="w-8 h-8 rounded-lg flex items-center justify-center text-emerald-600 bg-emerald-50 hover:bg-emerald-100 transition-colors" data-testid={`attention-complete-${it.task_id}`}><Check className="w-4 h-4" /></button>
      </div>
    </div>
  );
}

export function CriticalConfirmDialog({ item, onCancel, onConfirm }) {
  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="max-w-sm" data-testid="attention-critical-confirm">
        <DialogHeader>
          <DialogTitle>Attività critica</DialogTitle>
          <DialogDescription>Confermi di aver completato questa attività critica?{item ? ` "${item.titolo}"` : ""}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} data-testid="attention-critical-cancel">Annulla</Button>
          <Button onClick={onConfirm} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="attention-critical-confirm-btn">Sì, completata</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function PipelineAttention() {
  const navigate = useNavigate();
  const { data, persons, staffLinks, loadStaff, requestComplete, setResponsabile, confirmItem, setConfirmItem, confirmComplete } = useAttention(10);
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
            {data.items.map((it) => <AttentionRow key={it.task_id} it={it} persons={persons} staffLinks={staffLinks} onOpen={openItem} onComplete={requestComplete} onSetResponsabile={setResponsabile} onStaffAdded={loadStaff} />)}
          </div>
          {data.total > data.items.length && (
            <button onClick={() => navigate("/pipeline/attenzione")} className="mt-3 w-full text-center text-sm font-semibold text-tiffany-active hover:underline inline-flex items-center justify-center gap-1" data-testid="attention-see-all">
              Vedi tutte ({data.total}) <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </>
      )}
      <CriticalConfirmDialog item={confirmItem} onCancel={() => setConfirmItem(null)} onConfirm={confirmComplete} />
    </div>
  );
}
