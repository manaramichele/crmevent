import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { fileUrl, StatusBadge, formatDateRange } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import MapsLink from "@/components/MapsLink";
import {
  ArrowLeft, RefreshCw, FileDown, History, Presentation, CheckCircle2, AlertTriangle,
  Users, Map as MapIcon, CalendarClock, Utensils, Shield, UploadCloud,
  ChevronLeft, ChevronRight, X, Trash2, Clock, MapPin, Phone, Mail, BedDouble,
} from "lucide-react";

const CAT_LABEL = { staff: "Staff", volontario: "Volontario", collaboratore: "Collaboratore", referente: "Referente", team: "Team" };
const CAT_COLOR = { staff: "tiffany", volontario: "blue", collaboratore: "gray", referente: "green", team: "orange" };

function pctColor(p) {
  if (p >= 90) return { bar: "bg-emerald-500", text: "text-emerald-600", ring: "ring-emerald-200" };
  if (p >= 70) return { bar: "bg-tiffany", text: "text-tiffany-fg", ring: "ring-tiffany-border" };
  if (p >= 50) return { bar: "bg-amber-500", text: "text-amber-600", ring: "ring-amber-200" };
  return { bar: "bg-red-500", text: "text-red-600", ring: "ring-red-200" };
}

function StatCard({ icon: Icon, label, value, tone = "slate" }) {
  const tones = {
    slate: "text-slate-700 bg-slate-100", tiffany: "text-tiffany-fg bg-tiffany-light",
    blue: "text-sky-700 bg-sky-50", red: "text-red-600 bg-red-50", orange: "text-amber-700 bg-amber-50",
  };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3" data-testid={`stat-${label}`}>
      <div className={`h-10 w-10 rounded-lg flex items-center justify-center shrink-0 ${tones[tone]}`}><Icon className="w-5 h-5" /></div>
      <div className="min-w-0">
        <div className="text-2xl font-bold text-slate-900 leading-none">{value}</div>
        <div className="text-xs text-slate-500 mt-1 truncate">{label}</div>
      </div>
    </div>
  );
}

function Section({ id, icon: Icon, title, count, children }) {
  return (
    <section id={id} className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden briefing-section" data-testid={`briefing-section-${id}`}>
      <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-100 bg-slate-50/60">
        <Icon className="w-4 h-4 text-tiffany-active" />
        <h3 className="text-sm font-bold text-slate-800 font-display uppercase tracking-wide">{title}</h3>
        {count != null && <span className="ml-auto text-xs font-semibold text-slate-400">{count}</span>}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

const Empty = ({ text }) => <p className="text-sm text-slate-400 italic">{text}</p>;

function CoverHeader({ event }) {
  const dates = [event.data_inizio, event.data_fine].filter(Boolean);
  const dateStr = dates.length === 2 && dates[0] !== dates[1] ? `${dates[0]} → ${dates[1]}` : (dates[0] || "Date da definire");
  const luogo = [event.localita, event.citta].filter(Boolean).join(" · ");
  return (
    <div className="flex items-center gap-5 bg-gradient-to-br from-slate-900 to-slate-700 text-white rounded-xl p-6 briefing-cover" data-testid="briefing-cover">
      {event.logo_url ? (
        <div className="h-20 w-32 bg-white/95 rounded-lg flex items-center justify-center overflow-hidden shrink-0">
          <img src={fileUrl(event.logo_url)} alt="Logo evento" className="max-h-full max-w-full object-contain" data-testid="briefing-logo" />
        </div>
      ) : null}
      <div className="min-w-0">
        <div className="text-xs uppercase tracking-widest text-tiffany font-semibold mb-1">Briefing operativo</div>
        <h1 className="text-2xl md:text-3xl font-bold font-display leading-tight truncate">{event.nome}{event.edizione ? ` · ${event.edizione}` : ""}</h1>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm text-slate-200">
          <span className="inline-flex items-center gap-1.5"><CalendarClock className="w-4 h-4" />{dateStr}</span>
          {luogo && <span className="inline-flex items-center gap-1.5"><MapPin className="w-4 h-4" />{luogo}</span>}
          {event.responsabile && <span className="inline-flex items-center gap-1.5"><Shield className="w-4 h-4" />{event.responsabile}</span>}
        </div>
      </div>
    </div>
  );
}

function BriefingBody({ data }) {
  const { event, sections, stats } = data;
  const unassignedStaff = sections.staff.filter((s) => !s.team_id);
  return (
    <div className="space-y-5 briefing-print-body">
      <CoverHeader event={event} />

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard icon={Users} label="Staff" value={stats.staff_count} tone="tiffany" />
        <StatCard icon={Users} label="Volontari" value={stats.volontari_count} tone="blue" />
        <StatCard icon={Shield} label="Team" value={stats.teams_count} tone="orange" />
        <StatCard icon={CalendarClock} label="Turni" value={stats.turni_count} />
        <StatCard icon={AlertTriangle} label="Turni scoperti" value={stats.turni_scoperti} tone={stats.turni_scoperti ? "red" : "slate"} />
        <StatCard icon={MapIcon} label="Mappe" value={stats.mappe_count} />
        <StatCard icon={Utensils} label="Pernottamenti" value={stats.pernottamenti} />
        <StatCard icon={Utensils} label="Pasti" value={stats.pasti} />
      </div>

      <Section id="teams" icon={Shield} title="Team & responsabili" count={sections.teams.length}>
        {sections.teams.length === 0 ? <Empty text="Nessun team creato per questo evento." /> : (
          <div className="grid gap-3 md:grid-cols-2">
            {sections.teams.map((t) => (
              <div key={t.id} className="border border-slate-200 rounded-lg p-4" data-testid={`briefing-team-${t.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold text-slate-800">{t.nome}</div>
                  {t.area && <StatusBadge color="gray">{t.area}</StatusBadge>}
                </div>
                <div className="mt-1 text-sm text-slate-600">
                  Responsabile: {t.responsabile
                    ? <span className="font-medium text-slate-800">{t.responsabile.nome} {t.responsabile.cognome || ""}{t.responsabile.telefono ? ` · ${t.responsabile.telefono}` : ""}</span>
                    : <span className="text-amber-600 font-medium">non assegnato</span>}
                </div>
                {(t.luogo_operativo || t.punto_ritrovo) && (
                  <div className="mt-1 text-xs text-slate-500 flex flex-wrap gap-x-3">
                    {t.luogo_operativo && <span><MapPin className="w-3 h-3 inline mr-0.5" />{t.luogo_operativo}</span>}
                    {t.punto_ritrovo && <span><Clock className="w-3 h-3 inline mr-0.5" />{t.punto_ritrovo}</span>}
                  </div>
                )}
                <div className="mt-2 flex gap-1.5">
                  <StatusBadge color="tiffany">{t.staff_count} staff</StatusBadge>
                  <StatusBadge color="blue">{t.volontari_count} volontari</StatusBadge>
                </div>
                {t.descrizione && t.descrizione.trim() && (
                  <div className="mt-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-900 whitespace-pre-wrap" data-testid={`briefing-team-desc-${t.id}`}>{t.descrizione}</div>
                )}
                {t.membri.filter((m) => m.categoria !== "volontario").length > 0 && (
                  <div className="mt-2 text-xs text-slate-600">{t.membri.filter((m) => m.categoria !== "volontario").map((m) => `${m.nome} ${m.cognome || ""}`.trim()).join(", ")}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section id="staff" icon={Users} title="Staff & volontari non assegnati a un Team" count={unassignedStaff.length}>
        {unassignedStaff.length === 0 ? <Empty text="Tutte le persone collegate all'evento sono già assegnate a un Team." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-200 text-left text-slate-500">
                <th className="py-2 pr-3 font-semibold">Nome</th><th className="py-2 pr-3 font-semibold">Ruolo</th>
                <th className="py-2 pr-3 font-semibold">Team</th><th className="py-2 pr-3 font-semibold">Referente</th>
                <th className="py-2 pr-3 font-semibold">Contatti</th><th className="py-2 pr-3 font-semibold">Arrivo/Partenza</th>
              </tr></thead>
              <tbody>
                {unassignedStaff.map((s) => (
                  <tr key={s.persona_id} className="border-b border-slate-100 align-top" data-testid={`briefing-staff-${s.persona_id}`}>
                    <td className="py-2 pr-3">
                      <div className="font-medium text-slate-800">{s.nome} {s.cognome || ""}</div>
                      <StatusBadge color={CAT_COLOR[s.categoria] || "gray"}>{CAT_LABEL[s.categoria] || s.categoria || "—"}</StatusBadge>
                    </td>
                    <td className="py-2 pr-3 text-slate-600">{s.ruolo || "—"}</td>
                    <td className="py-2 pr-3 text-slate-600">{s.team_nome || "—"}</td>
                    <td className="py-2 pr-3 text-slate-600">{s.responsabile || <span className="text-amber-600">—</span>}</td>
                    <td className="py-2 pr-3 text-slate-600">
                      {s.telefono && <div className="whitespace-nowrap"><Phone className="w-3 h-3 inline mr-1" />{s.telefono}</div>}
                      {s.email && <div className="whitespace-nowrap text-xs"><Mail className="w-3 h-3 inline mr-1" />{s.email}</div>}
                      {!s.telefono && !s.email && "—"}
                    </td>
                    <td className="py-2 pr-3 text-slate-600 text-xs whitespace-nowrap">
                      {s.data_arrivo ? `${s.data_arrivo} ${s.ora_arrivo || ""}` : "—"}<br />
                      {s.data_partenza ? `${s.data_partenza} ${s.ora_partenza || ""}` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section id="shifts" icon={CalendarClock} title="Turni" count={sections.shifts.length}>
        {sections.shifts.length === 0 ? <Empty text="Nessun turno pianificato." /> : (
          <div className="space-y-2">
            {sections.shifts.map((s) => (
              <div key={s.id} className={`flex flex-wrap items-center gap-x-3 gap-y-1 border rounded-lg px-3 py-2 text-sm ${s.coperto ? "border-slate-200" : "border-red-200 bg-red-50"}`} data-testid={`briefing-shift-${s.id}`}>
                <span className="font-medium text-slate-700 whitespace-nowrap"><Clock className="w-3.5 h-3.5 inline mr-1 text-slate-400" />{s.data || "—"} {s.ora_inizio || ""}{s.ora_fine ? `-${s.ora_fine}` : ""}</span>
                {s.area && <StatusBadge color="gray">{s.area}</StatusBadge>}
                {s.ruolo && <span className="text-slate-600">{s.ruolo}</span>}
                {s.luogo && <span className="text-slate-500 text-xs"><MapPin className="w-3 h-3 inline mr-0.5" />{s.luogo}</span>}
                <span className="ml-auto">
                  {s.coperto ? <span className="font-medium text-slate-800">{s.persona_nome}</span> : <StatusBadge color="red">Turno scoperto</StatusBadge>}
                </span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section id="maps" icon={MapIcon} title="Mappe & percorsi" count={sections.maps.length}>
        {sections.maps.length === 0 ? <Empty text="Nessuna mappa o percorso caricato." /> : (
          <div className="grid gap-4 md:grid-cols-2">
            {sections.maps.map((m) => (
              <div key={m.id} className="border border-slate-200 rounded-lg overflow-hidden" data-testid={`briefing-map-${m.id}`}>
                {m.immagine_url && <img src={fileUrl(m.immagine_url)} alt={m.nome} className="w-full h-40 object-cover" />}
                <div className="p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-semibold text-slate-800">{m.nome}</div>
                    {m.distanza != null && m.distanza !== "" && <StatusBadge color="tiffany">{m.distanza} km</StatusBadge>}
                  </div>
                  {m.tipologia && <StatusBadge color="gray">{m.tipologia}</StatusBadge>}
                  {m.descrizione && <p className="text-xs text-slate-500 mt-1">{m.descrizione}</p>}
                  <div className="flex flex-wrap gap-2 mt-2 text-xs">
                    {m.google_maps_url && <a href={m.google_maps_url} target="_blank" rel="noreferrer" className="text-tiffany-active hover:underline">Google Maps</a>}
                    {m.gpx_url && <a href={fileUrl(m.gpx_url)} target="_blank" rel="noreferrer" className="text-tiffany-active hover:underline">GPX</a>}
                    {m.pdf_url && <a href={fileUrl(m.pdf_url)} target="_blank" rel="noreferrer" className="text-tiffany-active hover:underline">PDF</a>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <MealsSection days={sections.meals_by_day} legacy={sections.hospitality} />
      <LodgingSection structures={sections.lodging_structures} />

      <Section id="timeline" icon={CalendarClock} title="Timeline operativa" count={sections.timeline.length}>
        {sections.timeline.length === 0 ? <Empty text="Nessuna attività programmata con data." /> : (
          <div className="space-y-4">
            {sections.timeline.map((d) => (
              <div key={d.data} data-testid={`briefing-timeline-${d.data}`}>
                <div className="text-sm font-semibold text-tiffany-fg mb-1">{d.data}</div>
                <div className="border-l-2 border-tiffany-border pl-3 space-y-1">
                  {d.turni.map((t) => (
                    <div key={t.id} className="text-sm text-slate-600">
                      <span className="font-medium text-slate-700">{t.ora_inizio || ""}{t.ora_fine ? `-${t.ora_fine}` : ""}</span> · {t.area || t.ruolo || "Turno"} {t.coperto ? `— ${t.persona_nome}` : <span className="text-red-500">— scoperto</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

function CompletenessPanel({ completeness }) {
  const c = pctColor(completeness.percent);
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5" data-testid="briefing-completeness">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-slate-800 font-display uppercase tracking-wide">Completezza briefing</h3>
        <span className={`text-2xl font-bold ${c.text}`} data-testid="briefing-percent">{completeness.percent}%</span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-100 overflow-hidden mb-4">
        <div className={`h-full ${c.bar} transition-all`} style={{ width: `${completeness.percent}%` }} />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {completeness.checks.map((ch) => (
          <div key={ch.key} className="flex items-start gap-2 text-sm" data-testid={`check-${ch.key}`}>
            {ch.status === "ok"
              ? <CheckCircle2 className="w-4 h-4 text-emerald-500 mt-0.5 shrink-0" />
              : <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />}
            <div>
              <div className={ch.status === "ok" ? "text-slate-600" : "text-slate-800 font-medium"}>{ch.label}</div>
              {ch.detail && <div className="text-xs text-amber-600">{ch.detail}</div>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PresentationMode({ data, onClose }) {
  const unassignedStaff = data.sections.staff.filter((s) => !s.team_id);
  const deck = [
    { title: null, node: <CoverHeader event={data.event} /> },
    { title: "Panoramica", node: <OverviewGrid stats={data.stats} /> },
    ...(data.sections.teams.length ? [{ title: "Team & responsabili", node: <TeamsDeck teams={data.sections.teams} /> }] : []),
    ...(unassignedStaff.length ? [{ title: "Staff & volontari non assegnati a un Team", node: <StaffDeck staff={unassignedStaff} /> }] : []),
    ...(data.sections.shifts.length ? [{ title: "Turni", node: <ShiftsDeck shifts={data.sections.shifts} /> }] : []),
    ...(data.sections.maps.length ? [{ title: "Mappe & percorsi", node: <MapsDeck maps={data.sections.maps} /> }] : []),
    ...(data.sections.meals_by_day?.length ? [{ title: "Pasti", node: <MealsList days={data.sections.meals_by_day} /> }] : []),
    ...(data.sections.lodging_structures?.length ? [{ title: "Ospitalità", node: <LodgingList structures={data.sections.lodging_structures} /> }] : []),
    ...(data.sections.timeline.length ? [{ title: "Timeline", node: <TimelineDeck timeline={data.sections.timeline} /> }] : []),
  ];
  const [i, setI] = useState(0);
  const prev = useCallback(() => setI((v) => Math.max(0, v - 1)), []);
  const next = useCallback(() => setI((v) => Math.min(deck.length - 1, v + 1)), [deck.length]);
  useEffect(() => {
    const h = (e) => { if (e.key === "ArrowRight") next(); else if (e.key === "ArrowLeft") prev(); else if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [next, prev, onClose]);
  const slide = deck[i];
  return (
    <div className="fixed inset-0 z-[300] bg-white flex flex-col" data-testid="presentation-mode">
      <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200">
        <div className="text-sm font-semibold text-slate-500">{data.event.nome}</div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">{i + 1} / {deck.length}</span>
          <Button variant="ghost" size="icon" onClick={onClose} data-testid="presentation-close"><X className="w-5 h-5" /></Button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-6 md:px-16 py-8">
        <div className="max-w-4xl mx-auto">
          {slide.title && <h2 className="text-3xl font-bold font-display text-slate-900 mb-6">{slide.title}</h2>}
          {slide.node}
        </div>
      </div>
      <div className="flex items-center justify-between px-6 py-3 border-t border-slate-200">
        <Button variant="outline" onClick={prev} disabled={i === 0} data-testid="presentation-prev"><ChevronLeft className="w-4 h-4 mr-1" />Precedente</Button>
        <Button variant="outline" onClick={next} disabled={i === deck.length - 1} data-testid="presentation-next">Successiva<ChevronRight className="w-4 h-4 ml-1" /></Button>
      </div>
    </div>
  );
}

const OverviewGrid = ({ stats }) => (
  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
    <StatCard icon={Users} label="Staff" value={stats.staff_count} tone="tiffany" />
    <StatCard icon={Users} label="Volontari" value={stats.volontari_count} tone="blue" />
    <StatCard icon={Shield} label="Team" value={stats.teams_count} tone="orange" />
    <StatCard icon={CalendarClock} label="Turni" value={stats.turni_count} />
    <StatCard icon={AlertTriangle} label="Turni scoperti" value={stats.turni_scoperti} tone={stats.turni_scoperti ? "red" : "slate"} />
    <StatCard icon={MapIcon} label="Mappe" value={stats.mappe_count} />
  </div>
);
const TeamsDeck = ({ teams }) => (
  <div className="grid gap-4 md:grid-cols-2">
    {teams.map((t) => (
      <div key={t.id} className="border border-slate-200 rounded-xl p-5">
        <div className="text-lg font-semibold text-slate-800">{t.nome}</div>
        <div className="text-sm text-slate-600 mt-1">Responsabile: {t.responsabile ? `${t.responsabile.nome} ${t.responsabile.cognome || ""}` : "—"}</div>
        {t.punto_ritrovo && <div className="text-sm text-slate-500 mt-1"><Clock className="w-3.5 h-3.5 inline mr-1" />{t.punto_ritrovo}</div>}
        {t.descrizione && t.descrizione.trim() && <div className="mt-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-900 whitespace-pre-wrap">{t.descrizione}</div>}
        <div className="mt-2 flex gap-2"><StatusBadge color="tiffany">{t.staff_count} staff</StatusBadge><StatusBadge color="blue">{t.volontari_count} volontari</StatusBadge></div>
      </div>
    ))}
  </div>
);
const StaffDeck = ({ staff }) => (
  <div className="grid gap-2 md:grid-cols-2">
    {staff.map((s) => (
      <div key={s.persona_id} className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2">
        <span className="font-medium text-slate-800">{s.nome} {s.cognome || ""}</span>
        <StatusBadge color={CAT_COLOR[s.categoria] || "gray"}>{CAT_LABEL[s.categoria] || s.categoria}</StatusBadge>
      </div>
    ))}
  </div>
);
const ShiftsDeck = ({ shifts }) => (
  <div className="space-y-2">
    {shifts.map((s) => (
      <div key={s.id} className={`flex items-center justify-between border rounded-lg px-4 py-2 ${s.coperto ? "border-slate-200" : "border-red-200 bg-red-50"}`}>
        <span className="text-slate-700">{s.data} {s.ora_inizio}{s.ora_fine ? `-${s.ora_fine}` : ""} · {s.area || s.ruolo}</span>
        {s.coperto ? <span className="font-medium">{s.persona_nome}</span> : <StatusBadge color="red">Scoperto</StatusBadge>}
      </div>
    ))}
  </div>
);
const MapsDeck = ({ maps }) => (
  <div className="grid gap-4 md:grid-cols-2">
    {maps.map((m) => (
      <div key={m.id} className="border border-slate-200 rounded-xl overflow-hidden">
        {m.immagine_url && <img src={fileUrl(m.immagine_url)} alt={m.nome} className="w-full h-48 object-cover" />}
        <div className="p-3 font-semibold text-slate-800">{m.nome}{m.distanza ? ` · ${m.distanza} km` : ""}</div>
      </div>
    ))}
  </div>
);
const MEAL_LABEL = { colazione: "Colazione", pranzo: "Pranzo", cena: "Cena" };
const ddmm = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}` : "—");
const longDay = (d) => {
  if (!d) return "Data da definire";
  const s = new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const Line = ({ label, children }) => (children ? <div className="text-sm text-slate-600"><span className="text-slate-400">{label}:</span> {children}</div> : null);

function MealsList({ days }) {
  return (
    <div className="space-y-5">
      {days.map((d, di) => (
        <div key={d.data || di} className="break-inside-avoid" data-testid={`briefing-meal-day-${d.data || "nd"}`}>
          <div className="text-sm font-semibold text-tiffany-fg mb-2">{longDay(d.data)}</div>
          <div className="space-y-3 border-l-2 border-tiffany-border pl-3">
            {d.servizi.map((s) => (
              <div key={s.tipo_pasto || "altro"} data-testid={`briefing-meal-${d.data || "nd"}-${s.tipo_pasto || "altro"}`}>
                <div className="font-semibold text-slate-800">{MEAL_LABEL[s.tipo_pasto] || s.tipo_pasto || "Pasto"}</div>
                {s.entries.map((e, i) => (
                  <div key={i} className="mt-1 space-y-0.5">
                    {e.luogo && <div className="text-sm font-medium text-slate-700">{e.luogo}{e.google_maps_url && <span className="ml-2"><MapsLink url={e.google_maps_url} testid={`bmeal-maps-${d.data}-${s.tipo_pasto}-${i}`} /></span>}</div>}
                    <Line label="Indirizzo">{e.indirizzo}</Line>
                    <Line label="Orario">{e.orario}</Line>
                    <Line label="Riferimento">{[e.referente, e.telefono].filter(Boolean).join(" · ")}</Line>
                    <Line label="Persone">{e.persone || null}</Line>
                    <Line label="Esigenze">{Object.entries(e.esigenze || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</Line>
                    <Line label="Note">{e.note}</Line>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const Guest = ({ o }) => (
  <div className="text-sm text-slate-700" data-testid="briefing-guest">
    <span className="font-medium">{`${o.nome || ""} ${o.cognome || ""}`.trim()}</span>
    <span className="text-slate-500"> · check-in {ddmm(o.check_in)} · check-out {ddmm(o.check_out)}</span>
    {o.esterno && <span className="text-xs text-slate-400"> (esterno)</span>}
  </div>
);

function LodgingList({ structures }) {
  return (
    <div className="space-y-4">
      {structures.map((s, si) => (
        <div key={si} className="border border-slate-200 rounded-lg p-4 break-inside-avoid" data-testid={`briefing-structure-${si}`}>
          <div className="font-semibold text-slate-900">{s.nome}{s.google_maps_url && <span className="ml-2"><MapsLink url={s.google_maps_url} testid={`bstruct-maps-${si}`} /></span>}</div>
          <div className="mt-1 space-y-0.5">
            <Line label="Indirizzo">{s.indirizzo}</Line>
            <Line label="Telefono">{s.telefono}</Line>
            <Line label="Riferimento">{[s.referente, s.telefono_referente].filter(Boolean).join(" · ")}</Line>
            <Line label="Note struttura">{s.note}</Line>
          </div>
          <div className="mt-3 space-y-3">
            {s.camere.map((r, ri) => (
              <div key={ri} data-testid={`briefing-room-${si}-${r.numero}`}>
                <div className="text-sm font-semibold text-slate-800">Camera {r.numero}{r.tipo_camera ? ` · ${r.tipo_camera.charAt(0).toUpperCase()}${r.tipo_camera.slice(1)}` : ""}</div>
                <div className="pl-3 border-l-2 border-slate-100 mt-0.5 space-y-0.5">{r.ospiti.map((o, oi) => <Guest key={oi} o={o} />)}</div>
              </div>
            ))}
            {s.da_assegnare.length > 0 && (
              <div data-testid={`briefing-room-${si}-unassigned`}>
                <div className="text-sm font-semibold text-amber-700">Camera da assegnare</div>
                <div className="pl-3 border-l-2 border-amber-100 mt-0.5 space-y-0.5">{s.da_assegnare.map((o, oi) => <Guest key={oi} o={o} />)}</div>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function MealsSection({ days, legacy }) {
  if (!days && legacy) return <LegacyHosp hosp={legacy} />;
  const list = days || [];
  return (
    <Section id="meals" icon={Utensils} title="Pasti" count={list.length}>
      {list.length === 0 ? <Empty text="Nessun pasto assegnato." /> : <MealsList days={list} />}
    </Section>
  );
}

function LodgingSection({ structures }) {
  if (!structures) return null;
  return (
    <Section id="lodging" icon={BedDouble} title="Ospitalità" count={structures.length}>
      {structures.length === 0 ? <Empty text="Nessun pernottamento assegnato." /> : <LodgingList structures={structures} />}
    </Section>
  );
}

// Versioni pubblicate prima della riorganizzazione (formato per persona)
const LegacyHosp = ({ hosp }) => (
  <Section id="hospitality" icon={Utensils} title="Ospitalità & pasti" count={hosp.length}>
    {hosp.length === 0 ? <Empty text="Nessuna ospitalità o pasto assegnato." /> : (
      <div className="space-y-2">
        {hosp.map((h, i) => (
          <div key={i} className="border border-slate-200 rounded-lg px-3 py-2 text-sm" data-testid={`briefing-hosp-${i}`}>
            <span className="font-medium text-slate-800">{h.nome} {h.cognome || ""}</span>
            {h.lodgings.map((l, j) => <div key={j} className="text-xs text-slate-600 mt-1">{l.struttura?.nome || l.struttura_nome || "Struttura"} {l.check_in ? `· ${l.check_in}→${l.check_out || ""}` : ""}</div>)}
            {h.meals.map((m, j) => <div key={`m${j}`} className="text-xs text-slate-600 mt-1">{m.tipo_pasto || "Pasto"} {(m.data_inizio || m.data) ? `· ${formatDateRange(m.data_inizio || m.data, m.data_fine)}` : ""} {m.orario ? `· ${m.orario}` : ""}</div>)}
          </div>
        ))}
      </div>
    )}
  </Section>
);

const TimelineDeck = ({ timeline }) => (
  <div className="space-y-4">
    {timeline.map((d) => (
      <div key={d.data}>
        <div className="text-lg font-semibold text-tiffany-fg">{d.data}</div>
        <div className="border-l-2 border-tiffany-border pl-4 mt-1 space-y-1">
          {d.turni.map((t) => <div key={t.id} className="text-slate-600">{t.ora_inizio} · {t.area || t.ruolo} {t.coperto ? `— ${t.persona_nome}` : "— scoperto"}</div>)}
        </div>
      </div>
    ))}
  </div>
);

export default function Briefing() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [live, setLive] = useState(null);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState(null); // published version being viewed (null = live)
  const [versions, setVersions] = useState([]);
  const [showVersions, setShowVersions] = useState(false);
  const [showPublish, setShowPublish] = useState(false);
  const [presenting, setPresenting] = useState(false);
  const [pubForm, setPubForm] = useState({ titolo: "", note: "" });
  const [publishing, setPublishing] = useState(false);

  const loadLive = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/events/${id}/briefing-live`);
      setLive(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      if (e.response?.status === 404) navigate("/eventi");
    } finally { setLoading(false); }
  }, [id, navigate]);

  const loadVersions = useCallback(async () => {
    try { const { data } = await api.get(`/events/${id}/briefing-versions`); setVersions(data); } catch { /* noop */ }
  }, [id]);

  useEffect(() => { loadLive(); loadVersions(); }, [loadLive, loadVersions]);

  const publish = async () => {
    setPublishing(true);
    try {
      await api.post(`/events/${id}/briefing-versions`, pubForm);
      toast.success("Versione pubblicata");
      setShowPublish(false); setPubForm({ titolo: "", note: "" });
      await loadLive(); await loadVersions();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setPublishing(false); }
  };

  const openVersion = async (v) => {
    try {
      const { data } = await api.get(`/briefing-versions/${v.id}`);
      setViewing(data); setShowVersions(false);
      window.scrollTo({ top: 0 });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const deleteVersion = async (v) => {
    try { await api.delete(`/briefing-versions/${v.id}`); toast.success("Versione eliminata"); await loadVersions(); await loadLive(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  if (loading || !live) return <div className="text-slate-400">Caricamento briefing...</div>;

  const current = viewing ? viewing.content : live;

  return (
    <div className="animate-fade-up briefing-print-area">
      <style>{`
        @media print {
          body * { visibility: hidden !important; }
          .briefing-print-area, .briefing-print-area * { visibility: visible !important; }
          .briefing-print-area { position: absolute; left: 0; top: 0; width: 100%; padding: 0 !important; }
          .no-print { display: none !important; }
          .briefing-section, .briefing-cover { break-inside: avoid; }
          @page { size: A4; margin: 12mm; }
        }
      `}</style>

      {/* Toolbar */}
      <div className="no-print flex flex-wrap items-center gap-2 mb-4">
        <Button variant="ghost" size="sm" onClick={() => navigate("/eventi")} data-testid="briefing-back"><ArrowLeft className="w-4 h-4 mr-1" />Eventi</Button>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {!viewing && <Button variant="outline" size="sm" onClick={loadLive} data-testid="briefing-refresh"><RefreshCw className="w-4 h-4 mr-1.5" />Aggiorna</Button>}
          <Button variant="outline" size="sm" onClick={() => setShowVersions(true)} data-testid="briefing-versions-btn"><History className="w-4 h-4 mr-1.5" />Storico{versions.length ? ` (${versions.length})` : ""}</Button>
          <Button variant="outline" size="sm" onClick={() => setPresenting(true)} data-testid="briefing-present-btn"><Presentation className="w-4 h-4 mr-1.5" />Presentazione</Button>
          <Button variant="outline" size="sm" onClick={() => window.print()} data-testid="briefing-pdf-btn"><FileDown className="w-4 h-4 mr-1.5" />Esporta PDF</Button>
          {!viewing && <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={() => setShowPublish(true)} data-testid="briefing-publish-btn"><UploadCloud className="w-4 h-4 mr-1.5" />Pubblica versione</Button>}
        </div>
      </div>

      {/* Mode banner */}
      {viewing ? (
        <div className="no-print mb-4 flex flex-wrap items-center gap-2 bg-slate-900 text-white rounded-lg px-4 py-2.5 text-sm" data-testid="viewing-version-banner">
          <History className="w-4 h-4 text-tiffany" />
          Stai visualizzando la <span className="font-semibold">versione {viewing.versione}</span> — {viewing.titolo} · snapshot del {new Date(viewing.created_at).toLocaleString("it-IT")}
          <Button variant="secondary" size="sm" className="ml-auto h-7" onClick={() => setViewing(null)} data-testid="back-to-live">Torna alla bozza live</Button>
        </div>
      ) : (
        <div className="no-print mb-4 flex items-center gap-2 text-sm">
          <StatusBadge color="green">BOZZA LIVE</StatusBadge>
          <span className="text-slate-400 text-xs">Dati in tempo reale · generato {new Date(live.generated_at).toLocaleString("it-IT")}</span>
        </div>
      )}

      {/* Stale warning */}
      {!viewing && live.is_stale && (
        <div className="no-print mb-4 flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800" data-testid="stale-warning">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>I dati sono cambiati rispetto all'ultima versione pubblicata (<b>v{live.latest_version?.versione}</b>). Pubblica una nuova versione per aggiornare il documento distribuito.</span>
        </div>
      )}

      {!viewing && <div className="mb-5"><CompletenessPanel completeness={current.completeness} /></div>}

      <BriefingBody data={current} />

      {/* Versions dialog */}
      <Dialog open={showVersions} onOpenChange={setShowVersions}>
        <DialogContent className="max-w-lg" data-testid="versions-dialog">
          <DialogHeader><DialogTitle className="font-display">Storico versioni</DialogTitle><DialogDescription>Snapshot pubblicati del briefing.</DialogDescription></DialogHeader>
          <div className="space-y-2 max-h-[60vh] overflow-y-auto">
            {versions.length === 0 ? <Empty text="Nessuna versione pubblicata." /> : versions.map((v) => (
              <div key={v.id} className="flex items-center justify-between gap-2 border border-slate-200 rounded-lg p-3" data-testid={`version-row-${v.id}`}>
                <div className="min-w-0">
                  <div className="font-medium text-slate-800">v{v.versione} · {v.titolo}</div>
                  <div className="text-xs text-slate-400">{new Date(v.created_at).toLocaleString("it-IT")} · {v.published_by}</div>
                  {v.note && <div className="text-xs text-slate-500 mt-0.5">{v.note}</div>}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button variant="outline" size="sm" onClick={() => openVersion(v)} data-testid={`view-version-${v.id}`}>Visualizza</Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8 text-slate-400 hover:text-red-500" data-testid={`del-version-${v.id}`}><Trash2 className="w-4 h-4" /></Button></AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader><AlertDialogTitle>Eliminare la versione v{v.versione}?</AlertDialogTitle><AlertDialogDescription>Lo snapshot verrà rimosso definitivamente.</AlertDialogDescription></AlertDialogHeader>
                      <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={() => deleteVersion(v)}>Elimina</AlertDialogAction></AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Publish dialog */}
      <Dialog open={showPublish} onOpenChange={setShowPublish}>
        <DialogContent className="max-w-md" data-testid="publish-dialog">
          <DialogHeader><DialogTitle className="font-display">Pubblica versione briefing</DialogTitle><DialogDescription>Crea uno snapshot immutabile dei dati attuali.</DialogDescription></DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1.5"><Label className="text-xs">Titolo versione</Label><Input value={pubForm.titolo} onChange={(e) => setPubForm((f) => ({ ...f, titolo: e.target.value }))} placeholder="es. Briefing definitivo pre-evento" data-testid="publish-titolo" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Note (facoltative)</Label><Textarea value={pubForm.note} onChange={(e) => setPubForm((f) => ({ ...f, note: e.target.value }))} data-testid="publish-note" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPublish(false)}>Annulla</Button>
            <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={publish} disabled={publishing} data-testid="publish-confirm">{publishing ? "Pubblicazione..." : "Pubblica"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {presenting && <PresentationMode data={current} onClose={() => setPresenting(false)} />}
    </div>
  );
}
