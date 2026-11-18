import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Check, ChevronsUpDown, Eye, EyeOff, Pencil, Plus, Trash2, X } from "lucide-react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { apiErr, SEL } from "@/components/asd/asdShared";

export const ENTI_CHANGED = "asd-enti:changed";
const TIPI = { federazione: "Federazione", eps: "Ente di promozione sportiva", altro: "Altro organismo" };

export function useEnti() {
  const [d, setD] = useState({ items: [], tipi: TIPI, can_manage: false });
  const reload = useCallback(() => api.get("/asd/enti").then(({ data }) => setD(data)).catch(apiErr), []);
  useEffect(() => { reload(); const h = () => reload(); window.addEventListener(ENTI_CHANGED, h); return () => window.removeEventListener(ENTI_CHANGED, h); }, [reload]);
  return { ...d, reload };
}

function EnteForm({ initial, onClose, onSaved }) {
  const [f, setF] = useState(initial || { sigla: "", nome: "", tipo: "federazione" });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!f.sigla.trim()) { toast.error("Sigla: campo obbligatorio"); return; }
    setBusy(true);
    try {
      const { data } = f.id ? await api.put(`/asd/enti/${f.id}`, f) : await api.post("/asd/enti", f);
      toast.success(f.id ? "Voce aggiornata" : "Ente o federazione aggiunto");
      window.dispatchEvent(new Event(ENTI_CHANGED)); onSaved(data);
    } catch (e) { apiErr(e); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="w-[95vw] max-w-md z-[210]" data-testid="asd-ente-form">
        <DialogHeader><DialogTitle className="font-display">{f.id ? "Modifica ente o federazione" : "Aggiungi ente o federazione"}</DialogTitle><DialogDescription>La voce sarà disponibile nei tesseramenti e nelle Impostazioni.</DialogDescription></DialogHeader>
        <label className="text-xs text-slate-500">Sigla *<Input value={f.sigla} onChange={(e) => setF({ ...f, sigla: e.target.value })} className="mt-1" data-testid="asd-ente-sigla" /></label>
        <label className="text-xs text-slate-500">Denominazione completa<Input value={f.nome || ""} onChange={(e) => setF({ ...f, nome: e.target.value })} className="mt-1" data-testid="asd-ente-nome" /></label>
        <label className="text-xs text-slate-500">Tipologia<select className={`${SEL} w-full mt-1`} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })} data-testid="asd-ente-tipo">{Object.entries(TIPI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <div className="flex justify-end gap-2 pt-2"><Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button disabled={busy} onClick={save} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="asd-ente-save">Salva</Button></div>
      </DialogContent>
    </Dialog>
  );
}

// Menu ricercabile per sigla o denominazione; le voci disattivate non sono selezionabili (restano visibili nei dati storici).
export function EnteSelect({ value, onChange }) {
  const { items, tipi } = useEnti();
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const cur = items.find((e) => e.id === value);
  const active = items.filter((e) => e.active);
  return (
    <>
      <Popover open={open} onOpenChange={setOpen} modal>
        <PopoverTrigger asChild>
          <button type="button" className={`${SEL} w-full flex items-center justify-between text-left`} data-testid="asd-ente-select">
            <span className={`truncate ${cur ? "text-slate-900" : "text-slate-400"}`}>{cur ? `${cur.label}${cur.active ? "" : " (disattivato)"}` : "Cerca per sigla o denominazione…"}</span><ChevronsUpDown className="h-4 w-4 shrink-0 text-slate-400" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[280px] p-0 z-[200]" align="start">
          <Command>
            <CommandInput placeholder="Es. CSI, FIDAL, Nuoto…" data-testid="asd-ente-search" />
            <CommandList><CommandEmpty>Nessun ente trovato</CommandEmpty>
              {Object.entries(tipi).map(([t, lab]) => active.some((e) => e.tipo === t) && (
                <CommandGroup key={t} heading={lab}>{active.filter((e) => e.tipo === t).map((e) => (
                  <CommandItem key={e.id} value={`${e.sigla} ${e.nome || ""} ${e.id}`} onSelect={() => { onChange(e.id); setOpen(false); }} data-testid={`asd-ente-opt-${e.id}`}>
                    {value === e.id && <Check className="w-4 h-4 mr-1 text-tiffany-active" />}{e.label}</CommandItem>))}</CommandGroup>))}
            </CommandList>
          </Command>
          <button type="button" className="w-full border-t border-slate-100 px-3 py-2 text-left text-sm font-medium text-tiffany-fg hover:bg-slate-50 flex items-center gap-1" onClick={() => { setOpen(false); setAdding(true); }} data-testid="asd-ente-add"><Plus className="w-4 h-4" />Aggiungi ente o federazione</button>
        </PopoverContent>
      </Popover>
      {adding && <EnteForm onClose={() => setAdding(false)} onSaved={(e) => { setAdding(false); onChange(e.id); }} />}
    </>
  );
}

// Impostazioni → Gestione menu a tendina → gruppo Gestione Società (visibile solo con modulo attivo).
export function EntiSettings() {
  const { items, tipi, can_manage, reload } = useEnti();
  const [q, setQ] = useState("");
  const [form, setForm] = useState(null);
  const changed = () => { window.dispatchEvent(new Event(ENTI_CHANGED)); reload(); };
  const call = async (p) => { try { await p; changed(); } catch (e) { apiErr(e); } };
  const move = (i, d) => { const ids = items.map((e) => e.id); [ids[i], ids[i + d]] = [ids[i + d], ids[i]]; call(api.put("/asd/enti/order", { ids })); };
  const del = (e) => window.confirm(`Eliminare "${e.label}"?`) && call(api.delete(`/asd/enti/${e.id}`));
  const shown = items.map((e, i) => ({ e, i })).filter(({ e }) => !q || `${e.sigla} ${e.nome || ""}`.toLowerCase().includes(q.toLowerCase()));
  const ib = "h-7 w-7 inline-flex items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-30";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 lg:col-span-2" data-testid="optlist-enti">
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-2">
        <h4 className="text-sm font-semibold text-slate-800 flex-1">Enti e Federazioni <span className="text-xs font-normal text-slate-400">{items.length} voci</span></h4>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca sigla o denominazione" className="h-9 text-sm sm:w-64" data-testid="optlist-enti-search" />
        <Button variant="outline" size="sm" className="h-9" onClick={() => setForm({ sigla: "", nome: "", tipo: "federazione" })} data-testid="optlist-enti-add"><Plus className="w-4 h-4 mr-1" />Aggiungi</Button>
      </div>
      <ul className="divide-y divide-slate-100 max-h-[420px] overflow-y-auto">
        {shown.map(({ e, i }) => (
          <li key={e.id} className="flex items-center gap-1.5 py-1.5" data-testid={`optlist-enti-item-${e.id}`}>
            <span className={`flex-1 min-w-0 truncate text-sm ${e.active ? "text-slate-800" : "text-slate-400 line-through"}`}>{e.label}</span>
            <span className="hidden sm:inline text-[11px] text-slate-400 whitespace-nowrap">{tipi[e.tipo]}</span>
            {e.usage > 0 && <span className="text-[11px] text-slate-400 whitespace-nowrap">{e.usage} in uso</span>}
            {!e.active && <span className="text-[11px] font-semibold text-amber-700 bg-amber-50 rounded px-1.5">Disattivata</span>}
            {can_manage && (<>
              <button className={ib} disabled={q !== "" || i === 0} onClick={() => move(i, -1)} title="Sposta su" data-testid={`optlist-enti-up-${e.id}`}><ArrowUp className="w-3.5 h-3.5" /></button>
              <button className={ib} disabled={q !== "" || i === items.length - 1} onClick={() => move(i, 1)} title="Sposta giù" data-testid={`optlist-enti-down-${e.id}`}><ArrowDown className="w-3.5 h-3.5" /></button>
              <button className={ib} onClick={() => setForm({ id: e.id, sigla: e.sigla, nome: e.nome || "", tipo: e.tipo })} title="Modifica" data-testid={`optlist-enti-edit-${e.id}`}><Pencil className="w-3.5 h-3.5" /></button>
              <button className={ib} onClick={() => call(api.post(`/asd/enti/${e.id}/stato`, { active: !e.active }))} title={e.active ? "Disattiva" : "Riattiva"} data-testid={`optlist-enti-toggle-${e.id}`}>{e.active ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}</button>
              {!e.usage && <button className={`${ib} hover:text-red-500`} onClick={() => del(e)} title="Elimina" data-testid={`optlist-enti-delete-${e.id}`}><Trash2 className="w-3.5 h-3.5" /></button>}
            </>)}
          </li>))}
        {!shown.length && <li className="py-2 text-sm text-slate-400"><X className="w-4 h-4 inline mr-1" />Nessuna voce trovata</li>}
      </ul>
      <p className="text-xs text-slate-500 mt-2">Le voci usate nei tesseramenti non si eliminano: si disattivano e restano nei dati storici.</p>
      {form && <EnteForm initial={form} onClose={() => setForm(null)} onSaved={() => { setForm(null); reload(); }} />}
    </div>
  );
}
