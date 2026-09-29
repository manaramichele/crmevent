import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, toOptions, fileUrl, calcAge } from "@/components/crm";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Pencil, UserPlus, Trash2, Building2, CalendarDays, Users, Clock, ListChecks, IdCard, KeyRound, Plus } from "lucide-react";
import { toast } from "sonner";

const CAT = { referente: "Referente", staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario", team: "Team" };
const STATO = { da_contattare: "Da contattare", disponibilita_richiesta: "Disponibilità richiesta", disponibile: "Disponibile", da_riconfermare: "Da riconfermare", confermato: "Confermato", non_disponibile: "Non disponibile", rinunciato: "Rinunciato" };
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

export default function PersonDetailDialog({ personId, open, onOpenChange, events = [], teams = [], settings, onChanged, onEdit, onInvite }) {
  const [d, setD] = useState(null);
  const [pf, setPf] = useState({ categoria: "volontario", stato: "da_contattare" });

  const load = useCallback(async () => {
    if (!personId) return;
    try { const { data } = await api.get(`/persons/${personId}/detail`); setD(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [personId]);
  useEffect(() => { if (open) { setD(null); load(); } }, [open, load]);

  const addPresence = async () => {
    if (!pf.evento_id) { toast.error("Seleziona un evento"); return; }
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
      toast.success("Ruolo evento aggiornato"); await load(); onChanged && onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const p = d?.person;
  const eName = (id) => events.find((e) => e.id === id)?.nome || "—";
  const areaOpts = toOptions(settings?.aree_operative);
  const ruoloOpts = toOptions(settings?.ruoli_staff);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="person-detail-dialog">
        <DialogHeader><DialogTitle className="sr-only">Scheda persona</DialogTitle><DialogDescription className="sr-only">Dettaglio anagrafica persona</DialogDescription></DialogHeader>
        {!p ? <div className="py-10 text-center text-slate-400">Caricamento...</div> : (
          <>
            <div className="flex items-start gap-4">
              <Initials p={p} />
              <div className="flex-1 min-w-0">
                <h2 className="text-xl font-bold text-slate-900 font-display" data-testid="person-detail-name">{p.nome} {p.cognome}</h2>
                <p className="text-sm text-slate-500">{p.ruolo || "—"}</p>
                <div className="flex flex-wrap gap-1.5 mt-1.5">
                  {d.companies.length > 0 && <StatusBadge color="tiffany">Referente</StatusBadge>}
                  {d.events.some((x) => ["staff", "collaboratore"].includes(x.presence?.categoria)) && <StatusBadge color="blue">Staff</StatusBadge>}
                  {d.events.some((x) => x.presence?.categoria === "volontario") && <StatusBadge color="green">Volontario</StatusBadge>}
                </div>
              </div>
              <div className="flex gap-1.5">
                <Button variant="outline" size="sm" onClick={() => onEdit && onEdit(p)} data-testid="person-detail-edit"><Pencil className="w-4 h-4 mr-1" />Modifica</Button>
              </div>
            </div>

            <Tabs defaultValue="anagrafica" className="mt-4">
              <TabsList className="flex-wrap h-auto">
                <TabsTrigger value="anagrafica" data-testid="ptab-anagrafica"><IdCard className="w-4 h-4 mr-1" />Anagrafica</TabsTrigger>
                <TabsTrigger value="aziende" data-testid="ptab-aziende"><Building2 className="w-4 h-4 mr-1" />Aziende</TabsTrigger>
                <TabsTrigger value="eventi" data-testid="ptab-eventi"><CalendarDays className="w-4 h-4 mr-1" />Eventi</TabsTrigger>
                <TabsTrigger value="ruoli" data-testid="ptab-ruoli"><ListChecks className="w-4 h-4 mr-1" />Ruoli</TabsTrigger>
                <TabsTrigger value="team" data-testid="ptab-team"><Users className="w-4 h-4 mr-1" />Team</TabsTrigger>
                <TabsTrigger value="turni" data-testid="ptab-turni"><Clock className="w-4 h-4 mr-1" />Turni</TabsTrigger>
                <TabsTrigger value="attivita" data-testid="ptab-attivita">Attività</TabsTrigger>
                <TabsTrigger value="accesso" data-testid="ptab-accesso"><KeyRound className="w-4 h-4 mr-1" />Accesso</TabsTrigger>
              </TabsList>

              <TabsContent value="anagrafica" className="pt-2">
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
              </TabsContent>

              <TabsContent value="aziende" className="pt-2 space-y-2">
                {d.companies.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessuna azienda collegata.</p> :
                  d.companies.map((c, i) => (
                    <div key={i} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-3">
                      <div><div className="font-medium text-slate-800">{c.company.nome}</div>
                        <div className="text-xs text-slate-500">{c.relation.qualifica || c.relation.ruolo || c.company.settore || "—"}</div></div>
                      {c.relation.referente_principale && <StatusBadge color="tiffany">Referente principale</StatusBadge>}
                    </div>
                  ))}
              </TabsContent>

              <TabsContent value="eventi" className="pt-2 space-y-3">
                <div className="border border-dashed border-slate-300 rounded-lg p-3 bg-slate-50/50">
                  <p className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1"><Plus className="w-3.5 h-3.5" />Associa a un evento</p>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <Select value={pf.evento_id || ""} onValueChange={(v) => setPf((f) => ({ ...f, evento_id: v }))}>
                      <SelectTrigger data-testid="presence-event"><SelectValue placeholder="Evento" /></SelectTrigger>
                      <SelectContent>{events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}</SelectContent></Select>
                    <Select value={pf.categoria} onValueChange={(v) => setPf((f) => ({ ...f, categoria: v }))}>
                      <SelectTrigger data-testid="presence-cat"><SelectValue placeholder="Ruolo evento" /></SelectTrigger>
                      <SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem></SelectContent></Select>
                    <Select value={pf.team_id || ""} onValueChange={(v) => setPf((f) => ({ ...f, team_id: v }))}>
                      <SelectTrigger data-testid="presence-team"><SelectValue placeholder="Team (opzionale)" /></SelectTrigger>
                      <SelectContent>{teams.filter((t) => !pf.evento_id || t.evento_id === pf.evento_id).map((t) => <SelectItem key={t.id} value={t.id}>{t.nome}</SelectItem>)}</SelectContent></Select>
                    <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold sm:col-span-3" onClick={addPresence} data-testid="presence-add">Associa</Button>
                  </div>
                </div>
                {d.events.length === 0 ? <p className="text-sm text-slate-400 py-2">Nessun evento associato.</p> :
                  d.events.map((x) => (
                    <div key={x.presence.id} className="border border-slate-200 rounded-lg px-4 py-3" data-testid={`presence-row-${x.presence.id}`}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="font-medium text-slate-800">{x.event?.nome || "—"}</div>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-500" onClick={() => delPresence(x.presence.id)} data-testid={`presence-del-${x.presence.id}`}><Trash2 className="w-4 h-4" /></Button>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        <Select value={["staff", "volontario"].includes(x.presence.categoria) ? x.presence.categoria : ""} onValueChange={(v) => (v === "none" ? delPresence(x.presence.id) : savePresence(x.presence, { categoria: v }))}>
                          <SelectTrigger data-testid={`presence-edit-cat-${x.presence.id}`}><SelectValue placeholder="Ruolo evento" /></SelectTrigger>
                          <SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="volontario">Volontario</SelectItem><SelectItem value="none">Nessun ruolo (rimuovi)</SelectItem></SelectContent></Select>
                        <Select value={x.presence.team_id || "none"} onValueChange={(v) => savePresence(x.presence, { team_id: v === "none" ? "" : v })}>
                          <SelectTrigger data-testid={`presence-edit-team-${x.presence.id}`}><SelectValue placeholder="Team" /></SelectTrigger>
                          <SelectContent><SelectItem value="none">— Nessun team —</SelectItem>{teams.filter((t) => t.evento_id === x.presence.evento_id).map((t) => <SelectItem key={t.id} value={t.id}>{t.nome}</SelectItem>)}</SelectContent></Select>
                      </div>
                    </div>
                  ))}
              </TabsContent>

              <TabsContent value="ruoli" className="pt-2 space-y-2">
                {d.events.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun ruolo assegnato.</p> :
                  d.events.map((x) => (
                    <div key={x.presence.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5">
                      <span className="text-sm text-slate-700">{x.event?.nome}</span>
                      <span className="flex gap-1.5"><StatusBadge color="tiffany">{CAT[x.presence.categoria] || x.presence.categoria}</StatusBadge>{x.presence.ruolo && <StatusBadge color="gray">{x.presence.ruolo}</StatusBadge>}</span>
                    </div>
                  ))}
              </TabsContent>

              <TabsContent value="team" className="pt-2 space-y-2">
                {d.teams.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun team.</p> :
                  d.teams.map((t) => (
                    <div key={t.id} className="border border-slate-200 rounded-lg px-4 py-3">
                      <div className="font-medium text-slate-800">{t.nome}</div>
                      <div className="text-xs text-slate-500">{eName(t.evento_id)} · {t.area || "—"}{t.responsabile_id === personId ? " · Team Leader" : ""}</div>
                    </div>
                  ))}
              </TabsContent>

              <TabsContent value="turni" className="pt-2 space-y-2">
                {d.shifts.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun turno assegnato.</p> :
                  d.shifts.map((s) => (
                    <div key={s.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5">
                      <span className="text-sm text-slate-700">{s.data} · {s.ora_inizio}–{s.ora_fine}</span>
                      <span className="text-xs text-slate-500">{eName(s.evento_id)} · {s.luogo || s.area || "—"}</span>
                    </div>
                  ))}
              </TabsContent>

              <TabsContent value="attivita" className="pt-2 space-y-2">
                {(d.activities.length + d.followups.length) === 0 ? <p className="text-sm text-slate-400 py-4">Nessuna attività.</p> : <>
                  {d.activities.map((a) => (
                    <div key={a.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5">
                      <span className="text-sm text-slate-700">{a.titolo}</span><StatusBadge color="gray">{a.tipo || "attività"}</StatusBadge></div>
                  ))}
                  {d.followups.map((f) => (
                    <div key={f.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5">
                      <span className="text-sm text-slate-700">{f.titolo}</span><StatusBadge color="orange">follow-up {f.scadenza || ""}</StatusBadge></div>
                  ))}
                </>}
              </TabsContent>

              <TabsContent value="accesso" className="pt-2">
                <div className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-4">
                  <div><div className="text-sm text-slate-500 mb-1">Stato account <strong className="font-semibold text-slate-700">CRMEvent</strong></div>
                    <StatusBadge color={INV[p.invite_status || "non_invitato"]}>{INV_LABEL[p.invite_status || "non_invitato"]}</StatusBadge></div>
                  <Button variant="outline" onClick={() => onInvite && onInvite(p)} disabled={!p.email} data-testid="person-detail-invite"><UserPlus className="w-4 h-4 mr-1" />Gestisci accesso</Button>
                </div>
                {!p.email && <p className="text-xs text-amber-600 mt-2">Aggiungi un'email per poter invitare questa persona.</p>}
              </TabsContent>
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
