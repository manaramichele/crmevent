import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { ChevronsUpDown, Plus, Trash2 } from "lucide-react";
import TeamSelect from "@/components/TeamSelect";

export const PROVENIENZA = { manuale: "Inserimento manuale", link_disponibilita: "Link disponibilità", non_determinata: "Non determinata" };
const CATS = [["staff", "Staff"], ["volontario", "Volontario"]];
const sel = "h-10 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";
const blankRow = (categoria) => ({ key: Math.random().toString(36).slice(2), evento_id: "", categoria, team_id: "", ruolo: "", preferenza: "" });

function EventPicker({ value, events, onChange, testid }) {
  const [open, setOpen] = useState(false);
  const cur = events.find((e) => e.id === value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={`${sel} flex items-center justify-between text-left`} data-testid={testid}>
          <span className={`truncate ${cur ? "text-slate-900" : "text-slate-400"}`}>{cur?.nome || "Seleziona evento…"}</span><ChevronsUpDown className="h-4 w-4 shrink-0 text-slate-400" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[240px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Cerca evento…" data-testid={`${testid}-search`} />
          <CommandList><CommandEmpty>Nessun evento</CommandEmpty>
            {events.map((e) => <CommandItem key={e.id} value={`${e.nome} ${e.id}`} onSelect={() => { onChange(e.id); setOpen(false); }} data-testid={`${testid}-opt-${e.id}`}>{e.nome}</CommandItem>)}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function Section({ title, children, testid }) {
  return <section className="space-y-3" data-testid={testid}><h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 border-b border-slate-100 pb-1.5">{title}</h3>{children}</section>;
}

function AssignRow({ r, i, events, ruoli, availPref, onChange, onRemove }) {
  const set = (k, v) => onChange({ ...r, [k]: v, ...(k === "evento_id" ? { team_id: "" } : {}) });
  const prefOpts = [...new Set([...ruoli, ...(r.preferenza ? [r.preferenza] : [])])];
  return (
    <div className="rounded-lg border border-slate-200 p-3 space-y-2" data-testid={`mask-assign-${i}`}>
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0"><EventPicker value={r.evento_id} events={events} onChange={(v) => set("evento_id", v)} testid={`mask-assign-event-${i}`} /></div>
        <Button type="button" variant="ghost" size="icon" className="h-9 w-9 text-slate-400 hover:text-red-500" onClick={onRemove} title="Rimuovi associazione" data-testid={`mask-assign-remove-${i}`}><Trash2 className="h-4 w-4" /></Button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <label className="text-xs text-slate-500">Ruolo<select className={sel} value={r.categoria} onChange={(e) => set("categoria", e.target.value)} data-testid={`mask-assign-cat-${i}`}>{CATS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="text-xs text-slate-500">Preferenza
          <select className={sel} value={r.preferenza || ""} onChange={(e) => set("preferenza", e.target.value)} data-testid={`mask-assign-pref-${i}`}><option value="">{availPref ? `Dal link: ${availPref}` : "— Nessuna —"}</option>{prefOpts.map((x) => <option key={x} value={x}>{x}</option>)}</select></label>
        <div className="text-xs text-slate-500">Team<TeamSelect value={r.team_id || ""} eventoId={r.evento_id} onChange={(v) => set("team_id", v)} testid={`mask-assign-team-${i}`} /></div>
        <label className="text-xs text-slate-500">Mansione<select className={sel} value={r.ruolo || ""} onChange={(e) => set("ruolo", e.target.value)} data-testid={`mask-assign-mansione-${i}`}><option value="">— Nessuna —</option>{[...new Set([...ruoli, ...(r.ruolo ? [r.ruolo] : [])])].map((x) => <option key={x} value={x}>{x}</option>)}</select></label>
      </div>
    </div>
  );
}

const pick = (o, keys) => Object.fromEntries(keys.map((k) => [k, o?.[k] ?? ""]));

export default function PersonMask({ person, defaultCategoria = "staff", fields, events, ruoli = [], onClose, onSaved }) {
  const names = fields.map((f) => f.name);
  const initial = useMemo(() => ({
    data: pick(person, names),
    rows: (person?.assegnazioni || []).filter((a) => ["staff", "volontario", "collaboratore"].includes(a.categoria))
      .map((a) => ({ key: a.id, id: a.id, evento_id: a.evento_id, categoria: a.categoria === "collaboratore" ? "staff" : a.categoria, team_id: a.team_id || "", ruolo: a.ruolo || "", preferenza: a.preferenza || "", stato: a.stato, orig: a.categoria })),
  }), [person]); // eslint-disable-line react-hooks/exhaustive-deps
  const [data, setData] = useState(initial.data);
  const [rows, setRows] = useState(initial.rows);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { setData(initial.data); setRows(initial.rows); }, [initial]);
  const dirty = JSON.stringify({ data, rows }) !== JSON.stringify(initial);
  const close = () => { if (!dirty || window.confirm("Ci sono modifiche non salvate. Vuoi chiudere senza salvare?")) onClose(); };
  const availPref = (eid) => [...new Set((person?.preferenze || []).filter((p) => p.evento_id === eid).map((p) => p.preferenza).filter(Boolean))].join(", ");
  const prov = person ? (person.provenienza_tipo || "non_determinata") : "manuale";

  const save = async () => {
    setErr("");
    if (!(data.nome || "").trim()) return setErr("Il nome è obbligatorio.");
    if (rows.some((r) => !r.evento_id)) return setErr("Seleziona l'evento in ogni associazione oppure rimuovi la riga vuota.");
    const keys = rows.map((r) => `${r.evento_id}|${r.categoria}`);
    if (new Set(keys).size !== keys.length) return setErr("La stessa persona è associata due volte allo stesso evento con lo stesso ruolo: rimuovi il duplicato.");
    setBusy(true);
    try {
      const body = Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v === "" ? null : v]));
      const pid = person ? (await api.put(`/persons/${person.id}`, body), person.id) : (await api.post("/persons", body)).data.id;
      const keep = new Set(rows.filter((r) => r.id).map((r) => r.id));
      for (const a of initial.rows) if (!keep.has(a.id)) await api.delete(`/staff/${a.id}`);
      for (const r of rows) {
        const payload = { persona_id: pid, evento_id: r.evento_id, categoria: r.id && r.orig === "collaboratore" && r.categoria === "staff" ? "collaboratore" : r.categoria, team_id: r.team_id || null, ruolo: r.ruolo || null, preferenza: r.preferenza || null };
        if (!r.id) await api.post("/staff", { ...payload, stato: "da_contattare" });
        else {
          const o = initial.rows.find((x) => x.id === r.id);
          if (JSON.stringify(o) !== JSON.stringify(r)) await api.put(`/staff/${r.id}`, { ...payload, stato: r.stato });
        }
      }
      toast.success(person ? "Anagrafica aggiornata" : "Persona creata");
      onSaved();
    } catch (e) { setErr(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && close()}>
      <DialogContent className="w-[96vw] max-w-3xl max-h-[92dvh] p-0 flex flex-col gap-0" data-testid="person-mask" onInteractOutside={(e) => dirty && e.preventDefault()}>
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-slate-100">
          <DialogTitle className="font-display" data-testid="person-mask-title">{person ? `Modifica — ${person.cognome || ""} ${person.nome || ""}` : defaultCategoria === "volontario" ? "Nuovo Volontario" : "Nuovo Staff"}</DialogTitle>
          <DialogDescription>Anagrafica, ruolo, preferenza, team, mansione ed eventi in un'unica maschera.</DialogDescription>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
          <Section title="A · Dati anagrafici" testid="mask-section-anagrafica">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {fields.map((f) => (
                <label key={f.name} className={`text-xs text-slate-500 ${f.full ? "sm:col-span-2" : ""}`}>{f.label}{f.required ? " *" : ""}
                  {f.type === "textarea" ? <Textarea value={data[f.name] || ""} onChange={(e) => setData({ ...data, [f.name]: e.target.value })} className="mt-1 text-sm text-slate-900" data-testid={`mask-field-${f.name}`} />
                    : f.type === "select" ? <select className={`${sel} mt-1`} value={data[f.name] || ""} onChange={(e) => setData({ ...data, [f.name]: e.target.value })} data-testid={`mask-field-${f.name}`}><option value="">—</option>{(f.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
                      : <Input type={f.type || "text"} value={data[f.name] || ""} onChange={(e) => setData({ ...data, [f.name]: e.target.value })} className="mt-1 text-sm text-slate-900" data-testid={`mask-field-${f.name}`} />}
                </label>))}
            </div>
          </Section>
          <Section title="B · Dati organizzativi" testid="mask-section-org">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div><div className="text-xs text-slate-500">Provenienza registrazione</div><div className="mt-1 font-medium text-slate-800" data-testid="mask-provenienza">{PROVENIENZA[prov]}</div>
                {person?.provenienza?.at && <div className="text-xs text-slate-500">dal {new Date(person.provenienza.at).toLocaleDateString("it-IT")}{person.provenienza.evento_id && events.find((e) => e.id === person.provenienza.evento_id) ? ` · ${events.find((e) => e.id === person.provenienza.evento_id).nome}` : ""}</div>}
                <div className="text-[11px] text-slate-400">Dato di sistema, impostato automaticamente.</div></div>
              <div><div className="text-xs text-slate-500">Preferenze indicate nei link disponibilità</div><div className="mt-1 text-slate-700" data-testid="mask-avail-prefs">{(person?.preferenze || []).length ? person.preferenze.map((p) => `${p.preferenza || "Non indicata"}${p.evento_nome ? ` (${p.evento_nome})` : ""}`).join(" · ") : "—"}</div></div>
            </div>
            <p className="text-xs text-slate-500">Ruolo, preferenza, team e mansione si impostano per ciascun evento qui sotto: la stessa persona può avere valori diversi in eventi diversi.</p>
          </Section>
          <Section title="C · Eventi e assegnazioni" testid="mask-section-eventi">
            {rows.length === 0 && <p className="text-sm text-slate-400" data-testid="mask-no-events">Nessun evento associato.</p>}
            {rows.map((r, i) => <AssignRow key={r.key} r={r} i={i} events={events} ruoli={ruoli} availPref={availPref(r.evento_id)} onChange={(n) => setRows(rows.map((x) => (x.key === r.key ? n : x)))} onRemove={() => setRows(rows.filter((x) => x.key !== r.key))} />)}
            <Button type="button" variant="outline" onClick={() => setRows([...rows, blankRow(rows[rows.length - 1]?.categoria || defaultCategoria)])} data-testid="mask-add-event"><Plus className="h-4 w-4 mr-1.5" />Aggiungi evento</Button>
          </Section>
        </div>
        <div className="border-t border-slate-100 px-5 py-3 flex flex-col-reverse sm:flex-row sm:items-center gap-2 bg-white rounded-b-lg">
          {err && <p className="text-sm text-red-600 sm:flex-1" role="alert" data-testid="person-mask-error">{err}</p>}
          <div className="flex gap-2 sm:ml-auto">
            <Button variant="outline" onClick={close} className="flex-1 sm:flex-none" data-testid="person-mask-cancel">Annulla</Button>
            <Button onClick={save} disabled={busy} className="flex-1 sm:flex-none bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="person-mask-save">{busy ? "Salvataggio…" : "Salva"}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
