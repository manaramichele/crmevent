import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, fileUrl, calcAge } from "@/components/crm";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import TeamSelect from "@/components/TeamSelect";
import { Pencil, UserPlus, Trash2, CalendarDays, Users, Clock, ListChecks, IdCard, KeyRound, Plus, X, Save, AlertTriangle, Crown } from "lucide-react";
import { useTeams } from "@/lib/teamsStore";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { toast } from "sonner";

const CAT = { referente: "Referente", staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario", team: "Team" };
const INV = { non_invitato: "gray", invito_inviato: "orange", account_attivato: "green", accesso_disabilitato: "red" };
const INV_LABEL = { non_invitato: "Non invitato", invito_inviato: "Invito inviato", account_attivato: "Account attivo", accesso_disabilitato: "Accesso disabilitato" };

const Row = ({ label, value }) => value ? (
  <div className="flex flex-col"><span className="text-xs text-slate-400">{label}</span><span className="text-sm text-slate-800">{value}</span></div>
) : null;

function Initials({ p }) {
  const t = `${(p?.nome || "?")[0] || ""}${(p?.cognome || "")[0] || ""}`.toUpperCase();
  return p?.foto_url
    ? <img src={fileUrl(p.foto_url)} alt="" className="w-14 h-14 rounded-full object-cover" />
    : <div className="w-14 h-14 rounded-full bg-tiffany-light text-tiffany-fg flex items-center justify-center font-bold text-lg">{t}</div>;
}

export default function PersonDetailDialog({ personId, open, onOpenChange, events = [], settings, onChanged, onInvite }) {
  const { teams } = useTeams();
  const [d, setD] = useState(null);
  const [pf, setPf] = useState({ categoria: "volontario", stato: "da_contattare" });
  const [editMode, setEditMode] = useState(false);
  const [edit, setEdit] = useState(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [conflict, setConflict] = useState(null);
  const [shiftForm, setShiftForm] = useState(null);
  const [savingShift, setSavingShift] = useState(false);

  const load = useCallback(async () => {
    if (!personId) return;
    try { const { data } = await api.get(`/persons/${personId}/detail`); setD(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [personId]);
  useEffect(() => {
    if (open) { setD(null); setEditMode(false); setEdit(null); setConflict(null); setShiftForm(null); setPf({ categoria: "volontario", stato: "da_contattare" }); load(); }
  }, [open, load]);

  const p = d?.person;

  // --- Eventi / Ruoli / Team: mutazioni relazionali immediate sugli endpoint esistenti (/staff). ---
  const addPresence = async () => {
    if (!pf.evento_id) { toast.error("Seleziona un evento"); return; }
    if ((d?.events || []).some((x) => x.presence.evento_id === pf.evento_id)) {
      toast.error("La persona è già associata a questo evento"); return;
    }
    try {
      await api.post("/staff", { ...pf, persona_id: personId });
      toast.success("Persona associata all'evento");
      setPf({ categoria: "volontario", stato: "da_contattare" });
      await load(); onChanged && onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const delPresence = async (id) => {
    try { await api.delete(`/staff/${id}`); await load(); onChanged && onChanged(); toast.success("Associazione rimossa"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const savePresence = async (pres, patch) => {
    try {
      await api.put(`/staff/${pres.id}`, { evento_id: pres.evento_id, persona_id: personId, categoria: pres.categoria, ruolo: pres.ruolo, team_id: pres.team_id, area: pres.area, stato: pres.stato, ...patch });
      toast.success("Dati evento aggiornati"); await load(); onChanged && onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  // --- Turni: stesse strutture esistenti (/shifts), nessun sistema parallelo. ---
  const newShift = () => setShiftForm({ evento_id: (d?.events?.[0]?.presence?.evento_id) || "", data: "", ora_inizio: "", ora_fine: "", area: "", ruolo: "", team_id: "", luogo: "", note: "" });
  const editShift = (s) => setShiftForm({ id: s.id, evento_id: s.evento_id || "", data: s.data || "", ora_inizio: s.ora_inizio || "", ora_fine: s.ora_fine || "", area: s.area || "", ruolo: s.ruolo || "", team_id: s.team_id || "", luogo: s.luogo || "", note: s.note || "" });
  const saveShift = async () => {
    if (!shiftForm.evento_id) { toast.error("Seleziona un evento per il turno"); return; }
    setSavingShift(true);
    try {
      const payload = { evento_id: shiftForm.evento_id, persona_id: personId, data: shiftForm.data || "",
        ora_inizio: shiftForm.ora_inizio || "", ora_fine: shiftForm.ora_fine || "", area: shiftForm.area || "",
        ruolo: shiftForm.ruolo || "", team_id: shiftForm.team_id || "", luogo: shiftForm.luogo || "", note: shiftForm.note || "" };
      if (shiftForm.id) await api.put(`/shifts/${shiftForm.id}`, payload);
      else await api.post("/shifts", payload);
      toast.success(shiftForm.id ? "Turno aggiornato" : "Turno aggiunto");
      setShiftForm(null); await load(); onChanged && onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSavingShift(false); }
  };
  const delShift = async (id) => {
    try { await api.delete(`/shifts/${id}`); await load(); onChanged && onChanged(); toast.success("Turno rimosso"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  // --- Modalità modifica (unica finestra, tab sempre visibili) ---
  const startEdit = () => {
    setConflict(null);
    setEdit({ nome: p.nome || "", cognome: p.cognome || "", email: p.email || "", cellulare: p.cellulare || "", data_nascita: p.data_nascita || "", codice_fiscale: p.codice_fiscale || "", note: p.note || "" });
    setEditMode(true);
  };
  const cancelEdit = () => { setEditMode(false); setEdit(null); setConflict(null); setShiftForm(null); };
  const saveEdit = async () => {
    if (!edit.nome.trim()) { toast.error("Il nome è obbligatorio"); return; }
    if (edit.cellulare && !isValidPhoneNumber(edit.cellulare)) { toast.error("Numero di cellulare non valido"); return; }
    setSavingEdit(true);
    try {
      const conflicts = [];
      const newEmail = edit.email.trim();
      const emailChanged = newEmail && newEmail.toLowerCase() !== (p.email || "").toLowerCase();
      const phoneChanged = edit.cellulare && edit.cellulare !== (p.cellulare || "");
      const [emailRes, phoneRes] = await Promise.all([
        emailChanged ? api.post("/persons-match", { email: newEmail }) : Promise.resolve(null),
        phoneChanged ? api.post("/persons-match", { cellulare: edit.cellulare }) : Promise.resolve(null),
      ]);
      if (emailRes && (emailRes.data.matches || []).some((m) => m.id !== personId)) conflicts.push("Email");
      if (phoneRes && (phoneRes.data.matches || []).some((m) => m.id !== personId)) conflicts.push("Cellulare");
      if (conflicts.length) { setConflict(conflicts); setSavingEdit(false); return; }
      await api.put(`/persons/${personId}`, {
        nome: edit.nome.trim(), cognome: edit.cognome.trim(), email: newEmail,
        cellulare: edit.cellulare || "", data_nascita: edit.data_nascita || "",
        codice_fiscale: edit.codice_fiscale.trim(), note: edit.note,
      });
      toast.success("Anagrafica aggiornata");
      setEditMode(false); setEdit(null); setConflict(null);
      await load(); onChanged && onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSavingEdit(false); }
  };

  const eName = (id) => events.find((e) => e.id === id)?.nome || "—";
  const age = edit ? calcAge(edit.data_nascita) : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="person-detail-dialog">
        <DialogHeader><DialogTitle className="sr-only">Scheda persona</DialogTitle><DialogDescription className="sr-only">Dettaglio e gestione completa della persona</DialogDescription></DialogHeader>
        {!p ? <div className="py-10 text-center text-slate-400">Caricamento...</div> : (
          <>
            <div className="flex items-start gap-4">
              <Initials p={p} />
              <div className="flex-1 min-w-0">
                <h2 className="text-xl font-bold text-slate-900 font-display flex flex-wrap items-center gap-x-2 gap-y-1" data-testid="person-detail-name"><span>{p.cognome} {p.nome}</span>
                  {teams.some((t) => t.responsabile_id === p.id) && <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200 px-2 py-0.5 text-xs font-semibold font-sans" data-testid="person-detail-leader"><Crown className="w-3.5 h-3.5 text-[#D4AF37]" />Team Leader</span>}</h2>
                <p className="text-sm text-slate-500">{p.ruolo || "—"}</p>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {d.companies.length > 0 && <StatusBadge color="tiffany">Referente</StatusBadge>}
                  {d.events.some((x) => ["staff", "collaboratore"].includes(x.presence?.categoria)) && <StatusBadge color="blue">Staff</StatusBadge>}
                  {d.events.some((x) => x.presence?.categoria === "volontario") && <StatusBadge color="green">Volontario</StatusBadge>}
                  {editMode && <StatusBadge color="orange">Modalità modifica</StatusBadge>}
                </div>
              </div>
              {!editMode ? (
                <div className="flex gap-1.5">
                  <Button variant="outline" size="sm" onClick={startEdit} data-testid="person-detail-edit"><Pencil className="w-4 h-4 mr-1" />Modifica</Button>
                </div>
              ) : (
                <div className="flex gap-1.5">
                  <Button variant="outline" size="sm" onClick={cancelEdit} data-testid="person-detail-cancel"><X className="w-4 h-4 mr-1" />Annulla</Button>
                  <Button size="sm" onClick={saveEdit} disabled={savingEdit} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="person-detail-save"><Save className="w-4 h-4 mr-1" />{savingEdit ? "Salvataggio..." : "Salva"}</Button>
                </div>
              )}
            </div>

            {editMode && <p className="mt-3 text-xs text-slate-500">Puoi modificare Anagrafica, Eventi, Ruoli, Team e Turni dai rispettivi tab. Le associazioni vengono applicate subito; i dati anagrafici si salvano con «Salva». Passando tra i tab non perdi le modifiche.</p>}

            <Tabs defaultValue="anagrafica" className="mt-4">
              <TabsList className="flex-wrap h-auto">
                <TabsTrigger value="anagrafica" data-testid="ptab-anagrafica"><IdCard className="w-4 h-4 mr-1" />Anagrafica</TabsTrigger>
                <TabsTrigger value="eventi" data-testid="ptab-eventi"><CalendarDays className="w-4 h-4 mr-1" />Eventi</TabsTrigger>
                <TabsTrigger value="ruoli" data-testid="ptab-ruoli"><ListChecks className="w-4 h-4 mr-1" />Ruoli</TabsTrigger>
                <TabsTrigger value="team" data-testid="ptab-team"><Users className="w-4 h-4 mr-1" />Team</TabsTrigger>
                <TabsTrigger value="turni" data-testid="ptab-turni"><Clock className="w-4 h-4 mr-1" />Turni</TabsTrigger>
                <TabsTrigger value="accesso" data-testid="ptab-accesso"><KeyRound className="w-4 h-4 mr-1" />Accesso</TabsTrigger>
              </TabsList>

              {/* ---------------- Anagrafica ---------------- */}
              <TabsContent value="anagrafica" className="pt-2">
                {editMode && edit ? (
                  <div className="space-y-4" data-testid="person-edit-form">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-1.5"><Label className="text-xs font-medium text-slate-600">Nome *</Label>
                        <Input value={edit.nome} onChange={(e) => setEdit((s) => ({ ...s, nome: e.target.value }))} data-testid="person-edit-nome" /></div>
                      <div className="space-y-1.5"><Label className="text-xs font-medium text-slate-600">Cognome</Label>
                        <Input value={edit.cognome} onChange={(e) => setEdit((s) => ({ ...s, cognome: e.target.value }))} data-testid="person-edit-cognome" /></div>
                      <div className="space-y-1.5"><Label className="text-xs font-medium text-slate-600">Email</Label>
                        <Input type="email" value={edit.email} onChange={(e) => setEdit((s) => ({ ...s, email: e.target.value }))} data-testid="person-edit-email" /></div>
                      <div className="space-y-1.5"><Label className="text-xs font-medium text-slate-600">Cellulare</Label>
                        <PhoneInput international defaultCountry="IT" value={edit.cellulare || undefined} onChange={(v) => setEdit((s) => ({ ...s, cellulare: v || "" }))} className="phone-input" numberInputProps={{ "data-testid": "person-edit-cellulare-input" }} data-testid="person-edit-cellulare" /></div>
                      <div className="space-y-1.5"><Label className="text-xs font-medium text-slate-600">Data di nascita</Label>
                        <Input type="date" value={edit.data_nascita || ""} onChange={(e) => setEdit((s) => ({ ...s, data_nascita: e.target.value }))} data-testid="person-edit-data-nascita" /></div>
                      <div className="space-y-1.5"><Label className="text-xs font-medium text-slate-600">Età (automatica)</Label>
                        <Input value={age != null ? `${age} anni` : "—"} disabled readOnly data-testid="person-edit-eta" className="bg-slate-50 text-slate-500" /></div>
                      <div className="space-y-1.5 sm:col-span-2"><Label className="text-xs font-medium text-slate-600">Codice Fiscale</Label>
                        <Input value={edit.codice_fiscale} onChange={(e) => setEdit((s) => ({ ...s, codice_fiscale: e.target.value.toUpperCase() }))} className="font-mono" data-testid="person-edit-codice-fiscale" /></div>
                      <div className="space-y-1.5 sm:col-span-2"><Label className="text-xs font-medium text-slate-600">Note</Label>
                        <Textarea rows={3} value={edit.note || ""} onChange={(e) => setEdit((s) => ({ ...s, note: e.target.value }))} data-testid="person-edit-note" /></div>
                    </div>
                    {conflict && (
                      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 flex items-start gap-2" data-testid="person-edit-conflict">
                        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                        <span>{conflict.join(" e ")} {conflict.length > 1 ? "appartengono" : "appartiene"} già a un'altra anagrafica di questa organizzazione. Modifica il valore per evitare un duplicato.</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                      <Row label="Email" value={p.email} /><Row label="Email secondaria" value={p.email_secondaria} />
                      <Row label="Cellulare" value={p.cellulare} /><Row label="Telefono" value={p.telefono} />
                      <Row label="Data di nascita" value={p.data_nascita} /><Row label="Età" value={calcAge(p.data_nascita) != null ? `${calcAge(p.data_nascita)} anni` : null} />
                      <Row label="Codice Fiscale" value={p.codice_fiscale ? <span className="font-mono">{p.codice_fiscale}</span> : null} />
                      <Row label="LinkedIn" value={p.linkedin} />
                      <Row label="Indirizzo" value={p.indirizzo} /><Row label="CAP" value={p.cap} /><Row label="Città" value={p.citta} />
                      <Row label="Provincia" value={p.provincia} /><Row label="Regione" value={p.regione} /><Row label="Nazione" value={p.nazione} />
                    </div>
                    {p.note && <div className="mt-3 text-sm text-slate-600"><span className="text-xs text-slate-400 block">Note</span>{p.note}</div>}
                    {(p.esigenze_alimentari && p.esigenze_alimentari.length > 0) || p.esigenze_note ? (
                      <div className="mt-3"><span className="text-xs text-slate-400 block mb-1">Esigenze alimentari</span>
                        <span className="flex flex-wrap gap-1.5">{(p.esigenze_alimentari || []).map((e) => <StatusBadge key={e} color="blue">{e}</StatusBadge>)}</span>
                        {p.esigenze_note && <p className="text-sm text-slate-600 mt-1">{p.esigenze_note}</p>}</div>
                    ) : null}
                  </>
                )}
              </TabsContent>

              {/* ---------------- Eventi ---------------- */}
              <TabsContent value="eventi" className="pt-2 space-y-3">
                {editMode && (
                  <div className="border border-dashed border-slate-300 rounded-lg p-3 bg-slate-50/50">
                    <p className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1"><Plus className="w-3.5 h-3.5" />Associa a un evento</p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <Select value={pf.evento_id || ""} onValueChange={(v) => setPf((f) => ({ ...f, evento_id: v }))}>
                        <SelectTrigger data-testid="presence-event"><SelectValue placeholder="Evento" /></SelectTrigger>
                        <SelectContent>{events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}</SelectContent></Select>
                      <Select value={pf.categoria} onValueChange={(v) => setPf((f) => ({ ...f, categoria: v }))}>
                        <SelectTrigger data-testid="presence-cat"><SelectValue placeholder="Ruolo evento" /></SelectTrigger>
                        <SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem></SelectContent></Select>
                      <TeamSelect value={pf.team_id || ""} eventoId={pf.evento_id} onChange={(v) => setPf((f) => ({ ...f, team_id: v }))} testid="presence-team" noEventHint="Seleziona prima l'Evento." />
                      <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold sm:col-span-3" onClick={addPresence} data-testid="presence-add">Associa</Button>
                    </div>
                  </div>
                )}
                {d.events.length === 0 ? <p className="text-sm text-slate-400 py-2">Nessun evento associato.</p> :
                  d.events.map((x) => (
                    <div key={x.presence.id} className="border border-slate-200 rounded-lg px-4 py-3" data-testid={`presence-row-${x.presence.id}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="font-medium text-slate-800">{x.event?.nome || "—"}</div>
                        {editMode && <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-500" onClick={() => delPresence(x.presence.id)} data-testid={`presence-del-${x.presence.id}`}><Trash2 className="w-4 h-4" /></Button>}
                      </div>
                      {editMode ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          <Select value={["staff", "volontario"].includes(x.presence.categoria) ? x.presence.categoria : ""} onValueChange={(v) => (v === "none" ? delPresence(x.presence.id) : savePresence(x.presence, { categoria: v }))}>
                            <SelectTrigger data-testid={`presence-edit-cat-${x.presence.id}`}><SelectValue placeholder="Ruolo evento" /></SelectTrigger>
                            <SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem><SelectItem value="none">Nessun ruolo (rimuovi)</SelectItem></SelectContent></Select>
                          <TeamSelect value={x.presence.team_id || ""} eventoId={x.presence.evento_id} onChange={(v) => savePresence(x.presence, { team_id: v })} testid={`presence-edit-team-${x.presence.id}`} />
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-1.5 text-sm">
                          <StatusBadge color="tiffany">{CAT[x.presence.categoria] || x.presence.categoria}</StatusBadge>
                          {x.presence.team_id && <StatusBadge color="gray">Team: {d.teams.find((t) => t.id === x.presence.team_id)?.nome || "—"}</StatusBadge>}
                        </div>
                      )}
                    </div>
                  ))}
              </TabsContent>

              {/* ---------------- Ruoli ---------------- */}
              <TabsContent value="ruoli" className="pt-2 space-y-2">
                {d.events.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun ruolo assegnato.</p> :
                  d.events.map((x) => (
                    <div key={x.presence.id} className="border border-slate-200 rounded-lg px-4 py-2.5" data-testid={`role-row-${x.presence.id}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm text-slate-700 font-medium">{x.event?.nome}</span>
                        {editMode ? (
                          <div className="flex items-center gap-2">
                            <Select value={["staff", "volontario"].includes(x.presence.categoria) ? x.presence.categoria : ""} onValueChange={(v) => savePresence(x.presence, { categoria: v })}>
                              <SelectTrigger className="w-36" data-testid={`role-cat-${x.presence.id}`}><SelectValue placeholder="Ruolo" /></SelectTrigger>
                              <SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem></SelectContent></Select>
                            <Input defaultValue={x.presence.ruolo || ""} placeholder="Mansione (opz.)" className="w-44"
                              onBlur={(e) => e.target.value !== (x.presence.ruolo || "") && savePresence(x.presence, { ruolo: e.target.value })}
                              data-testid={`role-text-${x.presence.id}`} />
                          </div>
                        ) : (
                          <span className="flex gap-1.5"><StatusBadge color="tiffany">{CAT[x.presence.categoria] || x.presence.categoria}</StatusBadge>{x.presence.ruolo && <StatusBadge color="gray">{x.presence.ruolo}</StatusBadge>}</span>
                        )}
                      </div>
                    </div>
                  ))}
                {editMode && <p className="text-xs text-slate-400">Puoi assegnare ruoli diversi (Staff/Volontario) per ciascun evento. Associa nuovi eventi dal tab Eventi.</p>}
              </TabsContent>

              {/* ---------------- Team ---------------- */}
              <TabsContent value="team" className="pt-2 space-y-2">
                {editMode ? (
                  d.events.length === 0 ? <p className="text-sm text-slate-400 py-4">Associa prima la persona a un evento (tab Eventi) per assegnarla a un Team.</p> :
                    d.events.map((x) => (
                      <div key={x.presence.id} className="border border-slate-200 rounded-lg px-4 py-3" data-testid={`team-row-${x.presence.id}`}>
                        <div className="text-sm font-medium text-slate-800 mb-1.5">{x.event?.nome}{x.presence.team_id && d.teams.find((t) => t.id === x.presence.team_id)?.responsabile_id === personId ? " · Team Leader" : ""}</div>
                        <TeamSelect value={x.presence.team_id || ""} eventoId={x.presence.evento_id} onChange={(v) => savePresence(x.presence, { team_id: v })} testid={`team-assign-${x.presence.id}`} />
                      </div>
                    ))
                ) : (
                  d.teams.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun team.</p> :
                    d.teams.map((t) => (
                      <div key={t.id} className="border border-slate-200 rounded-lg px-4 py-3">
                        <div className="font-medium text-slate-800">{t.nome}</div>
                        <div className="text-xs text-slate-500">{eName(t.evento_id)} · {t.area || "—"}{t.responsabile_id === personId ? " · Team Leader" : ""}</div>
                      </div>
                    ))
                )}
              </TabsContent>

              {/* ---------------- Turni ---------------- */}
              <TabsContent value="turni" className="pt-2 space-y-2">
                {editMode && (
                  <div className="flex justify-end">
                    {!shiftForm && <Button size="sm" variant="outline" onClick={newShift} data-testid="shift-add-btn"><Plus className="w-4 h-4 mr-1" />Aggiungi turno</Button>}
                  </div>
                )}
                {editMode && shiftForm && (
                  <div className="border border-dashed border-slate-300 rounded-lg p-3 bg-slate-50/50 space-y-2" data-testid="shift-form">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      <div className="sm:col-span-3"><Label className="text-xs text-slate-600">Evento *</Label>
                        <Select value={shiftForm.evento_id || ""} onValueChange={(v) => setShiftForm((f) => ({ ...f, evento_id: v, team_id: "" }))}>
                          <SelectTrigger data-testid="shift-event"><SelectValue placeholder="Evento" /></SelectTrigger>
                          <SelectContent>{events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}</SelectContent></Select></div>
                      <div><Label className="text-xs text-slate-600">Data</Label><Input type="date" value={shiftForm.data} onChange={(e) => setShiftForm((f) => ({ ...f, data: e.target.value }))} data-testid="shift-data" /></div>
                      <div><Label className="text-xs text-slate-600">Ora inizio</Label><Input type="time" value={shiftForm.ora_inizio} onChange={(e) => setShiftForm((f) => ({ ...f, ora_inizio: e.target.value }))} data-testid="shift-ora-inizio" /></div>
                      <div><Label className="text-xs text-slate-600">Ora fine</Label><Input type="time" value={shiftForm.ora_fine} onChange={(e) => setShiftForm((f) => ({ ...f, ora_fine: e.target.value }))} data-testid="shift-ora-fine" /></div>
                      <div><Label className="text-xs text-slate-600">Area</Label><Input value={shiftForm.area} onChange={(e) => setShiftForm((f) => ({ ...f, area: e.target.value }))} data-testid="shift-area" /></div>
                      <div><Label className="text-xs text-slate-600">Ruolo</Label><Input value={shiftForm.ruolo} onChange={(e) => setShiftForm((f) => ({ ...f, ruolo: e.target.value }))} data-testid="shift-ruolo" /></div>
                      <div><Label className="text-xs text-slate-600">Luogo</Label><Input value={shiftForm.luogo} onChange={(e) => setShiftForm((f) => ({ ...f, luogo: e.target.value }))} data-testid="shift-luogo" /></div>
                      <div className="sm:col-span-3"><Label className="text-xs text-slate-600">Team</Label>
                        <TeamSelect value={shiftForm.team_id || ""} eventoId={shiftForm.evento_id} onChange={(v) => setShiftForm((f) => ({ ...f, team_id: v }))} testid="shift-team" /></div>
                      <div className="sm:col-span-3"><Label className="text-xs text-slate-600">Note</Label><Textarea rows={2} value={shiftForm.note} onChange={(e) => setShiftForm((f) => ({ ...f, note: e.target.value }))} data-testid="shift-note" /></div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <Button variant="outline" size="sm" onClick={() => setShiftForm(null)} data-testid="shift-cancel"><X className="w-4 h-4 mr-1" />Annulla</Button>
                      <Button size="sm" onClick={saveShift} disabled={savingShift} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="shift-save"><Save className="w-4 h-4 mr-1" />{savingShift ? "Salvataggio..." : "Salva turno"}</Button>
                    </div>
                  </div>
                )}
                {d.shifts.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun turno assegnato.</p> :
                  d.shifts.map((s) => (
                    <div key={s.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5" data-testid={`shift-row-${s.id}`}>
                      <div className="min-w-0">
                        <span className="text-sm text-slate-700">{s.data || "—"} · {s.ora_inizio || "--"}–{s.ora_fine || "--"}</span>
                        <div className="text-xs text-slate-500">{eName(s.evento_id)} · {s.luogo || s.area || "—"}</div>
                      </div>
                      {editMode && (
                        <div className="flex items-center gap-1 shrink-0">
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-tiffany-fg" onClick={() => editShift(s)} data-testid={`shift-edit-${s.id}`}><Pencil className="w-4 h-4" /></Button>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-500" onClick={() => delShift(s.id)} data-testid={`shift-del-${s.id}`}><Trash2 className="w-4 h-4" /></Button>
                        </div>
                      )}
                    </div>
                  ))}
              </TabsContent>

              {/* ---------------- Accesso ---------------- */}
              <TabsContent value="accesso" className="pt-2">
                <div className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-4">
                  <div><div className="text-sm text-slate-500 mb-1">Stato account <strong className="font-semibold text-slate-700">CRMEvent</strong></div>
                    <StatusBadge color={INV[p.invite_status || "non_invitato"]}>{INV_LABEL[p.invite_status || "non_invitato"]}</StatusBadge>
                    {p.invite_status === "account_attivato" && (
                      <div className="text-xs text-slate-500 mt-1.5" data-testid="person-invite-accepted">
                        Invito: <span className="font-semibold text-emerald-600">Accettato</span>
                        {p.invite_accepted_at ? ` · ${new Date(p.invite_accepted_at).toLocaleDateString("it-IT")}` : ""}
                      </div>
                    )}</div>
                  {onInvite && <Button variant="outline" onClick={() => onInvite(p)} disabled={!p.email} data-testid="person-detail-invite"><UserPlus className="w-4 h-4 mr-1" />Gestisci accesso</Button>}
                </div>
                {p.last_invite_at && <p className="text-xs text-slate-500 mt-2" data-testid="person-detail-last-invite">Ultimo invito: {new Date(p.last_invite_at).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</p>}
                {!p.email && <p className="text-xs text-amber-600 mt-2">Aggiungi un'email per poter invitare questa persona.</p>}
              </TabsContent>
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
