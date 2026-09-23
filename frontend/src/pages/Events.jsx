import { useState, useEffect } from "react";
import api, { formatApiError } from "@/lib/api";
import { EntityManager, StatusBadge, useSettings, toOptions, FileUpload, fileUrl } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { CalendarPlus, Map as MapIcon, Plus, Trash2 } from "lucide-react";

const STATO = { attivo: "green", pianificato: "tiffany", concluso: "gray", annullato: "red" };
const STATO_LABEL = { attivo: "Attivo", pianificato: "Pianificato", concluso: "Concluso", annullato: "Annullato" };

function MapsDialog({ eventId, open, onOpenChange }) {
  const [maps, setMaps] = useState([]);
  const [form, setForm] = useState({ nome: "", tipologia: "", descrizione: "", immagine_url: "", pdf_url: "", file_url: "", url_esterno: "", google_maps_url: "" });
  const load = async () => { const { data } = await api.get("/maps", { params: { evento_id: eventId } }); setMaps(data); };
  useEffect(() => { if (open) load(); /* eslint-disable-next-line */ }, [open, eventId]);
  const ch = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const add = async () => {
    if (!form.nome) return toast.error("Nome mappa obbligatorio");
    try { await api.post("/maps", { ...form, evento_id: eventId }); toast.success("Mappa aggiunta"); setForm({ nome: "", tipologia: "", descrizione: "", immagine_url: "", pdf_url: "", file_url: "", url_esterno: "", google_maps_url: "" }); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const del = async (id) => { await api.delete(`/maps/${id}`); toast.success("Mappa eliminata"); load(); };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="maps-dialog">
        <DialogHeader><DialogTitle className="font-display">Mappe & Percorsi</DialogTitle><DialogDescription className="sr-only">Gestisci mappe evento</DialogDescription></DialogHeader>
        <div className="space-y-2 mb-4">
          {maps.length === 0 && <p className="text-sm text-slate-400">Nessuna mappa.</p>}
          {maps.map((m) => (
            <div key={m.id} className="flex items-center justify-between border border-slate-200 rounded-lg p-2.5" data-testid={`map-row-${m.id}`}>
              <div className="text-sm"><span className="font-medium text-slate-800">{m.nome}</span>{m.tipologia && <span className="text-slate-400"> · {m.tipologia}</span>}
                {m.immagine_url && <a href={fileUrl(m.immagine_url)} target="_blank" rel="noreferrer" className="text-tiffany-active ml-2 text-xs">img</a>}
                {m.pdf_url && <a href={fileUrl(m.pdf_url)} target="_blank" rel="noreferrer" className="text-tiffany-active ml-2 text-xs">pdf</a>}
                {m.google_maps_url && <a href={m.google_maps_url} target="_blank" rel="noreferrer" className="text-tiffany-active ml-2 text-xs">maps</a>}
              </div>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-400 hover:text-red-500" onClick={() => del(m.id)} data-testid={`del-map-${m.id}`}><Trash2 className="w-4 h-4" /></Button>
            </div>
          ))}
        </div>
        <div className="border-t border-slate-100 pt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5"><Label className="text-xs">Nome</Label><Input value={form.nome} onChange={(e) => ch("nome", e.target.value)} data-testid="map-nome" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Tipologia</Label><Input value={form.tipologia} onChange={(e) => ch("tipologia", e.target.value)} placeholder="Percorso, Expo, Parcheggi..." /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label className="text-xs">Descrizione</Label><Input value={form.descrizione} onChange={(e) => ch("descrizione", e.target.value)} /></div>
          <FileUpload label="Immagine" value={form.immagine_url} onChange={(u) => ch("immagine_url", u)} accept="image/*" testid="map-img" />
          <FileUpload label="PDF" value={form.pdf_url} onChange={(u) => ch("pdf_url", u)} accept="application/pdf" testid="map-pdf" />
          <FileUpload label="File" value={form.file_url} onChange={(u) => ch("file_url", u)} testid="map-file" />
          <div className="space-y-1.5"><Label className="text-xs">Link Google Maps</Label><Input value={form.google_maps_url} onChange={(e) => ch("google_maps_url", e.target.value)} placeholder="https://maps.google.com/..." /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label className="text-xs">URL esterno</Label><Input value={form.url_esterno} onChange={(e) => ch("url_esterno", e.target.value)} /></div>
        </div>
        <Button onClick={add} className="mt-4 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="add-map-button"><Plus className="w-4 h-4 mr-1.5" />Aggiungi mappa</Button>
      </DialogContent>
    </Dialog>
  );
}

export default function Events() {
  const settings = useSettings();
  const [mapsFor, setMapsFor] = useState(null);
  if (!settings) return <div className="text-slate-400">Caricamento...</div>;

  const fields = [
    { name: "nome", label: "Nome evento", required: true, full: true },
    { name: "edizione", label: "Edizione" },
    { name: "tipologia", label: "Tipologia", type: "select", options: toOptions(settings.tipologie_evento) },
    { name: "data_inizio", label: "Data inizio", type: "date" },
    { name: "data_fine", label: "Data fine", type: "date" },
    { name: "ora_inizio", label: "Ora inizio", type: "time" },
    { name: "ora_fine", label: "Ora fine", type: "time" },
    { name: "localita", label: "Località / Venue" },
    { name: "indirizzo", label: "Indirizzo" },
    { name: "citta", label: "Città" },
    { name: "provincia", label: "Provincia" },
    { name: "regione", label: "Regione" },
    { name: "nazione", label: "Nazione" },
    { name: "organizzatore", label: "Organizzatore" },
    { name: "responsabile", label: "Responsabile evento" },
    { name: "sito_web", label: "Sito web" },
    { name: "email", label: "Email", type: "email" },
    { name: "telefono", label: "Telefono", type: "tel" },
    { name: "partecipanti_previsti", label: "Partecipanti previsti", type: "number" },
    { name: "budget", label: "Budget (€)", type: "number" },
    { name: "stato", label: "Stato", type: "select", options: Object.keys(STATO_LABEL).map((v) => ({ value: v, label: STATO_LABEL[v] })) },
    { name: "descrizione", label: "Descrizione", type: "textarea", full: true },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const columns = [
    { key: "nome", label: "Evento", render: (r) => <div><div className="font-medium text-slate-800">{r.nome}</div>{r.edizione && <div className="text-xs text-slate-400">Ed. {r.edizione}</div>}</div> },
    { key: "tipologia", label: "Tipologia" },
    { key: "citta", label: "Città" },
    { key: "data_inizio", label: "Date", render: (r) => <span>{r.data_inizio}{r.data_fine && r.data_fine !== r.data_inizio ? ` → ${r.data_fine}` : ""}</span> },
    { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO[r.stato] || "gray"}>{STATO_LABEL[r.stato] || r.stato}</StatusBadge> },
  ];

  const syncCal = async (row) => {
    try { const { data } = await api.post(`/events/${row.id}/calendar-sync`); toast.success("Evento sincronizzato su Google Calendar"); if (data.html_link) window.open(data.html_link, "_blank"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const rowActions = (row) => (
    <>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Mappe & Percorsi" onClick={() => setMapsFor(row.id)} data-testid={`maps-${row.id}`}><MapIcon className="w-4 h-4" /></Button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Aggiungi a Google Calendar" onClick={() => syncCal(row)} data-testid={`calsync-${row.id}`}><CalendarPlus className="w-4 h-4" /></Button>
    </>
  );

  return (
    <>
      <EntityManager title="Eventi" subtitle="Gestione multi-evento, mappe e sincronizzazione calendario"
        endpoint="/events" fields={fields} columns={columns} entityLabel="evento" testid="event"
        searchKeys={["nome", "citta", "tipologia"]} rowActions={rowActions} />
      {mapsFor && <MapsDialog eventId={mapsFor} open={!!mapsFor} onOpenChange={(o) => !o && setMapsFor(null)} />}
    </>
  );
}
