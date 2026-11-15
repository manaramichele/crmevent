import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Footer from "@/components/Footer";
import { fetchPublicPromo, fetchPublicPromoList } from "@/lib/promoMaterials";
import { Download, ArrowRight } from "lucide-react";

export default function PromoVideo() {
  const { slug } = useParams();
  const [p, setP] = useState(undefined);
  const [all, setAll] = useState([]);
  useEffect(() => {
    fetchPublicPromo(slug).then(setP).catch(() => setP(null));
    fetchPublicPromoList().then(setAll).catch(() => setAll([]));
  }, [slug]);
  if (p === undefined) return <div className="min-h-screen bg-slate-950" data-testid="promo-loading" />;
  if (!p) return <div className="min-h-screen flex items-center justify-center text-slate-600" data-testid="promo-missing">Video non trovato. <a href="/" className="ml-1 font-semibold text-[#088F8A]">Vai a CRMEvent</a></div>;
  const others = all.filter((x) => x.slug !== slug);
  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="promo-page">
      {p.status !== "pubblicato" && <div className="bg-amber-400 px-5 py-2 text-center text-sm font-semibold text-slate-900" data-testid="promo-draft-banner">Anteprima riservata al Super Admin: materiale in bozza, non ancora pubblico</div>}
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <a href="/" data-testid="promo-home-link"><img src="/logo-crmevent-dark.png" alt="CRMEvent" className="h-9 w-auto" /></a>
        <Link to="/registrati" className="rounded-full bg-[#0ABAB5] px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-[#09A8A3]" data-testid="promo-header-cta">Prova CRMEvent</Link>
      </header>
      <main className="mx-auto max-w-6xl px-5 pb-16">
        <div className="mb-6 border-l-4 border-[#0ABAB5] pl-4">
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight" data-testid="promo-title">{p.title}</h1>
          <p className="mt-1 text-base md:text-lg text-slate-300" data-testid="promo-subtitle">{p.subtitle}</p>
        </div>
        <div className="overflow-hidden rounded-2xl border border-white/10 bg-black shadow-2xl">
          <video key={p.slug} className="block aspect-video w-full" controls playsInline preload="metadata" poster={p.poster} data-testid="promo-video">
            {p.webm && <source src={p.webm} type="video/webm" />}
            <source src={p.mp4} type="video/mp4" />
          </video>
        </div>
        <div className="mt-6 grid gap-6 md:grid-cols-[1fr_auto] md:items-start">
          <p className="max-w-2xl text-sm sm:text-base text-slate-300" data-testid="promo-text">{p.description}</p>
          <div className="flex flex-wrap gap-3">
            <a href={p.mp4} download={`crmevent-${p.slug}-demo.mp4`} className="inline-flex items-center gap-2 rounded-full border border-white/20 px-4 py-2 text-sm font-semibold hover:bg-white/10" data-testid="promo-download"><Download className="h-4 w-4" />Scarica il video MP4</a>
            <a href="/" className="inline-flex items-center gap-2 rounded-full bg-[#0ABAB5] px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-[#09A8A3]" data-testid="promo-cta">Scopri CRMEvent<ArrowRight className="h-4 w-4" /></a>
          </div>
        </div>
        {others.length > 0 && (
          <div className="mt-12" data-testid="promo-others">
            <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Guarda anche gli altri video</div>
            <div className="flex flex-wrap gap-3">
              {others.map((o) => (
                <a key={o.slug} href={`/video/${o.slug}`} className="inline-flex items-center gap-2 rounded-full border border-[#0ABAB5]/40 px-4 py-2 text-sm font-semibold text-[#5EEAD4] hover:bg-[#0ABAB5]/10" data-testid={`promo-other-link-${o.slug}`}>{o.name}<ArrowRight className="h-4 w-4" /></a>
              ))}
            </div>
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
