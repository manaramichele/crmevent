import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { StatusBadge } from "@/components/crm";
import { CalendarDays, MapPin, ChevronRight } from "lucide-react";

const today = new Date().toISOString().slice(0, 10);

// Stato OPERATIVO della persona nell'evento (distinto dallo stato commerciale del Lead).
// "da_contattare" è lo stato iniziale/commerciale e non viene mostrato in dashboard:
// il badge appare solo quando esiste uno stato operativo realmente utile all'utente.
const OP_STATO = {
  disponibilita_richiesta: { label: "Disponibilità richiesta", color: "blue" },
  disponibile: { label: "Disponibile", color: "green" },
  da_riconfermare: { label: "Da riconfermare", color: "orange" },
  confermato: { label: "Confermato", color: "green" },
  non_disponibile: { label: "Non disponibile", color: "red" },
  rinunciato: { label: "Rinunciato", color: "red" },
};

export default function VolunteerDashboard() {
  const [items, setItems] = useState(null);
  const nav = useNavigate();
  useEffect(() => { api.get("/me/events").then(({ data }) => setItems(data.events)).catch(() => setItems([])); }, []);

  if (items === null) return <div className="text-slate-400 text-center py-10">Caricamento...</div>;

  const upcoming = items.filter((x) => (x.event.data_fine || x.event.data_inizio || "") >= today);
  const past = items.filter((x) => (x.event.data_fine || x.event.data_inizio || "") < today);
  const next = upcoming[0];

  const Card = ({ x, highlight }) => (
    <button onClick={() => nav(`/evento/${x.event.id}`)} data-testid={`vol-event-${x.event.id}`}
      className={`w-full text-left bg-white rounded-2xl border p-5 shadow-sm hover:shadow-md transition-all ${highlight ? "border-tiffany ring-2 ring-tiffany/30" : "border-slate-200"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {highlight && <div className="text-xs font-semibold text-tiffany-active uppercase tracking-wide mb-1">Prossimo evento</div>}
          <div className="font-display font-bold text-lg text-slate-900 truncate">{x.event.nome}</div>
          <div className="flex items-center gap-1.5 text-sm text-slate-500 mt-1"><CalendarDays className="w-4 h-4" />{x.event.data_inizio}{x.event.data_fine && x.event.data_fine !== x.event.data_inizio ? ` → ${x.event.data_fine}` : ""}</div>
          {x.event.citta && <div className="flex items-center gap-1.5 text-sm text-slate-500 mt-0.5"><MapPin className="w-4 h-4" />{x.event.localita || x.event.citta}</div>}
          <div className="mt-3 flex flex-wrap gap-2">
            {x.presence.ruolo && <StatusBadge color="tiffany">{x.presence.ruolo}</StatusBadge>}
            {OP_STATO[x.presence.stato] && <StatusBadge color={OP_STATO[x.presence.stato].color} data-testid="vol-op-stato">{OP_STATO[x.presence.stato].label}</StatusBadge>}
          </div>
        </div>
        <ChevronRight className="w-5 h-5 text-slate-300 shrink-0" />
      </div>
    </button>
  );

  return (
    <div className="space-y-5 animate-fade-up">
      <h1 className="font-display text-2xl font-bold text-slate-900">I miei eventi</h1>
      {items.length === 0 && <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center text-slate-400">Non hai ancora eventi assegnati.</div>}
      {next && <Card x={next} highlight />}
      {upcoming.slice(1).map((x) => <Card key={x.event.id} x={x} />)}
      {past.length > 0 && <>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 pt-2">Storico</h2>
        {past.map((x) => <Card key={x.event.id} x={x} />)}
      </>}
    </div>
  );
}
