import { useState, useEffect, useCallback, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { EntityManager, EntityDialog, StatusBadge, useCollection, useSettings, toOptions, PageHeader, PrimaryButton, TextAction, DeleteConfirm } from "@/components/crm";
import { TeamNoteButton } from "@/components/TeamNote";
import { personName, personOptions } from "@/lib/names";
import { useAuth } from "@/context/AuthContext";
import { can, canSendInvites } from "@/lib/perms";
import { PersonInviteDialog, BulkInviteBar, LastInvite, INV, INV_LABEL } from "@/components/PersonInvites";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Plus, Pencil, Trash2, UserPlus, Search, Users, Phone, Eye } from "lucide-react";
import { useSort, SortIcon, sortRows } from "@/lib/sortable";
import { toast } from "sonner";
import PersonDetailDialog from "@/components/PersonDetailDialog";
import TeamMembersDialog, { teamCounts } from "@/components/TeamMembersDialog";
import TeamSelect from "@/components/TeamSelect";
import { useTeams, invalidateTeams } from "@/lib/teamsStore";
import { usePeople } from "@/lib/peopleStore";

const CAT = { referente: "Referente", staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario", team: "Team" };
const STATO = { da_contattare: "Da contattare", disponibilita_richiesta: "Disponibilità richiesta", disponibile: "Disponibile", da_riconfermare: "Da riconfermare", confermato: "Confermato", non_disponibile: "Non disponibile", rinunciato: "Rinunciato" };
const STATO_COLOR = { confermato: "green", disponibile: "green", da_riconfermare: "orange", disponibilita_richiesta: "blue", da_contattare: "gray", non_disponibile: "red", rinunciato: "red" };

function EventRolesDialog({ person, events, settings, open, onOpenChange, onDone }) {
  const [links, setLinks] = useState([]);
  const [nf, setNf] = useState({ categoria: "staff" });
  const load = useCallback(async () => {
    if (!person?.id) return;
    try { const { data } = await api.get(`/persons/${person.id}/detail`); setLinks(data.events || []); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [person?.id]);
  useEffect(() => { if (open) load(); }, [open, load]);

  const clean = (pres, patch) => {
    const base = { evento_id: pres.evento_id, persona_id: person.id, categoria: pres.categoria, ruolo: pres.ruolo, team_id: pres.team_id, area: pres.area, stato: pres.stato };
    return { ...base, ...patch };
  };
  const save = async (pres, patch) => {
    try { await api.put(`/staff/${pres.id}`, clean(pres, patch)); toast.success("Ruolo aggiornato"); await load(); onDone && onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const del = async (id) => {
    try { await api.delete(`/staff/${id}`); toast.success("Ruolo rimosso"); await load(); onDone && onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const add = async () => {
    if (!nf.evento_id) return toast.error("Seleziona un evento");
    try {
      await api.post("/staff", { persona_id: person.id, evento_id: nf.evento_id, categoria: nf.categoria || "staff", ruolo: nf.ruolo, team_id: nf.team_id, stato: "da_contattare" });
      toast.success("Persona collegata all'evento"); setNf({ categoria: "staff" }); await load(); onDone && onDone();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="event-roles-dialog">
        <DialogHeader><DialogTitle className="font-display">Ruoli evento — {person?.cognome} {person?.nome}</DialogTitle>
          <DialogDescription>Assegna, modifica o rimuovi il ruolo di questa persona per ciascun evento. Una persona può avere ruoli diversi in eventi diversi.</DialogDescription></DialogHeader>

        <div className="space-y-2 py-2">
          {links.length === 0 && <p className="text-sm text-slate-400">Nessun evento collegato.</p>}
          {links.map((x) => {
            const p = x.presence;
            return (
              <div key={p.id} className="border border-slate-200 rounded-lg px-3 py-3" data-testid={`role-link-${p.id}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-slate-800 text-sm">{x.event?.nome || "—"}</span>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-400 hover:text-red-500" onClick={() => del(p.id)} data-testid={`role-del-${p.id}`}><Trash2 className="w-4 h-4" /></Button>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <Select value={["staff", "volontario"].includes(p.categoria) ? p.categoria : ""} onValueChange={(v) => (v === "none" ? del(p.id) : save(p, { categoria: v }))}>
                    <SelectTrigger data-testid={`role-cat-${p.id}`}><SelectValue placeholder="Ruolo evento" /></SelectTrigger>
                    <SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem><SelectItem value="none">Nessun ruolo (rimuovi)</SelectItem></SelectContent></Select>
                  <TeamSelect value={p.team_id || ""} eventoId={p.evento_id} onChange={(v) => save(p, { team_id: v })} testid={`role-team-${p.id}`} />
                </div>
              </div>
            );
          })}
        </div>

        <div className="border-t border-slate-100 pt-3">
          <p className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1"><Plus className="w-3.5 h-3.5" />Collega a un nuovo evento (o aggiungi un altro ruolo nello stesso evento)</p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <Select value={nf.evento_id || ""} onValueChange={(v) => setNf((f) => ({ ...f, evento_id: v }))}>
              <SelectTrigger data-testid="new-role-event"><SelectValue placeholder="Evento" /></SelectTrigger>
              <SelectContent>{events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}</SelectContent></Select>
            <Select value={nf.categoria} onValueChange={(v) => setNf((f) => ({ ...f, categoria: v }))}>
              <SelectTrigger data-testid="new-role-cat"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem></SelectContent></Select>
            <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={add} data-testid="new-role-add">Assegna ruolo</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PeopleTable({ rows, loading, tab, events = [], onOpen, onEdit, onInvite, onDelete, onRoleClick, onInvited }) {
  const [q, setQ] = useState("");
  const [evFilter, setEvFilter] = useState("all");
  const [sel, setSel] = useState(() => new Set());
  const flip = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const filtered = rows.filter((r) => {
    if (tab === "referenti_aziende" && !r.is_referente) return false;
    if (tab === "staff" && !r.is_staff) return false;
    if (tab === "volontari" && !r.is_volontario) return false;
    if (tab === "da_classificare" && (r.is_referente || r.is_staff || r.is_volontario)) return false;
    if (evFilter !== "all" && !(r.eventi_ids || []).includes(evFilter)) return false;
    if (q) { const s = `${r.nome} ${r.cognome} ${r.email || ""} ${r.ruolo || ""} ${(r.aziende_nomi || []).join(" ")}`.toLowerCase(); if (!s.includes(q.toLowerCase())) return false; }
    return true;
  });
  const { sort, toggle } = useSort({ key: "nome", dir: "asc" });
  const isStaffTab = tab === "staff" || tab === "volontari" || tab === "da_classificare";
  const ACC = {
    nome: (r) => `${r.cognome || ""} ${r.nome || ""}`.trim(),
    cellulare: (r) => r.cellulare || "",
    ruolo_evento: (r) => (r.is_staff ? "Staff" : r.is_volontario ? "Volontario" : r.is_referente ? "Referente" : ""),
    team: (r) => (r.teams_nomi || []).join(", "),
    evento: (r) => (r.eventi_nomi || []).join(", "),
    qualifica: (r) => r.ruolo || "",
    aziende: (r) => (r.aziende_nomi || []).join(", "),
    accesso: (r) => INV_LABEL[r.invite_status || "non_invitato"] || "",
  };
  const colsMeta = Object.entries(ACC).map(([key, sortAccessor]) => ({ key, sortAccessor, sortType: "string" }));
  const displayRows = sortRows(filtered, sort, colsMeta);
  const selectedRows = displayRows.filter((r) => sel.has(r.id));
  const allSel = displayRows.length > 0 && selectedRows.length === displayRows.length;
  const toggleAll = () => setSel(allSel ? new Set() : new Set(displayRows.map((r) => r.id)));
  const pick = (r) => onInvite && <input type="checkbox" className="accent-tiffany w-4 h-4" checked={sel.has(r.id)} onChange={() => flip(r.id)} onClick={(e) => e.stopPropagation()} aria-label="Seleziona per invito" data-testid={`select-invite-${r.id}`} />;
  const Th = ({ k, label, right }) => (
    <th onClick={() => toggle(k)} data-testid={`sort-${k}`} className={`font-semibold text-slate-600 px-4 py-3 whitespace-nowrap cursor-pointer select-none group ${right ? "text-right" : "text-left"}`}>
      <span className="inline-flex items-center gap-1">{label}<SortIcon active={sort.key === k} dir={sort.dir} /></span>
    </th>
  );
  const roleBadges = (r) => (
    <button type="button" onClick={() => onRoleClick(r)} title="Gestisci ruoli evento" data-testid={`role-cell-${r.id}`}
      className="flex flex-wrap items-center gap-1 rounded-md px-1.5 py-1 -ml-1.5 hover:bg-tiffany-light/60 transition-colors group">
      {r.is_staff && <StatusBadge color="blue">Staff</StatusBadge>}{r.is_volontario && <StatusBadge color="green">Volontario</StatusBadge>}
      {r.is_referente && <StatusBadge color="tiffany">Referente</StatusBadge>}
      {!r.is_staff && !r.is_volontario && !r.is_referente && <span className="text-slate-400">—</span>}
      <Pencil className="w-3 h-3 text-slate-300 group-hover:text-tiffany-active" />
    </button>
  );
  const actionsCell = (r) => (
    <div className="flex items-center justify-end gap-1">
      {onInvite && <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title={r.last_invite_at ? "Reinvia invito" : "Invita"} onClick={() => onInvite(r)} data-testid={`invite-${r.id}`}><UserPlus className="w-4 h-4" /></Button>}
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" onClick={() => onEdit(r)} data-testid={`edit-person-${r.id}`}><Pencil className="w-4 h-4" /></Button>
      <AlertDialog>
        <AlertDialogTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" data-testid={`delete-person-${r.id}`}><Trash2 className="w-4 h-4" /></Button></AlertDialogTrigger>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Confermi l'eliminazione?</AlertDialogTitle><AlertDialogDescription>Questa azione non può essere annullata.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={() => onDelete(r)} data-testid={`confirm-delete-person-${r.id}`}>Elimina</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
      </AlertDialog>
    </div>
  );
  const teamsCell = (r) => ((r.teams_nomi && r.teams_nomi.length)
    ? <div className="flex flex-wrap gap-1">{r.teams_nomi.map((t, i) => <span key={i} className="inline-flex items-center rounded-full bg-tiffany-light text-tiffany-fg px-2 py-0.5 text-xs font-medium whitespace-nowrap">{t}</span>)}</div>
    : <span className="text-slate-400">—</span>);
  return (
    <div>
      <div className="mb-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9" placeholder="Cerca persone..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="search-person-input" />
        </div>
        {isStaffTab && (
          <div className="w-full sm:w-56" data-testid="people-event-filter">
            <Select value={evFilter} onValueChange={setEvFilter}>
              <SelectTrigger><SelectValue placeholder="Tutti gli eventi" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tutti gli eventi</SelectItem>
                {events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
      <div className="md:hidden space-y-2.5" data-testid={`people-mobile-list-${tab}`}>
        {loading ? <div className="py-10 text-center text-slate-400 text-sm">Caricamento...</div>
          : displayRows.length === 0 ? <div className="py-10 text-center text-slate-400 text-sm">Nessuna persona trovata.</div>
          : displayRows.map((r) => (
            <div key={r.id} className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={`person-card-${r.id}`}>
              <div className="flex items-start gap-2">{pick(r)}<div className="font-semibold text-slate-900 break-words">{r.cognome} {r.nome}</div></div>
              <LastInvite person={r} className="mt-0.5" />
              {!isStaffTab && r.ruolo && <div className="text-sm text-slate-500">{r.ruolo}</div>}
              <div className="mt-2 space-y-1.5 text-sm text-slate-700">
                {r.cellulare && <a href={`tel:${r.cellulare}`} className="inline-flex items-center gap-1"><Phone className="w-3.5 h-3.5 text-slate-400" />{r.cellulare}</a>}
                <div>{roleBadges(r)}</div>
                {isStaffTab ? (<>
                  {r.teams_nomi?.length > 0 && <div>{teamsCell(r)}</div>}
                  {r.eventi_nomi?.length > 0 && <div className="text-xs text-slate-500">{r.eventi_nomi.join(", ")}</div>}
                  <StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge>
                </>) : (<>
                  {r.aziende_nomi?.length > 0 && <div className="text-xs text-slate-500">{r.aziende_nomi.join(", ")}</div>}
                  <StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge>
                </>)}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <TextAction icon={Eye} onClick={() => onOpen(r)} data-testid={`m-open-person-${r.id}`}>Apri</TextAction>
                <TextAction icon={Pencil} onClick={() => onEdit(r)} data-testid={`m-edit-person-${r.id}`}>Modifica</TextAction>
                {onInvite && <TextAction icon={UserPlus} onClick={() => onInvite(r)} data-testid={`m-invite-${r.id}`}>{r.last_invite_at ? "Reinvia" : "Invita"}</TextAction>}
                <DeleteConfirm onConfirm={() => onDelete(r)} testid={`m-confirm-delete-person-${r.id}`}><TextAction icon={Trash2} danger data-testid={`m-delete-person-${r.id}`}>Elimina</TextAction></DeleteConfirm>
              </div>
            </div>
          ))}
      </div>
      <div className="hidden md:block bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 bg-slate-50/70">
              {onInvite && <th className="pl-4 py-3 w-8"><input type="checkbox" className="accent-tiffany w-4 h-4" checked={allSel} onChange={toggleAll} aria-label="Seleziona tutti" data-testid={`select-invite-all-${tab}`} /></th>}
              {isStaffTab ? (<>
                <Th k="nome" label="Cognome e Nome" />
                <Th k="cellulare" label="Cellulare" />
                <Th k="ruolo_evento" label="Ruolo evento" />
                <Th k="team" label="Team" />
                <Th k="evento" label="Evento" />
                <Th k="accesso" label="Invito" />
                <th className="text-right font-semibold text-slate-600 px-4 py-3 whitespace-nowrap">Azioni</th>
              </>) : (<>
                <Th k="nome" label="Cognome e Nome" />
                <Th k="qualifica" label="Qualifica" />
                <Th k="aziende" label="Aziende" />
                <Th k="ruolo_evento" label="Ruolo eventi" />
                <Th k="accesso" label="Accesso" />
                <th className="text-right font-semibold text-slate-600 px-4 py-3 whitespace-nowrap">Azioni</th>
              </>)}
            </tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400">Caricamento...</td></tr>
                : displayRows.length === 0 ? <tr><td colSpan={8} className="px-4 py-10 text-center text-slate-400">Nessuna persona trovata.</td></tr>
                : displayRows.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50/80 transition-colors cursor-pointer" onClick={() => onOpen(r)} data-testid={`person-row-${r.id}`}>
                    {onInvite && <td className="pl-4 py-3" onClick={(e) => e.stopPropagation()}>{pick(r)}</td>}
                    <td className="px-4 py-3"><span className="font-medium text-slate-800">{r.cognome} {r.nome}</span><LastInvite person={r} /></td>
                    {isStaffTab ? (
                      <>
                        <td className="px-4 py-3 text-slate-700 whitespace-nowrap">{r.cellulare || "—"}</td>
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>{roleBadges(r)}</td>
                        <td className="px-4 py-3">{teamsCell(r)}</td>
                        <td className="px-4 py-3 text-slate-600">{(r.eventi_nomi && r.eventi_nomi.length) ? r.eventi_nomi.join(", ") : "—"}</td>
                        <td className="px-4 py-3" data-testid={`invite-status-${r.id}`}><StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge></td>
                      </>
                    ) : (
                      <>
                        <td className="px-4 py-3 text-slate-700">{r.ruolo || "—"}</td>
                        <td className="px-4 py-3 text-slate-700">{(r.aziende_nomi && r.aziende_nomi.length) ? r.aziende_nomi.join(", ") : "—"}</td>
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>{roleBadges(r)}</td>
                        <td className="px-4 py-3"><StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge></td>
                      </>
                    )}
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>{actionsCell(r)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
      {onInvite && <BulkInviteBar selected={selectedRows} onClear={() => setSel(new Set())} onDone={onInvited} />}
    </div>
  );
}

function TeamCoverage({ req, n, id }) {
  if (req === null || req === undefined) return <span className="text-xs text-slate-400" data-testid={`team-coverage-${id}`}>{n} assegnati · fabbisogno non indicato</span>;
  const miss = Math.max(req - n, 0);
  const extra = Math.max(n - req, 0);
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs whitespace-nowrap" data-testid={`team-coverage-${id}`}>
      <span className="text-slate-600">{req} richiesti · {n} {n === 1 ? "assegnato" : "assegnati"}</span>
      {miss > 0
        ? <span className="rounded-full bg-red-100 text-red-700 px-2 py-0.5 font-semibold" data-testid={`team-missing-${id}`}>{miss} mancanti</span>
        : <span className="rounded-full bg-emerald-100 text-emerald-700 px-2 py-0.5 font-semibold" data-testid={`team-complete-${id}`}>Completo</span>}
      {extra > 0 && <span className="rounded-full bg-amber-100 text-amber-800 px-2 py-0.5 font-semibold" data-testid={`team-extra-${id}`}>+{extra} in esubero</span>}
    </div>
  );
}

export default function Persons({ mode = "anagrafiche" }) {
  const { user } = useAuth();
  const { items: companies } = useCollection("/companies");
  const { items: events } = useCollection("/events");
  const { staff: staffLinks, persons: rows, loading, reload } = usePeople();
  const { teams } = useTeams();
  const settings = useSettings();
  const [detailId, setDetailId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [invite, setInvite] = useState(null);
  const [rolesFor, setRolesFor] = useState(null);

  const companyOpts = companies.map((c) => ({ value: c.id, label: c.nome }));
  const personFields = [
    { name: "nome", label: "Nome", required: true }, { name: "cognome", label: "Cognome" },
    { name: "ruolo", label: "Qualifica" }, { name: "email", label: "Email", type: "email" },
    { name: "email_secondaria", label: "Email secondaria", type: "email" }, { name: "cellulare", label: "Cellulare", type: "tel" },
    { name: "telefono", label: "Telefono", type: "tel" }, { name: "azienda_id", label: "Azienda principale", type: "select", options: companyOpts },
    { name: "data_nascita", label: "Data di nascita", type: "date" }, { name: "codice_fiscale", label: "Codice Fiscale" }, { name: "linkedin", label: "LinkedIn" },
    { name: "indirizzo", label: "Indirizzo" }, { name: "cap", label: "CAP" }, { name: "citta", label: "Città" },
    { name: "provincia", label: "Provincia" }, { name: "regione", label: "Regione" }, { name: "nazione", label: "Nazione" },
    { name: "foto_url", label: "Foto (URL)" }, { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const submitPerson = async (form) => {
    if (editing) { await api.put(`/persons/${editing.id}`, form); toast.success("Persona aggiornata"); }
    else { await api.post("/persons", form); toast.success("Persona creata"); }
    await reload();
  };
  const delPerson = async (r) => { try { await api.delete(`/persons/${r.id}`); await reload(); toast.success("Persona eliminata"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

  // team & shift configs
  const personOpts = personOptions(rows);
  // Team Leader: solo Staff dell'evento selezionato (esclude Volontari, Da classificare,
  // Referenti aziendali non-staff e Staff di altri eventi).
  const staffByEvent = useMemo(() => {
    const m = {};
    (staffLinks || []).forEach((l) => {
      if (["staff", "collaboratore"].includes(l.categoria)) {
        (m[l.evento_id] = m[l.evento_id] || new Set()).add(l.persona_id);
      }
    });
    return m;
  }, [staffLinks]);
  const staffPersonsForEvent = useCallback((eid) => {
    if (!eid) return [];
    const set = staffByEvent[eid] || new Set();
    return rows.filter((p) => set.has(p.id));
  }, [rows, staffByEvent]);
  const eventOpts = events.map((e) => ({ value: e.id, label: e.nome }));
  const teamOpts = teams.map((t) => ({ value: t.id, label: t.nome }));
  const areaOpts = toOptions(settings?.aree_operative);
  const pName = (id) => { const p = rows.find((x) => x.id === id); return p ? personName(p) : "—"; };
  const eName = (id) => events.find((e) => e.id === id)?.nome || "—";
  const tName = (id) => teams.find((t) => t.id === id)?.nome || "—";

  const teamFields = [
    { name: "nome", label: "Nome team", required: true, full: true }, { name: "evento_id", label: "Evento", required: true, type: "select", options: eventOpts },
    { name: "area", label: "Area", type: "select", settingKey: "aree_operative", addLabel: "Aggiungi nuova Area", options: settings?.aree_operative || [] }, { name: "responsabile_id", label: "Team Leader", type: "staffselect", eventFrom: "evento_id", staffPersonsFor: (form) => staffPersonsForEvent(form?.evento_id), allPersons: rows, onStaffAdded: reload, noEventHint: "Seleziona prima l'Evento per scegliere lo Staff." },
    { name: "luogo_operativo", label: "Luogo operativo" }, { name: "punto_ritrovo", label: "Punto di ritrovo" },
    { name: "volontari_richiesti", label: "Volontari richiesti", type: "number", placeholder: "Es. 20" },
    { name: "descrizione", label: "Descrizione", type: "textarea", full: true },
  ];
  // Conteggi da assegnazioni reali (teamCounts): stessa regola volontari del backend (_team_coverage)
  const teamCols = [
    { key: "nome", label: "Team", render: (r) => <span className="font-medium text-slate-800" data-testid={`team-name-${r.id}`}>{r.nome}</span> },
    { key: "evento_id", label: "Evento", render: (r) => eName(r.evento_id) },
    { key: "responsabile_id", label: "Team Leader", render: (r) => r.responsabile_id ? pName(r.responsabile_id) : <StatusBadge color="orange">Da assegnare</StatusBadge> },
    { key: "staff_count", label: "Staff", sortable: false, render: (r) => <span className="text-slate-700" data-testid={`team-staff-count-${r.id}`}>{teamCounts(r, staffLinks).staff.size}</span> },
    { key: "volontari_richiesti", label: "Volontari", render: (r) => <TeamCoverage req={r.volontari_richiesti} n={teamCounts(r, staffLinks).vol.size} id={r.id} /> },
  ];
  const canEditStaff = can(user, "teams", "edit");
  const canEditMembers = can(user, "staff", "edit");
  const saveNote = (update, id) => async (text) => { await update(id, { descrizione: text }); invalidateTeams(); };
  const teamMobileCard = (r, { openDetail, update, onDelete, allow, filterVals }) => {
    const c = teamCounts(r, staffLinks);
    const req = r.volontari_richiesti;
    const miss = req == null ? null : Math.max(req - c.vol.size, 0);
    const showEvent = !filterVals.evento_id || filterVals.evento_id === "all";
    return (
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={`team-mobile-card-${r.id}`}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="font-display font-bold uppercase tracking-wide text-slate-900 break-words" data-testid={`m-team-name-${r.id}`}>{r.nome}</div>
            {showEvent && <div className="text-xs text-slate-500 mt-0.5">{eName(r.evento_id)}</div>}
          </div>
          {miss > 0 ? <span className="shrink-0 rounded-full bg-red-100 text-red-700 px-2 py-0.5 text-xs font-semibold" data-testid={`m-team-missing-${r.id}`}>{miss} mancanti</span>
            : miss === 0 ? <span className="shrink-0 rounded-full bg-emerald-100 text-emerald-700 px-2 py-0.5 text-xs font-semibold">Completo</span> : null}
        </div>
        <div className="mt-2 text-sm text-slate-700">Team Leader: {r.responsabile_id ? <b className="font-semibold">{pName(r.responsabile_id)}</b> : <StatusBadge color="orange">Da assegnare</StatusBadge>}</div>
        <div className="text-sm text-slate-600" data-testid={`m-team-counts-${r.id}`}>Staff {c.staff.size} · Volontari {c.vol.size}{req != null ? `/${req}` : ""}</div>
        <div className="mt-3 flex flex-wrap gap-2">
          <TextAction icon={Pencil} onClick={openDetail} data-testid={`m-edit-team-${r.id}`}>Modifica</TextAction>
          <TeamNoteButton team={r} canEdit={canEditStaff} onSave={saveNote(update, r.id)} />
          {allow("delete") && <DeleteConfirm onConfirm={() => onDelete(r)} testid={`m-confirm-delete-team-${r.id}`}><TextAction icon={Trash2} danger data-testid={`m-delete-team-${r.id}`}>Elimina</TextAction></DeleteConfirm>}
        </div>
      </div>
    );
  };
  const shiftFields = [
    { name: "evento_id", label: "Evento", required: true, type: "select", options: eventOpts }, { name: "persona_id", label: "Persona (vuoto = scoperto)", type: "select", options: personOpts },
    { name: "data", label: "Data", type: "date" }, { name: "ora_inizio", label: "Ora inizio", type: "time" }, { name: "ora_fine", label: "Ora fine", type: "time" },
    { name: "area", label: "Area", type: "select", settingKey: "aree_operative", addLabel: "Aggiungi nuova Area", options: settings?.aree_operative || [] }, { name: "ruolo", label: "Ruolo", type: "select", settingKey: "ruoli_staff", addLabel: "Aggiungi nuovo Ruolo", options: settings?.ruoli_staff || [] },
    { name: "team_id", label: "Team", type: "teamselect", eventFrom: "evento_id" }, { name: "luogo", label: "Luogo" }, { name: "punto_ritrovo", label: "Punto di ritrovo" },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const shiftCols = [
    { key: "data", label: "Data", sortAccessor: (r) => `${r.data || ""} ${r.ora_inizio || ""}`.trim(), sortType: "string", render: (r) => <span className="font-medium text-slate-800">{r.data}</span> },
    { key: "ora", label: "Orario", render: (r) => `${r.ora_inizio || ""}–${r.ora_fine || ""}` },
    { key: "persona_id", label: "Persona", sortAccessor: (r) => (r.persona_id ? pName(r.persona_id) : ""), sortType: "string", render: (r) => r.persona_id ? pName(r.persona_id) : <StatusBadge color="red">Scoperto</StatusBadge> },
    { key: "area", label: "Area" }, { key: "team_id", label: "Team", render: (r) => r.team_id ? tName(r.team_id) : "—" },
  ];

  const isStaff = mode === "staff";
  const canInvite = canSendInvites(user);
  const peopleProps = {
    rows, loading, onOpen: (r) => setDetailId(r.id),
    onEdit: (r) => { setEditing(r); setFormOpen(true); }, onInvite: canInvite ? (r) => setInvite(r) : null,
    onDelete: delPerson, onRoleClick: (r) => setRolesFor(r), onInvited: reload,
  };

  return (
    <div className="animate-fade-up">
      <PageHeader
        title={isStaff ? "Staff / Volontari" : "Anagrafiche"}
        subtitle={isStaff ? "Staff e Volontari degli eventi: ruoli, team e turni" : "Referenti e contatti delle aziende"}
        action={can(user, isStaff ? "staff" : "anagrafiche", "create") ? <PrimaryButton onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="add-person-button"><Plus className="w-4 h-4 mr-1.5" />{isStaff ? "Aggiungi Staff / Volontario" : "Aggiungi persona"}</PrimaryButton> : null} />
      {isStaff ? (
        <Tabs defaultValue="staff">
          <TabsList className="mb-4 flex-wrap h-auto">
            <TabsTrigger value="staff" data-testid="tab-staff">Staff</TabsTrigger>
            <TabsTrigger value="volontari" data-testid="tab-volontari">Volontari</TabsTrigger>
            <TabsTrigger value="da_classificare" data-testid="tab-da-classificare">Da classificare</TabsTrigger>
            <TabsTrigger value="team" data-testid="tab-team">Team</TabsTrigger>
            <TabsTrigger value="turni" data-testid="tab-turni">Turni</TabsTrigger>
          </TabsList>
          {["staff", "volontari", "da_classificare"].map((t) => (
            <TabsContent key={t} value={t}>
              <PeopleTable tab={t} events={events} {...peopleProps} />
            </TabsContent>
          ))}
          <TabsContent value="team">
            <EntityManager title="Team" subtitle="Squadre operative per evento con Team Leader" endpoint="/teams"
              fields={teamFields} columns={teamCols} entityLabel="team" testid="team" section="teams" searchKeys={["nome", "area"]} onMutate={invalidateTeams} filters={[{ name: "evento_id", label: "Evento", options: eventOpts }]}
              extraActions={(r, { update }) => <TeamNoteButton team={r} canEdit={canEditStaff} onSave={saveNote(update, r.id)} />}
              mobileCard={teamMobileCard}
              renderDetail={(team, { close, edit, update }) => (
                <TeamMembersDialog team={team} open onOpenChange={(o) => !o && close()} persons={rows} staffLinks={staffLinks} events={events}
                  onReloadStaff={reload} onEdit={edit} canEdit={canEditMembers} onSaveNote={saveNote(update, team.id)}
                  onOpenPerson={(pid) => { close(); setDetailId(pid); }} />)} />
          </TabsContent>
          <TabsContent value="turni">
            <EntityManager title="Turni" subtitle="Turni operativi; lascia la persona vuota per un turno scoperto" endpoint="/shifts"
              fields={shiftFields} columns={shiftCols} entityLabel="turno" testid="shift" section="turni" searchKeys={["ruolo", "area", "luogo"]}
              filters={[{ name: "evento_id", label: "Evento", options: eventOpts }, { name: "area", label: "Area", options: areaOpts }, { name: "team_id", label: "Team", options: teamOpts }]} />
          </TabsContent>
        </Tabs>
      ) : (
        <PeopleTable tab="referenti_aziende" {...peopleProps} />
      )}

      <EntityDialog open={formOpen} onOpenChange={setFormOpen} title={editing ? "Modifica persona" : "Nuova persona"}
        fields={personFields} initial={editing} onSubmit={submitPerson} testid="person" />
      {detailId && <PersonDetailDialog personId={detailId} open={!!detailId} onOpenChange={(o) => !o && setDetailId(null)}
        events={events} settings={settings} onChanged={reload}
        onEdit={(p) => { setDetailId(null); setEditing(p); setFormOpen(true); }} onInvite={canInvite ? (p) => { setDetailId(null); setInvite(p); } : null} />}
      {invite && <PersonInviteDialog person={invite} open={!!invite} onOpenChange={(o) => !o && setInvite(null)} onDone={reload} />}
      {rolesFor && <EventRolesDialog person={rolesFor} events={events} settings={settings} open={!!rolesFor} onOpenChange={(o) => !o && setRolesFor(null)} onDone={reload} />}
    </div>
  );
}
