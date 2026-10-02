import { useState, useEffect, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { useSort, SortIcon, sortRows } from "@/lib/sortable";
import { Users, UserPlus, X, Search, Crown } from "lucide-react";

const pname = (p) => `${p?.nome || ""} ${p?.cognome || ""}`.trim() || p?.email || "—";

export default function TeamMembersDialog({ team, open, onOpenChange, persons = [], staffLinks = [], events = [], onReloadStaff, onOpenPerson }) {
  const [shifts, setShifts] = useState([]);
  const [tipoFilter, setTipoFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [addQuery, setAddQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const { sort, toggle } = useSort({ key: "cognome", dir: "asc" });

  const eventName = events.find((e) => e.id === team?.evento_id)?.nome || "—";

  useEffect(() => {
    if (open && team?.evento_id) {
      api.get("/shifts", { params: { evento_id: team.evento_id } }).then(({ data }) => setShifts(data)).catch(() => setShifts([]));
    }
  }, [open, team]);

  // Membri = record staff con team_id = questo team (anagrafiche uniche)
  const members = useMemo(() => {
    if (!team) return [];
    const byPerson = new Map();
    (staffLinks || []).filter((l) => l.team_id === team.id).forEach((l) => { if (!byPerson.has(l.persona_id)) byPerson.set(l.persona_id, l); });
    return [...byPerson.entries()].map(([pid, link]) => {
      const p = persons.find((x) => x.id === pid) || {};
      const shift = shifts.find((s) => s.persona_id === pid && (s.team_id === team.id || !s.team_id));
      return {
        id: pid, nome: p.nome || "", cognome: p.cognome || "", cellulare: p.cellulare || "",
        tipo: link.categoria === "volontario" ? "Volontario" : "Staff",
        ruolo: link.ruolo || "", link,
        turno: shift ? `${shift.data || ""} ${shift.ora_inizio || ""}${shift.ora_fine ? "–" + shift.ora_fine : ""}`.trim() : "",
        isLeader: team.responsabile_id === pid,
      };
    });
  }, [team, staffLinks, persons, shifts]);

  const totalTeam = members.length;

  const columns = [
    { key: "cognome", label: "Cognome e Nome", sortAccessor: (r) => `${r.cognome} ${r.nome}`.trim() },
    { key: "tipo", label: "Tipo" },
    { key: "cellulare", label: "Cellulare" },
    { key: "ruolo", label: "Ruolo" },
    { key: "turno", label: "Turno", sortType: "string" },
  ];

  const filtered = useMemo(() => {
    const ql = query.trim().toLowerCase();
    return members.filter((m) => {
      if (tipoFilter === "staff" && m.tipo !== "Staff") return false;
      if (tipoFilter === "volontari" && m.tipo !== "Volontario") return false;
      if (ql && !(`${m.nome} ${m.cognome} ${m.cellulare}`.toLowerCase().includes(ql))) return false;
      return true;
    });
  }, [members, tipoFilter, query]);
  const sorted = sortRows(filtered, sort, columns);
  const isFiltering = tipoFilter !== "all" || query.trim() !== "";

  // Candidati: Staff/Volontari dell'evento non ancora in questo team
  const candidates = useMemo(() => {
    if (!team) return [];
    const inTeam = new Set(members.map((m) => m.id));
    const byPerson = new Map();
    (staffLinks || []).filter((l) => l.evento_id === team.evento_id && ["staff", "collaboratore", "volontario"].includes(l.categoria) && (!l.team_id || l.team_id === team.id) && !inTeam.has(l.persona_id))
      .forEach((l) => { if (!byPerson.has(l.persona_id)) byPerson.set(l.persona_id, l); });
    const ql = addQuery.trim().toLowerCase();
    return [...byPerson.entries()].map(([pid, link]) => {
      const p = persons.find((x) => x.id === pid) || {};
      return { id: pid, label: pname(p), tipo: link.categoria === "volontario" ? "Volontario" : "Staff", link };
    }).filter((c) => !ql || c.label.toLowerCase().includes(ql))
      .sort((a, b) => a.label.localeCompare(b.label, "it", { sensitivity: "base" }));
  }, [team, staffLinks, members, persons, addQuery]);

  const addMember = async (cand) => {
    setBusy(true);
    try { await api.put(`/staff/${cand.link.id}`, { team_id: team.id }); await (onReloadStaff && onReloadStaff()); toast.success("Componente aggiunto al Team"); setAddQuery(""); setAddOpen(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const removeMember = async (m) => {
    setBusy(true);
    try { await api.put(`/staff/${m.link.id}`, { team_id: "" }); await (onReloadStaff && onReloadStaff()); toast.success("Rimosso dal Team"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  if (!team) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="team-members-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Users className="w-5 h-5 text-tiffany-active" />{team.nome}</DialogTitle>
          <DialogDescription>{eventName}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-2 mt-1">
          <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50">
            {[["all", "Tutti"], ["staff", "Staff"], ["volontari", "Volontari"]].map(([v, l]) => (
              <button key={v} onClick={() => setTipoFilter(v)} className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${tipoFilter === v ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`} data-testid={`team-filter-${v}`}>{l}</button>
            ))}
          </div>
          <div className="relative flex-1 min-w-[180px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input className="pl-9 h-9" placeholder="Cerca persona..." value={query} onChange={(e) => setQuery(e.target.value)} data-testid="team-members-search" />
          </div>
          <Popover open={addOpen} onOpenChange={setAddOpen}>
            <PopoverTrigger asChild>
              <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold h-9" data-testid="team-add-member"><UserPlus className="w-4 h-4 mr-1.5" />Aggiungi componente</Button>
            </PopoverTrigger>
            <PopoverContent className="w-72 p-0 z-[200]" align="end" data-testid="team-add-popover">
              <div className="p-1.5 border-b border-slate-100"><Input autoFocus value={addQuery} onChange={(e) => setAddQuery(e.target.value)} placeholder="Cerca staff/volontario..." className="h-8" data-testid="team-add-search" /></div>
              <div className="max-h-56 overflow-y-auto p-1">
                {candidates.length === 0 ? <div className="px-2 py-3 text-xs text-slate-400 text-center" data-testid="team-add-empty">Nessuno Staff/Volontario dell'evento disponibile.</div> :
                  candidates.map((c) => (
                    <button key={c.id} onClick={() => addMember(c)} disabled={busy} className="w-full text-left text-sm px-2 py-1.5 rounded-md hover:bg-slate-100 flex items-center justify-between" data-testid={`team-add-opt-${c.id}`}>
                      <span>{c.label}</span><span className="text-[10px] font-semibold text-slate-400">{c.tipo}</span>
                    </button>
                  ))}
              </div>
            </PopoverContent>
          </Popover>
        </div>

        <div className="mt-3 bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="team-members-table">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/70">
                  {columns.map((c) => (
                    <th key={c.key} onClick={() => toggle(c.key)} className="text-left font-semibold text-slate-600 px-4 py-2.5 whitespace-nowrap cursor-pointer select-none group">
                      <span className="inline-flex items-center gap-1">{c.label}<SortIcon active={sort.key === c.key} dir={sort.dir} /></span>
                    </th>
                  ))}
                  <th className="px-4 py-2.5 text-right font-semibold text-slate-600">Azioni</th>
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 ? (
                  <tr><td colSpan={columns.length + 1} className="px-4 py-8 text-center text-slate-400" data-testid="team-members-empty">Nessun componente.</td></tr>
                ) : sorted.map((m) => (
                  <tr key={m.id} className="border-b border-slate-100 hover:bg-slate-50/80" data-testid={`team-member-row-${m.id}`}>
                    <td className="px-4 py-2.5">
                      <button onClick={() => onOpenPerson && onOpenPerson(m.id)} className="font-medium text-tiffany-active hover:underline text-left" data-testid={`team-member-open-${m.id}`}>{m.cognome} {m.nome}</button>
                      {m.isLeader && <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 px-2 py-0.5 text-[10px] font-semibold align-middle" data-testid={`team-leader-badge-${m.id}`}><Crown className="w-3 h-3" />Team Leader</span>}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">{m.tipo}</td>
                    <td className="px-4 py-2.5 text-slate-600">{m.cellulare || "—"}</td>
                    <td className="px-4 py-2.5 text-slate-600">{m.ruolo || "—"}</td>
                    <td className="px-4 py-2.5 text-slate-600">{m.turno || "—"}</td>
                    <td className="px-4 py-2.5 text-right">
                      <Button variant="ghost" size="sm" className="h-8 text-slate-500 hover:text-red-500" onClick={() => removeMember(m)} disabled={busy} data-testid={`team-member-remove-${m.id}`}><X className="w-4 h-4 mr-1" />Rimuovi dal Team</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between px-4 py-3 bg-slate-50/70 border-t border-slate-200 text-sm font-semibold text-slate-700" data-testid="team-members-summary">
            {isFiltering ? <span>Visualizzati: <span data-testid="team-count-visible">{sorted.length}</span> · Totale Team: <span data-testid="team-count-total">{totalTeam}</span></span>
              : <span>Totale componenti Team: <span data-testid="team-count-total">{totalTeam}</span></span>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
