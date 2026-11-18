import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader } from "@/components/crm";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { NewsProductButton } from "@/components/news/NewsProductButton";

export const NEWS_READ_EVENT = "crmevent:news-read";
const fmtDate = (iso) => { try { return new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" }); } catch { return ""; } };
const AUD = { superadmin: "Solo Super Admin", plans: "Piani", service: "Modulo", service_missing: "Senza modulo" };
const chip = (on) => `h-8 px-3 rounded-full text-xs font-semibold border transition-colors ${on ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"}`;

export default function News() {
  const [items, setItems] = useState(null);
  const [area, setArea] = useState("");
  const [onlyUnread, setOnlyUnread] = useState(false);
  const { user } = useAuth();
  const isSuper = user?.role === "superadmin";
  useEffect(() => {
    let alive = true;
    api.get("/news").then(({ data }) => {
      if (!alive) return;
      setItems(data);
      if (data.some((n) => !n.read)) api.post("/news/mark-read", { ids: data.filter((n) => !n.read).map((n) => n.id) }).then(() => window.dispatchEvent(new Event(NEWS_READ_EVENT))).catch(() => {});
    }).catch((e) => { if (alive) { setItems([]); toast.error(formatApiError(e.response?.data?.detail)); } });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    const id = window.location.hash.replace("#", "");
    if (id && items) document.querySelector(`[data-testid="news-card-${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [items]);
  const areas = [...new Set((items || []).map((n) => n.area).filter(Boolean))];
  const shown = (items || []).filter((n) => (!area || n.area === area) && (!onlyUnread || !n.read));
  return (
    <div className="animate-fade-up max-w-2xl" data-testid="news-page">
      <PageHeader title="Novità" subtitle="Le ultime funzioni e i miglioramenti disponibili in CRMEvent" />
      {items?.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4" data-testid="news-filters">
          <button type="button" className={chip(!area)} onClick={() => setArea("")} data-testid="news-filter-all">Tutte</button>
          {areas.map((a) => <button key={a} type="button" className={chip(area === a)} onClick={() => setArea(a)} data-testid={`news-filter-${a}`}>{a}</button>)}
          <button type="button" className={chip(onlyUnread)} onClick={() => setOnlyUnread((v) => !v)} data-testid="news-filter-unread">Solo non lette</button>
        </div>
      )}
      {items === null ? <p className="text-sm text-slate-400" data-testid="news-loading">Caricamento...</p>
        : shown.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500" data-testid="news-empty">
            <Sparkles className="w-6 h-6 mx-auto mb-2 text-tiffany-active" />{items.length ? "Nessuna novità con questi filtri." : "Nessuna novità pubblicata al momento."}
          </div>
        ) : (
          <div className="space-y-3" data-testid="news-list">
            {shown.map((n, i) => (
              <article key={n.id} className={`bg-white border rounded-xl shadow-sm p-5 animate-fade-up ${n.read ? "border-slate-200" : "border-[#0ABAB5]"}`} style={{ animationDelay: `${i * 50}ms` }} data-testid={`news-card-${n.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <time className="text-xs font-medium text-slate-400" data-testid={`news-date-${n.id}`}>{fmtDate(n.published_at)}</time>
                  {!n.read && <span className="rounded-full bg-[#0ABAB5] text-slate-900 px-2 py-0.5 text-[11px] font-bold" data-testid={`news-new-${n.id}`}>Nuova</span>}
                  {isSuper && AUD[n.audience?.type] && <span className="rounded-full bg-slate-100 text-slate-600 px-2 py-0.5 text-[11px]" data-testid={`news-audience-${n.id}`}>{AUD[n.audience.type]}{n.audience.type === "plans" ? `: ${n.audience.plans.join(", ").toUpperCase()}` : n.audience.type === "service" || n.audience.type === "service_missing" ? `: ${n.audience.service}` : ""}</span>}
                </div>
                <h2 className="mt-1 text-lg font-bold text-slate-900 font-display leading-snug" data-testid={`news-title-${n.id}`}>{n.titolo}</h2>
                <p className="mt-1.5 text-sm text-slate-700 leading-relaxed whitespace-pre-wrap" data-testid={`news-text-${n.id}`}>{n.descrizione}</p>
                {n.area && <span className="mt-3 inline-flex rounded-full bg-tiffany-light text-tiffany-fg px-2.5 py-0.5 text-xs font-semibold" data-testid={`news-area-${n.id}`}>{n.area}</span>}
                {n.product && <div><NewsProductButton product={n.product} testid={`news-product-${n.id}`} /></div>}
              </article>
            ))}
          </div>
        )}
    </div>
  );
}
