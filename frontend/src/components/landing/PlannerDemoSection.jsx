import { lazy, Suspense, useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { trackDemo } from "@/lib/plannerDemo";
import { ArrowRight, Users, ListChecks, Route, Handshake, FileText, CalendarDays, MousePointerClick } from "lucide-react";

const PlannerDemo = lazy(() => import("@/components/planner/PlannerDemo"));

const LINKS = [[Users, "Staff e volontari", "persone assegnate alle postazioni"], [ListChecks, "Pipeline evento", "compiti operativi legati all'evento"],
  [Route, "Percorsi", "tracciati dell'evento"], [Handshake, "Sponsor e partner", "aree sponsor sulla mappa"],
  [FileText, "Briefing", "informazioni operative condivise"], [CalendarDays, "Eventi", "ogni planimetria è legata al suo evento"]];

// Anteprima leggera (solo SVG): il motore mappa si scarica solo quando il visitatore apre la demo.
function Preview({ onOpen, label }) {
  return (
    <button type="button" onClick={onOpen} className="group relative block w-full overflow-hidden rounded-2xl border border-slate-200 bg-[#EEF4F2] shadow-xl" data-testid="planner-demo-preview">
      <svg viewBox="0 0 480 320" className="h-auto w-full" aria-hidden="true">
        <rect width="480" height="320" fill="#EEF4F2" />
        <path d="M60 40 C140 70 120 160 200 200 S380 230 440 300" stroke="#fff" strokeWidth="14" fill="none" />
        <path d="M0 120 L480 90" stroke="#fff" strokeWidth="10" />
        <path d="M300 0 L260 320" stroke="#fff" strokeWidth="8" />
        <ellipse cx="230" cy="165" rx="150" ry="95" fill="#D5EBDD" />
        <path d="M150 110 C120 150 140 220 210 235 S340 230 345 170 S300 85 230 82 S170 90 150 110Z" stroke="#E11D48" strokeWidth="5" fill="none" strokeDasharray="1 0" />
        <rect x="140" y="98" width="34" height="8" rx="2" fill="#E11D48" transform="rotate(35 157 102)" />
        <polygon points="180,100 222,96 226,126 186,130" fill="#0F766E" opacity=".35" stroke="#0F766E" strokeWidth="2" />
        <rect x="196" y="106" width="16" height="9" fill="#0ABAB5" /><rect x="214" y="110" width="9" height="9" fill="#9333EA" />
        {[[300, 230, "#F59E0B"], [345, 170, "#EF4444"], [142, 160, "#22C55E"], [260, 82, "#166534"], [90, 70, "#1E40AF"]].map(([x, y, c]) => (
          <g key={`${x}${y}`}><circle cx={x} cy={y} r="9" fill={c} stroke="#fff" strokeWidth="3" /></g>))}
      </svg>
      <span className="absolute inset-0 flex items-center justify-center bg-slate-900/0 transition-colors group-hover:bg-slate-900/10">
        <span className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate-900 shadow-lg transition-transform group-hover:scale-105"><MousePointerClick className="h-4 w-4 text-tiffany-active" />{label}</span>
      </span>
    </button>
  );
}

export default function PlannerDemoSection({ onScroll }) {
  const [cfg, setCfg] = useState(null);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => { api.get("/public/planner-demo").then(({ data }) => setCfg(data)).catch(() => setCfg({ abilitata: false })); }, []);
  useEffect(() => {
    if (!cfg?.abilitata || !ref.current) return undefined;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { trackDemo("view"); io.disconnect(); } }, { threshold: 0.4 });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [cfg]);
  if (!cfg?.abilitata) return null;
  const second = () => {
    trackDemo("cta_features");
    const l = cfg.cta_funzioni_link || "#funzionalita";
    if (l.startsWith("#")) onScroll(l.slice(1)); else window.location.href = l;
  };

  return (
    <section id="event-planner" ref={ref} className="border-y border-slate-100 bg-slate-50/60 px-6 py-20" data-testid="home-event-planner">
      <div className="mx-auto max-w-6xl">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <div className="mb-3 text-sm font-semibold uppercase tracking-wide text-tiffany-active">Event Planner · una funzionalità di CRMEvent</div>
            <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 md:text-4xl" data-testid="home-planner-title">{cfg.titolo}</h2>
            <p className="mt-5 max-w-xl text-slate-500" data-testid="home-planner-subtitle">{cfg.sottotitolo}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <button type="button" onClick={() => setOpen(true)} className="cta-shimmer inline-flex h-12 items-center gap-2 rounded-lg bg-tiffany px-6 font-semibold text-slate-900 shadow-sm transition-transform hover:bg-tiffany-hover active:scale-[0.98]" data-testid="home-planner-try">{cfg.cta_demo} <ArrowRight className="h-4 w-4" /></button>
              <button type="button" onClick={second} className="inline-flex h-12 items-center rounded-lg border border-slate-300 bg-white px-6 font-semibold text-slate-800 transition-colors hover:border-slate-400" data-testid="home-planner-features">{cfg.cta_funzioni}</button>
            </div>
            <p className="mt-4 text-xs text-slate-500">Nessuna registrazione per provarla. Pianificazione su mappa per gare podistiche, eventi sportivi e manifestazioni: percorsi, logistica, aree e strutture in scala reale.</p>
          </div>
          {!open && <Preview onOpen={() => setOpen(true)} label={cfg.cta_demo} />}
          {open && <div className="hidden text-sm text-slate-500 lg:block">La demo è aperta qui sotto. Esplora la mappa, disegna e sposta gli elementi: è tutto dimostrativo.</div>}
        </div>
        {open && <div className="mt-10"><Suspense fallback={<div className="flex h-[600px] items-center justify-center rounded-2xl border border-slate-200 bg-white text-sm text-slate-500" data-testid="planner-demo-loading">Caricamento della mappa...</div>}>
          <PlannerDemo cfg={cfg} onClose={() => setOpen(false)} /></Suspense></div>}
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
