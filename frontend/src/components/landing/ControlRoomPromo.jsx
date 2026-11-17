import { Link } from "react-router-dom";
import { RadioTower, ArrowRight } from "lucide-react";

const POINTS = ["Mappa operativa con percorso, postazioni e mezzi", "Volontari, ambulanze e mezzi di soccorso", "Interventi con priorità e squadre assegnate", "Accesso mobile per gli operatori", "Diario operativo e report finale"];

export function ControlRoomPromo() {
  return (
    <section className="px-6 py-16" data-testid="home-controlroom">
      <div className="mx-auto grid max-w-6xl items-center gap-8 rounded-2xl bg-slate-900 p-8 text-white md:grid-cols-[1.3fr_1fr] md:p-12">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-[#5EEAD4]"><RadioTower className="h-5 w-5" />Nuovo applicativo</div>
          <h2 className="mt-3 font-display text-3xl font-bold tracking-tight md:text-4xl">CONTROL ROOM — TUTTO L'EVENTO SOTTO CONTROLLO</h2>
          <p className="mt-4 max-w-xl text-slate-300">Gestisci volontari, postazioni, mezzi di soccorso e interventi durante la manifestazione. Una centrale operativa digitale per coordinare il personale, monitorare il percorso e affrontare rapidamente ogni situazione.</p>
          <div className="mt-6 flex flex-wrap items-center gap-5">
            <div className="text-2xl font-bold" data-testid="home-controlroom-price">119 € PER EVENTO</div>
            <Link to="/funzionalita/control-room" className="inline-flex items-center gap-2 rounded-full bg-[#0ABAB5] px-6 py-3 text-sm font-semibold text-slate-900 hover:bg-[#09A8A3]" data-testid="home-controlroom-cta">SCOPRI CONTROL ROOM<ArrowRight className="h-4 w-4" /></Link>
          </div>
        </div>
        <ul className="space-y-2.5 text-sm text-slate-200">{POINTS.map((p) => <li key={p} className="flex gap-2"><span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#0ABAB5]" />{p}</li>)}</ul>
      </div>
    </section>
  );
}
