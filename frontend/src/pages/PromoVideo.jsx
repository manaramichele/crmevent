import { Link, useParams } from "react-router-dom";
import Footer from "@/components/Footer";
import { promoBySlug, PROMO } from "@/lib/promoMaterials";
import { Download, ArrowRight } from "lucide-react";

export default function PromoVideo() {
  const { slug } = useParams();
  const p = promoBySlug(slug);
  if (!p) return <div className="min-h-screen flex items-center justify-center text-slate-600" data-testid="promo-missing">Video non trovato. <Link to="/" className="ml-1 font-semibold text-[#088F8A]">Vai a CRMEvent</Link></div>;
  const other = PROMO.find((x) => x.slug !== slug);
  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="promo-page">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5">
        <Link to="/" data-testid="promo-home-link"><img src="/logo-crmevent-dark.png" alt="CRMEvent" className="h-9 w-auto" /></Link>
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
          <p className="max-w-2xl text-sm sm:text-base text-slate-300" data-testid="promo-text">{p.text}</p>
          <div className="flex flex-wrap gap-3">
            <a href={p.mp4} download={p.file} className="inline-flex items-center gap-2 rounded-full border border-white/20 px-4 py-2 text-sm font-semibold hover:bg-white/10" data-testid="promo-download"><Download className="h-4 w-4" />Scarica il video MP4</a>
            <Link to="/registrati" className="inline-flex items-center gap-2 rounded-full bg-[#0ABAB5] px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-[#09A8A3]" data-testid="promo-cta">Inizia con CRMEvent<ArrowRight className="h-4 w-4" /></Link>
          </div>
        </div>
        <a href={`/video/${other.slug}`} className="mt-10 inline-flex items-center gap-2 text-sm font-semibold text-[#5EEAD4]" data-testid="promo-other-link">Guarda anche il video di {other.name}<ArrowRight className="h-4 w-4" /></a>
      </main>
      <Footer />
    </div>
  );
}
