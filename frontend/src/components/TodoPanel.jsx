import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Check, ListTodo } from "lucide-react";

const TIPO = { pipeline: ["Pipeline", "bg-violet-50 text-violet-700"], attivita: ["Attività", "bg-sky-50 text-sky-700"], followup: ["Follow-up", "bg-amber-50 text-amber-700"] };
const BUCKET = { ritardo: ["In ritardo", "text-red-600"], scadenza: ["In scadenza", "text-amber-600"], da_fare: ["Da completare", "text-slate-500"] };
const STATO = { da_fare: "Da fare", in_corso: "In corso", in_attesa: "In attesa", aperto: "Aperto" };
const PRIO = { critica: "bg-red-100 text-red-800", alta: "bg-red-50 text-red-700", urgente: "bg-red-50 text-red-700", media: "bg-slate-100 text-slate-600", normale: "bg-slate-100 text-slate-600", bassa: "bg-slate-50 text-slate-500" };
const dmy = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "Senza scadenza");
const href = (i) => (i.tipo === "pipeline" ? `/eventi/${i.evento_id}/pipeline` : i.tipo === "attivita" ? "/attivita" : "/followup");

function TodoRow({ i, onDone }) {
  const [lbl, cls] = TIPO[i.tipo];
  return (
    <li className="flex items-start gap-3 px-3 py-2.5 border-b border-slate-100 last:border-0" data-testid={`todo-item-${i.id}`}>
      <button type="button" disabled={!i.can_edit} onClick={() => onDone(i)} title="Segna come completata" aria-label="Segna come completata" data-testid={`todo-complete-${i.id}`}
        className="mt-0.5 w-5 h-5 shrink-0 rounded-full border-2 border-[#0ABAB5] flex items-center justify-center text-transparent hover:bg-[#0ABAB5] hover:text-white transition-colors disabled:opacity-40 disabled:hover:bg-transparent">
        <Check className="w-3 h-3" />
      </button>
      <div className="min-w-0 flex-1">
        <Link to={href(i)} className="block text-sm font-semibold text-slate-900 hover:text-[#088F8A] truncate" data-testid={`todo-link-${i.id}`}>{i.titolo}</Link>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
          <span className={`rounded px-1.5 py-0.5 font-semibold ${cls}`}>{lbl}</span>
          {i.priorita && <span className={`rounded px-1.5 py-0.5 capitalize ${PRIO[i.priorita] || PRIO.media}`}>{i.priorita}</span>}
          <span className={BUCKET[i.bucket][1]}>{dmy(i.scadenza)}</span>
          {i.stato && <span>· {STATO[i.stato] || i.stato}</span>}
          {i.responsabile && <span className="truncate">· {i.responsabile}</span>}
          {i.evento && <span className="truncate">· {i.evento}</span>}
        </div>
      </div>
    </li>
  );
}

function TodoFilters({ items, tipo, setTipo, ev, setEv }) {
  const types = [...new Set(items.map((i) => i.tipo))];
  const events = [...new Map(items.filter((i) => i.evento_id).map((i) => [i.evento_id, i.evento || "Evento non trovato"])).entries()];
  const chip = (k, label) => (
    <button key={k} type="button" onClick={() => setTipo(k)} data-testid={`todo-filter-tipo-${k}`}
      className={`h-7 px-2.5 rounded-full text-xs font-semibold border transition-colors ${tipo === k ? "bg-[#0ABAB5] border-[#0ABAB5] text-slate-900" : "border-slate-200 text-slate-600 hover:border-[#0ABAB5]"}`}>{label}</button>
  );
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 py-2 border-b border-slate-100" data-testid="todo-filters">
      {chip("all", "Tutti")}{types.map((t) => chip(t, TIPO[t][0]))}
      {events.length > 0 && (
        <select value={ev} onChange={(e) => setEv(e.target.value)} aria-label="Filtra per evento" data-testid="todo-filter-evento"
          className="ml-auto h-7 max-w-[11rem] rounded-full border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none focus:border-[#0ABAB5]">
          <option value="all">Tutti gli eventi</option>
          {events.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
          <option value="none">Senza evento</option>
        </select>
      )}
    </div>
  );
}

export default function TodoPanel() {
  const [items, setItems] = useState(null);
  const [tipo, setTipo] = useState("all");
  const [ev, setEv] = useState("all");
  const load = () => api.get("/my/todo").then(({ data }) => setItems(data.items)).catch(() => setItems([]));
  useEffect(() => { load(); }, []);
  const done = async (i) => {
    try { await api.post("/my/todo/complete", { tipo: i.tipo, id: i.id }); setItems((l) => l.filter((x) => x.id !== i.id)); toast.success("Attività completata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const shown = (items || []).filter((i) => (tipo === "all" || i.tipo === tipo) && (ev === "all" || (ev === "none" ? !i.evento_id : i.evento_id === ev)));
  const groups = Object.keys(BUCKET).map((b) => [b, shown.filter((i) => i.bucket === b)]).filter(([, l]) => l.length);
  return (
    <section className="flex flex-col min-h-0 h-[420px] lg:h-[calc(100dvh-14rem)] lg:min-h-[420px] rounded-xl border border-slate-200 bg-white" data-testid="todo-panel">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
        <ListTodo className="w-4 h-4 text-[#0ABAB5]" /><h2 className="font-semibold text-slate-900">To Do List</h2>
        {items && <span className="ml-auto rounded-full bg-[#0ABAB5]/15 text-slate-800 text-xs font-semibold px-2 py-0.5" data-testid="todo-count">{shown.length}</span>}
      </header>
      {items?.length > 0 && <TodoFilters items={items} tipo={tipo} setTipo={setTipo} ev={ev} setEv={setEv} />}
      <div className="flex-1 overflow-y-auto" data-testid="todo-list">
        {items === null ? <p className="p-4 text-sm text-slate-400">Caricamento...</p>
          : !items.length ? <p className="p-4 text-sm text-slate-500" data-testid="todo-empty">Nessuna attività da completare.</p>
          : !shown.length ? <p className="p-4 text-sm text-slate-500" data-testid="todo-filter-empty">Nessuna attività con i filtri selezionati.</p>
          : groups.map(([b, l]) => (
            <div key={b} data-testid={`todo-group-${b}`}>
              <div className={`sticky top-0 bg-slate-50 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide ${BUCKET[b][1]}`}>{BUCKET[b][0]} · {l.length}</div>
              <ul>{l.map((i) => <TodoRow key={`${i.tipo}-${i.id}`} i={i} onDone={done} />)}</ul>
            </div>
          ))}
      </div>
    </section>
  );
}
