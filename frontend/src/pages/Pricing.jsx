import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Footer from "@/components/Footer";
import PlansSection from "@/components/PlansSection";
import { trackEvent } from "@/lib/analytics";
import { useAuth } from "@/context/AuthContext";
import { Menu, X } from "lucide-react";

export default function Pricing() {
  const [open, setOpen] = useState(false);
  const { user } = useAuth();
  const authed = !!(user && user.org_id);
  useEffect(() => { trackEvent("pricing_view"); }, []);
  const cta = authed ? "/profilo?tab=abbonamento" : "/registrati";
  return (
    <div className="bg-white text-slate-900" data-testid="pricing-page">
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" data-testid="pricing-logo"><img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-14 sm:h-16 w-auto" /></Link>
          <nav className="hidden lg:flex items-center gap-7">
            <Link to="/#funzionalita" className="text-sm font-medium text-slate-600 hover:text-slate-900">Funzionalità</Link>
            <Link to="/prezzi" className="text-sm font-semibold text-slate-900">Prezzi</Link>
          </nav>
          <div className="hidden lg:flex items-center gap-3">
            <Link to="/login" className="text-sm font-semibold text-slate-700 hover:text-slate-900">Accedi</Link>
            <Link to={cta} data-testid="pricing-header-cta" className="h-10 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm transition-all active:scale-[0.98] flex items-center">{authed ? "Il mio abbonamento" : "Prova GOLD gratis"}</Link>
          </div>
          <button className="lg:hidden" onClick={() => setOpen((o) => !o)} data-testid="pricing-menu">{open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}</button>
        </div>
        {open && (
          <div className="lg:hidden border-t border-slate-100 bg-white px-6 py-4 space-y-3">
            <Link to="/#funzionalita" className="block text-sm font-medium text-slate-600">Funzionalità</Link>
            <Link to="/prezzi" className="block text-sm font-semibold text-slate-900">Prezzi</Link>
            <div className="flex gap-3 pt-2">
              <Link to="/login" className="flex-1 h-10 rounded-lg border border-slate-200 flex items-center justify-center text-sm font-semibold">Accedi</Link>
              <Link to={cta} className="flex-1 h-10 rounded-lg bg-tiffany text-slate-900 text-sm font-semibold flex items-center justify-center">{authed ? "Abbonamento" : "Prova gratis"}</Link>
            </div>
          </div>
        )}
      </header>
      <section className="max-w-6xl mx-auto px-6 pt-14 pb-16">
        <PlansSection authed={authed} />
      </section>
      <Footer />
    </div>
  );
}
