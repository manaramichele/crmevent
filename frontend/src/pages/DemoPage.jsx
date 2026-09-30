import { useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ExternalLink, LogIn, PlayCircle } from "lucide-react";
import { trackOnce } from "@/lib/analytics";

// Official Demosmith public embed URL (Share → Embed Settings). Inline embed, no autoplay.
const DEMO_EMBED_URL = "https://public.demosmith.ai/f97202d5/embed.html";
const EMBED_IS_PUBLIC = true;

function leadId() {
  try { return (JSON.parse(localStorage.getItem("crmevent_lead")) || {}).id || null; } catch { return null; }
}

export default function DemoPage() {
  useEffect(() => {
    document.title = "Demo interattiva · CRMEvent";
    // Ensure this funnel page is never indexed (noindex, nofollow).
    let meta = document.querySelector('meta[name="robots"]');
    const created = !meta;
    if (!meta) { meta = document.createElement("meta"); meta.name = "robots"; document.head.appendChild(meta); }
    const prev = meta.getAttribute("content");
    meta.setAttribute("content", "noindex, nofollow");
    return () => { if (created) meta.remove(); else if (prev) meta.setAttribute("content", prev); };
  }, []);

  const onDemoReady = () => {
    const lid = leadId();
    trackOnce(`demo_started_${lid || "anon"}`, "demo_started");
    if (lid) { import("@/lib/api").then(({ default: api }) => api.post(`/leads/${lid}/funnel`, { status: "demo_started" }).catch(() => {})); }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50" data-testid="demo-page">
      {/* Minimal branded header — no nav, keeps focus on the funnel */}
      <header className="sticky top-0 z-30 bg-white/90 backdrop-blur border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="font-display text-xl font-bold tracking-tight text-slate-900" data-testid="demo-logo">
            CRM<span className="text-tiffany-active">Event</span>
          </Link>
          <div className="flex items-center gap-2">
            <Link to="/login" data-testid="demo-login-cta" className="h-10 px-4 rounded-lg border border-slate-200 hover:bg-slate-100 text-slate-700 text-sm font-semibold inline-flex items-center gap-1.5"><LogIn className="w-4 h-4" />Accedi</Link>
            <Link to="/registrati" data-testid="demo-try-cta" className="h-10 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm inline-flex items-center gap-1.5">Inizia gratuitamente <ArrowRight className="w-4 h-4" /></Link>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <div className="max-w-3xl">
          <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">Scopri CRMEvent in pochi minuti</h1>
          <p className="text-slate-500 mt-3 text-base sm:text-lg">Guarda come CRMEvent ti aiuta a gestire eventi, persone, staff, sponsor, attività e tutte le informazioni operative in un'unica piattaforma.</p>
        </div>

        {/* Interactive demo — takes most of the space on desktop */}
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
          <div className="relative w-full" style={{ aspectRatio: "16 / 9", minHeight: "360px" }}>
            {EMBED_IS_PUBLIC ? (
              <iframe
                src={DEMO_EMBED_URL}
                title="Demo interattiva CRMEvent"
                className="absolute inset-0 w-full h-full"
                style={{ border: 0 }}
                allow="fullscreen; clipboard-write"
                allowFullScreen
                onLoad={onDemoReady}
                data-testid="demo-iframe"
              />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-slate-900 text-white text-center px-6" data-testid="demo-launcher">
                <div className="w-16 h-16 rounded-full bg-tiffany flex items-center justify-center text-slate-900"><PlayCircle className="w-9 h-9" /></div>
                <div className="font-display text-xl sm:text-2xl font-bold">Demo interattiva CRMEvent</div>
                <p className="text-slate-300 text-sm max-w-md">Clicca per avviare la demo guidata: ti mostreremo eventi, persone, staff, sponsor e attività in pochi minuti.</p>
                <a href={DEMO_EMBED_URL} target="_blank" rel="noopener noreferrer" onClick={onDemoReady} data-testid="demo-launch-btn" className="h-12 px-6 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold inline-flex items-center gap-2">Avvia la demo <ArrowRight className="w-4 h-4" /></a>
              </div>
            )}
          </div>
        </div>
        {EMBED_IS_PUBLIC && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <a href={DEMO_EMBED_URL} target="_blank" rel="noopener noreferrer" onClick={onDemoReady} data-testid="demo-open-fullscreen" className="text-sm text-slate-500 hover:text-slate-800 inline-flex items-center gap-1.5"><ExternalLink className="w-4 h-4" />Se la demo non si carica qui, aprila a schermo intero</a>
          </div>
        )}

        {/* Persistent conversion CTA */}
        <div className="mt-10 rounded-2xl bg-slate-900 text-white p-6 sm:p-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-5">
          <div>
            <div className="font-display text-xl sm:text-2xl font-bold">Vuoi usare CRMEvent con il tuo evento?</div>
            <p className="text-slate-300 text-sm mt-1.5">Registrati gratuitamente e ricevi 100 crediti CRMEvent. Nessuna carta richiesta.</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Link to="/login" className="h-11 px-5 rounded-lg border border-white/25 hover:bg-white/10 text-white text-sm font-semibold inline-flex items-center">Accedi</Link>
            <Link to="/registrati" data-testid="demo-try-cta-bottom" className="h-11 px-6 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold inline-flex items-center gap-1.5">Inizia gratuitamente <ArrowRight className="w-4 h-4" /></Link>
          </div>
        </div>
      </main>

      {/* Floating CTA — always reachable on mobile without disturbing the demo */}
      <Link to="/registrati" data-testid="demo-try-cta-floating" className="sm:hidden fixed bottom-4 inset-x-4 z-40 h-12 rounded-xl bg-tiffany text-slate-900 font-semibold shadow-lg flex items-center justify-center gap-1.5">Inizia gratuitamente <ArrowRight className="w-4 h-4" /></Link>
    </div>
  );
}
