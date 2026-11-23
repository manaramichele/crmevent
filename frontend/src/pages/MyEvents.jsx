import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { CalendarDays, MapPin, Phone, LogOut, BadgeCheck } from "lucide-react";

const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" }) : "");

function EventCard({ x }) {
  const e = x.event;
  const where = [e.localita, e.indirizzo, e.citta, e.provincia].filter(Boolean).join(", ");
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3" data-testid={`my-event-${x.assignment_id}`}>
      <div className="font-display text-xl font-bold text-slate-900">{e.nome}{e.edizione ? ` · ${e.edizione}` : ""}</div>
      <div className="inline-flex items-center gap-2 rounded-lg bg-tiffany/10 text-slate-800 px-3 py-1.5 text-sm" data-testid={`my-event-role-${x.assignment_id}`}>
        <BadgeCheck className="w-4 h-4 text-tiffany-active" />Il tuo incarico: <b>{x.incarico || "da definire"}</b></div>
      {x.note && <p className="text-sm text-slate-600 whitespace-pre-line">{x.note}</p>}
      {x.info.includes("orari") && e.data_inizio && <div className="flex gap-2 text-sm text-slate-600"><CalendarDays className="w-4 h-4 mt-0.5" />{d(e.data_inizio)}{e.data_fine && e.data_fine !== e.data_inizio ? ` – ${d(e.data_fine)}` : ""}{e.ora_inizio ? ` · ${e.ora_inizio}${e.ora_fine ? `–${e.ora_fine}` : ""}` : ""}</div>}
      {x.info.includes("luogo") && where && <div className="flex gap-2 text-sm text-slate-600"><MapPin className="w-4 h-4 mt-0.5" />{where}</div>}
      {x.info.includes("descrizione") && e.descrizione && <p className="text-sm text-slate-700 whitespace-pre-line">{e.descrizione}</p>}
      {x.info.includes("contatti") && (e.email || e.telefono || e.responsabile) && <div className="flex gap-2 text-sm text-slate-600"><Phone className="w-4 h-4 mt-0.5" />{[e.responsabile, e.telefono, e.email].filter(Boolean).join(" · ")}</div>}
    </div>
  );
}

export default function MyEvents() {
  const { logout } = useAuth();
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/my-event-access").then(({ data: x }) => setData(x)).catch(() => setData({ events: [] })); }, []);
  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-2xl mx-auto p-4 sm:p-8 space-y-5" data-testid="my-events-page">
        <div className="flex items-center justify-between gap-3">
          <div><div className="text-xs font-semibold uppercase text-slate-500">{data?.org_name}</div><h1 className="font-display text-3xl font-bold text-slate-900">I miei eventi</h1></div>
          <Button variant="outline" onClick={logout} data-testid="my-events-logout"><LogOut className="w-4 h-4 mr-1.5" />Esci</Button>
        </div>
        {!data && <p className="text-slate-400">Caricamento...</p>}
        {data?.events.length === 0 && <p className="text-slate-500" data-testid="my-events-empty">Al momento non hai eventi assegnati.</p>}
        {data?.events.map((x) => <EventCard key={x.assignment_id} x={x} />)}
      </div>
    </div>
  );
}
