import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { BellRing, Sparkles, X } from "lucide-react";
import api from "@/lib/api";
import { NEWS_READ_EVENT } from "@/pages/News";

const fmtDate = (iso) => { try { return new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" }); } catch { return ""; } };

// Stato Novità condiviso: si aggiorna a ogni cambio pagina, al ritorno sulla scheda e dopo lettura/pubblicazione (nessun polling).
export function useNewsState() {
  const { pathname } = useLocation();
  const [s, setS] = useState({ count: 0, latest: null, banner: false });
  const load = useCallback(() => api.get("/news/unread-count").then(({ data }) => setS(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [pathname, load]);
  useEffect(() => {
    const onFocus = () => { if (document.visibilityState === "visible") load(); };
    window.addEventListener(NEWS_READ_EVENT, load);
    document.addEventListener("visibilitychange", onFocus);
    return () => { window.removeEventListener(NEWS_READ_EVENT, load); document.removeEventListener("visibilitychange", onFocus); };
  }, [load]);
  return s;
}

export function NewsButton() {
  const { count } = useNewsState();
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/novita")} data-testid="header-news-button" title="Novità" aria-label={count ? `Novità, ${count} non lette` : "Novità"}
      className="relative h-9 w-9 inline-flex items-center justify-center rounded-lg hover:bg-slate-100 text-slate-700 transition-colors">
      <BellRing className="w-5 h-5" />
      <Sparkles className="absolute top-1 left-1 w-3 h-3 text-tiffany-active" aria-hidden />
      {count > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center" data-testid="header-news-count">{count > 99 ? "99+" : count}</span>}
    </button>
  );
}

export function NewsBanner() {
  const { count, latest, banner } = useNewsState();
  const navigate = useNavigate();
  const [hidden, setHidden] = useState(false);
  if (!banner || !latest || hidden) return null;
  const close = () => { setHidden(true); api.post("/news/dismiss-banner").then(() => window.dispatchEvent(new Event(NEWS_READ_EVENT))).catch(() => {}); };
  return (
    <div className="relative rounded-xl border border-[#0ABAB5]/40 bg-[#0ABAB5]/10 p-4 pr-11 flex flex-col sm:flex-row sm:items-center gap-3 animate-fade-up" data-testid="news-banner">
      <Sparkles className="w-6 h-6 text-tiffany-active shrink-0 hidden sm:block" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold text-slate-900">Novità CRMEvent!{count > 1 && <span className="ml-2 rounded-full bg-slate-900 text-white px-2 py-0.5 text-[11px]" data-testid="news-banner-count">{count} novità da leggere</span>}</div>
        <div className="text-sm text-slate-800 mt-0.5"><b data-testid="news-banner-title">{latest.titolo}</b> <span className="text-xs text-slate-500" data-testid="news-banner-date">· {fmtDate(latest.published_at)}</span></div>
        <p className="text-sm text-slate-600 mt-0.5 line-clamp-2" data-testid="news-banner-text">{latest.descrizione}</p>
      </div>
      <button type="button" onClick={() => navigate("/novita")} className="h-9 px-4 rounded-full bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 text-sm font-semibold shrink-0 self-start sm:self-center" data-testid="news-banner-open">Scopri le novità</button>
      <button type="button" onClick={close} className="absolute top-2 right-2 p-1.5 text-slate-500 hover:text-slate-900" aria-label="Chiudi avviso" data-testid="news-banner-close"><X className="w-4 h-4" /></button>
    </div>
  );
}
