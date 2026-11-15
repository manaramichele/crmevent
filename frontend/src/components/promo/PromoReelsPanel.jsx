import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { ReelCard } from "@/components/promo/ReelCard";

export function PromoReelsPanel() {
  const [data, setData] = useState(null);
  const load = useCallback(() => api.get("/promo-reels").then((r) => setData(r.data)).catch(() => setData({ reels: [] })), []);
  useEffect(() => { load(); }, [load]);
  const busy = data?.reels?.some((r) => r.versions?.some((v) => ["queued", "processing"].includes(v.status)));
  useEffect(() => {
    if (!busy) return undefined;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [busy, load]);
  if (!data) return <div className="text-sm text-slate-400" data-testid="reels-loading">Caricamento…</div>;
  const main = data.reels.filter((r) => r.kind === "principale");
  const short = data.reels.filter((r) => r.kind !== "principale");
  return (
    <div className="space-y-5" data-testid="promo-reels-panel">
      <div>
        <h2 className="text-base md:text-lg font-semibold text-slate-900" data-testid="reels-campaign-name">{data.campaign}</h2>
        <p className="text-sm text-slate-500">Video verticali 1080×1920 (MP4 H.264) con copertina JPG, descrizione e hashtag per Instagram. Ogni video è un progetto di montaggio modificabile: la rigenerazione crea una nuova versione e conserva le precedenti. Da qui non viene pubblicato nulla sui social.</p>
      </div>
      <div className="grid gap-4 2xl:grid-cols-2">{[...main, ...short].map((r) => <ReelCard key={r.slug} r={r} assets={data.assets} music={data.music} onChange={load} />)}</div>
    </div>
  );
}
