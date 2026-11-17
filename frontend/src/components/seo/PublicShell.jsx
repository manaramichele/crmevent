import { Link } from "react-router-dom";
import Footer from "@/components/Footer";
import { ArrowRight } from "lucide-react";
import SEO from "@/seo/seoPages.json";

const NAV = [["/funzionalita/eventi", "Funzionalità"], ["/organizzatori/gare-podistiche-maratone", "Organizzatori"], ["/prezzi", "Prezzi"], ["/faq", "FAQ"]];
export const pageByPath = (p) => (p === SEO.faq.path ? SEO.faq : SEO.pages.find((x) => x.path === p));

export function PublicShell({ crumbs, children, related = [] }) {
  return (
    <div className="min-h-screen bg-white text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-100 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-5">
          <Link to="/" data-testid="seo-home-link"><img src="/logo-crmevent-header.png" alt="CRMEvent" className="h-8 w-auto" /></Link>
          <nav className="hidden items-center gap-6 text-sm font-medium text-slate-600 md:flex">{NAV.map(([to, l]) => <Link key={to} to={to} className="hover:text-slate-900">{l}</Link>)}</nav>
          <Link to="/registrati" className="rounded-lg bg-tiffany px-4 py-2 text-sm font-semibold text-slate-900 hover:bg-tiffany-hover" data-testid="seo-header-cta">Prova gratis</Link>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-5 py-12">
        <nav aria-label="Breadcrumb" className="mb-6 text-xs text-slate-500" data-testid="seo-breadcrumb">
          {crumbs.map(([name, path], i) => <span key={path}>{i > 0 && " › "}{i < crumbs.length - 1 ? <Link to={path} className="hover:underline">{name}</Link> : name}</span>)}
        </nav>
        {children}
        <section className="mt-12 rounded-2xl bg-slate-900 p-8 text-white">
          <h2 className="text-lg font-semibold">Prova CRMEvent per 14 giorni</h2>
          <p className="mt-2 text-sm text-slate-300">Gratis e senza carta di credito.</p>
          <Link to="/registrati" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-tiffany px-5 py-2.5 text-sm font-semibold text-slate-900" data-testid="seo-cta-register">Registrati gratis<ArrowRight className="h-4 w-4" /></Link>
        </section>
        {related.length > 0 && (
          <section className="mt-10" data-testid="seo-related">
            <h2 className="text-base md:text-lg font-semibold">Approfondisci</h2>
            <ul className="mt-3 grid gap-2 sm:grid-cols-3">
              {related.map((p) => { const r = p === "/prezzi" ? { name: "Prezzi" } : pageByPath(p); return r && <li key={p}><Link to={p} className="block rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium hover:border-tiffany">{r.name}</Link></li>; })}
            </ul>
          </section>
        )}
      </main>
      <Footer />
    </div>
  );
}
