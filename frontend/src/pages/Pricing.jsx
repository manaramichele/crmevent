import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Footer from "@/components/Footer";
import { trackEvent } from "@/lib/analytics";
import { Check, Sparkles, Zap, Users, CalendarCheck, Megaphone, Menu, X, Minus } from "lucide-react";

// Prezzo per singolo evento (standard). Fonte dati: pricing_plans (fascia "small") — nessun hardcoding in produzione.
const PRICING = { starter: 49, professional: 99, premium: 199 };

const PLANS = {
  starter: {
    id: "starter",
    kicker: "Gestisci il team",
    kickerIcon: Users,
    title: "STARTER",
    subtitle: "Per gestire il tuo team",
    description: "Organizza staff e volontari del tuo evento: team, turni e disponibilità.",
    intro: null,
    features: ["Staff e volontari", "Team", "Turni", "Disponibilità e conferme", "Informazioni allo staff"],
    ctaTestid: "plan-starter-cta",
  },
  professional: {
    id: "professional",
    kicker: "Gestisci l'evento",
    kickerIcon: CalendarCheck,
    title: "PROFESSIONAL",
    subtitle: "Per organizzare il tuo evento",
    description: null,
    intro: "Tutto ciò che trovi in Starter, più:",
    features: ["Aziende e contatti", "Sponsor e partner", "Attività, follow-up e scadenze", "Responsabili e stato attività", "Ospitalità e pernottamenti", "Pasti", "Briefing", "Documenti", "Mappe e percorsi"],
    ctaTestid: "plan-professional-cta",
  },
  premium: {
    id: "premium",
    kicker: "Organizza e promuovi l'evento",
    kickerIcon: Megaphone,
    title: "PREMIUM",
    subtitle: "Per organizzare e promuovere il tuo evento",
    description: null,
    intro: "Tutto ciò che trovi in Professional, più:",
    features: ["Checklist completa dell'evento", "Pipeline organizzativa pre-evento", "Controllo avanzamento", "Modelli per tipologia di evento", "Marketing dell'evento", "Piano editoriale e calendario social", "Libreria media", "Creazione contenuti", "Gestione e pubblicazione social"],
    ctaTestid: "plan-premium-cta",
  },
};

function PriceBlock({ amount }) {
  return (
    <div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-display text-5xl font-bold text-slate-900" data-testid="price-value">{amount} €</span>
        <span className="text-slate-500 text-sm font-medium">+ IVA</span>
      </div>
      <div className="text-sm text-slate-400 mt-0.5">/ evento</div>
    </div>
  );
}

function PlanCard({ plan, amount, highlighted }) {
  const Kicker = plan.kickerIcon;
  return (
    <div
      data-testid={`plan-card-${plan.id}`}
      className={`relative flex flex-col h-full rounded-3xl p-7 transition-all ${
        highlighted
          ? "bg-white border-2 border-tiffany shadow-xl shadow-tiffany/20 md:-translate-y-3"
          : "bg-white border border-slate-200 shadow-sm hover:shadow-md hover:-translate-y-1"
      }`}
    >
      {highlighted && (
        <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap" data-testid="plan-professional-badge">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-tiffany text-slate-900 px-3.5 py-1.5 text-xs font-bold shadow-sm">
            <Zap className="w-3.5 h-3.5" fill="currentColor" />Miglior rapporto qualità-prezzo
          </span>
        </div>
      )}

      <div className={`inline-flex items-center gap-1.5 self-start rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${highlighted ? "bg-tiffany-light text-tiffany-fg" : "bg-slate-100 text-slate-500"}`}>
        <Kicker className="w-3.5 h-3.5" />{plan.kicker}
      </div>

      <h3 className="font-display text-2xl font-bold text-slate-900 mt-4">{plan.title}</h3>
      <p className="text-sm text-slate-500 mt-1">{plan.subtitle}</p>

      <div className="mt-6 min-h-[76px]"><PriceBlock amount={amount} /></div>

      {plan.description && <p className="text-sm text-slate-600 mt-4 leading-relaxed">{plan.description}</p>}
      {plan.intro && <p className="text-sm font-semibold text-slate-800 mt-4">{plan.intro}</p>}

      <ul className="mt-4 space-y-2.5 flex-1">
        {plan.features.map((f) => (
          <li key={f} className="flex items-start gap-2.5 text-sm text-slate-700" data-testid={`plan-${plan.id}-feature`}>
            <span className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${highlighted ? "bg-tiffany-light text-tiffany-active" : "bg-emerald-50 text-emerald-600"}`}>
              <Check className="w-3.5 h-3.5" />
            </span>
            <span>{f}</span>
          </li>
        ))}
      </ul>

      <Link
        to="/registrati"
        data-testid={plan.ctaTestid}
        onClick={() => trackEvent("pricing_cta_click", { plan: plan.id })}
        className={`mt-7 inline-flex items-center justify-center h-12 px-6 rounded-xl text-base font-semibold transition-all active:scale-[0.98] ${
          highlighted
            ? "bg-tiffany hover:bg-tiffany-hover text-slate-900 shadow-sm"
            : "bg-slate-900 hover:bg-slate-800 text-white"
        }`}
      >
        Prova gratis 14 giorni
      </Link>
      <p className="text-xs text-slate-400 mt-2 text-center" data-testid={`${plan.ctaTestid}-note`}>Nessuna carta richiesta</p>
    </div>
  );
}

// Tabella di confronto — SOLO funzionalità già esistenti / previste nello sviluppo CRMEvent.
// Logica: STARTER = gestione staff · PROFESSIONAL = gestione completa evento · PREMIUM = PROFESSIONAL + organizzazione avanzata + marketing/social.
const COMPARISON = [
  { area: "Gestione staff", rows: [
    ["Staff e volontari", true, true, true],
    ["Team", true, true, true],
    ["Turni", true, true, true],
    ["Disponibilità e conferme", true, true, true],
    ["Informazioni allo staff", true, true, true],
  ]},
  { area: "Gestione evento", rows: [
    ["Aziende e contatti", false, true, true],
    ["Sponsor e partner", false, true, true],
    ["Attività e follow-up", false, true, true],
    ["Scadenze", false, true, true],
    ["Responsabili delle attività", false, true, true],
    ["Stato delle attività", false, true, true],
    ["Ospitalità", false, true, true],
    ["Pernottamenti", false, true, true],
    ["Pasti", false, true, true],
    ["Briefing", false, true, true],
    ["Documenti", false, true, true],
    ["Mappe e percorsi", false, true, true],
  ]},
  { area: "Organizzazione avanzata", rows: [
    ["Checklist completa dell'evento", false, false, true],
    ["Pipeline organizzativa pre-evento", false, false, true],
    ["Controllo avanzamento", false, false, true],
    ["Modelli per tipologia di evento", false, false, true],
  ]},
  { area: "Marketing e social", rows: [
    ["Piano editoriale", false, false, true],
    ["Calendario social", false, false, true],
    ["Libreria media", false, false, true],
    ["Creazione contenuti", false, false, true],
    ["Gestione social", false, false, true],
    ["Pubblicazione social", false, false, true],
  ]},
];

function Cell({ on, pro }) {
  return (
    <div className={`flex items-center justify-center py-3 ${pro ? "bg-tiffany-light/40" : ""}`}>
      {on
        ? <span className="w-5 h-5 rounded-full bg-tiffany-light text-tiffany-active flex items-center justify-center"><Check className="w-3.5 h-3.5" /></span>
        : <Minus className="w-4 h-4 text-slate-300" />}
    </div>
  );
}

function ComparisonTable({ prices }) {
  const GRID = "grid grid-cols-[1fr_repeat(3,minmax(56px,1fr))] sm:grid-cols-[1.6fr_repeat(3,1fr)]";
  return (
    <section id="confronto" className="max-w-4xl mx-auto px-6 pt-14 pb-4" data-testid="comparison-section">
      <div className="text-center mb-8">
        <h2 className="font-display text-3xl font-bold">Confronta i piani nel dettaglio</h2>
        <p className="text-slate-500 mt-3 text-sm md:text-base">Tutto ciò che è incluso in Starter, Professional e Premium, area per area.</p>
      </div>

      <div className="rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        {/* Intestazione piani (sticky) */}
        <div className={`${GRID} sticky top-16 z-20 bg-white border-b border-slate-200`} data-testid="comparison-header">
          <div className="py-3 px-3 sm:px-4" />
          <div className="py-3 text-center text-xs sm:text-sm font-bold text-slate-700">STARTER</div>
          <div className="py-3 text-center text-xs sm:text-sm font-bold text-slate-900 bg-tiffany-light/40 border-x border-tiffany/30">
            PROFESSIONAL
            <span className="hidden sm:flex items-center justify-center gap-1 text-[10px] font-semibold text-tiffany-fg mt-0.5"><Zap className="w-3 h-3" fill="currentColor" />Consigliato</span>
          </div>
          <div className="py-3 text-center text-xs sm:text-sm font-bold text-slate-700">PREMIUM</div>
        </div>

        {COMPARISON.map((group, gi) => (
          <div key={group.area}>
            <div className={`${GRID} bg-slate-50 border-b border-slate-100`}>
              <div className="col-span-4 py-2.5 px-3 sm:px-4 text-[11px] font-bold uppercase tracking-wide text-slate-500" data-testid={`comparison-area-${gi}`}>{group.area}</div>
            </div>
            {group.rows.map(([label, s, p, pr], ri) => (
              <div key={label} className={`${GRID} ${ri % 2 ? "bg-white" : "bg-slate-50/40"} border-b border-slate-100 last:border-0 items-center`} data-testid="comparison-row">
                <div className="py-3 px-3 sm:px-4 text-sm text-slate-700">{label}</div>
                <Cell on={s} />
                <Cell on={p} pro />
                <Cell on={pr} />
              </div>
            ))}
          </div>
        ))}

        {/* Riga finale di scelta — prezzi dinamici coerenti con il selettore */}
        <div className="grid grid-cols-1 sm:grid-cols-[1.6fr_repeat(3,1fr)] border-t-2 border-slate-200 bg-white" data-testid="comparison-choice-row">
          <div className="hidden sm:flex items-center px-4 text-sm font-semibold text-slate-700">Scegli il tuo piano</div>
          {["starter", "professional", "premium"].map((id) => {
            const pro = id === "professional";
            const label = id === "starter" ? "Starter" : id === "professional" ? "Professional" : "Premium";
            return (
              <div key={id} className={`flex flex-col items-center gap-2 text-center p-4 border-t border-slate-100 sm:border-t-0 ${pro ? "bg-tiffany-light/40 sm:border-x sm:border-tiffany/30" : ""}`}>
                <span className={`sm:hidden inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wide ${pro ? "text-tiffany-fg" : "text-slate-500"}`}>
                  {pro && <Zap className="w-3 h-3" fill="currentColor" />}{label}
                </span>
                <div>
                  <span className="font-display text-2xl font-bold text-slate-900">{prices[id]} €</span>
                  <span className="text-slate-500 text-xs font-medium ml-1">+ IVA</span>
                  <div className="text-xs text-slate-400">/ evento</div>
                </div>
                <Link to="/registrati" data-testid={`choice-${id}-cta`} onClick={() => trackEvent("pricing_cta_click", { plan: id, where: "table" })}
                  className={`w-full max-w-[200px] inline-flex items-center justify-center py-2.5 px-3 rounded-lg text-xs sm:text-sm font-semibold transition-all active:scale-[0.98] text-center leading-tight ${pro ? "bg-tiffany hover:bg-tiffany-hover text-slate-900 shadow-sm" : "bg-slate-900 hover:bg-slate-800 text-white"}`}>Prova gratis 14 giorni</Link>
                <span className="text-[11px] text-slate-400">Nessuna carta richiesta</span>
              </div>
            );
          })}
        </div>
      </div>
      <p className="text-xs text-slate-400 mt-4 text-center">STARTER = gestione staff · PROFESSIONAL = gestione completa dell'evento · PREMIUM = tutto Professional + organizzazione avanzata + marketing/social.</p>
    </section>
  );
}

export default function Pricing() {
  const [open, setOpen] = useState(false);
  const [pricing, setPricing] = useState(PRICING);
  const prices = pricing;
  useEffect(() => {
    trackEvent("pricing_view");
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/pricing`)
      .then((r) => r.json())
      .then((d) => {
        if (!d || !Array.isArray(d.plans)) return;
        const next = {};
        d.plans.forEach((p) => { if (p.fascia === "small") next[p.plan] = p.net; });
        if (next.starter && next.professional && next.premium) setPricing(next);
      })
      .catch(() => {});
  }, []);

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
      <section className="max-w-3xl mx-auto px-6 pt-16 pb-6 text-center">
        <div className="inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold mb-5">
          <Sparkles className="w-3.5 h-3.5" />14 giorni di prova gratuita · Nessuna carta richiesta
        </div>
        <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">Scegli il piano giusto per il tuo evento.</h1>
        <p className="text-base md:text-lg text-slate-500 mt-4 max-w-xl mx-auto">Dalla gestione dello staff all'organizzazione completa e alla promozione: paghi in base a quanti eventi organizzi ogni anno.</p>
      </section>

      {/* Sottotitolo modello per-evento */}
      <section className="max-w-3xl mx-auto px-6 pb-2 text-center" data-testid="pricing-selector">
        <div className="flex flex-wrap justify-center gap-2">
          <p className="inline-flex items-center gap-2 rounded-full bg-slate-100 text-slate-600 px-4 py-2 text-sm font-medium">
            <Sparkles className="w-4 h-4 text-tiffany-active" />Nessun abbonamento mensile · paghi per singolo evento
          </p>
          <p className="inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-4 py-2 text-sm font-semibold" data-testid="pricing-updates-included">
            <Check className="w-4 h-4" />Aggiornamenti inclusi in tutti i piani
          </p>
        </div>
      </section>

      {/* 3 piani */}
      <section className="max-w-6xl mx-auto px-6 pt-10 pb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8 items-stretch">
          <PlanCard plan={PLANS.starter} amount={prices.starter} highlighted={false} />
          <PlanCard plan={PLANS.professional} amount={prices.professional} highlighted={true} />
          <PlanCard plan={PLANS.premium} amount={prices.premium} highlighted={false} />
        </div>
        <p className="text-xs text-slate-400 mt-8 text-center max-w-2xl mx-auto">
          Prezzi IVA esclusa, per singolo evento. Nessun abbonamento mensile: paghi per il tuo evento e gli aggiornamenti sono inclusi. Il trattamento IVA sarà applicato secondo la normativa vigente.
        </p>
      </section>

      {/* Pacchetti (predisposizione commerciale) */}
      <section className="max-w-4xl mx-auto px-6 pt-4 pb-2" data-testid="pricing-packages">
        <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-6 sm:p-7">
          <div className="text-center max-w-xl mx-auto">
            <h3 className="font-display text-xl font-bold text-slate-900">Organizzi più di un evento?</h3>
            <p className="text-sm text-slate-500 mt-2">Nessun abbonamento. Paghi per evento e gli aggiornamenti sono sempre inclusi. Per chi organizza più eventi stiamo preparando pacchetti dedicati.</p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-6">
            {[
              { n: "1 evento", d: "Prezzo standard", tag: "Disponibile", active: true },
              { n: "3 eventi", d: "Prezzo agevolato", tag: "In arrivo", active: false },
              { n: "5 eventi", d: "Prezzo agevolato", tag: "In arrivo", active: false },
              { n: "Più di 5", d: "Soluzione su misura", tag: "Contattaci", active: false },
            ].map((p) => (
              <div key={p.n} data-testid={`package-${p.n}`} className={`rounded-xl border p-4 text-center ${p.active ? "border-tiffany bg-white shadow-sm" : "border-slate-200 bg-white/60"}`}>
                <div className="font-display text-base font-bold text-slate-900">{p.n}</div>
                <div className="text-xs text-slate-500 mt-1">{p.d}</div>
                <span className={`inline-block mt-3 text-[11px] font-semibold rounded-full px-2.5 py-1 ${p.active ? "bg-tiffany-light text-tiffany-fg" : "bg-slate-100 text-slate-500"}`}>{p.tag}</span>
              </div>
            ))}
          </div>
          <p className="text-center text-xs text-slate-400 mt-5">Organizzi più di 5 eventi all'anno? <Link to="/#demo" className="underline hover:text-slate-600">Contattaci</Link> per una soluzione dedicata.</p>
        </div>
      </section>

      {/* Tabella di confronto completa */}
      <ComparisonTable prices={prices} />

      {/* Final CTA */}
      <section className="max-w-3xl mx-auto px-6 py-16 mt-6 text-center">
        <h2 className="font-display text-3xl font-bold">Inizia oggi, senza pensieri.</h2>
        <p className="text-slate-500 mt-3">14 giorni di prova gratuita con accesso a tutte le funzionalità Premium. Nessuna carta richiesta.</p>
        <div className="mt-7 flex justify-center">
          <Link to="/registrati" data-testid="pricing-cta-bottom"
            className="inline-flex items-center justify-center gap-2 h-12 px-7 rounded-xl bg-tiffany hover:bg-tiffany-hover text-slate-900 text-base font-semibold shadow-sm transition-all active:scale-[0.98]">
            <Sparkles className="w-5 h-5" />Prova gratis 14 giorni
          </Link>
        </div>
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
