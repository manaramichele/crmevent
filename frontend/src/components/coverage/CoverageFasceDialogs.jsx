import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { AlertTriangle } from "lucide-react";
import { cmpIt } from "@/lib/sortOptions";

const COV = { complete: ["Completa", "bg-emerald-50 text-emerald-700"], partial: ["Parziale", "bg-sky-50 text-sky-700"], tbc: ["Da verificare", "bg-amber-50 text-amber-800"], none: ["Non disponibile", "bg-slate-100 text-slate-500"] };
const fmtD = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
const byName = (a, b) => cmpIt(a.cognome, b.cognome) || cmpIt(a.nome, b.nome);
const Badge = ({ cls, children, testid }) => <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`} data-testid={testid}>{children}</span>;

function PersonRow({ p, row, eventoId, onOpen, onChanged }) {
  const [warn, setWarn] = useState(null);
  const [busy, setBusy] = useState(false);
  const [lab, cls] = COV[p.cov];
  const base = { evento_id: eventoId, date: row.date, fascia: row.fascia };
  const assign = async (opts = {}) => {
    setBusy(true);
    try { await api.post("/staff-coverage/assign", { ...base, team_id: row.team_id, persona_id: p.id, ...opts }); setWarn(null); onChanged(); }
    catch (e) { const d = e.response?.data?.detail; if (e.response?.status === 409 && d?.message) setWarn({ ...d, opts }); else toast.error(formatApiError(d)); }
    setBusy(false);
  };
  const remove = async () => {
    setBusy(true);
    try { await api.delete("/staff-coverage/assign", { params: { ...base, persona_id: p.id } }); onChanged(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  return (
    <tr className="border-t border-slate-100 align-top" data-testid={`fx-person-${p.id}`}>
      <td className="px-2 py-1.5 font-medium text-slate-800"><button type="button" className="hover:underline text-left" onClick={() => onOpen(p.id)} data-testid={`fx-person-edit-${p.id}`}>{p.cognome} {p.nome}</button><div className="text-[11px] text-slate-400 font-normal">{p.categoria}</div></td>
      <td className="px-2 py-1.5">{p.gruppo || "—"}</td>
      <td className="px-2 py-1.5"><div className="flex flex-wrap gap-1 items-center"><Badge cls={cls}>{lab}</Badge>{p.cov !== "none" && <span className="tabular-nums text-slate-600">{p.orario}</span>}
        {p.legacy && <Badge cls="bg-amber-100 text-amber-900" testid={`fx-person-legacy-${p.id}`}>Da aggiornare · vecchio modulo</Badge>}</div></td>
      <td className="px-2 py-1.5">
        {p.assigned ? <div className="flex flex-wrap items-center gap-1.5"><Badge cls="bg-emerald-100 text-emerald-800" testid={`fx-person-assigned-${p.id}`}>Assegnato</Badge>{p.forced && <Badge cls="bg-red-50 text-red-700">Fuori disponibilità</Badge>}
          <Button size="sm" variant="ghost" className="h-7 px-2 text-red-600" disabled={busy} onClick={remove} data-testid={`fx-unassign-${p.id}`}>Rimuovi</Button></div>
          : <div className="space-y-1">{p.assigned_other && <div className="text-[11px] text-slate-500">Assegnato a {p.assigned_other}</div>}
            <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => assign()} data-testid={`fx-assign-${p.id}`}>Assegna</Button></div>}
        {warn && <div className="mt-1 rounded bg-amber-50 border border-amber-200 p-1.5 text-xs text-amber-900" data-testid={`fx-assign-warn-${p.id}`}>{warn.message}
          <div className="mt-1 flex gap-2"><Button size="sm" className="h-7" disabled={busy} onClick={() => assign(warn.code === "other_team" ? { move: true } : { ...warn.opts, force: true })} data-testid={`fx-assign-force-${p.id}`}>Conferma</Button><Button size="sm" variant="ghost" className="h-7" onClick={() => setWarn(null)}>Annulla</Button></div></div>}
      </td>
    </tr>
  );
}

export function TeamSlotDialog({ row, eventoId, onClose, onOpenPerson, onChanged }) {
  const [flt, setFlt] = useState("all");
  const ppl = (row?.people || []).filter((p) => flt === "all" || (flt === "avail" ? p.cov !== "none" : flt === "legacy" ? p.legacy : p.assigned)).sort(byName);
  return (
    <Dialog open={!!row} onOpenChange={(o) => { if (!o) { setFlt("all"); onClose(); } }}>
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" data-testid="fx-people-dialog">
        <DialogHeader><DialogTitle className="pr-8">{row && `${row.team} · ${row.label}${row.start ? ` ${row.start}–${row.end}` : ""}`}</DialogTitle>
          {row && <DialogDescription>{fmtD(row.date)} · {row.available} disponibili · {row.assigned} assegnati · {row.needed ? `${row.needed} necessari · ${row.missing} mancanti` : "necessari non indicati"}</DialogDescription>}</DialogHeader>
        <div className="flex flex-wrap gap-2 text-sm">
          {[["all", "Tutti i membri"], ["avail", "Disponibili"], ["assigned", "Assegnati"], ["legacy", "Da aggiornare"]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => setFlt(k)} className={`px-3 py-1 rounded-full border ${flt === k ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600"}`} data-testid={`fx-filter-${k}`}>{l}</button>))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="text-xs text-slate-500"><tr>{["Cognome e nome", "Gruppo", "Disponibilità", "Assegnazione"].map((h) => <th key={h} className="text-left font-medium px-2 py-1">{h}</th>)}</tr></thead>
            <tbody>{row && ppl.map((p) => <PersonRow key={p.id} p={p} row={row} eventoId={eventoId} onOpen={onOpenPerson} onChanged={onChanged} />)}</tbody>
          </table>
          {!ppl.length && <p className="text-sm text-slate-400 py-6 text-center" data-testid="fx-people-empty">Nessun membro confermato.</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function MansioneWarnings({ w, onOpenPerson }) {
  const [open, setOpen] = useState(false);
  if (!w || (!w.mansione_needs && !w.fascia_needs && !w.no_team.length)) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700" data-testid="cov-mansione-warnings">
      <button type="button" className="inline-flex items-center gap-2 font-medium" onClick={() => setOpen(!open)} data-testid="cov-mansione-warnings-toggle"><AlertTriangle className="w-4 h-4 text-amber-600" />Da sistemare a mano per il passaggio ai Team</button>
      {open && <ul className="mt-2 space-y-1 list-disc pl-5 text-xs">
        {w.mansione_needs > 0 && <li>{w.mansione_needs} fabbisogni impostati per mansione: non sono più usati, reinserisci i Necessari per Team nella tabella.</li>}
        {w.fascia_needs > 0 && <li>{w.fascia_needs} fabbisogni per fascia senza Team: non sono più usati.</li>}
        {w.no_team.length > 0 && <li>{w.no_team.length} persone confermate senza Team (non assegnabili): {w.no_team.sort(byName).map((p, i) => <span key={p.id}>{i > 0 && ", "}<button type="button" className="underline" onClick={() => onOpenPerson(p.id)}>{p.cognome} {p.nome}</button>{p.mansioni.length ? ` (${p.mansioni.join(", ")})` : ""}</span>)}</li>}
      </ul>}
    </div>
  );
}

export function LegacyDialog({ open, list, onClose, onOpenPerson }) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="cov-legacy-dialog">
        <DialogHeader><DialogTitle>Disponibilità da aggiornare ({list.length})</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">Staff e Volontari confermati con disponibilità del vecchio modulo, incomplete o non indicate. Apri la scheda e scegli Mattina e/o Pomeriggio: i giorni non modificati restano invariati.</p>
        <div className="divide-y divide-slate-100">
          {[...list].sort(byName).map((p) => (
            <div key={p.id} className="py-2 flex flex-col sm:flex-row sm:items-center gap-2" data-testid={`cov-legacy-person-${p.id}`}>
              <div className="flex-1"><div className="font-medium text-slate-800">{p.cognome} {p.nome} <span className="text-xs text-slate-400 font-normal">{p.categoria}{p.team ? ` · ${p.team}` : ""}</span></div>
                <div className="text-xs text-slate-600">{p.days.length ? p.days.map((d) => `${fmtD(d.date)}: ${d.orario}`).join(" · ") : <i>{p.reason}</i>}</div></div>
              <Button size="sm" variant="outline" onClick={() => onOpenPerson(p.id)} data-testid={`cov-legacy-edit-${p.id}`}>Modifica anagrafica</Button>
            </div>))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
