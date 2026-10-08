import { useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useWheelScroll } from "@/lib/useWheelScroll";
import { ChevronsUpDown, UserPlus, ArrowLeft } from "lucide-react";

const pname = (p) => (p ? (`${p.cognome || ""} ${p.nome || ""}`.trim() || p.email || p.id) : "");

// Selettore Staff condiviso tra Pipeline (campo Responsabile) e Checklist (Assegna).
// Mostra SOLO lo Staff dell'evento + "Aggiungi nuovo Staff" (quick-add con dedup).
export function StaffAssignSelect({
  eventoId, staffPersons = [], allPersons = [], value = null,
  onChange, onStaffAdded, trigger, align = "start", triggerTestid,
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [quick, setQuick] = useState(null);
  const [existing, setExisting] = useState(null);
  const [busy, setBusy] = useState(false);
  const bindWheel = useWheelScroll();

  const selected = useMemo(() => {
    if (!value) return null;
    return staffPersons.find((p) => p.id === value) || allPersons.find((p) => p.id === value) || null;
  }, [value, staffPersons, allPersons]);
  const isStale = !!value && !staffPersons.some((p) => p.id === value);

  const list = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return staffPersons
      .filter((p) => !ql || pname(p).toLowerCase().includes(ql))
      .sort((a, b) => `${a.cognome || ""} ${a.nome || ""}`.trim().localeCompare(`${b.cognome || ""} ${b.nome || ""}`.trim(), "it", { sensitivity: "base" }));
  }, [staffPersons, q]);

  const reset = () => { setQ(""); setQuick(null); setExisting(null); };
  const close = () => { setOpen(false); reset(); };
  const pick = (pid) => { onChange?.(pid); close(); };

  const onListKeyDown = (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const btns = [...e.currentTarget.querySelectorAll("button[data-opt]")];
    const idx = btns.indexOf(document.activeElement);
    let next = e.key === "ArrowDown" ? idx + 1 : idx - 1;
    if (next < 0) next = 0;
    if (next >= btns.length) next = btns.length - 1;
    btns[next]?.focus();
  };
  const focusFirstOpt = (e) => {
    if (e.key !== "ArrowDown") return;
    e.preventDefault();
    const first = e.currentTarget.closest("[data-radix-popper-content-wrapper]")?.querySelector("button[data-opt]")
      || document.querySelector("[data-testid='staff-assign-list'] button[data-opt]");
    first?.focus();
  };

  const submitQuick = async () => {
    if (!quick.nome.trim() || !quick.cognome.trim()) return toast.error("Nome e Cognome obbligatori");
    setBusy(true);
    try {
      const { data } = await api.post("/staff/quick-add", { evento_id: eventoId, nome: quick.nome.trim(), cognome: quick.cognome.trim(), cellulare: quick.cellulare, email: quick.email });
      if (data.status === "exists") { setExisting(data.person); return; }
      if (onStaffAdded) await onStaffAdded(data.person);
      onChange?.(data.person.id);
      toast.success("Staff aggiunto e selezionato");
      close();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const useExisting = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/staff/quick-add", { evento_id: eventoId, nome: quick.nome.trim() || existing.nome, cognome: (quick.cognome.trim() || existing.cognome || ""), use_existing_person_id: existing.id });
      if (onStaffAdded) await onStaffAdded(data.person);
      onChange?.(data.person.id);
      toast.success("Anagrafica esistente associata allo Staff");
      close();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  const defaultTrigger = (
    <button type="button" data-testid={triggerTestid}
      className="flex h-10 w-full items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2 text-sm hover:border-slate-300">
      <span className={value ? "text-slate-800 truncate" : "text-slate-400"}>{selected ? `${pname(selected)}${isStale ? " · non più nello Staff" : ""}` : "—"}</span>
      <ChevronsUpDown className="h-4 w-4 opacity-50 shrink-0" />
    </button>
  );

  return (
    <Popover open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
      <PopoverTrigger asChild>{trigger || defaultTrigger}</PopoverTrigger>
      <PopoverContent className="w-72 p-0 z-[200]" align={align} data-testid="staff-assign-popover" onOpenAutoFocus={(e) => { if (quick) e.preventDefault(); }}>
        {quick ? (
          <div className="p-3 space-y-3" data-testid="staff-quick-add-form">
            <button type="button" onClick={() => { setQuick(null); setExisting(null); }} className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"><ArrowLeft className="w-3.5 h-3.5" />Indietro</button>
            <div className="text-sm font-semibold text-slate-800">Aggiungi nuovo Staff</div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1"><Label className="text-xs">Nome *</Label><Input autoFocus value={quick.nome} onChange={(e) => setQuick((s) => ({ ...s, nome: e.target.value }))} className="h-8" data-testid="qs-nome" /></div>
              <div className="space-y-1"><Label className="text-xs">Cognome *</Label><Input value={quick.cognome} onChange={(e) => setQuick((s) => ({ ...s, cognome: e.target.value }))} className="h-8" data-testid="qs-cognome" /></div>
            </div>
            <div className="space-y-1"><Label className="text-xs">Cellulare</Label><Input value={quick.cellulare} onChange={(e) => setQuick((s) => ({ ...s, cellulare: e.target.value }))} className="h-8" placeholder="+39..." data-testid="qs-cellulare" /></div>
            <div className="space-y-1"><Label className="text-xs">Email</Label><Input type="email" value={quick.email} onChange={(e) => setQuick((s) => ({ ...s, email: e.target.value }))} className="h-8" data-testid="qs-email" /></div>
            {existing && <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">Esiste già un'anagrafica con questi contatti: <b>{existing.cognome} {existing.nome}</b>. Usarla come Staff di questo evento?</div>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => { setQuick(null); setExisting(null); }}>Annulla</Button>
              {existing
                ? <Button type="button" size="sm" onClick={useExisting} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="qs-use-existing">Usa esistente</Button>
                : <Button type="button" size="sm" onClick={submitQuick} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="qs-submit">Aggiungi</Button>}
            </div>
          </div>
        ) : (
          <>
            <div className="p-1.5 border-b border-slate-100"><Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={focusFirstOpt} placeholder="Cerca staff..." className="h-8" data-testid="staff-assign-search" /></div>
            <div ref={bindWheel} onKeyDown={onListKeyDown} className="max-h-56 overflow-y-auto p-1" data-testid="staff-assign-list">
              <button type="button" data-opt onClick={() => pick(null)} className="w-full text-left text-sm px-2 py-1.5 rounded-md hover:bg-slate-100 focus:bg-slate-100 outline-none text-slate-500" data-testid="staff-opt-none">—</button>
              {list.map((p) => (
                <button type="button" data-opt key={p.id} onClick={() => pick(p.id)} className={`w-full text-left text-sm px-2 py-1.5 rounded-md hover:bg-slate-100 focus:bg-slate-100 outline-none ${p.id === value ? "bg-tiffany-light/40 font-semibold" : ""}`} data-testid={`staff-opt-${p.id}`}>{pname(p)}</button>
              ))}
              {list.length === 0 && <div className="px-2 py-2 text-xs text-slate-400" data-testid="staff-opt-empty">Nessuno Staff trovato</div>}
              {isStale && selected && <div className="px-2 py-1.5 text-xs text-amber-700">{pname(selected)} · non più nello Staff</div>}
            </div>
            <div className="p-1 border-t border-slate-100">
              <button type="button" onClick={() => { setExisting(null); setQuick({ nome: q.trim(), cognome: "", cellulare: "", email: "" }); }} className="w-full text-left text-sm text-tiffany-active font-semibold px-2 py-1.5 rounded hover:bg-tiffany-light/50 inline-flex items-center gap-1" data-testid="staff-add-new"><UserPlus className="w-3.5 h-3.5" />Aggiungi nuovo Staff</button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}
