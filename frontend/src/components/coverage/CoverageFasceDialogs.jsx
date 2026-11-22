import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cmpIt } from "@/lib/sortOptions";

const COV = { complete: ["Completa", "bg-emerald-50 text-emerald-700"], partial: ["Parziale", "bg-sky-50 text-sky-700"], tbc: ["Da verificare", "bg-amber-50 text-amber-800"] };
const fmtD = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" });
const byName = (a, b) => cmpIt(a.cognome, b.cognome) || cmpIt(a.nome, b.nome);
const Badge = ({ cls, children, testid }) => <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`} data-testid={testid}>{children}</span>;

function assignText(p) {
  const parts = [p.mansioni.length ? `Mansione: ${p.mansioni.join(", ")}` : "", p.team ? `Team: ${p.team}` : "", p.turni.length ? `Turno ${p.turni.join(", ")}` : ""].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Non assegnato";
}

function PersonRow({ p, onOpen }) {
  const [lab, cls] = COV[p.cov];
  return (
    <tr className="border-t border-slate-100 align-top" data-testid={`fx-person-${p.id}`}>
      <td className="px-2 py-1.5 font-medium text-slate-800">{p.cognome} {p.nome}<div className="text-[11px] text-slate-400 font-normal">{p.categoria}</div></td>
      <td className="px-2 py-1.5">{p.team || "—"}</td>
      <td className="px-2 py-1.5">{p.gruppo || "—"}</td>
      <td className="px-2 py-1.5">{p.mansioni.join(", ") || (p.preferenza ? <span className="text-slate-400">Pref.: {p.preferenza}</span> : "—")}</td>
      <td className="px-2 py-1.5"><div className="flex flex-wrap gap-1 items-center"><Badge cls={cls}>{lab}</Badge><span className="tabular-nums text-slate-600">{p.orario}</span>
        {p.legacy && <Badge cls="bg-amber-100 text-amber-900" testid={`fx-person-legacy-${p.id}`}>Da aggiornare · vecchio modulo</Badge>}
        {p.changed && <Badge cls="bg-red-50 text-red-700">Orari fascia modificati</Badge>}</div></td>
      <td className="px-2 py-1.5 text-slate-600">{assignText(p)}</td>
      <td className="px-2 py-1.5"><Button size="sm" variant="outline" onClick={() => onOpen(p.id)} data-testid={`fx-person-edit-${p.id}`}>Modifica</Button></td>
    </tr>
  );
}

export function FasciaPeopleDialog({ row, onClose, onOpenPerson }) {
  const [flt, setFlt] = useState("all");
  const ppl = (row?.people || []).filter((p) => flt === "all" || (flt === "legacy" ? p.legacy : !p.legacy)).sort(byName);
  return (
    <Dialog open={!!row} onOpenChange={(o) => { if (!o) { setFlt("all"); onClose(); } }}>
      <DialogContent className="max-w-5xl max-h-[85vh] overflow-y-auto" data-testid="fx-people-dialog">
        <DialogHeader><DialogTitle className="pr-8">{row && `${row.label} · ${fmtD(row.date)}${row.start ? ` · ${row.start}–${row.end}` : ""}`}</DialogTitle></DialogHeader>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {[["all", "Tutti"], ["new", "Aggiornati"], ["legacy", "Da aggiornare"]].map(([k, l]) => (
            <button key={k} type="button" onClick={() => setFlt(k)} className={`px-3 py-1 rounded-full border ${flt === k ? "bg-slate-900 text-white border-slate-900" : "border-slate-200 text-slate-600"}`} data-testid={`fx-filter-${k}`}>{l}</button>))}
          {row && <span className="text-slate-500 sm:ml-auto">{row.available} complete · {row.partial} parziali · {row.tbc} da verificare · {row.assigned} assegnati</span>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[760px]">
            <thead className="text-xs text-slate-500"><tr>{["Cognome e nome", "Team", "Gruppo", "Mansione", "Disponibilità", "Stato assegnazione", ""].map((h) => <th key={h} className="text-left font-medium px-2 py-1">{h}</th>)}</tr></thead>
            <tbody>{ppl.map((p) => <PersonRow key={p.id} p={p} onOpen={onOpenPerson} />)}</tbody>
          </table>
          {!ppl.length && <p className="text-sm text-slate-400 py-6 text-center" data-testid="fx-people-empty">Nessuna persona.</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function LegacyDialog({ open, list, onClose, onOpenPerson }) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="cov-legacy-dialog">
        <DialogHeader><DialogTitle>Disponibilità da aggiornare ({list.length})</DialogTitle></DialogHeader>
        <p className="text-sm text-slate-500">Persone con giorni comunicati con il vecchio modulo a orario libero. Apri la scheda e scegli Mattina e/o Pomeriggio: i giorni non modificati restano invariati.</p>
        <div className="divide-y divide-slate-100">
          {[...list].sort(byName).map((p) => (
            <div key={p.id} className="py-2 flex flex-col sm:flex-row sm:items-center gap-2" data-testid={`cov-legacy-person-${p.id}`}>
              <div className="flex-1"><div className="font-medium text-slate-800">{p.cognome} {p.nome} <span className="text-xs text-slate-400 font-normal">{p.categoria}</span></div>
                <div className="text-xs text-slate-600">{p.days.map((d) => `${fmtD(d.date)}: ${d.orario}`).join(" · ")}</div></div>
              <Button size="sm" variant="outline" onClick={() => onOpenPerson(p.id)} data-testid={`cov-legacy-edit-${p.id}`}>Modifica anagrafica</Button>
            </div>))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
