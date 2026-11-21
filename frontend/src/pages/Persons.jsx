import { useState, useEffect, useCallback, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { EntityManager, EntityDialog, StatusBadge, useCollection, useSettings, toOptions, PageHeader, PrimaryButton, TextAction, DeleteConfirm } from "@/components/crm";
import { TeamNoteButton } from "@/components/TeamNote";
import { personName, personOptions } from "@/lib/names";
import { useAuth } from "@/context/AuthContext";
import { can, canSendInvites } from "@/lib/perms";
import { PersonInviteDialog, BulkInviteBar, LastInvite, INV, INV_LABEL } from "@/components/PersonInvites";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ImportLink } from "@/components/import/ImportLink";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Plus, Pencil, Trash2, UserPlus, Search, Users, Phone, Eye, Crown, Check } from "lucide-react";
import { toast } from "sonner";
import { useSort, SortIcon, sortRows } from "@/lib/sortable";
import PersonDetailDialog from "@/components/PersonDetailDialog";
import TeamMembersDialog, { teamCounts } from "@/components/TeamMembersDialog";
import VolunteerSummary from "@/components/VolunteerSummary";
import TeamSelect from "@/components/TeamSelect";
import { useTeams, invalidateTeams } from "@/lib/teamsStore";
import { usePeople } from "@/lib/peopleStore";
import { PERSON_RULES } from "@/lib/textCase";
import PersonMask, { PROVENIENZA } from "@/components/PersonMask";
import ExportPdfButton from "@/components/ExportPdfButton";

const CAT = { referente: "Referente", staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario", team: "Team" };
const STATO = { da_contattare: "Da contattare", disponibilita_richiesta: "Disponibilità richiesta", disponibile: "Disponibile", da_riconfermare: "Da riconfermare", confermato: "Confermato", non_disponibile: "Non disponibile", rinunciato: "Rinunciato" };
const STATO_COLOR = { confermato: "green", disponibile: "green", da_riconfermare: "orange", disponibilita_richiesta: "blue", da_contattare: "gray", non_disponibile: "red", rinunciato: "red" };

function PeopleTable({ rows, loading, tab, events = [], teams = [], staffLinks = [], ruoli = [], onReload, onOpen, onEdit, onInvite, onDelete, onInvited, canDelete = true }) {
  const [q, setQ] = useState("");
  const [tagliaFilter, setTagliaFilter] = useState("all");
  const [gruppoFilter, setGruppoFilter] = useState("all");
  const [evFilter, setEvFilter] = useState("all");
  const [prefFilter, setPrefFilter] = useState("all");
  const [teamFilter, setTeamFilter] = useState("all");
  const [mansFilter, setMansFilter] = useState("all");
  const [provFilter, setProvFilter] = useState("all");
  const TAB_CATS = { staff: ["staff", "collaboratore"], volontari: ["volontario"] }[tab];
  const asg = (r) => (r.assegnazioni || []).filter((a) => (evFilter === "all" || a.evento_id === evFilter) && (!TAB_CATS || TAB_CATS.includes(a.categoria)));
  const evName = (id) => events.find((e) => e.id === id)?.nome || "—";
  const teamName = (id) => teams.find((t) => t.id === id)?.nome;
  const [bulkRole, setBulkRole] = useState("");
  const [sel, setSel] = useState(() => new Set());
  const prefsOf = (r) => {
    const own = asg(r).filter((a) => a.preferenza).map((a) => ({ evento_id: a.evento_id, preferenza: a.preferenza }));
    const ownEv = new Set(own.map((p) => p.evento_id));
    return [...own, ...(r.preferenze || []).filter((p) => (evFilter === "all" || p.evento_id === evFilter) && !ownEv.has(p.evento_id))];
  };
  const prefText = (r) => { const ps = prefsOf(r); if (!ps.length) return ""; return [...new Set(ps.map((p) => p.preferenza || "Non indicata"))].join(", "); };
  const multi = (r, f) => [...new Set(asg(r).map(f).filter(Boolean))];
  const multiCell = (r, f, testid) => {
    const vals = multi(r, f);
    if (!vals.length) return <span className="text-slate-400">—</span>;
    if (vals.length > 1 && evFilter === "all") {
      const detail = asg(r).map((a) => `${evName(a.evento_id)}: ${f(a) || "—"}`).join("\n");
      return <span title={detail} className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 whitespace-nowrap" data-testid={`${testid}-multi-${r.id}`}>{vals.length} associazioni</span>;
    }
    return <span className="text-slate-700" data-testid={`${testid}-${r.id}`}>{vals.join(", ")}</span>;
  };
  const mansioniOf = (r) => (r.mansioni || []).filter((m) => evFilter === "all" || m.evento_id === evFilter);
  const mansioneText = (r) => { const ms = mansioniOf(r).map((m) => m.ruolo).filter(Boolean); return ms.length ? [...new Set(ms)].join(", ") : (isStaffTab ? "" : r.ruolo || ""); };
  const flip = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const filtered = rows.filter((r) => {
    if (tab === "referenti_aziende" && !r.is_referente) return false;
    if (tab === "staff" && !r.is_staff) return false;
    if (tab === "volontari" && !r.is_volontario) return false;
    if (tab === "da_classificare" && !r.is_da_classificare && (r.is_referente || r.is_staff || r.is_volontario)) return false;
    if (evFilter !== "all" && !(r.eventi_ids || []).includes(evFilter) && !(r.preferenze || []).some((p) => p.evento_id === evFilter)) return false;
    if (prefFilter !== "all" && !prefsOf(r).some((p) => (p.preferenza || "Non indicata") === prefFilter)) return false;
    if (teamFilter !== "all" && !asg(r).some((a) => (teamFilter === "none" ? !a.team_id : a.team_id === teamFilter))) return false;
    if (mansFilter !== "all" && !asg(r).some((a) => (mansFilter === "none" ? !a.ruolo : a.ruolo === mansFilter))) return false;
    if (provFilter !== "all" && (r.provenienza_tipo || "non_determinata") !== provFilter) return false;
    if (tagliaFilter !== "all" && (tagliaFilter === "none" ? !!r.taglia : r.taglia !== tagliaFilter)) return false;
    if (gruppoFilter !== "all" && (gruppoFilter === "none" ? !!r.gruppo_appartenenza : r.gruppo_appartenenza !== gruppoFilter)) return false;
    if (q) { const s = `${r.nome} ${r.cognome} ${r.email || ""} ${r.codice_fiscale || ""} ${r.cellulare || ""} ${r.ruolo || ""} ${r.gruppo_appartenenza || ""} ${(r.aziende_nomi || []).join(" ")}`.toLowerCase(); if (!s.includes(q.toLowerCase())) return false; }
    return true;
  });
  const { sort, toggle } = useSort({ key: "cognome", dir: "asc" });
  const isStaffTab = tab === "staff" || tab === "volontari" || tab === "da_classificare";
  const leaderIds = new Set(teams.filter((t) => t.responsabile_id && (evFilter === "all" || t.evento_id === evFilter)).map((t) => t.responsabile_id));
  const ACC = {
    cognome: (r) => `${r.cognome || ""} ${r.nome || ""}`.trim(),
    nome: (r) => `${r.nome || ""} ${r.cognome || ""}`.trim(),
    cellulare: (r) => r.cellulare || "",
    preferenza: (r) => prefText(r),
    taglia: (r) => r.taglia || "",
    ruolo_evento: (r) => (r.is_staff ? "Staff" : r.is_volontario ? "Volontario" : r.is_referente ? "Referente" : ""),
    team: (r) => multi(r, (a) => teamName(a.team_id)).join(", "),
    evento: (r) => (r.eventi_nomi || []).join(", "),
    qualifica: (r) => mansioneText(r),
    gruppo: (r) => r.gruppo_appartenenza || "",
    aziende: (r) => (r.aziende_nomi || []).join(", "),
    accesso: (r) => INV_LABEL[r.invite_status || "non_invitato"] || "",
  };
  const colsMeta = Object.entries(ACC).map(([key, sortAccessor]) => ({ key, sortAccessor, sortType: "string" }));
  const displayRows = sortRows(filtered, sort, colsMeta);
  const selectedRows = displayRows.filter((r) => sel.has(r.id));
  const allSel = displayRows.length > 0 && selectedRows.length === displayRows.length;
  const toggleAll = () => setSel(allSel ? new Set() : new Set(displayRows.map((r) => r.id)));
  const pick = (r) => (onInvite || isStaffTab) && <input type="checkbox" className="accent-tiffany w-4 h-4" checked={sel.has(r.id)} onChange={() => flip(r.id)} onClick={(e) => e.stopPropagation()} aria-label="Seleziona" data-testid={`select-invite-${r.id}`} />;
  const prefOptions = [...new Set(rows.flatMap((r) => prefsOf(r).map((p) => p.preferenza || "Non indicata")))].sort((a, b) => a.localeCompare(b, "it"));
  const eventFor = (r) => {
    if (evFilter !== "all") return evFilter;
    const ps = prefsOf(r);
    if (ps.length === 1) return ps[0].evento_id;
    const evs = [...new Set((r.mansioni || []).map((m) => m.evento_id))];
    return evs.length === 1 ? evs[0] : evs.length === 0 ? null : undefined;
  };
  const assign = async (people, mansione) => {
    const byEv = {};
    for (const r of people) {
      const ev = eventFor(r);
      if (ev === undefined) { toast.error(`${r.cognome || ""} ${r.nome || ""} partecipa a più eventi: scegli prima l'evento nel filtro`); return; }
      (byEv[ev || ""] = byEv[ev || ""] || []).push(r.id);
    }
    try {
      let n = 0;
      for (const [ev, ids] of Object.entries(byEv)) {
        const { data } = await api.post("/persons/mansione-bulk", { person_ids: ids, mansione, evento_id: ev || null });
        n += data.partecipazioni + data.anagrafiche;
      }
      toast.success(`Mansione "${mansione}" assegnata (${n})`); onReload && onReload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const confirmPrefs = async (people) => {
    const groups = {};
    people.forEach((r) => { const ps = prefsOf(r).map((p) => p.preferenza).filter((p) => ruoli.includes(p)); if (ps.length === 1) (groups[ps[0]] = groups[ps[0]] || []).push(r); });
    if (!Object.keys(groups).length) { toast.error("Nessuna preferenza corrisponde a una mansione esistente: scegli la mansione dal menu"); return; }
    for (const [m, ppl] of Object.entries(groups)) await assign(ppl, m);
    const skipped = people.length - Object.values(groups).flat().length;
    if (skipped) toast.info(`${skipped} persone saltate: preferenze multiple o senza mansione corrispondente`);
  };
  const prefCell = (r) => {
    const t = prefText(r);
    return t ? <span className="text-slate-700" data-testid={`pref-${r.id}`}>{t}</span> : <span className="text-slate-400">—</span>;
  };
  const Th = ({ k, label, right }) => (
    <th onClick={() => toggle(k)} data-testid={`sort-${k}`} className={`font-semibold text-slate-600 px-4 py-3 whitespace-nowrap cursor-pointer select-none group ${right ? "text-right" : "text-left"}`}>
      <span className="inline-flex items-center gap-1">{label}<SortIcon active={sort.key === k} dir={sort.dir} /></span>
    </th>
  );
  const roleBadges = (r) => {
    const cats = isStaffTab ? new Set(asg(r).map((a) => a.categoria)) : null;
    const st = cats ? cats.has("staff") || cats.has("collaboratore") : r.is_staff;
    const vo = cats ? cats.has("volontario") : r.is_volontario;
    return (
      <div className="flex flex-wrap items-center gap-1" data-testid={`role-cell-${r.id}`}>
        {leaderIds.has(r.id) && <Crown className="w-3.5 h-3.5 text-[#D4AF37]" aria-label="Team Leader" data-testid={`leader-crown-${r.id}`} />}
        {st && <StatusBadge color="blue">Staff</StatusBadge>}{vo && <StatusBadge color="green">Volontario</StatusBadge>}
        {r.is_referente && !isStaffTab && <StatusBadge color="tiffany">Referente</StatusBadge>}
        {r.is_socio && <StatusBadge color="gray" data-testid={`socio-badge-${r.id}`}>Socio</StatusBadge>}
        {(isStaffTab ? asg(r).some((a) => a.categoria === "da_classificare") : r.is_da_classificare) && <StatusBadge color="orange">Da classificare</StatusBadge>}
        {!st && !vo && !(r.is_referente && !isStaffTab) && !r.is_da_classificare && <span className="text-slate-400">—</span>}
      </div>
    );
  };
  const fullName = (r) => `${r.nome || ""} ${r.cognome || ""}`.trim();
  const delDialog = (r, trigger, testid) => (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent onClick={(e) => e.stopPropagation()}><AlertDialogHeader><AlertDialogTitle>Eliminare {fullName(r)}?</AlertDialogTitle><AlertDialogDescription>Se la persona ha assegnazioni o dati storici, viene tolta dagli elenchi ma lo storico resta conservato.</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel data-testid={`cancel-delete-person-${r.id}`}>Annulla</AlertDialogCancel><AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={() => onDelete(r)} data-testid={testid}>Elimina</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
    </AlertDialog>
  );
  const actionsCell = (r) => (
    <div className="flex items-center justify-end gap-0.5">
      {onInvite && <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title={r.last_invite_at ? "Reinvia invito" : "Invita"} onClick={() => onInvite(r)} data-testid={`invite-${r.id}`}><UserPlus className="w-4 h-4" /></Button>}
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Modifica" onClick={() => onEdit(r)} data-testid={`edit-person-${r.id}`}><Pencil className="w-4 h-4" /></Button>
      {canDelete && delDialog(r, <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" title="Elimina" data-testid={`delete-person-${r.id}`}><Trash2 className="w-4 h-4" /></Button>, `confirm-delete-person-${r.id}`)}
    </div>
  );
  const teamsCell = (r) => (isStaffTab ? multiCell(r, (a) => teamName(a.team_id), "team") : ((r.teams_nomi && r.teams_nomi.length)
    ? <div className="flex flex-wrap gap-1">{r.teams_nomi.map((t, i) => <span key={i} className="inline-flex items-center rounded-full bg-tiffany-light text-tiffany-fg px-2 py-0.5 text-xs font-medium whitespace-nowrap">{t}</span>)}</div>
    : <span className="text-slate-400">—</span>));
  const mansCell = (r) => multiCell(r, (a) => a.ruolo, "mansione");
  const gruppoCell = (r) => (r.gruppo_appartenenza
    ? <span className="block max-w-[180px] truncate text-slate-700" title={r.gruppo_appartenenza} data-testid={`gruppo-${r.id}`}>{r.gruppo_appartenenza}</span>
    : <span className="italic text-slate-400" data-testid={`gruppo-${r.id}`}>Nessun gruppo</span>);
  const gruppoOpts = [...new Set(rows.map((r) => r.gruppo_appartenenza).filter(Boolean))].sort((a, b) => a.localeCompare(b, "it"));
  const teamOpts = [...new Map(rows.flatMap((r) => (r.assegnazioni || []).filter((a) => a.team_id && (evFilter === "all" || a.evento_id === evFilter)).map((a) => [a.team_id, teamName(a.team_id)])).filter(([, n]) => n)).entries()].sort((a, b) => a[1].localeCompare(b[1], "it"));
  const mansOpts = [...new Set(rows.flatMap((r) => (r.assegnazioni || []).map((a) => a.ruolo).filter(Boolean)))].sort((a, b) => a.localeCompare(b, "it"));
  const tagliaOpts = [...new Set(rows.map((r) => r.taglia).filter(Boolean))];
  const fsel = "h-10 w-full sm:w-48 rounded-md border border-slate-200 bg-white px-2 text-sm";
  return (
    <div>
      <div className="mb-4 flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-3">
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
        {isStaffTab && prefOptions.length > 0 && (
          <select className="h-10 w-full sm:w-56 rounded-md border border-slate-200 bg-white px-2 text-sm" value={prefFilter} onChange={(e) => setPrefFilter(e.target.value)} data-testid="people-pref-filter">
            <option value="all">Tutte le preferenze</option>{prefOptions.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        )}
        {isStaffTab && <select className={fsel} value={teamFilter} onChange={(e) => setTeamFilter(e.target.value)} data-testid="people-team-filter"><option value="all">Tutti i team</option><option value="none">Senza team</option>{teamOpts.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>}
        {isStaffTab && <select className={fsel} value={mansFilter} onChange={(e) => setMansFilter(e.target.value)} data-testid="people-mansione-filter"><option value="all">Tutte le mansioni</option><option value="none">Senza mansione</option>{mansOpts.map((m) => <option key={m} value={m}>{m}</option>)}</select>}
        {isStaffTab && <select className={fsel} value={provFilter} onChange={(e) => setProvFilter(e.target.value)} data-testid="people-provenienza-filter"><option value="all">Tutte le provenienze</option>{Object.entries(PROVENIENZA).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>}
        {isStaffTab && <select className="h-10 w-full sm:w-36 rounded-md border border-slate-200 bg-white px-2 text-sm" value={tagliaFilter} onChange={(e) => setTagliaFilter(e.target.value)} data-testid="people-taglia-filter"><option value="all">Tutte le taglie</option><option value="none">Senza taglia</option>{tagliaOpts.map((t) => <option key={t} value={t}>{t}</option>)}</select>}
        {isStaffTab && <select className={fsel} value={gruppoFilter} onChange={(e) => setGruppoFilter(e.target.value)} data-testid="people-gruppo-filter"><option value="all">Tutti i gruppi</option><option value="none">Nessun gruppo</option>{gruppoOpts.map((g) => <option key={g} value={g}>{g}</option>)}</select>}
        {(tab === "staff" || tab === "volontari") && <ExportPdfButton section={tab} eventoId={evFilter !== "all" ? evFilter : null} eventName={evFilter !== "all" ? evName(evFilter) : ""} personIds={displayRows.map((r) => r.id)} scopeLabel={`${displayRows.length} ${displayRows.length === 1 ? "persona" : "persone"} con i filtri attuali`} />}
      </div>
      {isStaffTab && selectedRows.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-tiffany/40 bg-tiffany-light/40 px-3 py-2 text-sm" data-testid="bulk-mansione-bar">
          <span className="font-medium">{selectedRows.length} selezionati</span>
          <Button size="sm" variant="outline" onClick={() => confirmPrefs(selectedRows)} data-testid="bulk-confirm-prefs"><Check className="w-4 h-4 mr-1" />Conferma preferenze</Button>
          <select className="h-9 rounded-md border border-slate-200 bg-white px-2" value={bulkRole} onChange={(e) => setBulkRole(e.target.value)} data-testid="bulk-mansione-select"><option value="">Mansione…</option>{ruoli.map((x) => <option key={x} value={x}>{x}</option>)}</select>
          <Button size="sm" disabled={!bulkRole} onClick={() => assign(selectedRows, bulkRole)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900" data-testid="bulk-mansione-apply">Assegna a {selectedRows.length}</Button>
          <Button size="sm" variant="ghost" onClick={() => setSel(new Set())} data-testid="bulk-clear">Annulla selezione</Button>
        </div>
      )}
      {tab === "volontari" && <VolunteerSummary teams={teams} staffLinks={staffLinks} events={events} evFilter={evFilter} />}
      <div className="md:hidden space-y-2.5" data-testid={`people-mobile-list-${tab}`}>
        {loading ? <div className="py-10 text-center text-slate-400 text-sm">Caricamento...</div>
          : displayRows.length === 0 ? <div className="py-10 text-center text-slate-400 text-sm">Nessuna persona trovata.</div>
          : displayRows.map((r) => (
            <div key={r.id} className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" onClick={() => isStaffTab && onOpen(r)} data-testid={`person-card-${r.id}`}>
              <div className="flex items-start gap-2" onClick={(e) => e.stopPropagation()}>{pick(r)}<div className="font-semibold text-slate-900 break-words">{r.cognome} {r.nome}</div></div>
              <LastInvite person={r} className="mt-0.5" />
              {!isStaffTab && r.ruolo && <div className="text-sm text-slate-500">{r.ruolo}</div>}
              <div className="mt-2 space-y-1.5 text-sm text-slate-700">
                {r.cellulare && <a href={`tel:${r.cellulare}`} className="inline-flex items-center gap-1"><Phone className="w-3.5 h-3.5 text-slate-400" />{r.cellulare}</a>}
                <div>{roleBadges(r)}</div>
                {isStaffTab && <div className="flex items-start gap-2" data-testid={`m-pref-${r.id}`}><span className="w-20 shrink-0 text-xs text-slate-400 pt-1.5">Preferenza</span>{prefCell(r)}</div>}
                {isStaffTab && <div className="flex items-start gap-2" data-testid={`m-taglia-${r.id}`}><span className="w-20 shrink-0 text-xs text-slate-400">Taglia</span><span>{r.taglia || "—"}</span></div>}
                {isStaffTab ? (<>
                  <div className="flex items-start gap-2"><span className="w-20 shrink-0 text-xs text-slate-400 pt-0.5">Team</span>{teamsCell(r)}</div>
                  <div className="flex items-start gap-2" data-testid={`m-mansione-${r.id}`}><span className="w-20 shrink-0 text-xs text-slate-400 pt-0.5">Mansione</span>{mansCell(r)}</div>
                  <div className="flex items-start gap-2 min-w-0" data-testid={`m-gruppo-${r.id}`}><span className="w-20 shrink-0 text-xs text-slate-400 pt-0.5">Gruppo</span><div className="min-w-0">{gruppoCell(r)}</div></div>
                  {r.eventi_nomi?.length > 0 && <div className="text-xs text-slate-500">{r.eventi_nomi.join(", ")}</div>}
                  <StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge>
                </>) : (<>
                  {r.aziende_nomi?.length > 0 && <div className="text-xs text-slate-500">{r.aziende_nomi.join(", ")}</div>}
                  <StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge>
                </>)}
              </div>
              <div className="mt-3 flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
                {!isStaffTab && <TextAction icon={Eye} onClick={() => onOpen(r)} data-testid={`m-open-person-${r.id}`}>Apri</TextAction>}
                {onInvite && <TextAction icon={UserPlus} onClick={() => onInvite(r)} data-testid={`m-invite-${r.id}`}>{r.last_invite_at ? "Reinvia" : "Invita"}</TextAction>}
                <TextAction icon={Pencil} onClick={() => onEdit(r)} data-testid={`m-edit-person-${r.id}`}>Modifica</TextAction>
                {canDelete && delDialog(r, <TextAction icon={Trash2} danger data-testid={`m-delete-person-${r.id}`}>Elimina</TextAction>, `m-confirm-delete-person-${r.id}`)}
              </div>
            </div>
          ))}
      </div>
      <div className="hidden md:block bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 bg-slate-50/70">
              {(onInvite || isStaffTab) && <th className="pl-4 py-3 w-8"><input type="checkbox" className="accent-tiffany w-4 h-4" checked={allSel} onChange={toggleAll} aria-label="Seleziona tutti" data-testid={`select-invite-all-${tab}`} /></th>}
              {isStaffTab ? (<>
                <Th k="cognome" label="Cognome" />
                <Th k="nome" label="Nome" />
                <Th k="cellulare" label="Cellulare" />
                <Th k="ruolo_evento" label="Ruolo" />
                <Th k="preferenza" label="Preferenza" />
                <Th k="taglia" label="Taglia" />
                <Th k="team" label="Team" />
                <Th k="qualifica" label="Mansione" />
                <Th k="gruppo" label="Gruppo di appartenenza" />
                <Th k="evento" label="Evento" />
                <th className="text-right font-semibold text-slate-600 px-4 py-3 whitespace-nowrap">Azioni</th>
              </>) : (<>
                <Th k="cognome" label="Cognome e Nome" />
                <Th k="qualifica" label="Qualifica" />
                <Th k="aziende" label="Aziende" />
                <Th k="ruolo_evento" label="Ruolo eventi" />
                <Th k="accesso" label="Accesso" />
                <th className="text-right font-semibold text-slate-600 px-4 py-3 whitespace-nowrap">Azioni</th>
              </>)}
            </tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={11} className="px-4 py-10 text-center text-slate-400">Caricamento...</td></tr>
                : displayRows.length === 0 ? <tr><td colSpan={11} className="px-4 py-10 text-center text-slate-400">Nessuna persona trovata.</td></tr>
                : displayRows.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50/80 transition-colors cursor-pointer" onClick={() => onOpen(r)} data-testid={`person-row-${r.id}`}>
                    {(onInvite || isStaffTab) && <td className="pl-4 py-3" onClick={(e) => e.stopPropagation()}>{pick(r)}</td>}
                    {isStaffTab ? (
                      <>
                        <td className="px-4 py-3"><span className="font-medium text-slate-800" data-testid={`cognome-${r.id}`}>{r.cognome || "—"}</span><LastInvite person={r} /></td>
                        <td className="px-4 py-3 text-slate-800" data-testid={`nome-${r.id}`}>{r.nome}</td>
                        <td className="px-4 py-3 text-slate-700 whitespace-nowrap">{r.cellulare || "—"}</td>
                        <td className="px-4 py-3">{roleBadges(r)}</td>
                        <td className="px-4 py-3">{prefCell(r)}</td>
                        <td className="px-3 py-3 text-slate-700 whitespace-nowrap" data-testid={`taglia-${r.id}`}>{r.taglia || "—"}</td>
                        <td className="px-4 py-3">{teamsCell(r)}</td>
                        <td className="px-4 py-3">{mansCell(r)}</td>
                        <td className="px-4 py-3">{gruppoCell(r)}</td>
                        <td className="px-4 py-3 text-slate-600">{(r.eventi_nomi && r.eventi_nomi.length) ? r.eventi_nomi.join(", ") : "—"}</td>
                      </>
                    ) : (
                      <>
                        <td className="px-4 py-3"><span className="font-medium text-slate-800">{r.cognome} {r.nome}</span><LastInvite person={r} /></td>
                        <td className="px-4 py-3 text-slate-700">{r.ruolo || "—"}</td>
                        <td className="px-4 py-3 text-slate-700">{(r.aziende_nomi && r.aziende_nomi.length) ? r.aziende_nomi.join(", ") : "—"}</td>
                        <td className="px-4 py-3">{roleBadges(r)}</td>
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
  const { items: companies } = useCollection(can(user, "aziende") ? "/companies" : null);
  const { items: events } = useCollection("/events");
  const { staff: staffLinks, persons: rows, loading, reload } = usePeople();
  const { teams } = useTeams();
  const settings = useSettings();
  const [detailId, setDetailId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [invite, setInvite] = useState(null);
  const [mask, setMask] = useState(null);

  const companyOpts = companies.map((c) => ({ value: c.id, label: c.nome }));
  const personFields = mode === "staff" ? [
    { name: "nome", label: "Nome", required: true }, { name: "cognome", label: "Cognome" },
    { name: "email", label: "Email", type: "email" }, { name: "cellulare", label: "Cellulare", type: "tel" },
    { name: "telefono", label: "Telefono", type: "tel" },
    { name: "data_nascita", label: "Data di nascita", type: "date" }, { name: "eta", label: "Età", type: "age", virtual: true },
    { name: "codice_fiscale", label: "Codice Fiscale" }, { name: "luogo_nascita", label: "Luogo di nascita" },
    { name: "taglia", label: "Taglia", type: "setting", settingKey: "taglie", options: settings?.taglie || [] },
    { name: "gruppo_appartenenza", label: "Gruppo di appartenenza", type: "setting", settingKey: "gruppi_appartenenza", noneLabel: "Nessun gruppo", options: (settings?.gruppi_appartenenza || []).filter((g) => !((settings?.disattivati || {}).gruppi_appartenenza || []).includes(g)) },
    { name: "indirizzo", label: "Indirizzo e numero civico", full: true }, { name: "cap", label: "CAP" }, { name: "citta", label: "Località / Comune" },
    { name: "provincia", label: "Provincia" }, { name: "regione", label: "Regione" }, { name: "nazione", label: "Nazione" },
    { name: "note", label: "Note", type: "textarea", full: true },
  ] : [
    { name: "nome", label: "Nome", required: true }, { name: "cognome", label: "Cognome" },
    { name: "ruolo", label: "Qualifica" }, { name: "email", label: "Email", type: "email" },
    { name: "email_secondaria", label: "Email secondaria", type: "email" }, { name: "cellulare", label: "Cellulare", type: "tel" },
    { name: "telefono", label: "Telefono", type: "tel" }, { name: "azienda_id", label: "Azienda principale", type: "select", options: companyOpts },
    { name: "data_nascita", label: "Data di nascita", type: "date" }, { name: "codice_fiscale", label: "Codice Fiscale" }, { name: "luogo_nascita", label: "Luogo di nascita" }, { name: "linkedin", label: "LinkedIn" },
    { name: "indirizzo", label: "Indirizzo" }, { name: "cap", label: "CAP" }, { name: "citta", label: "Città" },
    { name: "provincia", label: "Provincia" }, { name: "regione", label: "Regione" }, { name: "nazione", label: "Nazione" },
    { name: "foto_url", label: "Foto (URL)" }, { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const daClassificare = rows.filter((r) => r.is_da_classificare || !(r.is_referente || r.is_staff || r.is_volontario)).length;
  const submitPerson = async (form) => {
    if (editing) { await api.put(`/persons/${editing.id}`, form); toast.success("Persona aggiornata"); }
    else { await api.post("/persons", form); toast.success("Persona creata"); }
    await reload();
  };
  const delPerson = async (r) => { try { const { data } = await api.delete(`/persons/${r.id}`); await reload(); toast.success(data?.archived ? "Persona eliminata dall'elenco (storico conservato)" : "Persona eliminata"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

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
    rows, loading, onOpen: (r) => (isStaff ? setMask({ person: r }) : setDetailId(r.id)), canDelete: can(user, isStaff ? "staff" : "anagrafiche", "delete"),
    onEdit: (r) => (isStaff ? setMask({ person: r }) : (setEditing(r), setFormOpen(true))), onInvite: canInvite ? (r) => setInvite(r) : null,
    onDelete: delPerson, onInvited: reload,
  };

  return (
    <div className="animate-fade-up">
      <PageHeader
        title={isStaff ? "Staff / Volontari" : "Anagrafiche"}
        subtitle={isStaff ? "Staff e Volontari degli eventi: ruoli, team e turni" : "Referenti e contatti delle aziende"}
        action={!can(user, isStaff ? "staff" : "anagrafiche", "create") ? null : isStaff ? (
          <div className="flex flex-wrap gap-2">
            <ImportLink target="persone" />
            <PrimaryButton onClick={() => setMask({ person: null, cat: "staff" })} data-testid="add-staff-button"><Plus className="w-4 h-4 mr-1.5" />Aggiungi Staff</PrimaryButton>
            <PrimaryButton onClick={() => setMask({ person: null, cat: "volontario" })} data-testid="add-volunteer-button"><Plus className="w-4 h-4 mr-1.5" />Aggiungi Volontario</PrimaryButton>
          </div>
        ) : <PrimaryButton onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="add-person-button"><Plus className="w-4 h-4 mr-1.5" />Aggiungi persona</PrimaryButton>} />
      {isStaff ? (
        <Tabs defaultValue="staff">
          <TabsList className="mb-4 flex-wrap h-auto">
            <TabsTrigger value="staff" data-testid="tab-staff">Staff</TabsTrigger>
            <TabsTrigger value="volontari" data-testid="tab-volontari">Volontari</TabsTrigger>
            <TabsTrigger value="da_classificare" data-testid="tab-da-classificare">Da classificare{daClassificare > 0 && <span className="ml-1.5 rounded-full bg-amber-100 text-amber-800 px-1.5 text-[11px] font-bold" data-testid="da-classificare-count">{daClassificare}</span>}</TabsTrigger>
            <TabsTrigger value="team" data-testid="tab-team">Team</TabsTrigger>
            <TabsTrigger value="turni" data-testid="tab-turni">Turni</TabsTrigger>
          </TabsList>
          {["staff", "volontari", "da_classificare"].map((t) => (
            <TabsContent key={t} value={t}>
              <PeopleTable tab={t} events={events} teams={teams} staffLinks={staffLinks} ruoli={settings?.ruoli_staff || []} onReload={reload} {...peopleProps} />
            </TabsContent>
          ))}
          <TabsContent value="team">
            <EntityManager title="Team" subtitle="Squadre operative per evento con Team Leader" endpoint="/teams"
              fields={teamFields} columns={teamCols} entityLabel="team" testid="team" section="teams" searchKeys={["nome", "area"]} onMutate={invalidateTeams} filters={[{ name: "evento_id", label: "Evento", options: eventOpts }]}
              extraActions={(r, { update }) => <TeamNoteButton team={r} canEdit={canEditStaff} onSave={saveNote(update, r.id)} />}
              mobileCard={teamMobileCard}
              belowFilters={(fv) => (<>
                <div className="mb-3 flex justify-end"><ExportPdfButton section="team" eventoId={fv.evento_id && fv.evento_id !== "all" ? fv.evento_id : null} eventName={events.find((e) => e.id === fv.evento_id)?.nome || ""} scopeLabel="tutti i Team dell'evento" /></div>
                <VolunteerSummary teams={teams} staffLinks={staffLinks} events={events} evFilter={fv.evento_id || "all"} />
              </>)}
              renderDetail={(team, { close, edit, update }) => (
                <TeamMembersDialog team={team} open onOpenChange={(o) => !o && close()} persons={rows} staffLinks={staffLinks} events={events}
                  onReloadStaff={reload} onEdit={edit} canEdit={canEditMembers} onSaveNote={saveNote(update, team.id)}
                  onOpenPerson={(pid) => { close(); const p = rows.find((x) => x.id === pid); if (p) setMask({ person: p }); else setDetailId(pid); }} />)} />
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
        fields={personFields} initial={editing} onSubmit={submitPerson} testid="person" caseRules={PERSON_RULES} />
      {detailId && <PersonDetailDialog personId={detailId} open={!!detailId} onOpenChange={(o) => !o && setDetailId(null)}
        events={events} settings={settings} onChanged={reload}
        onEdit={(p) => { setDetailId(null); if (isStaff) setMask({ person: rows.find((x) => x.id === p.id) || p }); else { setEditing(p); setFormOpen(true); } }} onInvite={canInvite ? (p) => { setDetailId(null); setInvite(p); } : null} />}
      {invite && <PersonInviteDialog person={invite} open={!!invite} onOpenChange={(o) => !o && setInvite(null)} onDone={reload} />}
      {mask && <PersonMask person={mask.person ? rows.find((p) => p.id === mask.person.id) || mask.person : null} defaultCategoria={mask.person ? (mask.person.is_volontario && !mask.person.is_staff ? "volontario" : "staff") : mask.cat}
        fields={personFields} events={events} ruoli={settings?.ruoli_staff || []} onClose={() => setMask(null)} onSaved={async () => { setMask(null); await reload(); invalidateTeams(); }} />}
    </div>
  );
}
