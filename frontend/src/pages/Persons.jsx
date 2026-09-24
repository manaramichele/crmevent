import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { EntityManager, EntityDialog, StatusBadge, useCollection, useSettings, toOptions, PageHeader, PrimaryButton } from "@/components/crm";
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
import { Plus, Pencil, Trash2, UserPlus, Search } from "lucide-react";
import { toast } from "sonner";
import PersonDetailDialog from "@/components/PersonDetailDialog";

const INV = { non_invitato: "gray", invito_inviato: "orange", account_attivato: "green", accesso_disabilitato: "red" };
const INV_LABEL = { non_invitato: "Non invitato", invito_inviato: "Invito inviato", account_attivato: "Attivo", accesso_disabilitato: "Disabilitato" };
const CAT = { referente: "Referente", staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario", team: "Team" };
const STATO = { da_contattare: "Da contattare", disponibilita_richiesta: "Disponibilità richiesta", disponibile: "Disponibile", da_riconfermare: "Da riconfermare", confermato: "Confermato", non_disponibile: "Non disponibile", rinunciato: "Rinunciato" };
const STATO_COLOR = { confermato: "green", disponibile: "green", da_riconfermare: "orange", disponibilita_richiesta: "blue", da_contattare: "gray", non_disponibile: "red", rinunciato: "red" };

function InviteDialog({ person, open, onOpenChange, onDone }) {
  const [role, setRole] = useState("volunteer");
  const [busy, setBusy] = useState(false);
  const status = person?.invite_status || "non_invitato";
  const invite = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/persons/${person.id}/invite`, { role }); toast.success(data.email_sent ? "Invito inviato via email" : "Invito creato (email non inviata)"); onDone(); onOpenChange(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const toggle = async (enabled) => {
    try { await api.put(`/persons/${person.id}/access`, { enabled }); toast.success(enabled ? "Accesso riattivato" : "Accesso disabilitato"); onDone(); onOpenChange(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="invite-dialog">
        <DialogHeader><DialogTitle className="font-display">Invita su <strong className="font-semibold">CRMEvent</strong></DialogTitle>
          <DialogDescription>{person?.nome} {person?.cognome} — {person?.email || "nessuna email"}</DialogDescription></DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-2"><span className="text-sm text-slate-500">Stato attuale:</span><StatusBadge color={INV[status]}>{INV_LABEL[status]}</StatusBadge></div>
          <div className="space-y-1.5"><Label className="text-xs">Ruolo accesso</Label>
            <Select value={role} onValueChange={setRole}><SelectTrigger data-testid="invite-role"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="volunteer">Volontario</SelectItem><SelectItem value="staff">Staff</SelectItem></SelectContent></Select>
          </div>
        </div>
        <DialogFooter className="flex-col sm:flex-row gap-2">
          {status === "account_attivato" && <Button variant="outline" onClick={() => toggle(false)} data-testid="disable-access">Disabilita accesso</Button>}
          {status === "accesso_disabilitato" && <Button variant="outline" onClick={() => toggle(true)} data-testid="enable-access">Riattiva accesso</Button>}
          <Button onClick={invite} disabled={busy || !person?.email} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="send-invite">{busy ? "..." : status === "non_invitato" ? "Invia invito" : "Reinvia invito"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PeopleTable({ rows, loading, tab, onOpen, onEdit, onInvite, onDelete }) {
  const [q, setQ] = useState("");
  const filtered = rows.filter((r) => {
    if (tab === "referenti" && !r.is_referente) return false;
    if (tab === "staff" && !r.is_staff) return false;
    if (tab === "volontari" && !r.is_volontario) return false;
    if (q) { const s = `${r.nome} ${r.cognome} ${r.email || ""} ${r.ruolo || ""} ${(r.aziende_nomi || []).join(" ")}`.toLowerCase(); if (!s.includes(q.toLowerCase())) return false; }
    return true;
  });
  return (
    <div>
      <div className="mb-4 relative w-full sm:w-72">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input className="pl-9" placeholder="Cerca persone..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="search-person-input" />
      </div>
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 bg-slate-50/70">
              {["Nome", "Qualifica", "Aziende", "Ruolo eventi", "Accesso", "Azioni"].map((h) => <th key={h} className={`text-left font-semibold text-slate-600 px-4 py-3 whitespace-nowrap ${h === "Azioni" ? "text-right" : ""}`}>{h}</th>)}
            </tr></thead>
            <tbody>
              {loading ? <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Caricamento...</td></tr>
                : filtered.length === 0 ? <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Nessuna persona trovata.</td></tr>
                : filtered.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50/80 transition-colors cursor-pointer" onClick={() => onOpen(r)} data-testid={`person-row-${r.id}`}>
                    <td className="px-4 py-3"><span className="font-medium text-slate-800">{r.nome} {r.cognome}</span></td>
                    <td className="px-4 py-3 text-slate-700">{r.ruolo || "—"}</td>
                    <td className="px-4 py-3 text-slate-700">{(r.aziende_nomi && r.aziende_nomi.length) ? r.aziende_nomi.join(", ") : "—"}</td>
                    <td className="px-4 py-3"><span className="flex flex-wrap gap-1">{r.is_staff && <StatusBadge color="blue">Staff</StatusBadge>}{r.is_volontario && <StatusBadge color="green">Volontario</StatusBadge>}{!r.is_staff && !r.is_volontario && "—"}</span></td>
                    <td className="px-4 py-3"><StatusBadge color={INV[r.invite_status || "non_invitato"]}>{INV_LABEL[r.invite_status || "non_invitato"]}</StatusBadge></td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Invita" onClick={() => onInvite(r)} data-testid={`invite-${r.id}`}><UserPlus className="w-4 h-4" /></Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" onClick={() => onEdit(r)} data-testid={`edit-person-${r.id}`}><Pencil className="w-4 h-4" /></Button>
                        <AlertDialog>
                          <AlertDialogTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" data-testid={`delete-person-${r.id}`}><Trash2 className="w-4 h-4" /></Button></AlertDialogTrigger>
                          <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Confermi l'eliminazione?</AlertDialogTitle><AlertDialogDescription>Questa azione non può essere annullata.</AlertDialogDescription></AlertDialogHeader>
                            <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={() => onDelete(r)} data-testid={`confirm-delete-person-${r.id}`}>Elimina</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default function Persons() {
  const { items: companies } = useCollection("/companies");
  const { items: events } = useCollection("/events");
  const { items: teams } = useCollection("/teams");
  const settings = useSettings();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detailId, setDetailId] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [invite, setInvite] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get("/persons-enriched"); setRows(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const companyOpts = companies.map((c) => ({ value: c.id, label: c.nome }));
  const personFields = [
    { name: "nome", label: "Nome", required: true }, { name: "cognome", label: "Cognome" },
    { name: "ruolo", label: "Qualifica" }, { name: "email", label: "Email", type: "email" },
    { name: "email_secondaria", label: "Email secondaria", type: "email" }, { name: "cellulare", label: "Cellulare", type: "tel" },
    { name: "telefono", label: "Telefono", type: "tel" }, { name: "azienda_id", label: "Azienda principale", type: "select", options: companyOpts },
    { name: "data_nascita", label: "Data di nascita", type: "date" }, { name: "linkedin", label: "LinkedIn" },
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
  const personOpts = rows.map((p) => ({ value: p.id, label: `${p.nome} ${p.cognome || ""}`.trim() }));
  const eventOpts = events.map((e) => ({ value: e.id, label: e.nome }));
  const teamOpts = teams.map((t) => ({ value: t.id, label: t.nome }));
  const areaOpts = toOptions(settings?.aree_operative);
  const ruoloOpts = toOptions(settings?.ruoli_staff);
  const pName = (id) => { const p = rows.find((x) => x.id === id); return p ? `${p.nome} ${p.cognome || ""}`.trim() : "—"; };
  const eName = (id) => events.find((e) => e.id === id)?.nome || "—";
  const tName = (id) => teams.find((t) => t.id === id)?.nome || "—";

  const teamFields = [
    { name: "nome", label: "Nome team", required: true, full: true }, { name: "evento_id", label: "Evento", required: true, type: "select", options: eventOpts },
    { name: "area", label: "Area", type: "select", options: areaOpts }, { name: "responsabile_id", label: "Team Leader", type: "select", options: personOpts },
    { name: "luogo_operativo", label: "Luogo operativo" }, { name: "punto_ritrovo", label: "Punto di ritrovo" },
    { name: "descrizione", label: "Descrizione", type: "textarea", full: true },
  ];
  const teamCols = [
    { key: "nome", label: "Team", render: (r) => <span className="font-medium text-slate-800">{r.nome}</span> },
    { key: "evento_id", label: "Evento", render: (r) => eName(r.evento_id) }, { key: "area", label: "Area" },
    { key: "responsabile_id", label: "Team Leader", render: (r) => r.responsabile_id ? pName(r.responsabile_id) : <StatusBadge color="orange">Da assegnare</StatusBadge> },
    { key: "luogo_operativo", label: "Luogo" },
  ];
  const shiftFields = [
    { name: "evento_id", label: "Evento", required: true, type: "select", options: eventOpts }, { name: "persona_id", label: "Persona (vuoto = scoperto)", type: "select", options: personOpts },
    { name: "data", label: "Data", type: "date" }, { name: "ora_inizio", label: "Ora inizio", type: "time" }, { name: "ora_fine", label: "Ora fine", type: "time" },
    { name: "area", label: "Area", type: "select", options: areaOpts }, { name: "ruolo", label: "Ruolo", type: "select", options: ruoloOpts },
    { name: "team_id", label: "Team", type: "select", options: teamOpts }, { name: "luogo", label: "Luogo" }, { name: "punto_ritrovo", label: "Punto di ritrovo" },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const shiftCols = [
    { key: "data", label: "Data", render: (r) => <span className="font-medium text-slate-800">{r.data}</span> },
    { key: "ora", label: "Orario", render: (r) => `${r.ora_inizio || ""}–${r.ora_fine || ""}` },
    { key: "persona_id", label: "Persona", render: (r) => r.persona_id ? pName(r.persona_id) : <StatusBadge color="red">Scoperto</StatusBadge> },
    { key: "area", label: "Area" }, { key: "team_id", label: "Team", render: (r) => r.team_id ? tName(r.team_id) : "—" },
  ];

  return (
    <div className="animate-fade-up">
      <PageHeader title="Persone" subtitle="Anagrafica unica: referenti, staff, volontari, team e turni"
        action={<PrimaryButton onClick={() => { setEditing(null); setFormOpen(true); }} data-testid="add-person-button"><Plus className="w-4 h-4 mr-1.5" />Aggiungi persona</PrimaryButton>} />
      <Tabs defaultValue="tutte">
        <TabsList className="mb-4 flex-wrap h-auto">
          <TabsTrigger value="tutte" data-testid="tab-tutte">Tutte</TabsTrigger>
          <TabsTrigger value="referenti" data-testid="tab-referenti">Referenti</TabsTrigger>
          <TabsTrigger value="staff" data-testid="tab-staff">Staff</TabsTrigger>
          <TabsTrigger value="volontari" data-testid="tab-volontari">Volontari</TabsTrigger>
          <TabsTrigger value="team" data-testid="tab-team">Team</TabsTrigger>
          <TabsTrigger value="turni" data-testid="tab-turni">Turni</TabsTrigger>
        </TabsList>
        {["tutte", "referenti", "staff", "volontari"].map((t) => (
          <TabsContent key={t} value={t}>
            <PeopleTable rows={rows} loading={loading} tab={t} onOpen={(r) => setDetailId(r.id)}
              onEdit={(r) => { setEditing(r); setFormOpen(true); }} onInvite={(r) => setInvite(r)} onDelete={delPerson} />
          </TabsContent>
        ))}
        <TabsContent value="team">
          <EntityManager title="Team" subtitle="Squadre operative per evento con Team Leader" endpoint="/teams"
            fields={teamFields} columns={teamCols} entityLabel="team" testid="team" searchKeys={["nome", "area"]} filters={[{ name: "evento_id", label: "Evento", options: eventOpts }]} />
        </TabsContent>
        <TabsContent value="turni">
          <EntityManager title="Turni" subtitle="Turni operativi; lascia la persona vuota per un turno scoperto" endpoint="/shifts"
            fields={shiftFields} columns={shiftCols} entityLabel="turno" testid="shift" searchKeys={["ruolo", "area", "luogo"]}
            filters={[{ name: "evento_id", label: "Evento", options: eventOpts }, { name: "area", label: "Area", options: areaOpts }, { name: "team_id", label: "Team", options: teamOpts }]} />
        </TabsContent>
      </Tabs>

      <EntityDialog open={formOpen} onOpenChange={setFormOpen} title={editing ? "Modifica persona" : "Nuova persona"}
        fields={personFields} initial={editing} onSubmit={submitPerson} testid="person" />
      {detailId && <PersonDetailDialog personId={detailId} open={!!detailId} onOpenChange={(o) => !o && setDetailId(null)}
        events={events} teams={teams} settings={settings} onChanged={reload}
        onEdit={(p) => { setDetailId(null); setEditing(p); setFormOpen(true); }} onInvite={(p) => { setDetailId(null); setInvite(p); }} />}
      {invite && <InviteDialog person={invite} open={!!invite} onOpenChange={(o) => !o && setInvite(null)} onDone={reload} />}
    </div>
  );
}
