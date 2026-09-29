import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, fileUrl } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import RouteMapDialog from "@/components/RouteMapDialog";
import {
  ArrowLeft, CalendarDays, MapPin, Clock, Users, UserCog, Navigation, Map as MapIcon,
  CalendarPlus, BedDouble, UtensilsCrossed, ClipboardList, Route as RouteIcon, ExternalLink,
} from "lucide-react";

// Stato OPERATIVO (mai lo stato commerciale/iniziale: 'da_contattare' non va mai mostrato).
const OP_STATO = {
  disponibilita_richiesta: { label: "Disponibilità richiesta", color: "blue" },
  disponibile: { label: "Disponibile", color: "green" },
  da_riconfermare: { label: "Da riconfermare", color: "orange" },
  confermato: { label: "Confermato", color: "green" },
  non_disponibile: { label: "Non disponibile", color: "red" },
  rinunciato: { label: "Rinunciato", color: "red" },
};
const CAT_LABEL = { staff: "Staff", collaboratore: "Staff", volontario: "Volontario" };

// Costruisce un link Google Maps: usa quello esplicito, altrimenti cerca per indirizzo.
const gmaps = (explicit, address) =>
  explicit || (address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}` : null);

function Row({ icon: Icon, label, value }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-2 text-sm">
      <Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
      <span className="text-slate-500 min-w-[92px]">{label}</span>
      <span className="text-slate-800 font-medium">{value}</span>
    </div>
  );
}

function Block({ title, children, icon: Icon, testid }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm" data-testid={testid}>
      <div className="flex items-center gap-2 mb-3"><Icon className="w-5 h-5 text-tiffany-active" /><h2 className="font-display font-bold text-slate-900">{title}</h2></div>
      {children}
    </div>
  );
}

function GMapsButton({ url }) {
  if (!url) return null;
  return (
    <a href={url} target="_blank" rel="noreferrer" data-testid="open-gmaps"
      className="inline-flex items-center gap-1.5 text-xs font-semibold text-tiffany-active hover:underline mt-1">
      <Navigation className="w-3.5 h-3.5" />Apri in Google Maps
    </a>
  );
}

export default function VolunteerEvent() {
  const { id } = useParams();
  const nav = useNavigate();
  const [d, setD] = useState(null);
  const [route, setRoute] = useState(null); // { gpxUrl, title }

  useEffect(() => {
    api.get(`/me/events/${id}`).then(({ data }) => setD(data)).catch(() => { toast.error("Evento non trovato"); nav("/app"); });
  }, [id, nav]);

  if (!d) return <div className="text-slate-400 text-center py-10">Caricamento...</div>;
  const { event, presence, shifts, team, team_leader, colleagues, maps, lodgings = [], meals = [] } = d;
  const giorni = event.giorni_descrizioni && Object.keys(event.giorni_descrizioni).length
    ? Object.entries(event.giorni_descrizioni).sort(([a], [b]) => a.localeCompare(b)) : [];

  const syncEvent = async () => { try { const { data } = await api.post(`/me/events/${id}/calendar-sync`); toast.success("Aggiunto a Google Calendar"); if (data.html_link) window.open(data.html_link, "_blank"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const syncShift = async (sid) => { try { const { data } = await api.post(`/me/shifts/${sid}/calendar-sync`); toast.success("Turno aggiunto a Google Calendar"); if (data.html_link) window.open(data.html_link, "_blank"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

  const arrivo = [presence.data_arrivo, presence.ora_arrivo].filter(Boolean).join(" ");
  const partenza = [presence.data_partenza, presence.ora_partenza].filter(Boolean).join(" ");
  const eventAddr = [event.localita, event.indirizzo, event.citta].filter(Boolean).join(", ");

  return (
    <div className="space-y-4 animate-fade-up pb-8">
      <button onClick={() => nav("/app")} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800" data-testid="vol-back"><ArrowLeft className="w-4 h-4" />Indietro</button>

      {/* EVENTO */}
      <div className="bg-slate-900 rounded-2xl p-6 text-white relative overflow-hidden" data-testid="vol-event-header">
        <div className="absolute -right-16 -top-16 w-52 h-52 rounded-full bg-tiffany/20 blur-2xl" />
        <div className="relative">
          <div className="text-[11px] font-semibold tracking-wide text-tiffany uppercase mb-2">La mia partecipazione</div>
          <div className="flex items-start gap-4">
            {event.logo_url && <img src={fileUrl(event.logo_url)} alt="" className="w-14 h-14 rounded-xl object-contain bg-white/10 p-1 shrink-0" />}
            <div className="min-w-0">
              <h1 className="font-display text-2xl font-bold leading-tight">{event.nome}</h1>
              <div className="flex items-center gap-1.5 text-slate-300 text-sm mt-2"><CalendarDays className="w-4 h-4" />{event.data_inizio}{event.data_fine && event.data_fine !== event.data_inizio ? ` → ${event.data_fine}` : ""}{event.ora_inizio ? ` · ${event.ora_inizio}` : ""}</div>
              {eventAddr && <div className="flex items-center gap-1.5 text-slate-300 text-sm mt-1"><MapPin className="w-4 h-4" />{eventAddr}</div>}
            </div>
          </div>
          {event.descrizione && <p className="text-slate-300 text-sm mt-3">{event.descrizione}</p>}
          <div className="flex flex-wrap gap-2 mt-4">
            <Button onClick={syncEvent} data-testid="vol-sync-event" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><CalendarPlus className="w-4 h-4 mr-1.5" />Aggiungi a Google Calendar</Button>
            {gmaps(null, eventAddr) && <a href={gmaps(null, eventAddr)} target="_blank" rel="noreferrer" data-testid="vol-event-gmaps" className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-white/10 hover:bg-white/20 text-white text-sm font-semibold"><Navigation className="w-4 h-4" />Apri in Google Maps</a>}
          </div>
        </div>
      </div>

      {/* IL MIO INCARICO */}
      <Block title="Il mio incarico" icon={UserCog} testid="vol-incarico">
        <div className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            {presence.categoria && <StatusBadge color={presence.categoria === "volontario" ? "green" : "blue"}>{CAT_LABEL[presence.categoria] || presence.categoria}</StatusBadge>}
            {OP_STATO[presence.stato] && <StatusBadge color={OP_STATO[presence.stato].color} data-testid="vol-op-stato">{OP_STATO[presence.stato].label}</StatusBadge>}
          </div>
          <Row icon={UserCog} label="Ruolo" value={presence.ruolo} />
          <Row icon={MapIcon} label="Area" value={presence.area} />
          <Row icon={Users} label="Team" value={team?.nome} />
          <Row icon={UserCog} label="Team Leader" value={team_leader ? `${team_leader.nome} ${team_leader.cognome || ""}`.trim() : null} />
          <Row icon={UserCog} label="Referente" value={presence.responsabile} />
          <Row icon={MapPin} label="Luogo" value={presence.luogo_operativo || team?.luogo_operativo} />
          <Row icon={Navigation} label="Ritrovo" value={presence.punto_ritrovo || team?.punto_ritrovo} />
          <Row icon={Clock} label="Arrivo" value={arrivo} />
          <Row icon={Clock} label="Partenza" value={partenza} />
          {presence.note_operative && <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 mt-2 whitespace-pre-wrap">{presence.note_operative}</p>}
        </div>
      </Block>

      {/* I MIEI TURNI */}
      <Block title="I miei turni" icon={Clock} testid="vol-turni">
        {shifts.length === 0 ? <p className="text-sm text-slate-400">Nessun turno assegnato.</p> : (
          <div className="space-y-3">
            {shifts.map((s) => (
              <div key={s.id} className="border border-slate-200 rounded-xl p-3" data-testid={`vol-shift-${s.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-slate-800 text-sm">{s.data}{s.ora_inizio ? ` · ${s.ora_inizio}${s.ora_fine ? `–${s.ora_fine}` : ""}` : ""}</div>
                  <Button size="sm" variant="outline" onClick={() => syncShift(s.id)} data-testid={`vol-sync-shift-${s.id}`} className="h-7 text-xs shrink-0"><CalendarPlus className="w-3.5 h-3.5 mr-1" />Calendar</Button>
                </div>
                {(s.ruolo || s.area) && <div className="text-xs text-slate-600 mt-1 font-medium">{[s.ruolo, s.area].filter(Boolean).join(" · ")}</div>}
                {(s.luogo || s.punto_ritrovo) && <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-1"><MapPin className="w-3 h-3" />{[s.luogo, s.punto_ritrovo && `Ritrovo: ${s.punto_ritrovo}`].filter(Boolean).join(" · ")}</div>}
                {s.note && <div className="text-xs text-slate-500 mt-1 whitespace-pre-wrap">{s.note}</div>}
              </div>
            ))}
          </div>
        )}
      </Block>

      {/* BRIEFING */}
      {(giorni.length > 0 || event.note) && (
        <Block title="Briefing evento" icon={ClipboardList} testid="vol-briefing">
          <div className="space-y-3">
            {giorni.map(([day, desc]) => (
              <div key={day} className="border-l-2 border-tiffany pl-3">
                <div className="text-xs font-semibold text-slate-700">{day}</div>
                <p className="text-sm text-slate-600 whitespace-pre-wrap">{desc}</p>
              </div>
            ))}
            {event.note && <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 whitespace-pre-wrap">{event.note}</p>}
          </div>
        </Block>
      )}

      {/* PERCORSI E MAPPE */}
      {maps.length > 0 && (
        <Block title="Percorsi e mappe" icon={MapIcon} testid="vol-mappe">
          <div className="space-y-3">
            {maps.map((m) => {
              const mapsLink = gmaps(m.google_maps_url, null) || (m.url_esterno && m.url_esterno.includes("google.") ? m.url_esterno : null);
              return (
                <div key={m.id} className="border border-slate-200 rounded-xl p-3" data-testid={`vol-map-${m.id}`}>
                  <div className="font-semibold text-slate-800 text-sm">{m.nome}{m.tipologia ? ` · ${m.tipologia}` : ""}{m.distanza ? ` · ${m.distanza} km` : ""}</div>
                  {m.descrizione && <p className="text-xs text-slate-500 mt-0.5 whitespace-pre-wrap">{m.descrizione}</p>}
                  {m.immagine_url && <img src={fileUrl(m.immagine_url)} alt="" className="mt-2 rounded-lg w-full object-cover max-h-64" />}
                  <div className="flex flex-wrap items-center gap-2 mt-2">
                    {m.gpx_url && <Button size="sm" onClick={() => setRoute({ gpxUrl: m.gpx_url, title: m.nome })} data-testid={`vol-view-route-${m.id}`} className="h-8 text-xs bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><RouteIcon className="w-3.5 h-3.5 mr-1" />Visualizza percorso</Button>}
                    {mapsLink && <a href={mapsLink} target="_blank" rel="noreferrer" data-testid={`vol-map-gmaps-${m.id}`} className="inline-flex items-center gap-1.5 text-xs font-semibold text-tiffany-active hover:underline"><Navigation className="w-3.5 h-3.5" />Apri in Google Maps</a>}
                    {m.pdf_url && <a href={fileUrl(m.pdf_url)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:underline"><ExternalLink className="w-3.5 h-3.5" />PDF</a>}
                    {m.url_esterno && !(m.url_esterno.includes("google.")) && <a href={m.url_esterno} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-slate-500 hover:underline"><ExternalLink className="w-3.5 h-3.5" />Link</a>}
                  </div>
                </div>
              );
            })}
          </div>
        </Block>
      )}

      {/* LA MIA OSPITALITÀ */}
      {lodgings.length > 0 && (
        <Block title="La mia ospitalità" icon={BedDouble} testid="vol-ospitalita">
          <div className="space-y-3">
            {lodgings.map((l, i) => {
              const st = l.struttura || {};
              const addr = st.indirizzo || l.indirizzo;
              const fullAddr = [st.nome || l.struttura_nome, addr, st.citta].filter(Boolean).join(", ");
              return (
                <div key={l.id || i} className="border border-slate-200 rounded-xl p-3" data-testid={`vol-lodging-${l.id || i}`}>
                  <div className="font-semibold text-slate-800 text-sm">{st.nome || l.struttura_nome || "Struttura"}{l.tipo_struttura ? ` · ${l.tipo_struttura}` : ""}</div>
                  <div className="mt-1 space-y-1">
                    <Row icon={MapPin} label="Indirizzo" value={addr} />
                    <Row icon={CalendarDays} label="Check-in" value={l.check_in} />
                    <Row icon={CalendarDays} label="Check-out" value={l.check_out} />
                    <Row icon={BedDouble} label="Camera" value={l.tipo_camera} />
                  </div>
                  {l.note && <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 mt-2 whitespace-pre-wrap">{l.note}</p>}
                  <GMapsButton url={gmaps(st.google_maps_url, fullAddr)} />
                </div>
              );
            })}
          </div>
        </Block>
      )}

      {/* I MIEI PASTI */}
      {meals.length > 0 && (
        <Block title="I miei pasti" icon={UtensilsCrossed} testid="vol-pasti">
          <div className="space-y-3">
            {meals.map((m, i) => {
              const st = m.struttura || {};
              const luogo = st.nome || m.struttura_nome || m.luogo;
              const fullAddr = [luogo, st.indirizzo || m.indirizzo, st.citta].filter(Boolean).join(", ");
              return (
                <div key={m.id || i} className="border border-slate-200 rounded-xl p-3" data-testid={`vol-meal-${m.id || i}`}>
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="font-semibold text-slate-800 text-sm capitalize">{[m.data, m.tipo_pasto].filter(Boolean).join(" · ")}</div>
                    {m.orario && <span className="text-xs text-slate-500">{m.orario}</span>}
                  </div>
                  <div className="mt-1 space-y-1">
                    <Row icon={MapPin} label="Luogo" value={luogo} />
                    <Row icon={UtensilsCrossed} label="Servizio" value={m.tipologia_servizio} />
                  </div>
                  {m.note && <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 mt-2 whitespace-pre-wrap">{m.note}</p>}
                  <GMapsButton url={gmaps(st.google_maps_url, fullAddr)} />
                </div>
              );
            })}
          </div>
        </Block>
      )}

      {/* IL MIO TEAM */}
      {colleagues.length > 0 && (
        <Block title="Il mio Team" icon={Users} testid="vol-team">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {colleagues.map((c, i) => (
              <div key={i} className="flex items-center gap-3 border border-slate-200 rounded-xl p-3">
                {c.foto_url ? <img src={fileUrl(c.foto_url)} alt="" className="w-10 h-10 rounded-full object-cover" /> : <div className="w-10 h-10 rounded-full bg-tiffany-light flex items-center justify-center text-tiffany-fg font-bold">{(c.nome || "?")[0]}</div>}
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-800 truncate">{c.nome} {c.cognome}</div>
                  <div className="text-xs text-slate-500">{c.ruolo}{c.is_leader ? " · Team Leader" : ""}</div>
                </div>
              </div>
            ))}
          </div>
        </Block>
      )}

      <RouteMapDialog open={!!route} onOpenChange={(o) => !o && setRoute(null)} gpxUrl={route?.gpxUrl} title={route?.title} />
    </div>
  );
}
