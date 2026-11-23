import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/crm";

export default function CoverageSlotDialog({ slot, data, eventName, onClose, onOpenPerson }) {
  const [q, setQ] = useState("");
  if (!slot) return null;
  const ids = slot.tbc ? data.tbc : [...slot.full, ...slot.partial];
  const partial = new Set(slot.partial || []);
  const people = ids.map((id) => data.people[id]).filter(Boolean)
    .filter((p) => !q.trim() || `${p.cognome} ${p.nome} ${p.gruppo} ${p.team} ${p.mansioni.join(" ")}`.toLowerCase().includes(q.trim().toLowerCase()))
    .sort((a, b) => `${a.cognome} ${a.nome}`.localeCompare(`${b.cognome} ${b.nome}`, "it"));
  return (
    <Dialog open onOpenChange={(o) => { if (!o) { setQ(""); onClose(); } }}>
      <DialogContent className="w-[96vw] max-w-4xl max-h-[85vh] overflow-y-auto" data-testid="cov-slot-dialog">
        <DialogHeader>
          <DialogTitle>{slot.tbc ? "Orario da confermare" : `Disponibili ${slot.start}–${slot.end}`}</DialogTitle>
          <DialogDescription>{eventName} · {data.date}{!slot.tbc && ` · ${slot.available} disponibili (${slot.partial.length} parziali) · ${slot.assigned} assegnati · ${slot.needed ?? "—"} necessari`}</DialogDescription>
        </DialogHeader>
        <Input placeholder="Cerca…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="cov-slot-search" />
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="cov-slot-table">
            <thead><tr className="text-xs text-slate-500 text-left">{["Cognome e nome", "Cellulare", "Mansione", "Gruppo", "Team", "Taglia", "Orario", "Assegnazione"].map((h) => <th key={h} className="py-2 pr-3 whitespace-nowrap">{h}</th>)}</tr></thead>
            <tbody>
              {people.length === 0 ? <tr><td colSpan={8} className="py-6 text-center text-slate-400">Nessuna persona</td></tr> : people.map((p) => (
                <tr key={p.id} className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={() => onOpenPerson?.(p.id)} data-testid={`cov-person-${p.id}`}>
                  <td className="py-2 pr-3 font-medium text-slate-800">{p.cognome} {p.nome}<div className="text-[11px] text-slate-400">{p.categoria}</div></td>
                  <td className="py-2 pr-3 whitespace-nowrap">{p.cellulare || "—"}</td>
                  <td className="py-2 pr-3">{p.mansioni.join(", ") || (p.preferenza ? <i className="text-slate-500">Pref.: {p.preferenza}</i> : "—")}</td>
                  <td className="py-2 pr-3">{p.gruppo || <i className="text-slate-400">Nessun gruppo</i>}</td>
                  <td className="py-2 pr-3">{p.team || "—"}</td>
                  <td className="py-2 pr-3">{p.taglia || "—"}</td>
                  <td className="py-2 pr-3 whitespace-nowrap">{p.orario}{partial.has(p.id) && <div className="text-[11px] text-amber-600">parte della fascia</div>}
                    {p.legacy && <div><span className="inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-900" data-testid={`cov-person-legacy-${p.id}`}>Disponibilità da aggiornare</span></div>}</td>
                  <td className="py-2 pr-3">{p.assigned ? <StatusBadge color="green">Mansione assegnata</StatusBadge> : <StatusBadge color="gray">Solo disponibile</StatusBadge>}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </DialogContent>
    </Dialog>
  );
}
