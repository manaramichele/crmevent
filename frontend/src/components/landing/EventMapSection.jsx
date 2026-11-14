import { useNavigate } from "react-router-dom";
import { ArrowRight, Route, Film, Share2 } from "lucide-react";
import { DemoVideo } from "@/components/landing/PlannerDemoSection";
import { trackDemo } from "@/lib/plannerDemo";

const POINTS = [[Route, "Dalla traccia GPX al video", "il percorso si disegna da solo sulla mappa reale"],
  [Film, "Con il logo del tuo evento", "nome, distanza, partenza e arrivo in evidenza"],
  [Share2, "Pronto per i social", "formato verticale per Instagram, Facebook, TikTok e YouTube"]];

export default function EventMapSection() {
  const nav = useNavigate();
  const register = () => { trackDemo("cta_register", "event-map"); nav("/registrati?da=event-map"); };
  return (
    <section id="event-map" className="px-6 py-20 bg-white" data-testid="home-event-map">
      <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-[1fr_auto]">
        <div>
          <div className="mb-3 text-sm font-semibold uppercase tracking-wide text-tiffany-active">Event Map · una funzionalità di CRMEvent</div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 md:text-4xl" data-testid="home-eventmap-title">Il tuo percorso diventa protagonista.</h2>
          <p className="mt-5 max-w-xl text-slate-500" data-testid="home-eventmap-subtitle">Trasforma la traccia GPX del tuo evento in un video animato, personalizzato con il logo della manifestazione e pronto da condividere sui social.</p>
          <ul className="mt-8 space-y-4">
            {POINTS.map(([Icon, t, d]) => (
              <li key={t} className="flex gap-3"><Icon className="mt-0.5 h-5 w-5 shrink-0 text-tiffany-active" />
                <div><div className="text-sm font-semibold text-slate-900">{t}</div><div className="text-sm text-slate-500">{d}</div></div></li>))}
          </ul>
          <button type="button" onClick={register} className="mt-8 inline-flex h-12 items-center gap-2 rounded-lg bg-tiffany px-7 font-semibold text-slate-900 shadow-sm transition-transform hover:bg-tiffany-hover active:scale-[0.98]" data-testid="home-eventmap-register">Registrati gratis <ArrowRight className="h-4 w-4" /></button>
        </div>
        <div className="mx-auto w-full max-w-[300px]">
          <div className="rounded-[2.2rem] bg-slate-900 p-2.5 shadow-[0_30px_80px_-20px_rgba(15,23,42,0.45)]">
            <DemoVideo mp4="/media/event-map-demo.mp4" webm="/media/event-map-demo.webm" poster="/media/event-map-demo-poster.jpg"
              label="Video dimostrativo di Event Map" testid="home-eventmap-video" className="aspect-[9/16]" />
          </div>
          <p className="mt-3 text-center text-xs text-slate-400" data-testid="home-eventmap-note">Video generato da Event Map a partire da una traccia GPX reale nel centro di Pisa (evento dimostrativo).</p>
        </div>
      </div>
    </section>
  );
}
