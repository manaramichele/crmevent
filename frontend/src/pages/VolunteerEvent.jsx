import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge, fileUrl } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  ArrowLeft, CalendarDays, MapPin, Clock, Users, UserCog, Navigation, Map as MapIcon, CalendarPlus,
} from "lucide-react";

function Row({ icon: Icon, label, value }) {
  if (!value) return null;
  return <div className="flex items-start gap-2 text-sm"><Icon className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" /><span className="text-slate-500 min-w-[90px]">{label}</span><span className="text-slate-800 font-medium">{value}</span></div>;
}

function Block({ title, children, icon: Icon }) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-3"><Icon className="w-5 h-5 text-tiffany-active" /><h2 className="font-display font-bold text-slate-900">{title}</h2></div>
      {children}
    </div>
  );
}

export default function VolunteerEvent() {
  const { id } = useParams();
  const nav = useNavigate();
  const [d, setD] = useState(null);

  useEffect(() => { api.get(`/me/events/${id}`).then(({ data }) => setD(data)).catch(() => { toast.error("Evento non trovato"); nav("/"); }); }, [id, nav]);

  if (!d) return <div className="text-slate-400 text-center py-10">Caricamento...</div>;
  const { event, presence, shifts, team, team_leader, colleagues, maps } = d;

  const syncEvent = async () => { try { const { data } = await api.post(`/me/events/${id}/calendar-sync`); toast.success("Aggiunto a Google Calendar"); if (data.html_link) window.open(data.html_link, "_blank"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const syncShift = async (sid) => { try { const { data } = await api.post(`/me/shifts/${sid}/calendar-sync`); toast.success("Turno aggiunto a Google Calendar"); if (data.html_link) window.open(data.html_link, "_blank"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

  return (
    <div className="space-y-4 animate-fade-up">
      <button onClick={() => nav("/")} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"><ArrowLeft className="w-4 h-4" />Indietro</button>

      <div className="bg-slate-900 rounded-2xl p-6 text-white relative overflow-hidden">
        <div className="absolute -right-16 -top-16 w-52 h-52 rounded-full bg-tiffany/20 blur-2xl" />
        <div className="relative">
          <h1 className="font-display text-2xl font-bold">{event.nome}</h1>
          <div className="flex items-center gap-1.5 text-slate-300 text-sm mt-2"><CalendarDays className="w-4 h-4" />{event.data_inizio}{event.data_fine && event.data_fine !== event.data_inizio ? ` → ${event.data_fine}` : ""}{event.ora_inizio ? ` · ${event.ora_inizio}` : ""}</div>
          {(event.localita || event.citta) && <div className="flex items-center gap-1.5 text-slate-300 text-sm mt-1"><MapPin className="w-4 h-4" />{[event.localita, event.indirizzo, event.citta].filter(Boolean).join(", ")}</div>}
          {event.descrizione && <p className="text-slate-300 text-sm mt-3">{event.descrizione}</p>}
          <Button onClick={syncEvent} data-testid="vol-sync-event" className="mt-4 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><CalendarPlus className="w-4 h-4 mr-1.5" />Aggiungi a Google Calendar</Button>
        </div>
      </div>

      <Block title="La mia presenza" icon={CalendarDays}>
        <div className="space-y-2">
          <Row icon={Clock} label="Arrivo" value={[presence.data_arrivo, presence.ora_arrivo].filter(Boolean).join(" ")} />
          <Row icon={Clock} label="Partenza" value={[presence.data_partenza, presence.ora_partenza].filter(Boolean).join(" ")} />
          <div className="flex items-center gap-2 pt-1"><StatusBadge color={presence.stato === "confermato" ? "green" : "orange"}>{(presence.stato || "").replaceAll("_", " ")}</StatusBadge></div>
        </div>
      </Block>

      <Block title="Il mio ruolo" icon={UserCog}>
        <div className="space-y-2">
          <Row icon={UserCog} label="Ruolo" value={presence.ruolo} />
          <Row icon={MapIcon} label="Area" value={presence.area} />
          <Row icon={Users} label="Team" value={team?.nome} />
          <Row icon={UserCog} label="Team Leader" value={team_leader ? `${team_leader.nome} ${team_leader.cognome || ""}` : null} />
          <Row icon={UserCog} label="Responsabile" value={presence.responsabile} />
          <Row icon={MapPin} label="Luogo" value={presence.luogo_operativo || team?.luogo_operativo} />
          <Row icon={Navigation} label="Ritrovo" value={presence.punto_ritrovo || team?.punto_ritrovo} />
          {presence.note_operative && <p className="text-sm text-slate-600 bg-slate-50 rounded-lg p-3 mt-2">{presence.note_operative}</p>}
        </div>
      </Block>

      <Block title="I miei turni" icon={Clock}>
        {shifts.length === 0 ? <p className="text-sm text-slate-400">Nessun turno assegnato.</p> : (
          <div className="space-y-3">
            {shifts.map((s) => (
              <div key={s.id} className="border border-slate-200 rounded-xl p-3" data-testid={`vol-shift-${s.id}`}>
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-slate-800 text-sm">{s.data} · {s.ora_inizio}–{s.ora_fine}</div>
                  <Button size="sm" variant="outline" onClick={() => syncShift(s.id)} data-testid={`vol-sync-shift-${s.id}`} className="h-7 text-xs"><CalendarPlus className="w-3.5 h-3.5 mr-1" />Calendar</Button>
                </div>
                <div className="text-xs text-slate-500 mt-1">{[s.ruolo, s.area, s.luogo].filter(Boolean).join(" · ")}</div>
              </div>
            ))}
          </div>
        )}
      </Block>

      {colleagues.length > 0 && (
        <Block title="Il mio Team" icon={Users}>
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

      {maps.length > 0 && (
        <Block title="Mappe e percorsi" icon={MapIcon}>
          <div className="space-y-3">
            {maps.map((m) => (
              <div key={m.id} className="border border-slate-200 rounded-xl p-3" data-testid={`vol-map-${m.id}`}>
                <div className="font-semibold text-slate-800 text-sm">{m.nome}{m.tipologia ? ` · ${m.tipologia}` : ""}</div>
                {m.descrizione && <p className="text-xs text-slate-500 mt-0.5">{m.descrizione}</p>}
                {m.immagine_url && <img src={fileUrl(m.immagine_url)} alt="" className="mt-2 rounded-lg w-full object-cover max-h-64" />}
                <div className="flex flex-wrap gap-2 mt-2">
                  {m.pdf_url && <a href={fileUrl(m.pdf_url)} target="_blank" rel="noreferrer" className="text-xs text-tiffany-active hover:underline">Apri PDF</a>}
                  {m.file_url && <a href={fileUrl(m.file_url)} target="_blank" rel="noreferrer" className="text-xs text-tiffany-active hover:underline">Scarica file</a>}
                  {m.url_esterno && <a href={m.url_esterno} target="_blank" rel="noreferrer" className="text-xs text-tiffany-active hover:underline">Link esterno</a>}
                  {m.google_maps_url && <a href={m.google_maps_url} target="_blank" rel="noreferrer" className="text-xs inline-flex items-center gap-1 text-tiffany-active hover:underline"><Navigation className="w-3.5 h-3.5" />Apri in Google Maps</a>}
                </div>
              </div>
            ))}
          </div>
        </Block>
      )}
    </div>
  );
}
