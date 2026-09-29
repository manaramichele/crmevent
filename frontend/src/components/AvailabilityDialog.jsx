import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, useCollection, useSettings, calcAge } from "@/components/crm";
import PersonDetailDialog from "@/components/PersonDetailDialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Link2, Copy, ExternalLink, RefreshCw, Ban, ClipboardList, Users, AlertTriangle } from "lucide-react";
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
          <span className={d.fase === "allestimento" ? "text-amber-600 font-medium" : "text-slate-500"}>{dm(d.date)}</span>
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
  const copy = async () => {
    try { await navigator.clipboard.writeText(link.url); toast.success("Link copiato"); }
    catch { toast.error("Impossibile copiare"); }
  };

  const updateRow = async (aid, patch) => {
    try { const { data } = await api.put(`/availabilities/${aid}`, patch); setRows((p) => p.map((r) => (r.id === aid ? { ...r, ...data } : r))); if (patch.apply_person) toast.success("Anagrafica aggiornata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto" data-testid="availability-dialog">
          <DialogHeader>
            <DialogTitle className="font-display flex items-center gap-2"><ClipboardList className="w-5 h-5 text-tiffany-active" />Raccolta disponibilità</DialogTitle>
            <DialogDescription className="sr-only">Genera il link pubblico e consulta le disponibilità ricevute</DialogDescription>
          </DialogHeader>

          {event && (event.data_inizio || event.data_inizio_allestimento) && (
            <p className="text-sm text-slate-500 -mt-2">
              {event.data_inizio_allestimento && <span className="text-amber-600">Allestimento dal {dm(event.data_inizio_allestimento)} · </span>}
              {event.data_inizio && <span>Evento {dm(event.data_inizio)}{event.data_fine && event.data_fine !== event.data_inizio ? ` → ${dm(event.data_fine)}` : ""}</span>}
            </p>
          )}

          <Tabs defaultValue="link" className="mt-2">
            <TabsList>
              <TabsTrigger value="link" data-testid="avtab-link"><Link2 className="w-4 h-4 mr-1" />Link pubblico</TabsTrigger>
              <TabsTrigger value="ricevute" data-testid="avtab-ricevute"><Users className="w-4 h-4 mr-1" />Disponibilità ricevute{rows.length ? ` (${rows.length})` : ""}</TabsTrigger>
            </TabsList>

            <TabsContent value="link" className="pt-3">
              {link?.active ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge color="green">Link attivo</StatusBadge>
                    <span className="text-xs text-slate-400">Condividi questo link con i potenziali collaboratori.</span>
                  </div>
                  <Input readOnly value={link.url} className="font-mono text-sm" data-testid="avail-link-url" onFocus={(e) => e.target.select()} />
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={copy} data-testid="avail-copy"><Copy className="w-4 h-4 mr-1.5" />Copia link</Button>
                    <Button variant="outline" size="sm" onClick={() => window.open(link.url, "_blank")} data-testid="avail-open"><ExternalLink className="w-4 h-4 mr-1.5" />Apri pagina</Button>
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

            <TabsContent value="ricevute" className="pt-3">
              {loading ? <p className="text-sm text-slate-400 py-8 text-center">Caricamento...</p>
                : rows.length === 0 ? <p className="text-sm text-slate-400 py-8 text-center">Nessuna disponibilità ricevuta finora.</p>
                : (
                  <div className="overflow-x-auto border border-slate-200 rounded-xl">
                    <table className="w-full text-sm">
                      <thead><tr className="border-b border-slate-200 bg-slate-50/70 text-left">
                        {["Nome", "Cellulare", "Email", "Età", "Disponibilità", "Preferenza", "Ruolo evento", "Stato"].map((h) => <th key={h} className="font-semibold text-slate-600 px-3 py-2.5 whitespace-nowrap">{h}</th>)}
                      </tr></thead>
                      <tbody>
                        {rows.map((r) => (
                          <tr key={r.id} className="border-b border-slate-100 align-top" data-testid={`avail-row-${r.id}`}>
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
