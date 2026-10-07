import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";

export const NEWS_READ_EVENT = "crmevent:news-read";
const fmtDate = (iso) => { try { return new Date(iso).toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" }); } catch { return ""; } };

export default function News() {
  const [items, setItems] = useState(null);
  useEffect(() => {
    api.get("/news").then(({ data }) => setItems(data)).catch((e) => { setItems([]); toast.error(formatApiError(e.response?.data?.detail)); });
    api.post("/news/mark-read").then(() => window.dispatchEvent(new Event(NEWS_READ_EVENT))).catch(() => {});
  }, []);
  return (
    <div className="animate-fade-up max-w-2xl" data-testid="news-page">
      <PageHeader title="Novità" subtitle="Le ultime funzioni e i miglioramenti disponibili in CRMEvent" />
      {items === null ? <p className="text-sm text-slate-400" data-testid="news-loading">Caricamento...</p>
        : items.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500" data-testid="news-empty">
            <Sparkles className="w-6 h-6 mx-auto mb-2 text-tiffany-active" />Nessuna novità pubblicata al momento.
          </div>
        ) : (
          <div className="space-y-3" data-testid="news-list">
            {items.map((n, i) => (
              <article key={n.id} className="bg-white border border-slate-200 rounded-xl shadow-sm p-5 animate-fade-up" style={{ animationDelay: `${i * 50}ms` }} data-testid={`news-card-${n.id}`}>
                <time className="text-xs font-medium text-slate-400" data-testid={`news-date-${n.id}`}>{fmtDate(n.published_at)}</time>
                <h2 className="mt-1 text-lg font-bold text-slate-900 font-display leading-snug" data-testid={`news-title-${n.id}`}>{n.titolo}</h2>
                <p className="mt-1.5 text-sm text-slate-700 leading-relaxed whitespace-pre-wrap" data-testid={`news-text-${n.id}`}>{n.descrizione}</p>
                {n.area && <span className="mt-3 inline-flex rounded-full bg-tiffany-light text-tiffany-fg px-2.5 py-0.5 text-xs font-semibold" data-testid={`news-area-${n.id}`}>{n.area}</span>}
              </article>
            ))}
          </div>
        )}
    </div>
  );
}
