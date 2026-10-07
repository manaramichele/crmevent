import { useState, useEffect, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useSort, SortIcon, sortRows } from "@/lib/sortable";
import { MODAL } from "@/lib/modal";
import { useWheelScroll } from "@/lib/useWheelScroll";
import { TextAction } from "@/components/crm";
import { TeamNoteDialog, hasNote } from "@/components/TeamNote";
import PhoneInput from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { Users, UserPlus, X, Search, Crown, ArrowLeft, Pencil, Phone, StickyNote } from "lucide-react";

// Nome identificabile: Cognome Nome (fallback email). Vuoto => persona senza nominativo.
const displayName = (p) => `${p?.cognome || ""} ${p?.nome || ""}`.trim() || (p?.email || "");
const hasName = (p) => !!displayName(p);
const emptyNew = { nome: "", cognome: "", cellulare: "", email: "", tipo: "staff" };

const RINUNCIA = ["rinunciato", "non_disponibile"];

// Conteggi Team (unica regola, usata da tabella e scheda): Staff unici + Team Leader contato una sola volta;
// volontari assegnati = volontari non rinunciatari con questo team.
export function teamCounts(team, staffLinks = []) {
  const links = (staffLinks || []).filter((l) => l.team_id === team.id && l.persona_id);
  const staff = new Set(links.filter((l) => l.categoria !== "volontario").map((l) => l.persona_id));
  const volAll = new Set(links.filter((l) => l.categoria === "volontario").map((l) => l.persona_id));
  const vol = new Set(links.filter((l) => l.categoria === "volontario" && !RINUNCIA.includes(l.stato)).map((l) => l.persona_id));
  if (team.responsabile_id && !volAll.has(team.responsabile_id)) staff.add(team.responsabile_id);
  return { staff, vol };
}

const Info = ({ label, value, testid }) => (
  <div className="min-w-0"><div className="text-[11px] uppercase tracking-wide text-slate-400">{label}</div><div className="text-sm text-slate-800 break-words whitespace-pre-wrap" data-testid={testid}>{value || "—"}</div></div>
);

const Section = ({ title, action, children, testid }) => (
  <section className="rounded-xl border border-slate-200 bg-white shrink-0" data-testid={testid}>
    <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-slate-100 bg-slate-50/70 rounded-t-xl">
      <h3 className="text-sm font-semibold text-slate-800 font-display">{title}</h3>{action}
    </div>
    <div className="p-4">{children}</div>
  </section>
);

const Stat = ({ label, value, tone = "slate", testid }) => {
  const tones = { slate: "bg-slate-50 text-slate-900", red: "bg-red-50 text-red-700", green: "bg-emerald-50 text-emerald-700" };
  return (
    <div className={`rounded-lg px-3 py-2.5 ${tones[tone]}`}>
      <div className="text-[11px] uppercase tracking-wide opacity-70">{label}</div>
      <div className="text-xl font-bold leading-tight" data-testid={testid}>{value}</div>
    </div>
  );
};

const Tel = ({ n }) => (n ? <a href={`tel:${n}`} className="inline-flex items-center gap-1 text-slate-700"><Phone className="w-3.5 h-3.5 text-slate-400" />{n}</a> : <span className="text-slate-400">—</span>);

function MemberCard({ m, canEdit, busy, onOpenPerson, onRemove }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3" data-testid={`team-member-card-${m.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-900">{m.cognome} {m.nome}</span>
        {m.isLeader && <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 px-2 py-0.5 text-[10px] font-semibold"><Crown className="w-3 h-3" />Team Leader</span>}
      </div>
      <div className="mt-1 space-y-0.5 text-sm text-slate-600">
        {m.ruolo && <div>Ruolo: {m.ruolo}</div>}
        <div><Tel n={m.cellulare} /></div>
        {m.turno && <div>Turno: {m.turno}</div>}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-2">
        {onOpenPerson && <TextAction icon={Pencil} onClick={() => onOpenPerson(m.id)} data-testid={`m-team-member-open-${m.id}`}>Modifica</TextAction>}
        {m.link && canEdit && <TextAction icon={X} danger disabled={busy} onClick={() => onRemove(m)} data-testid={`m-team-member-remove-${m.id}`}>Rimuovi</TextAction>}
      </div>
    </div>
  );
}

export default function TeamMembersDialog({ team, open, onOpenChange, persons = [], staffLinks = [], events = [], onReloadStaff, onOpenPerson, onEdit, onSaveNote, canEdit = true }) {
  const [shifts, setShifts] = useState([]);
  const [query, setQuery] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [addQuery, setAddQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [nf, setNf] = useState(emptyNew);
  const [existing, setExisting] = useState(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const { sort, toggle } = useSort({ key: "cognome", dir: "asc" });
  const bindWheel = useWheelScroll();

  const eventName = events.find((e) => e.id === team?.evento_id)?.nome || "—";

  useEffect(() => {
    if (open && team?.evento_id) {
      api.get("/shifts", { params: { evento_id: team.evento_id } }).then(({ data }) => setShifts(data)).catch(() => setShifts([]));
    }
  }, [open, team]);

  const resetAdd = () => { setCreating(false); setNf(emptyNew); setExisting(null); setAddQuery(""); };

  // Membri = record staff con team_id = questo team (anagrafiche uniche, con nominativo)
  const members = useMemo(() => {
    if (!team) return [];
    const byPerson = new Map();
    (staffLinks || []).filter((l) => l.team_id === team.id).forEach((l) => { if (!byPerson.has(l.persona_id)) byPerson.set(l.persona_id, l); });
    return [...byPerson.entries()].map(([pid, link]) => {
      const p = persons.find((x) => x.id === pid) || {};
      const shift = shifts.find((s) => s.persona_id === pid && (s.team_id === team.id || !s.team_id));
      return {
        id: pid, nome: p.nome || "", cognome: p.cognome || "", email: p.email || "", cellulare: p.cellulare || "",
        tipo: link.categoria === "volontario" ? "Volontario" : "Staff",
        ruolo: link.ruolo || "", link,
        turno: shift ? `${shift.data || ""} ${shift.ora_inizio || ""}${shift.ora_fine ? "–" + shift.ora_fine : ""}`.trim() : "",
        isLeader: team.responsabile_id === pid,
      };
    }).filter((m) => hasName(m));
  }, [team, staffLinks, persons, shifts]);

  const counts = useMemo(() => (team ? teamCounts(team, staffLinks) : { staff: new Set(), vol: new Set() }), [team, staffLinks]);
  const leader = team?.responsabile_id ? persons.find((p) => p.id === team.responsabile_id) : null;
  const req = team?.volontari_richiesti;
  const miss = req == null ? null : Math.max(req - counts.vol.size, 0);
  const extra = req == null ? 0 : Math.max(counts.vol.size - req, 0);

  const columns = [
    { key: "cognome", label: "Cognome e Nome", sortAccessor: (r) => `${r.cognome} ${r.nome}`.trim() },
    { key: "tipo", label: "Tipo" },
    { key: "cellulare", label: "Cellulare" },
    { key: "ruolo", label: "Ruolo" },
    { key: "turno", label: "Turno", sortType: "string" },
  ];

  const filtered = useMemo(() => {
    const ql = query.trim().toLowerCase();
    const list = members.filter((m) => !ql || `${m.nome} ${m.cognome} ${m.cellulare}`.toLowerCase().includes(ql));
    // Team Leader non assegnato come presenza: compare comunque tra lo Staff (contato una sola volta)
    if (leader && !members.some((m) => m.id === leader.id) && (!ql || `${leader.nome} ${leader.cognome}`.toLowerCase().includes(ql))) {
      list.push({ id: leader.id, nome: leader.nome || "", cognome: leader.cognome || "", cellulare: leader.cellulare || "", tipo: "Staff", ruolo: "", turno: "", isLeader: true, link: null });
    }
    return list;
  }, [members, query, leader]);
  const sortedStaff = sortRows(filtered.filter((m) => m.tipo === "Staff"), sort, columns);
  const sortedVol = sortRows(filtered.filter((m) => m.tipo === "Volontario"), sort, columns);

  // Candidati: Staff + Volontari dell'evento non ancora in questo team, con nominativo,
  // ordinati Cognome -> Nome (A-Z, case-insensitive).
  const candidates = useMemo(() => {
    if (!team) return [];
    const inTeam = new Set(members.map((m) => m.id));
    const byPerson = new Map();
    (staffLinks || []).filter((l) => l.evento_id === team.evento_id && ["staff", "collaboratore", "volontario"].includes(l.categoria) && (!l.team_id || l.team_id === team.id) && !inTeam.has(l.persona_id))
      .forEach((l) => { if (!byPerson.has(l.persona_id)) byPerson.set(l.persona_id, l); });
    const ql = addQuery.trim().toLowerCase();
    return [...byPerson.entries()].map(([pid, link]) => {
      const p = persons.find((x) => x.id === pid) || {};
      return { id: pid, label: displayName(p), nome: p.nome || "", cognome: p.cognome || "", email: p.email || "", tipo: link.categoria === "volontario" ? "Volontario" : "Staff", link };
    })
      .filter((c) => c.label)
      .filter((c) => !ql || `${c.label} ${c.email}`.toLowerCase().includes(ql))
      .sort((a, b) => `${a.cognome} ${a.nome}`.trim().localeCompare(`${b.cognome} ${b.nome}`.trim(), "it", { sensitivity: "base" }));
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

  // Crea/riutilizza anagrafica -> associa all'evento con Tipo -> aggiunge al Team.
  const createPerson = async (useExistingId = null) => {
    if (!useExistingId && (!nf.nome.trim() || !nf.cognome.trim())) { toast.error("Nome e Cognome obbligatori"); return; }
    setBusy(true);
    try {
      const payload = {
        evento_id: team.evento_id, nome: nf.nome.trim(), cognome: nf.cognome.trim(),
        cellulare: nf.cellulare || "", email: nf.email || "", categoria: nf.tipo, team_id: team.id,
      };
      if (useExistingId) { payload.use_existing_person_id = useExistingId; payload.confirm_existing = true; }
      const { data } = await api.post("/staff/quick-add", payload);
      if (data.status === "exists") { setExisting(data.person); return; }
      await (onReloadStaff && onReloadStaff());
      toast.success(`${nf.tipo === "volontario" ? "Volontario" : "Staff"} creato e aggiunto al Team`);
      resetAdd(); setAddOpen(false);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  if (!team) return null;

  const addPopover = canEdit && (
    <Popover open={addOpen} onOpenChange={(o) => { setAddOpen(o); if (!o) resetAdd(); }}>
      <PopoverTrigger asChild>
        <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold h-9 w-full sm:w-auto" data-testid="team-add-member"><UserPlus className="w-4 h-4 mr-1.5" />Aggiungi componente</Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(20rem,calc(100vw-2rem))] p-0 z-[200]" align="end" data-testid="team-add-popover" onOpenAutoFocus={(e) => { if (creating) e.preventDefault(); }}>
        {creating ? (
          <div className="p-3 space-y-3" data-testid="team-new-person-form">
            <button type="button" onClick={() => { setCreating(false); setExisting(null); }} className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 py-1"><ArrowLeft className="w-3.5 h-3.5" />Indietro</button>
            <div className="text-sm font-semibold text-slate-800">Aggiungi nuova persona</div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1"><Label className="text-xs">Nome *</Label><Input autoFocus value={nf.nome} onChange={(e) => setNf((s) => ({ ...s, nome: e.target.value }))} className="h-9" data-testid="tp-nome" /></div>
              <div className="space-y-1"><Label className="text-xs">Cognome *</Label><Input value={nf.cognome} onChange={(e) => setNf((s) => ({ ...s, cognome: e.target.value }))} className="h-9" data-testid="tp-cognome" /></div>
            </div>
            <div className="space-y-1"><Label className="text-xs">Cellulare</Label>
              <PhoneInput international defaultCountry="IT" value={nf.cellulare || undefined} onChange={(v) => setNf((s) => ({ ...s, cellulare: v || "" }))} className="phone-input" numberInputProps={{ "data-testid": "tp-cellulare-input" }} data-testid="tp-cellulare" /></div>
            <div className="space-y-1"><Label className="text-xs">Email</Label><Input type="email" value={nf.email} onChange={(e) => setNf((s) => ({ ...s, email: e.target.value }))} className="h-9" data-testid="tp-email" /></div>
            <div className="space-y-1"><Label className="text-xs">Tipo *</Label>
              <Select value={nf.tipo} onValueChange={(v) => setNf((s) => ({ ...s, tipo: v }))}>
                <SelectTrigger className="h-9" data-testid="tp-tipo"><SelectValue /></SelectTrigger>
                <SelectContent className="z-[300]"><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem></SelectContent>
              </Select>
            </div>
            {existing && <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">Esiste già un'anagrafica con questi contatti: <b>{existing.nome} {existing.cognome}</b>. Usarla per questo Team?</div>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => { setCreating(false); setExisting(null); }}>Annulla</Button>
              {existing
                ? <Button type="button" size="sm" onClick={() => createPerson(existing.id)} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="tp-use-existing">Usa esistente</Button>
                : <Button type="button" size="sm" onClick={() => createPerson()} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="tp-save">Salva e aggiungi</Button>}
            </div>
          </div>
        ) : (
          <>
            <div className="p-1.5 border-b border-slate-100"><Input autoFocus value={addQuery} onChange={(e) => setAddQuery(e.target.value)} placeholder="Cerca staff/volontario..." className="h-9" data-testid="team-add-search" /></div>
            <div ref={bindWheel} className="max-h-56 overflow-y-auto p-1" data-testid="team-add-list">
              {candidates.length === 0 ? <div className="px-2 py-3 text-xs text-slate-400 text-center" data-testid="team-add-empty">Nessuno Staff/Volontario dell'evento disponibile.</div> :
                candidates.map((c) => (
                  <button key={c.id} onClick={() => addMember(c)} disabled={busy} className="w-full text-left text-sm px-2 py-2.5 rounded-md hover:bg-slate-100 flex items-center justify-between" data-testid={`team-add-opt-${c.id}`}>
                    <span>{c.label}</span><span className="text-[10px] font-semibold text-slate-400">{c.tipo}</span>
                  </button>
                ))}
            </div>
            <div className="p-1 border-t border-slate-100">
              <button type="button" onClick={() => { setExisting(null); setNf({ ...emptyNew }); setCreating(true); }} className="w-full text-left text-sm text-tiffany-active font-semibold px-2 py-2.5 rounded hover:bg-tiffany-light/50 inline-flex items-center gap-1" data-testid="team-add-new-person"><UserPlus className="w-3.5 h-3.5" />Aggiungi nuova persona</button>
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  );

  const memberList = (key, list) => (
    <>
      <div className="md:hidden space-y-2" data-testid={`team-members-cards-${key}`}>
        {list.length === 0 ? <p className="text-sm text-slate-400 text-center py-3" data-testid={`m-team-members-empty-${key}`}>{key === "staff" ? "Nessuno Staff assegnato." : "Nessun volontario assegnato."}</p>
          : list.map((m) => <MemberCard key={m.id} m={m} canEdit={canEdit} busy={busy} onOpenPerson={onOpenPerson} onRemove={removeMember} />)}
      </div>
      <div className="hidden md:block overflow-x-auto -mx-4 -mb-4">
        <table className="w-full text-sm" data-testid={`team-members-table-${key}`}>
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              {columns.map((c) => (
                <th key={c.key} onClick={() => toggle(c.key)} className="text-left font-semibold text-slate-600 px-4 py-2.5 whitespace-nowrap cursor-pointer select-none group">
                  <span className="inline-flex items-center gap-1">{c.label}<SortIcon active={sort.key === c.key} dir={sort.dir} /></span>
                </th>
              ))}
              <th className="px-4 py-2.5 text-right font-semibold text-slate-600">Azioni</th>
            </tr>
          </thead>
          <tbody>
            {list.length === 0 ? (
              <tr><td colSpan={columns.length + 1} className="px-4 py-6 text-center text-slate-400" data-testid={`team-members-empty-${key}`}>{key === "staff" ? "Nessuno Staff assegnato." : "Nessun volontario assegnato."}</td></tr>
            ) : list.map((m) => (
              <tr key={m.id} className="border-b border-slate-100 hover:bg-slate-50/80" data-testid={`team-member-row-${m.id}`}>
                <td className="px-4 py-2.5">
                  <span className="font-medium text-slate-800">{m.cognome} {m.nome}</span>
                  {m.isLeader && <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 px-2 py-0.5 text-[10px] font-semibold align-middle" data-testid={`team-leader-badge-${m.id}`}><Crown className="w-3 h-3" />Team Leader</span>}
                </td>
                <td className="px-4 py-2.5 text-slate-600">{m.tipo}</td>
                <td className="px-4 py-2.5 text-slate-600">{m.cellulare || "—"}</td>
                <td className="px-4 py-2.5 text-slate-600">{m.ruolo || "—"}</td>
                <td className="px-4 py-2.5 text-slate-600">{m.turno || "—"}</td>
                <td className="px-4 py-2.5">
                  <div className="flex justify-end gap-2">
                    {onOpenPerson && <TextAction icon={Pencil} onClick={() => onOpenPerson(m.id)} data-testid={`team-member-open-${m.id}`}>Modifica</TextAction>}
                    {m.link && canEdit && <TextAction icon={X} danger disabled={busy} onClick={() => removeMember(m)} data-testid={`team-member-remove-${m.id}`}>Rimuovi</TextAction>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={`${MODAL.large} max-h-[90vh] overflow-y-auto flex flex-col gap-3 bg-slate-50 max-sm:!h-[100dvh] max-sm:!max-h-[100dvh] max-sm:!rounded-none`} data-testid="team-members-dialog">
        <DialogHeader className="shrink-0 text-left">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 pr-8">
            <div className="min-w-0">
              <DialogTitle className="font-display flex items-center gap-2 text-left"><Users className="w-5 h-5 text-tiffany-active shrink-0" /><span className="break-words" data-testid="team-card-name">{team.nome}</span></DialogTitle>
              <DialogDescription className="text-left" data-testid="team-card-event">{eventName}</DialogDescription>
            </div>
            {canEdit && onEdit && <TextAction icon={Pencil} onClick={() => onEdit(team)} className="self-start" data-testid="team-card-edit">Modifica dati Team</TextAction>}
          </div>
        </DialogHeader>

        <Section title="Dati Team" testid="team-card-details">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Info label="Area" value={team.area} testid="team-card-area" />
            <Info label="Luogo operativo" value={team.luogo_operativo} testid="team-card-luogo" />
            <Info label="Punto di ritrovo" value={team.punto_ritrovo} testid="team-card-ritrovo" />
            {team.note && <div className="sm:col-span-3"><Info label="Note" value={team.note} /></div>}
          </div>
        </Section>

        <Section title="Team Leader" testid="team-card-leader-section">
          {leader ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="font-semibold text-slate-900" data-testid="team-card-leader">{`${leader.nome || ""} ${leader.cognome || ""}`.trim()}</span>
              <Tel n={leader.cellulare} />
            </div>
          ) : <span className="text-sm font-semibold text-amber-700" data-testid="team-card-leader">Da assegnare</span>}
        </Section>

        <Section title={`Volontari (${counts.vol.size}${req != null ? `/${req}` : ""})`} testid="team-card-coverage">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Necessari" value={req == null ? "—" : req} testid="team-card-req" />
            <Stat label="Assegnati" value={counts.vol.size} testid="team-card-assigned" />
            <Stat label="Mancanti" value={miss == null ? "—" : miss} tone={miss == null ? "slate" : miss > 0 ? "red" : "green"} testid="team-card-missing" />
          </div>
          {miss === 0 && <p className="mt-2 text-xs font-semibold text-emerald-700">Completo</p>}
          {extra > 0 && <p className="mt-2 text-xs font-semibold text-amber-700">+{extra} in esubero</p>}
          {req == null && <p className="mt-2 text-xs text-slate-400">Fabbisogno non indicato.</p>}
        </Section>

        <Section title="Nota" testid="team-card-note"
          action={(canEdit || hasNote(team)) && onSaveNote && <TextAction icon={StickyNote} onClick={() => setNoteOpen(true)} data-testid="team-card-note-btn">{canEdit ? (hasNote(team) ? "Modifica" : "Aggiungi") : "Apri"}</TextAction>}>
          {hasNote(team) ? <p className="text-sm text-slate-800 whitespace-pre-wrap break-words" data-testid="team-card-note-text">{team.descrizione}</p>
            : <p className="text-sm text-slate-400" data-testid="team-card-note-empty">Nessuna nota.</p>}
        </Section>

        <div className="flex flex-col sm:flex-row sm:items-center gap-2 shrink-0">
          <div className="relative flex-1 min-w-0">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <Input className="pl-9 h-9 bg-white" placeholder="Cerca persona..." value={query} onChange={(e) => setQuery(e.target.value)} data-testid="team-members-search" />
          </div>
          {addPopover}
        </div>

        <Section title={`Staff (${counts.staff.size})`} testid="team-card-staff">{memberList("staff", sortedStaff)}</Section>
        <Section title={`Volontari del Team (${counts.vol.size}${req != null ? `/${req}` : ""})`} testid="team-card-volontari">{memberList("volontari", sortedVol)}</Section>

        {noteOpen && <TeamNoteDialog team={team} open={noteOpen} onOpenChange={setNoteOpen} canEdit={canEdit} onSave={onSaveNote} />}
      </DialogContent>
    </Dialog>
  );
}
