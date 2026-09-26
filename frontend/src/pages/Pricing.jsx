import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import Footer from "@/components/Footer";
import { trackEvent } from "@/lib/analytics";
import { Check, Sparkles, ShieldCheck, RefreshCw, CreditCard, Menu, X } from "lucide-react";

const FEATURES = [
  "Gestione eventi", "Persone e aziende", "Sponsor e partner", "Staff e volontari",
  "Team e turni", "Attività e follow-up", "Ospitalità e pasti", "Mappe e percorsi GPX",
  "Documenti", "Briefing Staff", "Assistenza CRMEvent", "Aggiornamenti inclusi",
];

function CTA({ testid, className = "" }) {
  return (
    <Link to="/registrati" data-testid={testid}
      className={`inline-flex items-center justify-center gap-2 h-12 px-7 rounded-xl bg-tiffany hover:bg-tiffany-hover text-slate-900 text-base font-semibold shadow-sm transition-all active:scale-[0.98] ${className}`}>
      <Sparkles className="w-5 h-5" />Prova CRMEvent gratis
    </Link>
  );
}

export default function Pricing() {
  const [cycle, setCycle] = useState("annual"); // monthly | annual
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const monthly = cycle === "monthly";
  useEffect(() => { trackEvent("pricing_view"); }, []);

  return (
    <div className="bg-white text-slate-900" data-testid="pricing-page">
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" data-testid="pricing-logo"><img src="/logo-crmevent.png?v=2" alt="CRMEvent" className="h-14 sm:h-16 w-auto" /></Link>
          <nav className="hidden lg:flex items-center gap-7">
            <Link to="/#funzionalita" className="text-sm font-medium text-slate-600 hover:text-slate-900">Funzionalità</Link>
            <Link to="/prezzi" className="text-sm font-semibold text-slate-900">Prezzi</Link>
          </nav>
          <div className="hidden lg:flex items-center gap-3">
            <Link to="/login" className="text-sm font-semibold text-slate-700 hover:text-slate-900">Accedi</Link>
            <Link to="/registrati" data-testid="pricing-header-cta" className="h-10 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm transition-all active:scale-[0.98] flex items-center">Prova gratis</Link>
          </div>
          <button className="lg:hidden" onClick={() => setOpen((o) => !o)}>{open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}</button>
        </div>
        {open && (
          <div className="lg:hidden border-t border-slate-100 bg-white px-6 py-4 space-y-3">
            <Link to="/#funzionalita" className="block text-sm font-medium text-slate-600">Funzionalità</Link>
            <Link to="/prezzi" className="block text-sm font-semibold text-slate-900">Prezzi</Link>
            <div className="flex gap-3 pt-2">
              <Link to="/login" className="flex-1 h-10 rounded-lg border border-slate-200 flex items-center justify-center text-sm font-semibold">Accedi</Link>
              <Link to="/registrati" className="flex-1 h-10 rounded-lg bg-tiffany text-slate-900 text-sm font-semibold flex items-center justify-center">Prova gratis</Link>
            </div>
          </div>
        )}
      </header>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-6 pt-16 pb-8 text-center">
        <div className="inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold mb-5">
          <Sparkles className="w-3.5 h-3.5" />14 giorni di prova gratuita · Nessuna carta richiesta
        </div>
        <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">Un solo piano. Tutto CRMEvent.</h1>
        <p className="text-base md:text-lg text-slate-500 mt-4 max-w-xl mx-auto">Tutto ciò che ti serve per organizzare e gestire i tuoi eventi in un'unica piattaforma.</p>
        <div className="mt-7 flex justify-center"><CTA testid="pricing-cta-top" /></div>
        <p className="text-xs text-slate-400 mt-3">Nessun costo di attivazione · Aggiornamenti inclusi · Cancella quando vuoi</p>
      </section>

      {/* Price card */}
      <section className="max-w-4xl mx-auto px-6 pb-16">
        <div className="rounded-3xl border border-slate-200 shadow-xl shadow-slate-200/50 overflow-hidden md:grid md:grid-cols-5">
          <div className="md:col-span-2 bg-slate-900 text-white p-8 flex flex-col">
            <div className="text-sm uppercase tracking-widest text-tiffany font-semibold">Piano CRMEvent</div>
            {/* cycle toggle */}
            <div className="mt-5 inline-flex bg-white/10 rounded-full p-1 self-start" data-testid="cycle-toggle">
              <button onClick={() => setCycle("monthly")} data-testid="cycle-monthly"
                className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all ${monthly ? "bg-tiffany text-slate-900" : "text-slate-200"}`}>Mensile</button>
              <button onClick={() => setCycle("annual")} data-testid="cycle-annual"
                className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all ${!monthly ? "bg-tiffany text-slate-900" : "text-slate-200"}`}>Annuale</button>
            </div>
            <div className="mt-8">
              <div className="flex items-end gap-2">
                <span className="text-5xl font-bold font-display" data-testid="price-amount">{monthly ? "19,90 €" : "199 €"}</span>
                <span className="text-slate-300 mb-1.5">{monthly ? "/ mese" : "/ anno"}</span>
              </div>
              <div className="text-sm text-slate-300 mt-1">+ IVA</div>
              {!monthly && (
                <div className="mt-4 inline-flex flex-col gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-tiffany/20 text-tiffany px-3 py-1 text-xs font-semibold" data-testid="annual-badge">2 mesi inclusi</span>
                  <span className="text-xs text-slate-300">Risparmia 39,80 € rispetto al mensile</span>
                </div>
              )}
            </div>
            <div className="mt-8 space-y-2 text-sm text-slate-300">
              <div className="flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-tiffany" />14 giorni di prova gratuita</div>
              <div className="flex items-center gap-2"><CreditCard className="w-4 h-4 text-tiffany" />Nessuna carta richiesta per iniziare</div>
              <div className="flex items-center gap-2"><RefreshCw className="w-4 h-4 text-tiffany" />Aggiornamenti inclusi</div>
            </div>
            <div className="mt-8"><CTA testid="pricing-cta-price" className="w-full" /></div>
          </div>

          <div className="md:col-span-3 p-8">
            <div className="text-sm font-semibold text-slate-800 mb-4">Tutto incluso nell'abbonamento</div>
            <ul className="grid sm:grid-cols-2 gap-x-6 gap-y-3">
              {FEATURES.map((f) => (
                <li key={f} className="flex items-center gap-2.5 text-sm text-slate-700" data-testid={`feature-${f}`}>
                  <span className="w-5 h-5 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0"><Check className="w-3.5 h-3.5" /></span>
                  {f}
                </li>
              ))}
            </ul>
            <p className="text-xs text-slate-400 mt-6">Prezzi IVA esclusa. Il trattamento IVA sarà applicato secondo la normativa vigente in base alla configurazione fiscale definita all'attivazione dell'abbonamento.</p>
          </div>
        </div>
      </section>

      {/* Aggiornamenti inclusi */}
      <section className="bg-slate-50 border-y border-slate-100">
        <div className="max-w-4xl mx-auto px-6 py-16 text-center">
          <div className="inline-flex w-12 h-12 rounded-2xl bg-tiffany-light text-tiffany-active items-center justify-center mb-5"><RefreshCw className="w-6 h-6" /></div>
          <h2 className="font-display text-3xl font-bold">CRMEvent cresce insieme ai tuoi eventi.</h2>
          <p className="text-base text-slate-500 mt-4 max-w-2xl mx-auto">Tutti gli aggiornamenti della piattaforma e le nuove funzionalità rilasciate per il tuo piano sono inclusi nell'abbonamento, senza costi aggiuntivi.</p>
        </div>
      </section>

      {/* Final CTA */}
      <section className="max-w-3xl mx-auto px-6 py-16 text-center">
        <h2 className="font-display text-3xl font-bold">Inizia oggi, senza pensieri.</h2>
        <p className="text-slate-500 mt-3">14 giorni gratis. Nessuna carta richiesta. Cancella quando vuoi.</p>
        <div className="mt-7 flex justify-center"><CTA testid="pricing-cta-bottom" /></div>
        <p className="text-xs text-slate-400 mt-6">
          Registrandoti accetti i <Link to="/termini" className="underline hover:text-slate-600">Termini e Condizioni</Link>,
          la <Link to="/privacy-policy" className="underline hover:text-slate-600">Privacy Policy</Link> e
          la <Link to="/cookie" className="underline hover:text-slate-600">Cookie Policy</Link>.
        </p>
      </section>

      <Footer />
    </div>
  );
}
