import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { trackDemo } from "@/lib/plannerDemo";
import { ArrowRight, Users, ListChecks, Route, Handshake, FileText, CalendarDays } from "lucide-react";

const VIDEO_MP4 = "/media/event-planner-demo.mp4";
const VIDEO_WEBM = "/media/event-planner-demo.webm";
const POSTER = "/media/event-planner-demo-poster.jpg";
const LINKS = [[Users, "Staff e volontari", "persone assegnate alle postazioni"], [ListChecks, "Pipeline evento", "compiti operativi legati all'evento"],
  [Route, "Percorsi", "tracciati dell'evento"], [Handshake, "Sponsor e partner", "aree sponsor sulla mappa"],
  [FileText, "Briefing", "informazioni operative condivise"], [CalendarDays, "Eventi", "ogni planimetria è legata al suo evento"]];

// Il video si scarica e parte solo quando è visibile; fuori schermo va in pausa.
export function DemoVideo({ mp4 = VIDEO_MP4, webm = VIDEO_WEBM, poster = POSTER, label = "Video dimostrativo di Event Planner", testid = "home-planner-video", className = "aspect-video" }) {
  const ref = useRef(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return undefined;
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { if (v.preload === "none") { v.preload = "auto"; v.load(); } v.play().catch(() => {}); } else v.pause();
    }, { threshold: 0.25 });
    io.observe(v);
    return () => io.disconnect();
  }, []);
  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-slate-100 shadow-[0_30px_80px_-20px_rgba(15,23,42,0.35)] ring-1 ring-black/5" data-testid={`${testid}-wrap`}>
      <video ref={ref} className={`block h-auto w-full ${className}`} muted loop playsInline preload="none" poster={poster}
        aria-label={label} data-testid={testid}>
        <source src={webm} type="video/webm" />
        <source src={mp4} type="video/mp4" />
      </video>
    </div>
  );
}

export default function PlannerDemoSection() {
  const nav = useNavigate();
  const [cfg, setCfg] = useState(null);
  const ref = useRef(null);
  useEffect(() => { api.get("/public/planner-demo").then(({ data }) => setCfg(data)).catch(() => setCfg({ abilitata: false })); }, []);
  useEffect(() => {
    if (!cfg?.abilitata || !ref.current) return undefined;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { trackDemo("view"); io.disconnect(); } }, { threshold: 0.4 });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [cfg]);
  if (!cfg?.abilitata) return null;
  const register = () => { trackDemo("cta_register"); nav("/registrati?da=event-planner"); };

  return (
    <section id="event-planner" ref={ref} className="border-y border-slate-100 bg-slate-50/60 px-6 py-20" data-testid="home-event-planner">
      <div className="mx-auto max-w-6xl">
        <div className="mx-auto max-w-3xl text-center">
          <div className="mb-3 text-sm font-semibold uppercase tracking-wide text-tiffany-active">Event Planner · una funzionalità di CRMEvent</div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 md:text-4xl" data-testid="home-planner-title">Il tuo evento prende forma, direttamente sulla mappa.</h2>
          <p className="mt-5 text-slate-500" data-testid="home-planner-subtitle">Disegna percorsi, organizza spazi, posiziona strutture e coordina le risorse. Con Event Planner puoi visualizzare ogni dettaglio del tuo evento.</p>
        </div>
        <div className="mt-10"><DemoVideo /></div>
        <div className="mt-8 flex justify-center">
          <button type="button" onClick={register} className="cta-shimmer inline-flex h-12 items-center gap-2 rounded-lg bg-tiffany px-7 font-semibold text-slate-900 shadow-sm transition-transform hover:bg-tiffany-hover active:scale-[0.98]" data-testid="home-planner-register">Registrati gratis <ArrowRight className="h-4 w-4" /></button>
        </div>
        <div className="mt-12">
          <div className="mb-4 text-sm font-semibold text-slate-700">Integrato con il resto di CRMEvent</div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {LINKS.map(([Icon, t, d]) => (
              <div key={t} className="rounded-xl border border-slate-200 bg-white p-3">
                <Icon className="h-5 w-5 text-tiffany-active" /><div className="mt-2 text-sm font-semibold text-slate-900">{t}</div><div className="mt-0.5 text-xs text-slate-500">{d}</div>
              </div>))}
          </div>
        </div>
      </div>
    </section>
  );
}
