import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, useCollection, useSettings, calcAge } from "@/components/crm";
import PersonDetailDialog from "@/components/PersonDetailDialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Link2, Copy, ExternalLink, RefreshCw, Ban, ClipboardList, Users, AlertTriangle, CheckCircle2, Mail } from "lucide-react";
import { toast } from "sonner";

const dm = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) : "");
const RUOLO_LABEL = { da_definire: "Da definire", staff: "Staff", volontario: "Volontario" };
const STATO_LABEL = { nuova: "Nuova", confermata: "Confermata", non_utilizzata: "Non utilizzata" };
const STATO_COLOR = { nuova: "blue", confermata: "green", non_utilizzata: "gray" };

function DaysSummary({ days = [] }) {
  if (!days.length) return <span className="text-slate-400">—</span>;
  return (
    <div className="flex flex-col gap-0.5">
      {days.map((d, i) => (
        <span key={i} className="text-xs text-slate-700 whitespace-nowrap">
          <span className={d.fase === "allestimento" ? "text-amber-600 font-medium" : d.fase === "disallestimento" ? "text-violet-600 font-medium" : "text-slate-500"}>{dm(d.date)}</span>
          {" · "}{d.dalle || d.alle ? `${d.dalle || "?"}–${d.alle || "?"}` : "disponibile"}
        </span>
      ))}
    </div>
  );
}

export default function AvailabilityDialog({ eventId, open, onOpenChange }) {
  const { items: events } = useCollection("/events");
  const { items: teams } = useCollection("/teams");
  const settings = useSettings();
  const [link, setLink] = useState(null);
  const [event, setEvent] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [personId, setPersonId] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [fRuolo, setFRuolo] = useState("all");
  const [fStato, setFStato] = useState("all");

  const loadLink = useCallback(async () => {
    try { const { data } = await api.get(`/events/${eventId}/availability/link`); setLink(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [eventId]);

  const loadRows = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get(`/events/${eventId}/availabilities`); setRows(data.availabilities); setEvent(data.event); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  }, [eventId]);

  useEffect(() => { if (open) { loadLink(); loadRows(); } }, [open, loadLink, loadRows]);

  const genLink = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/events/${eventId}/availability/link`); setLink(data); toast.success("Link pubblico generato"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const deactivate = async () => {
    try { await api.post(`/events/${eventId}/availability/link/deactivate`); await loadLink(); toast.success("Link disattivato"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const updateRow = async (aid, patch) => {
    try { const { data } = await api.put(`/availabilities/${aid}`, patch); setRows((p) => p.map((r) => (r.id === aid ? { ...r, ...data } : r))); toast.success(patch.apply_person ? "Anagrafica aggiornata" : "Disponibilità aggiornata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const filtered = rows.filter((r) =>
    (fRuolo === "all" || (r.ruolo_evento || "da_definire") === fRuolo) &&
    (fStato === "all" || (r.stato || "nuova") === fStato));
  const toggleSel = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSel = filtered.length > 0 && filtered.every((r) => selected.has(r.id));
  const toggleAll = () => setSelected(() => { const n = new Set(); if (!allSel) filtered.forEach((r) => n.add(r.id)); return n; });
  const toggleConfirm = (r, on) => updateRow(r.id, { stato: on ? "confermata" : "nuova" });
  const bulkConfirm = async () => {
    try { const { data } = await api.post(`/events/${eventId}/availabilities/confirm-bulk`, { ids: [...selected] }); toast.success(`${data.confirmed} confermate`); setSelected(new Set()); await loadRows(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="w-[95vw] max-w-[1200px] max-h-[90vh] flex flex-col overflow-hidden" data-testid="availability-dialog">
          <DialogHeader className="shrink-0">
            <DialogTitle className="font-display flex items-center gap-2"><ClipboardList className="w-5 h-5 text-tiffany-active" />Raccolta disponibilità</DialogTitle>
            <DialogDescription className="sr-only">Genera il link pubblico e consulta le disponibilità ricevute</DialogDescription>
          </DialogHeader>

          {event && (event.data_inizio || event.data_inizio_allestimento) && (
            <p className="text-sm text-slate-500 -mt-2 shrink-0">
              {event.data_inizio_allestimento && <span className="text-amber-600">Allestimento dal {dm(event.data_inizio_allestimento)} · </span>}
              {event.data_inizio && <span>Evento {dm(event.data_inizio)}{event.data_fine && event.data_fine !== event.data_inizio ? `–${dm(event.data_fine)}` : ""}</span>}
              {event.data_fine_disallestimento && <span className="text-violet-600"> · Disallestimento fino al {dm(event.data_fine_disallestimento)}</span>}
            </p>
          )}

          <Tabs defaultValue="link" className="mt-2 flex flex-col min-h-0 flex-1">
            <TabsList className="shrink-0">
              <TabsTrigger value="link" data-testid="avtab-link"><Link2 className="w-4 h-4 mr-1" />Link pubblico</TabsTrigger>
              <TabsTrigger value="ricevute" data-testid="avtab-ricevute"><Users className="w-4 h-4 mr-1" />Disponibilità ricevute{rows.length ? ` (${rows.length})` : ""}</TabsTrigger>
            </TabsList>

            <TabsContent value="link" className="pt-3 overflow-y-auto">
              {link?.active ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <StatusBadge color="green">Link attivo</StatusBadge>
                    <span className="text-xs text-slate-400">Condividi il link nella lingua corretta con i collaboratori.</span>
                  </div>
                  {(() => {
                    const base = link.url;
                    const withLang = (l) => base + (base.includes("?") ? "&" : "?") + "lang=" + l;
                    const itUrl = withLang("it");
                    const enUrl = withLang("en");
                    const copyUrl = async (u, msg) => { try { await navigator.clipboard.writeText(u); toast.success(msg); } catch { toast.error("Impossibile copiare"); } };
                    return (
                      <div className="space-y-3">
                        <div>
                          <div className="text-xs font-semibold text-slate-600 mb-1 flex items-center gap-1.5">🇮🇹 Link partecipazione — Italiano</div>
                          <Input readOnly value={itUrl} className="font-mono text-sm" data-testid="avail-link-url" onFocus={(e) => e.target.select()} />
                          <div className="flex flex-wrap gap-2 mt-2">
                            <Button variant="outline" size="sm" onClick={() => copyUrl(itUrl, "Link IT copiato")} data-testid="avail-copy-it"><Copy className="w-4 h-4 mr-1.5" />Copia link IT</Button>
                            <Button variant="outline" size="sm" onClick={() => window.open(itUrl, "_blank")} data-testid="avail-open-it"><ExternalLink className="w-4 h-4 mr-1.5" />Apri IT</Button>
                          </div>
                        </div>
                        <div>
                          <div className="text-xs font-semibold text-slate-600 mb-1 flex items-center gap-1.5">🇬🇧 Link partecipazione — English</div>
                          <Input readOnly value={enUrl} className="font-mono text-sm" data-testid="avail-link-url-en" onFocus={(e) => e.target.select()} />
                          <div className="flex flex-wrap gap-2 mt-2">
                            <Button variant="outline" size="sm" onClick={() => copyUrl(enUrl, "EN link copied")} data-testid="avail-copy-en"><Copy className="w-4 h-4 mr-1.5" />Copy EN link</Button>
                            <Button variant="outline" size="sm" onClick={() => window.open(enUrl, "_blank")} data-testid="avail-open-en"><ExternalLink className="w-4 h-4 mr-1.5" />Open EN</Button>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
                  <div className="flex flex-wrap gap-2 pt-1 border-t border-slate-100">
                    <AlertDialog>
                      <AlertDialogTrigger asChild><Button variant="outline" size="sm" data-testid="avail-regen"><RefreshCw className="w-4 h-4 mr-1.5" />Rigenera link</Button></AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader><AlertDialogTitle>Rigenerare il link?</AlertDialogTitle><AlertDialogDescription>Il link precedente verrà invalidato immediatamente. Le disponibilità già raccolte restano salvate.</AlertDialogDescription></AlertDialogHeader>
                        <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction onClick={genLink} data-testid="avail-regen-confirm">Rigenera</AlertDialogAction></AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                    <AlertDialog>
                      <AlertDialogTrigger asChild><Button variant="outline" size="sm" className="text-red-500 hover:text-red-600" data-testid="avail-deactivate"><Ban className="w-4 h-4 mr-1.5" />Disattiva link</Button></AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader><AlertDialogTitle>Disattivare il link?</AlertDialogTitle><AlertDialogDescription>La pagina pubblica non accetterà più nuove disponibilità. Potrai rigenerare un link in seguito.</AlertDialogDescription></AlertDialogHeader>
                        <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={deactivate} data-testid="avail-deactivate-confirm">Disattiva</AlertDialogAction></AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <StatusBadge color="gray">Nessun link attivo</StatusBadge>
                  <p className="text-sm text-slate-500 mt-3 mb-4">Genera un link pubblico da condividere: le persone potranno indicare la propria disponibilità senza accedere a CRMEvent.</p>
                  <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={genLink} disabled={busy} data-testid="avail-generate"><Link2 className="w-4 h-4 mr-1.5" />{busy ? "Generazione..." : "Genera link pubblico"}</Button>
                </div>
              )}
            </TabsContent>

            <TabsContent value="ricevute" className="pt-3 flex flex-col min-h-0 flex-1 data-[state=inactive]:hidden">
              {loading ? <p className="text-sm text-slate-400 py-8 text-center">Caricamento...</p>
                : rows.length === 0 ? <p className="text-sm text-slate-400 py-8 text-center">Nessuna disponibilità ricevuta finora.</p>
                : (
                  <div className="flex flex-col min-h-0 flex-1">
                    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 mb-3 shrink-0" data-testid="avail-kpi">
                      {[
                        { k: "total", label: "Ricevute", val: rows.length, on: () => { setFRuolo("all"); setFStato("all"); }, color: "text-slate-900" },
                        { k: "nuovi", label: "Nuovi", val: rows.filter((r) => (r.stato || "nuova") === "nuova").length, on: () => setFStato("nuova"), color: "text-blue-600" },
                        { k: "confermati", label: "Confermati", val: rows.filter((r) => r.stato === "confermata").length, on: () => setFStato("confermata"), color: "text-emerald-600" },
                        { k: "staff", label: "Staff", val: rows.filter((r) => r.ruolo_evento === "staff").length, on: () => setFRuolo("staff"), color: "text-indigo-600" },
                        { k: "volontari", label: "Volontari", val: rows.filter((r) => r.ruolo_evento === "volontario").length, on: () => setFRuolo("volontario"), color: "text-teal-600" },
                        { k: "dadefinire", label: "Da definire", val: rows.filter((r) => (r.ruolo_evento || "da_definire") === "da_definire").length, on: () => setFRuolo("da_definire"), color: "text-amber-600" },
                      ].map((c) => (
                        <button key={c.k} onClick={c.on} data-testid={`kpi-${c.k}`} className="border border-slate-200 rounded-xl p-2.5 text-left hover:border-tiffany-border hover:bg-tiffany-light/20 transition-colors">
                          <div className={`text-xl font-bold ${c.color}`}>{c.val}</div>
                          <div className="text-[11px] text-slate-500">{c.label}</div>
                        </button>
                      ))}
                    </div>
                    {(() => {
                      const inviate = rows.filter((r) => r.availability_email_sent_at || r.confirmation_email_sent_at).length;
                      const errore = rows.filter((r) => r.confirmation_email_error || r.brevo_status === "error").length;
                      const daInviare = Math.max(0, rows.length - inviate - errore);
                      return (
                        <div className="flex items-center gap-3 mb-3 text-xs" data-testid="avail-email-stats">
                          <span className="inline-flex items-center gap-1 text-slate-500"><Mail className="w-3.5 h-3.5" />Email:</span>
                          <span className="text-emerald-600">Inviate {inviate}</span>
                          <span className="text-slate-500">Da inviare {daInviare}</span>
                          <span className="text-red-500">Errore {errore}</span>
                        </div>
                      );
                    })()}
                    <div className="flex flex-wrap items-center gap-2 mb-3 shrink-0">
                      <Select value={fRuolo} onValueChange={setFRuolo}>
                        <SelectTrigger className="h-8 w-40" data-testid="avail-filter-ruolo"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Ruolo: tutti</SelectItem>
                          <SelectItem value="da_definire">Da definire</SelectItem>
                          <SelectItem value="staff">Staff</SelectItem>
                          <SelectItem value="volontario">Volontari</SelectItem>
                        </SelectContent>
                      </Select>
                      <Select value={fStato} onValueChange={setFStato}>
                        <SelectTrigger className="h-8 w-40" data-testid="avail-filter-stato"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">Stato: tutti</SelectItem>
                          <SelectItem value="nuova">Nuovi</SelectItem>
                          <SelectItem value="confermata">Confermati</SelectItem>
                          <SelectItem value="non_utilizzata">Non utilizzati</SelectItem>
                        </SelectContent>
                      </Select>
                      <span className="text-xs text-slate-400">{filtered.length} risultati</span>
                      {selected.size > 0 && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button size="sm" className="ml-auto bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="avail-bulk-confirm"><CheckCircle2 className="w-4 h-4 mr-1.5" />Conferma selezionati ({selected.size})</Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader><AlertDialogTitle>Confermare {selected.size} persone?</AlertDialogTitle>
                              <AlertDialogDescription>Stai per confermare {selected.size} persone. Verrà inviata l'email di conferma a {selected.size} destinatari (quando l'invio Brevo è attivo). Vuoi continuare?</AlertDialogDescription></AlertDialogHeader>
                            <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction onClick={bulkConfirm} data-testid="avail-bulk-confirm-ok">Conferma</AlertDialogAction></AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      )}
                    </div>
                    <div className="flex-1 min-h-0 overflow-auto border border-slate-200 rounded-xl">
                      <table className="w-full text-sm">
                        <thead className="sticky top-0 z-10"><tr className="border-b border-slate-200 bg-slate-100 text-left">
                          <th className="px-3 py-2.5"><Checkbox checked={allSel} onCheckedChange={toggleAll} data-testid="avail-select-all" /></th>
                          {["Nome", "Cellulare", "Email", "Età", "Disponibilità", "Preferenza", "Ruolo evento", "Confermato", "Stato"].map((h) => <th key={h} className="font-semibold text-slate-600 px-3 py-2.5 whitespace-nowrap">{h}</th>)}
                        </tr></thead>
                        <tbody>
                          {filtered.map((r) => (
                            <tr key={r.id} className="border-b border-slate-100 align-top" data-testid={`avail-row-${r.id}`}>
                              <td className="px-3 py-2.5"><Checkbox checked={selected.has(r.id)} onCheckedChange={() => toggleSel(r.id)} data-testid={`avail-select-${r.id}`} /></td>
                              <td className="px-3 py-2.5">
                                <button className="font-medium text-tiffany-active hover:underline text-left" onClick={() => setPersonId(r.persona?.id)} data-testid={`avail-person-${r.id}`}>{r.persona?.nome} {r.persona?.cognome}</button>
                                {r.has_mismatch && (
                                  <div className="mt-1 flex items-center gap-1">
                                    <StatusBadge color="orange"><AlertTriangle className="w-3 h-3 mr-1" />Dati diversi</StatusBadge>
                                    <button className="text-[11px] text-tiffany-active hover:underline" onClick={() => updateRow(r.id, { apply_person: true })} data-testid={`avail-apply-${r.id}`}>Aggiorna anagrafica</button>
                                  </div>
                                )}
                              </td>
                              <td className="px-3 py-2.5 text-slate-700 whitespace-nowrap">{r.persona?.cellulare || "—"}</td>
                              <td className="px-3 py-2.5 text-slate-700">{r.persona?.email || "—"}</td>
                              <td className="px-3 py-2.5 text-slate-700 whitespace-nowrap">{r.eta != null ? `${r.eta} anni` : "—"}</td>
                              <td className="px-3 py-2.5"><DaysSummary days={r.days} /></td>
                              <td className="px-3 py-2.5 text-slate-700">{r.preferenza_attivita === "Altro" ? `Altro: ${r.preferenza_altro || ""}` : (r.preferenza_attivita || "—")}</td>
                              <td className="px-3 py-2.5">
                                <Select value={r.ruolo_evento || "da_definire"} onValueChange={(v) => updateRow(r.id, { ruolo_evento: v })}>
                                  <SelectTrigger className="h-8 w-36" data-testid={`avail-ruolo-${r.id}`}><SelectValue /></SelectTrigger>
                                  <SelectContent>{Object.entries(RUOLO_LABEL).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
                                </Select>
                              </td>
                              <td className="px-3 py-2.5">
                                <div className="flex flex-col items-start gap-0.5">
                                  <Checkbox checked={r.stato === "confermata"} onCheckedChange={(v) => toggleConfirm(r, !!v)} data-testid={`avail-confirm-${r.id}`} />
                                  {r.stato === "confermata" && r.confirmation_email_sent_at && <span className="text-[10px] text-emerald-600 inline-flex items-center gap-0.5"><Mail className="w-3 h-3" />inviata</span>}
                                  {r.stato === "confermata" && !r.confirmation_email_sent_at && r.confirmation_email_status && r.confirmation_email_status !== "sent" && <span className="text-[10px] text-amber-600">email: {r.confirmation_email_status}</span>}
                                </div>
                              </td>
                              <td className="px-3 py-2.5">
                                <Select value={r.stato || "nuova"} onValueChange={(v) => updateRow(r.id, { stato: v })}>
                                  <SelectTrigger className="h-8 w-36" data-testid={`avail-stato-${r.id}`}><SelectValue /></SelectTrigger>
                                  <SelectContent>{Object.entries(STATO_LABEL).map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
                                </Select>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
            </TabsContent>
          </Tabs>
        </DialogContent>
      </Dialog>

      {personId && <PersonDetailDialog personId={personId} open={!!personId} onOpenChange={(o) => !o && setPersonId(null)}
        events={events} teams={teams} settings={settings} onChanged={loadRows} onEdit={() => {}} onInvite={() => {}} />}
    </>
  );
}
