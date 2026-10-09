import { useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ChevronDown, UserMinus } from "lucide-react";

const loadPeople = () => api.get("/my/todo/assignees").then(({ data }) => data.items);

export default function AssignSelect({ item, onAssigned }) {
  const [open, setOpen] = useState(false);
  const [people, setPeople] = useState(null);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const label = item.responsabile || "Assegna";
  const shown = useMemo(() => (people || []).filter((p) => `${p.cognome || ""} ${p.nome || ""}`.toLowerCase().includes(q.toLowerCase())), [people, q]);
  if (!item.can_edit) return item.responsabile ? <span className="truncate">· {item.responsabile}</span> : null;
  const openMenu = (o) => { setOpen(o); if (o && !people) loadPeople().then(setPeople).catch(() => setPeople([])); if (!o) setQ(""); };
  const pick = async (pid) => {
    setBusy(true);
    try {
      const { data } = await api.post("/my/todo/assign", { tipo: item.tipo, id: item.id, responsabile_id: pid });
      onAssigned(item, pid, data.responsabile); setOpen(false); setQ("");
      toast.success(pid ? `Assegnata a ${data.responsabile}` : "Assegnazione rimossa");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <span className="inline-flex items-center">·
      <Popover open={open} onOpenChange={openMenu}>
        <PopoverTrigger asChild>
          <button type="button" data-testid={`todo-assign-${item.id}`}
            className={`ml-1 inline-flex items-center gap-0.5 min-h-[24px] rounded px-1 font-semibold transition-colors ${item.responsabile ? "text-slate-700 hover:text-[#088F8A]" : "text-[#088F8A] hover:bg-[#0ABAB5]/10"}`}>
            <span className="truncate max-w-[10rem]">{label}</span><ChevronDown className="w-3 h-3 shrink-0" />
          </button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 max-w-[calc(100vw-2rem)] p-2" data-testid={`todo-assign-menu-${item.id}`}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca persona..." data-testid="todo-assign-search"
            className="w-full h-9 rounded-md border border-slate-200 px-2 text-sm outline-none focus:border-[#0ABAB5]" />
          <ul className="mt-2 max-h-60 overflow-y-auto text-sm">
            {people === null ? <li className="px-2 py-1.5 text-slate-400">Caricamento...</li>
              : !shown.length ? <li className="px-2 py-1.5 text-slate-500">Nessuna persona trovata</li>
              : shown.map((p) => (
                <li key={p.id}><button type="button" disabled={busy} onClick={() => pick(p.id)} data-testid={`todo-assign-opt-${p.id}`}
                  className={`w-full text-left px-2 py-2 rounded hover:bg-[#0ABAB5]/10 ${p.id === item.responsabile_id ? "font-semibold text-[#088F8A]" : "text-slate-700"}`}>{`${p.cognome || ""} ${p.nome || ""}`.trim()}</button></li>
              ))}
          </ul>
          {item.responsabile_id && <button type="button" disabled={busy} onClick={() => pick(null)} data-testid="todo-assign-remove"
            className="mt-1 w-full flex items-center gap-1.5 px-2 py-2 rounded text-sm text-red-600 hover:bg-red-50"><UserMinus className="w-4 h-4" />Rimuovi assegnazione</button>}
        </PopoverContent>
      </Popover>
    </span>
  );
}
