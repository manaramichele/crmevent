import { useState, useEffect, useRef } from "react";
import api, { formatApiError } from "@/lib/api";
import { EntityManager, StatusBadge, useSettings, toOptions, FileUpload, fileUrl } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { EventCreditDialog } from "@/components/EventCreditDialog";
import { Coins, Rocket } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CalendarPlus, Map as MapIcon, Plus, Trash2, Eye, Pencil, Download, RefreshCw, Route, X, FileText, ClipboardList } from "lucide-react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import AvailabilityDialog from "@/components/AvailabilityDialog";
import { RechargeDialog } from "@/components/CreditsSection";

const STATO = { attivo: "green", pianificato: "tiffany", concluso: "gray", annullato: "red" };
const STATO_LABEL = { attivo: "In corso", pianificato: "Pianificato", concluso: "Concluso", annullato: "Annullato" };
const FASE_EDIT_OPTIONS = [
  { value: "pianificato", label: "Pianificato" },
  { value: "concluso", label: "Concluso" },
  { value: "annullato", label: "Annullato" },
];

const EMPTY = { nome: "", tipologia: "", descrizione: "", immagine_url: "", pdf_url: "", file_url: "", gpx_url: "", distanza: null, url_esterno: "", google_maps_url: "" };

function haversine(a, b) {
  const R = 6371, toRad = (x) => (x * Math.PI) / 180;
  const dLat = toRad(b[0] - a[0]), dLon = toRad(b[1] - a[1]);
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
function parseGpx(text) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  if (doc.getElementsByTagName("parsererror").length) return { points: [], distanceKm: 0 };
  let nodes = Array.from(doc.getElementsByTagName("trkpt"));
  if (nodes.length < 2) nodes = Array.from(doc.getElementsByTagName("rtept"));
  if (nodes.length < 2) nodes = Array.from(doc.getElementsByTagName("wpt"));
  const points = nodes
    .map((n) => [parseFloat(n.getAttribute("lat")), parseFloat(n.getAttribute("lon"))])
    .filter((p) => !isNaN(p[0]) && !isNaN(p[1]));
  let d = 0;
  for (let i = 1; i < points.length; i++) d += haversine(points[i - 1], points[i]);
  return { points, distanceKm: Math.round(d * 100) / 100 };
}

function GpxMap({ gpxUrl }) {
  const boxRef = useRef(null);
  const mapRef = useRef(null);
  const [msg, setMsg] = useState("Caricamento tracciato...");
  useEffect(() => {
    let cancelled = false;
    const cleanup = () => { if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
    (async () => {
      try {
        const res = await fetch(fileUrl(gpxUrl), { credentials: "include" });
        const text = await res.text();
        const { points } = parseGpx(text);
        if (cancelled || !boxRef.current) return;
        if (points.length < 2) { setMsg("Traccia GPX non disponibile"); return; }
        setMsg("");
        cleanup();
        const map = L.map(boxRef.current, { scrollWheelZoom: true });
        mapRef.current = map;
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap", maxZoom: 19 }).addTo(map);
        const line = L.polyline(points, { color: "#0f766e", weight: 4 }).addTo(map);
        L.circleMarker(points[0], { radius: 7, color: "#059669", fillColor: "#10b981", fillOpacity: 1 }).addTo(map).bindTooltip("Partenza");
        L.circleMarker(points[points.length - 1], { radius: 7, color: "#dc2626", fillColor: "#ef4444", fillOpacity: 1 }).addTo(map).bindTooltip("Arrivo");
        map.fitBounds(line.getBounds(), { padding: [20, 20] });
        setTimeout(() => { if (mapRef.current) mapRef.current.invalidateSize(); }, 150);
      } catch {
        if (!cancelled) setMsg("Impossibile caricare la mappa GPX");
      }
    })();
    return () => { cancelled = true; cleanup(); };
  }, [gpxUrl]);
  return (
    <div className="relative">
      <div ref={boxRef} data-testid="gpx-map" style={{ height: 260 }} className="rounded-lg overflow-hidden border border-slate-200 bg-slate-50 z-0" />
      {msg && <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-400 pointer-events-none">{msg}</div>}
    </div>
  );
}

function MapsDialog({ eventId, open, onOpenChange }) {
  const [maps, setMaps] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [gpxBusy, setGpxBusy] = useState(false);
  const panelRef = useRef(null);

  const load = async () => {
    const { data } = await api.get("/maps", { params: { evento_id: eventId } });
    setMaps(data);
  };
  useEffect(() => { if (open) { load(); resetNew(); } /* eslint-disable-next-line */ }, [open, eventId]);

  const ch = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const resetNew = () => { setEditingId(null); setForm(EMPTY); };
  const loadForEdit = (m) => {
    setEditingId(m.id);
    setForm({ ...EMPTY, ...m });
    setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  const onGpxFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".gpx")) { toast.error("Seleziona un file con estensione .gpx"); e.target.value = ""; return; }
    setGpxBusy(true);
    try {
      const text = await f.text();
      const { points, distanceKm } = parseGpx(text);
      if (points.length < 2) { toast.error("File GPX non valido o privo di traccia"); return; }
      const fd = new FormData(); fd.append("file", f);
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setForm((prev) => ({ ...prev, gpx_url: data.url, distanza: prev.distanza != null && prev.distanza !== "" ? prev.distanza : distanceKm }));
      toast.success(`GPX caricato e validato · ${distanceKm} km`);
    } catch { toast.error("Errore nell'elaborazione del GPX"); }
    finally { setGpxBusy(false); e.target.value = ""; }
  };

  const save = async () => {
    if (!form.nome) return toast.error("Nome percorso obbligatorio");
    setSaving(true);
    try {
      const payload = { ...form, evento_id: eventId };
      if (editingId) {
        await api.put(`/maps/${editingId}`, payload);
        toast.success("Modifiche salvate");
      } else {
        const { data } = await api.post("/maps", payload);
        setEditingId(data.id); // resta in modifica su questo record: nessun duplicato ai salvataggi successivi
        toast.success("Percorso aggiunto");
      }
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const del = async (id) => {
    try { await api.delete(`/maps/${id}`); toast.success("Percorso eliminato"); if (editingId === id) resetNew(); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="maps-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><Route className="w-5 h-5 text-tiffany-active" />Mappe & Percorsi</DialogTitle>
          <DialogDescription className="sr-only">Gestisci i percorsi dell'evento</DialogDescription>
        </DialogHeader>

        {/* ---- PERCORSI ESISTENTI ---- */}
        <div className="mb-5">
          <div className="text-[11px] font-bold tracking-wider text-slate-400 uppercase mb-2">Percorsi esistenti</div>
          <div className="space-y-2">
            {maps.length === 0 && <p className="text-sm text-slate-400">Nessun percorso ancora inserito.</p>}
            {maps.map((m) => (
              <div key={m.id} className={`flex items-center justify-between gap-2 border rounded-lg p-3 transition-colors ${editingId === m.id ? "border-tiffany-border bg-tiffany-light/30" : "border-slate-200 hover:bg-slate-50"}`} data-testid={`map-row-${m.id}`}>
                <div className="min-w-0">
                  <div className="font-medium text-slate-800 truncate">{m.nome}</div>
                  <div className="flex flex-wrap items-center gap-1.5 mt-1">
                    {m.tipologia && <StatusBadge color="gray">{m.tipologia}</StatusBadge>}
                    {m.distanza != null && m.distanza !== "" && <StatusBadge color="tiffany">{m.distanza} km</StatusBadge>}
                    <StatusBadge color={m.gpx_url ? "green" : "gray"}>{m.gpx_url ? "GPX presente" : "GPX assente"}</StatusBadge>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Visualizza" onClick={() => loadForEdit(m)} data-testid={`view-map-${m.id}`}><Eye className="w-4 h-4" /></Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Modifica" onClick={() => loadForEdit(m)} data-testid={`edit-map-${m.id}`}><Pencil className="w-4 h-4" /></Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" title="Elimina" data-testid={`del-map-${m.id}`}><Trash2 className="w-4 h-4" /></Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader><AlertDialogTitle>Eliminare "{m.nome}"?</AlertDialogTitle><AlertDialogDescription>Questa azione non può essere annullata.</AlertDialogDescription></AlertDialogHeader>
                      <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={() => del(m.id)} data-testid={`confirm-del-map-${m.id}`}>Elimina</AlertDialogAction></AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ---- NUOVO / MODIFICA ---- */}
        <div ref={panelRef} className="border-t border-slate-200 pt-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[11px] font-bold tracking-wider uppercase text-slate-400">
              {editingId ? <span className="text-tiffany-active">Modifica percorso</span> : "Nuovo percorso"}
              {editingId && <span className="ml-2 normal-case tracking-normal text-slate-500 font-medium">· {form.nome || "—"}</span>}
            </div>
            <Button variant="outline" size="sm" onClick={resetNew} data-testid="new-map-button"><Plus className="w-4 h-4 mr-1" />Nuovo percorso</Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5"><Label className="text-xs">Nome</Label><Input value={form.nome} onChange={(e) => ch("nome", e.target.value)} data-testid="map-nome" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Tipologia</Label><Input value={form.tipologia || ""} onChange={(e) => ch("tipologia", e.target.value)} placeholder="Percorso, Expo, Parcheggi..." data-testid="map-tipologia" /></div>
            <div className="space-y-1.5 sm:col-span-2"><Label className="text-xs">Descrizione</Label><Input value={form.descrizione || ""} onChange={(e) => ch("descrizione", e.target.value)} data-testid="map-descrizione" /></div>
            <FileUpload label="Immagine" value={form.immagine_url} onChange={(u) => ch("immagine_url", u)} accept="image/*" testid="map-img" />
            <FileUpload label="PDF" value={form.pdf_url} onChange={(u) => ch("pdf_url", u)} accept="application/pdf" testid="map-pdf" />
            <FileUpload label="File" value={form.file_url} onChange={(u) => ch("file_url", u)} testid="map-file" />
            <div className="space-y-1.5"><Label className="text-xs">Distanza (km)</Label><Input type="number" step="0.01" value={form.distanza ?? ""} onChange={(e) => ch("distanza", e.target.value === "" ? null : Number(e.target.value))} data-testid="map-distanza" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Link Google Maps</Label><Input value={form.google_maps_url || ""} onChange={(e) => ch("google_maps_url", e.target.value)} placeholder="https://maps.google.com/..." data-testid="map-gmaps" /></div>
            <div className="space-y-1.5 sm:col-span-2"><Label className="text-xs">URL esterno</Label><Input value={form.url_esterno || ""} onChange={(e) => ch("url_esterno", e.target.value)} data-testid="map-url" /></div>

            {/* ---- File GPX dedicato ---- */}
            <div className="space-y-1.5 sm:col-span-2 border border-slate-200 rounded-lg p-3 bg-slate-50/60">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-semibold flex items-center gap-1.5"><Route className="w-3.5 h-3.5 text-tiffany-active" />File GPX (.gpx)</Label>
                {form.gpx_url && <StatusBadge color="green">Associato</StatusBadge>}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input type="file" accept=".gpx" onChange={onGpxFile} data-testid="map-gpx-input"
                  className="text-xs file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-tiffany-light file:text-tiffany-fg file:font-medium file:cursor-pointer" />
                {gpxBusy && <span className="text-xs text-slate-400">Elaborazione...</span>}                {form.gpx_url && !gpxBusy && (
                  <>
                    <a href={fileUrl(form.gpx_url)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-tiffany-active hover:underline" data-testid="map-gpx-download"><Download className="w-3.5 h-3.5" />Scarica</a>
                    <span className="inline-flex items-center gap-1 text-xs text-slate-400"><RefreshCw className="w-3.5 h-3.5" />Seleziona un file per sostituire</span>
                    <button type="button" onClick={() => ch("gpx_url", "")} className="inline-flex items-center gap-1 text-xs text-red-500 hover:underline" data-testid="map-gpx-remove"><X className="w-3.5 h-3.5" />Elimina GPX</button>
                  </>
                )}
              </div>
              {form.gpx_url && <div className="mt-2"><GpxMap gpxUrl={form.gpx_url} /></div>}
              <p className="text-[11px] text-slate-400 mt-1.5">La distanza viene calcolata automaticamente dal GPX quando il campo "Distanza" è vuoto.</p>
            </div>
          </div>

          <Button onClick={save} disabled={saving} className="mt-4 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="save-map-button">
            {editingId ? (saving ? "Salvataggio..." : "Salva modifiche") : (saving ? "Aggiunta..." : <><Plus className="w-4 h-4 mr-1.5" />Aggiungi percorso</>)}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const EV_STATE = {
  preparazione: ["Da attivare", "bg-slate-100 text-slate-600"],
  attivo: ["Attivo", "bg-emerald-50 text-emerald-700"],
  sospeso: ["Sospeso", "bg-red-50 text-red-700"],
  concluso: ["Concluso", "bg-slate-100 text-slate-500"],
};
const dmyEv = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4) : "");
function eventDisplayState(r) {
  const end = r.data_fine || r.data_inizio;
  if (end && new Date(end + "T23:59:59") < new Date()) return "concluso";
  if (r.credit_state === "attivo") return "attivo";
  if (r.credit_state === "sospeso") return "sospeso";
  if (r.credit_state === "concluso") return "concluso";
  if (!r.credit_state) return "attivo"; // legacy: operativo, nessun prompt
  return "preparazione";
}

export default function Events() {
  const settings = useSettings();
  const navigate = useNavigate();
  const [mapsFor, setMapsFor] = useState(null);
  const [sp, setSp] = useSearchParams();
  useEffect(() => {
    const m = sp.get("maps");
    if (m) { setMapsFor(m); sp.delete("maps"); setSp(sp, { replace: true }); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [availFor, setAvailFor] = useState(null);
  const [creditFor, setCreditFor] = useState(null);
  const [recharge, setRecharge] = useState(false);
  const [noCredits, setNoCredits] = useState(false);
  const balRef = useRef({ balance: null });
  const refreshBalance = async () => {
    try { const { data } = await api.get("/credits/balance"); balRef.current = data; return data; } catch { return null; }
  };
  useEffect(() => { refreshBalance(); }, []);
  const guardCreate = async () => {
    const b = await refreshBalance();
    if (b && b.balance < 1) { setNoCredits(true); return false; }
    return true;
  };
  if (!settings) return <div className="text-slate-400">Caricamento...</div>;

  const fields = [
    { name: "nome", label: "Nome evento", required: true, full: true },
    { name: "logo_url", label: "Logo evento (PNG/JPG)", type: "image", full: true },
    { name: "edizione", label: "Edizione" },
    { name: "tipologia", label: "Tipologia", type: "select", options: toOptions(settings.tipologie_evento) },
    { name: "data_inizio_allestimento", label: "Data inizio allestimento (facoltativa)", type: "date" },
    { name: "data_inizio", label: "Data inizio", type: "date" },
    { name: "data_fine", label: "Data fine", type: "date" },
    { name: "data_fine_disallestimento", label: "Data fine disallestimento (facoltativa)", type: "date" },
    { name: "giorni_descrizioni", label: "Descrizione delle singole giornate (facoltativa)", type: "daydesc", full: true },
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
    { name: "stato", label: "Fase evento", keepOrder: true, type: "select", options: FASE_EDIT_OPTIONS },
    { name: "descrizione", label: "Descrizione", type: "textarea", full: true },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const columns = [
    { key: "nome", label: "Evento", render: (r) => <div><div className="font-medium text-slate-800">{r.nome}</div>{r.edizione && <div className="text-xs text-slate-400">Ed. {r.edizione}</div>}</div> },
    { key: "tipologia", label: "Tipologia" },
    { key: "citta", label: "Città" },
    { key: "data_inizio", label: "Date", render: (r) => {
      const dm = (d) => d ? d.slice(8, 10) + "/" + d.slice(5, 7) : "";
      const ev = r.data_inizio ? (r.data_fine && r.data_fine !== r.data_inizio ? `${dm(r.data_inizio)}–${dm(r.data_fine)}` : dm(r.data_inizio)) : "";
      return (
        <div className="text-sm space-y-0.5">
          {r.data_inizio_allestimento && <div className="text-xs text-amber-600">Allestimento dal {dm(r.data_inizio_allestimento)}</div>}
          <span className="text-slate-700">{ev ? `Evento ${ev}` : "—"}</span>
          {r.data_fine_disallestimento && <div className="text-xs text-violet-600">Disallestimento fino al {dm(r.data_fine_disallestimento)}</div>}
        </div>
      );
    } },
    { key: "stato", label: "Fase", render: (r) => <StatusBadge color={STATO[r.stato] || "gray"}>{STATO_LABEL[r.stato] || r.stato}</StatusBadge> },
    { key: "credit_state", label: "CRMEvent", render: (r) => {
      const s = eventDisplayState(r);
      const [lbl, cls] = EV_STATE[s] || EV_STATE.preparazione;
      const end = r.data_fine || r.data_inizio;
      return (
        <button onClick={() => setCreditFor(r.id)} data-testid={`event-credit-badge-${r.id}`} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${cls} hover:opacity-80 transition`}>
          <Coins className="w-3.5 h-3.5" />
          {s === "attivo" && end ? `Attivo · fino al ${dmyEv(end)}` : lbl}
        </button>
      );
    } },
  ];

  const syncCal = async (row) => {
    try { const { data } = await api.post(`/events/${row.id}/calendar-sync`); toast.success("Evento sincronizzato su Google Calendar"); if (data.html_link) window.open(data.html_link, "_blank"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const rowActions = (row) => (
    <>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Crediti evento (attiva / stato)" onClick={() => setCreditFor(row.id)} data-testid={`event-credits-${row.id}`}><Coins className="w-4 h-4" /></Button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Raccolta disponibilità" onClick={() => setAvailFor(row.id)} data-testid={`availability-${row.id}`}><ClipboardList className="w-4 h-4" /></Button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Briefing evento" onClick={() => navigate(`/eventi/${row.id}/briefing`)} data-testid={`briefing-${row.id}`}><FileText className="w-4 h-4" /></Button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Pipeline evento" onClick={() => navigate(`/eventi/${row.id}/pipeline`)} data-testid={`pipeline-${row.id}`}><Rocket className="w-4 h-4" /></Button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Mappe & Percorsi" onClick={() => setMapsFor(row.id)} data-testid={`maps-${row.id}`}><MapIcon className="w-4 h-4" /></Button>
      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Aggiungi a Google Calendar" onClick={() => syncCal(row)} data-testid={`calsync-${row.id}`}><CalendarPlus className="w-4 h-4" /></Button>
    </>
  );

  return (
    <>
      <EntityManager title="Eventi" subtitle="Gestione multi-evento, mappe e sincronizzazione calendario"
        endpoint="/events" fields={fields} columns={columns} entityLabel="evento" testid="event"
        searchKeys={["nome", "citta", "tipologia"]} rowActions={rowActions} guardCreate={guardCreate} />
      {mapsFor && <MapsDialog eventId={mapsFor} open={!!mapsFor} onOpenChange={(o) => !o && setMapsFor(null)} />}
      {availFor && <AvailabilityDialog eventId={availFor} open={!!availFor} onOpenChange={(o) => !o && setAvailFor(null)} />}
      {creditFor && <EventCreditDialog eventId={creditFor} open={!!creditFor} onOpenChange={(o) => { if (!o) { setCreditFor(null); refreshBalance(); } }} />}
      <Dialog open={noCredits} onOpenChange={setNoCredits}>
        <DialogContent className="max-w-md" data-testid="event-no-credits-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Coins className="w-5 h-5 text-tiffany-active" />Crediti insufficienti</DialogTitle>
            <DialogDescription>Per creare un nuovo evento devi avere almeno 1 credito disponibile. Il tuo saldo è {balRef.current?.balance ?? 0} crediti.</DialogDescription>
          </DialogHeader>
          <Button onClick={() => { setNoCredits(false); setRecharge(true); }} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-no-credits-recharge"><Coins className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>
        </DialogContent>
      </Dialog>
      <RechargeDialog open={recharge} onClose={() => { setRecharge(false); refreshBalance(); }} />
    </>
  );
}
