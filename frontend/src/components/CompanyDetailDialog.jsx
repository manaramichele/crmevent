import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, formatEUR } from "@/components/crm";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Pencil, Plus, Trash2, Building2, Users, CalendarDays, Handshake, ListChecks, BellRing, UserCheck } from "lucide-react";
import { toast } from "sonner";

const emptyRef = { nome: "", cognome: "", ruolo: "", email: "", cellulare: "", linkedin: "", referente_principale: false, note: "" };

const Row = ({ label, value }) => value ? (
  <div className="flex flex-col"><span className="text-xs text-slate-400">{label}</span><span className="text-sm text-slate-800">{value}</span></div>
) : null;

export default function CompanyDetailDialog({ companyId, open, onOpenChange, onChanged, onEdit }) {
  const [d, setD] = useState(null);
  const [adding, setAdding] = useState(false);
  const [ref, setRef] = useState(emptyRef);
  const [matches, setMatches] = useState(null);

  const load = useCallback(async () => {
    if (!companyId) return;
    try { const { data } = await api.get(`/companies/${companyId}/detail`); setD(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [companyId]);
  useEffect(() => { if (open) { setD(null); setAdding(false); setRef(emptyRef); setMatches(null); load(); } }, [open, load]);

  const refresh = async () => { await load(); onChanged && onChanged(); };
  const resetForm = () => { setAdding(false); setRef(emptyRef); setMatches(null); };

  const checkDup = async () => {
    try {
      const { data } = await api.post("/persons-match", { email: ref.email, cellulare: ref.cellulare, nome: ref.nome, cognome: ref.cognome });
      if (data.matches.length === 0) { toast.info("Nessun duplicato trovato"); await createNew(); }
      else setMatches(data.matches);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const createNew = async () => {
    if (!ref.nome) { toast.error("Nome referente obbligatorio"); return; }
    try { await api.post(`/companies/${companyId}/contacts`, ref); toast.success("Referente creato e collegato"); resetForm(); await refresh(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const linkExisting = async (personId) => {
    try { await api.post(`/companies/${companyId}/contacts`, { person_id: personId, ruolo: ref.ruolo, referente_principale: ref.referente_principale, note: ref.note }); toast.success("Persona esistente collegata"); resetForm(); await refresh(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const removeContact = async (rel) => {
    if (!rel.id) { toast.error("Referente legacy: modifica dalla scheda persona"); return; }
    try { await api.delete(`/company-contacts/${rel.id}`); await refresh(); toast.success("Referente scollegato"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const c = d?.company;
  const principale = d?.contacts.find((x) => x.relation.referente_principale);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="company-detail-dialog">
        <DialogHeader><DialogTitle className="sr-only">Scheda azienda</DialogTitle><DialogDescription className="sr-only">Dettaglio anagrafica azienda</DialogDescription></DialogHeader>
        {!c ? <div className="py-10 text-center text-slate-400">Caricamento...</div> : (
          <>
            <div className="flex items-start gap-4">
              <div className="w-14 h-14 rounded-xl bg-tiffany-light text-tiffany-fg flex items-center justify-center"><Building2 className="w-7 h-7" /></div>
              <div className="flex-1 min-w-0">
                <h2 className="text-xl font-bold text-slate-900 font-display" data-testid="company-detail-name">{c.nome}</h2>
                <div className="text-sm text-slate-500 flex flex-wrap gap-x-3 gap-y-0.5">
                  {c.settore && <span>{c.settore}</span>}
                  {principale && <span>· Referente: {principale.person.cognome} {principale.person.nome}</span>}
                  {c.email && <span>· {c.email}</span>}{c.telefono && <span>· {c.telefono}</span>}
                  {c.sito_web && <span>· {c.sito_web}</span>}{c.responsabile_interno && <span>· Resp.: {c.responsabile_interno}</span>}
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => onEdit && onEdit(c)} data-testid="company-detail-edit"><Pencil className="w-4 h-4 mr-1" />Modifica</Button>
            </div>

            <Tabs defaultValue="anagrafica" className="mt-4">
              <TabsList className="flex-wrap h-auto">
                <TabsTrigger value="anagrafica" data-testid="ctab-anagrafica">Anagrafica</TabsTrigger>
                <TabsTrigger value="referenti" data-testid="ctab-referenti"><Users className="w-4 h-4 mr-1" />Referenti</TabsTrigger>
                <TabsTrigger value="eventi" data-testid="ctab-eventi"><CalendarDays className="w-4 h-4 mr-1" />Eventi</TabsTrigger>
                <TabsTrigger value="trattative" data-testid="ctab-trattative"><Handshake className="w-4 h-4 mr-1" />Trattative</TabsTrigger>
                <TabsTrigger value="sponsorship" data-testid="ctab-sponsorship">Sponsorship</TabsTrigger>
                <TabsTrigger value="attivita" data-testid="ctab-attivita"><ListChecks className="w-4 h-4 mr-1" />Attività</TabsTrigger>
                <TabsTrigger value="followup" data-testid="ctab-followup"><BellRing className="w-4 h-4 mr-1" />Follow-up</TabsTrigger>
              </TabsList>

              <TabsContent value="anagrafica" className="pt-2">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  <Row label="Settore" value={c.settore} /><Row label="Tipo" value={c.tipo} /><Row label="Partita IVA" value={c.partita_iva} />
                  <Row label="Email" value={c.email} /><Row label="Telefono" value={c.telefono} /><Row label="Sito web" value={c.sito_web} />
                  <Row label="Indirizzo" value={c.indirizzo} /><Row label="CAP" value={c.cap} /><Row label="Città" value={c.citta} />
                  <Row label="Provincia" value={c.provincia} /><Row label="Regione" value={c.regione} /><Row label="Nazione" value={c.nazione} />
                  <Row label="Responsabile interno" value={c.responsabile_interno} />
                </div>
                {c.note && <div className="mt-3 text-sm text-slate-600"><span className="text-xs text-slate-400 block">Note</span>{c.note}</div>}
              </TabsContent>

              <TabsContent value="referenti" className="pt-2 space-y-2">
                {!adding && <Button variant="outline" size="sm" onClick={() => setAdding(true)} data-testid="add-referente-btn"><Plus className="w-4 h-4 mr-1" />Aggiungi referente</Button>}
                {adding && (
                  <div className="border border-dashed border-slate-300 rounded-lg p-3 bg-slate-50/50 space-y-2" data-testid="referente-form">
                    <div className="grid grid-cols-2 gap-2">
                      <div><Label className="text-xs">Nome*</Label><Input value={ref.nome} onChange={(e) => setRef({ ...ref, nome: e.target.value })} data-testid="ref-nome" /></div>
                      <div><Label className="text-xs">Cognome</Label><Input value={ref.cognome} onChange={(e) => setRef({ ...ref, cognome: e.target.value })} data-testid="ref-cognome" /></div>
                      <div><Label className="text-xs">Ruolo / Qualifica</Label><Input value={ref.ruolo} onChange={(e) => setRef({ ...ref, ruolo: e.target.value })} data-testid="ref-ruolo" /></div>
                      <div><Label className="text-xs">Email</Label><Input value={ref.email} onChange={(e) => setRef({ ...ref, email: e.target.value })} data-testid="ref-email" /></div>
                      <div><Label className="text-xs">Cellulare</Label><Input value={ref.cellulare} onChange={(e) => setRef({ ...ref, cellulare: e.target.value })} data-testid="ref-cellulare" /></div>
                      <div><Label className="text-xs">LinkedIn</Label><Input value={ref.linkedin} onChange={(e) => setRef({ ...ref, linkedin: e.target.value })} data-testid="ref-linkedin" /></div>
                    </div>
                    <label className="flex items-center gap-2 text-sm text-slate-600"><Checkbox checked={ref.referente_principale} onCheckedChange={(v) => setRef({ ...ref, referente_principale: !!v })} data-testid="ref-principale" />Referente principale</label>
                    {matches && (
                      <div className="border border-amber-200 bg-amber-50 rounded-lg p-2 space-y-1" data-testid="ref-matches">
                        <p className="text-xs text-amber-700 font-medium">Trovate persone simili. Collega una persona esistente:</p>
                        {matches.map((m) => (
                          <div key={m.id} className="flex items-center justify-between text-sm">
                            <span>{m.cognome} {m.nome} — {m.email || m.cellulare || m.telefono || "—"}</span>
                            <Button size="sm" variant="outline" onClick={() => linkExisting(m.id)} data-testid={`link-person-${m.id}`}><UserCheck className="w-3.5 h-3.5 mr-1" />Collega</Button>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="flex gap-2">
                      <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={matches ? createNew : checkDup} data-testid="ref-save">{matches ? "Crea nuovo comunque" : "Verifica e salva"}</Button>
                      <Button size="sm" variant="ghost" onClick={resetForm} data-testid="ref-cancel">Annulla</Button>
                    </div>
                  </div>
                )}
                {d.contacts.length === 0 ? <p className="text-sm text-slate-400 py-2">Nessun referente collegato.</p> :
                  d.contacts.map((x, i) => (
                    <div key={x.relation.id || i} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-3">
                      <div><div className="font-medium text-slate-800 flex items-center gap-2">{x.person.cognome} {x.person.nome}{x.relation.referente_principale && <StatusBadge color="tiffany">Principale</StatusBadge>}</div>
                        <div className="text-xs text-slate-500">{x.relation.qualifica || x.person.ruolo || "—"} · {x.person.email || x.person.cellulare || x.person.telefono || "—"}</div></div>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-500" onClick={() => removeContact(x.relation)} data-testid={`ref-del-${x.person.id}`}><Trash2 className="w-4 h-4" /></Button>
                    </div>
                  ))}
              </TabsContent>

              <TabsContent value="eventi" className="pt-2 space-y-2">
                {d.events.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun evento collegato.</p> :
                  d.events.map((x, i) => (
                    <div key={i} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-3">
                      <span className="font-medium text-slate-800">{x.event.nome}</span><StatusBadge color="tiffany">{x.tipo || "—"}</StatusBadge></div>
                  ))}
              </TabsContent>

              <TabsContent value="trattative" className="pt-2 space-y-2">
                {d.deals.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessuna trattativa.</p> :
                  d.deals.map((dl) => (
                    <div key={dl.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-3">
                      <div><div className="font-medium text-slate-800">{dl.tipo} · {dl.livello || "—"}</div><div className="text-xs text-slate-500">Fase: {dl.fase}</div></div>
                      <span className="text-sm font-semibold text-slate-700">{formatEUR(dl.valore)}</span></div>
                  ))}
              </TabsContent>

              <TabsContent value="sponsorship" className="pt-2 space-y-2">
                {d.deals.filter((x) => ["sponsor", "partner"].includes(x.tipo)).length === 0 ? <p className="text-sm text-slate-400 py-4">Nessuna sponsorship.</p> :
                  d.deals.filter((x) => ["sponsor", "partner"].includes(x.tipo)).map((dl) => (
                    <div key={dl.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-3">
                      <span className="font-medium text-slate-800">{dl.tipo} · {dl.livello || "—"}</span>
                      <span className="text-sm font-semibold text-emerald-600">{formatEUR(dl.valore_confermato || dl.valore)}</span></div>
                  ))}
              </TabsContent>

              <TabsContent value="attivita" className="pt-2 space-y-2">
                {d.activities.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessuna attività.</p> :
                  d.activities.map((a) => (
                    <div key={a.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5">
                      <span className="text-sm text-slate-700">{a.titolo}</span><StatusBadge color="gray">{a.tipo || "attività"}</StatusBadge></div>
                  ))}
              </TabsContent>

              <TabsContent value="followup" className="pt-2 space-y-2">
                {d.followups.length === 0 ? <p className="text-sm text-slate-400 py-4">Nessun follow-up.</p> :
                  d.followups.map((f) => (
                    <div key={f.id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2.5">
                      <span className="text-sm text-slate-700">{f.titolo}</span><StatusBadge color="orange">{f.scadenza || "—"}</StatusBadge></div>
                  ))}
              </TabsContent>
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
