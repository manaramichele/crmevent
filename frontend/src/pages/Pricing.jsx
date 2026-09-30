import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Footer from "@/components/Footer";
import { trackEvent } from "@/lib/analytics";
import { Check, Sparkles, Zap, Users, CalendarCheck, Megaphone, Menu, X, ChevronDown, Minus } from "lucide-react";

// Prezzi legati al numero di eventi (solo visualizzazione — nessuna logica Stripe qui).
const PRICING = {
  small: { plus: 49, premium: 99 },   // Fino a 3 eventi
  large: { plus: 79, premium: 149 },  // Più di 3 eventi
};

const PLANS = {
  free: {
    id: "free",
    kicker: "Gestisci le persone",
    kickerIcon: Users,
    title: "FREE",
    subtitle: "Per gestire il tuo team",
    description: "Inizia gratuitamente a organizzare staff e volontari del tuo evento.",
    intro: null,
    features: ["1 evento", "Staff e volontari", "Team", "Turni", "Disponibilità e conferme", "Informazioni allo staff"],
    cta: "Crea account",
    ctaTestid: "plan-free-cta",
  },
  plus: {
    id: "plus",
    kicker: "Gestisci l'evento",
    kickerIcon: CalendarCheck,
    title: "PLUS",
    subtitle: "Per organizzare il tuo evento",
    description: null,
    intro: "Tutto ciò che trovi nel Free, più:",
    features: ["Aziende e contatti", "Sponsor e partner", "Ospitalità e pernottamenti", "Pasti", "Attività e follow-up", "Briefing", "Documenti", "Mappe e percorsi"],
    cta: "Scegli Plus",
    ctaTestid: "plan-plus-cta",
  },
  premium: {
    id: "premium",
    kicker: "Organizza e promuovi l'evento",
    kickerIcon: Megaphone,
    title: "PREMIUM",
    subtitle: "Per organizzare e promuovere il tuo evento",
    description: null,
    intro: "Tutto ciò che trovi nel Plus, più:",
    features: ["Checklist completa dell'evento", "Pipeline organizzativa pre-evento", "Scadenze e controllo avanzamento", "Marketing dell'evento", "Piano editoriale", "Calendario social", "Gestione social", "Creazione contenuti", "Libreria media", "Pubblicazione social"],
    cta: "Scegli Premium",
    ctaTestid: "plan-premium-cta",
  },
};

// Tabella di confronto — SOLO funzionalità già esistenti / previste nello sviluppo CRMEvent.
// Logica: FREE = gestione staff · PLUS = FREE + gestione completa evento · PREMIUM = PLUS + organizzazione avanzata + marketing/social.
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
    ["Ospitalità", false, true, true],
    ["Pernottamenti", false, true, true],
    ["Pasti", false, true, true],
    ["Briefing", false, true, true],
    ["Documenti", false, true, true],
    ["Mappe e percorsi", false, true, true],
  ]},
  { area: "Organizzazione avanzata", rows: [
    ["Checklist dell'evento", false, false, true],
    ["Pipeline organizzativa", false, false, true],
    ["Scadenze", false, false, true],
    ["Responsabili delle attività", false, false, true],
    ["Controllo avanzamento", false, false, true],
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

function Cell({ on, plus }) {
  return (
    <div className={`flex items-center justify-center py-3 ${plus ? "bg-tiffany-light/40" : ""}`}>
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
        <p className="text-slate-500 mt-3 text-sm md:text-base">Tutto ciò che è incluso in FREE, PLUS e PREMIUM, area per area.</p>
      </div>

      <div className="rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
        {/* Intestazione piani (sticky) */}
        <div className={`${GRID} sticky top-16 z-20 bg-white border-b border-slate-200`} data-testid="comparison-header">
          <div className="py-3 px-3 sm:px-4" />
          <div className="py-3 text-center text-xs sm:text-sm font-bold text-slate-700">FREE</div>
          <div className="py-3 text-center text-xs sm:text-sm font-bold text-slate-900 bg-tiffany-light/40 border-x border-tiffany/30">
            PLUS
            <span className="hidden sm:flex items-center justify-center gap-1 text-[10px] font-semibold text-tiffany-fg mt-0.5"><Zap className="w-3 h-3" fill="currentColor" />Consigliato</span>
          </div>
          <div className="py-3 text-center text-xs sm:text-sm font-bold text-slate-700">PREMIUM</div>
        </div>

        {COMPARISON.map((group, gi) => (
          <div key={group.area}>
            <div className={`${GRID} bg-slate-50 border-b border-slate-100`}>
              <div className="col-span-4 py-2.5 px-3 sm:px-4 text-[11px] font-bold uppercase tracking-wide text-slate-500" data-testid={`comparison-area-${gi}`}>{group.area}</div>
            </div>
            {group.rows.map(([label, f, p, pr], ri) => (
              <div key={label} className={`${GRID} ${ri % 2 ? "bg-white" : "bg-slate-50/40"} border-b border-slate-100 last:border-0 items-center`} data-testid="comparison-row">
                <div className="py-3 px-3 sm:px-4 text-sm text-slate-700">{label}</div>
                <Cell on={f} />
                <Cell on={p} plus />
                <Cell on={pr} />
              </div>
            ))}
          </div>
        ))}

        {/* Riga finale di scelta — prezzi dinamici coerenti con il selettore */}
        <div className="grid grid-cols-1 sm:grid-cols-[1.6fr_repeat(3,1fr)] border-t-2 border-slate-200 bg-white" data-testid="comparison-choice-row">
          <div className="hidden sm:flex items-center px-4 text-sm font-semibold text-slate-700">Scegli il tuo piano</div>

          {/* FREE */}
          <div className="flex flex-col items-center gap-2 text-center p-4 border-t border-slate-100 sm:border-t-0">
            <span className="sm:hidden text-xs font-bold uppercase tracking-wide text-slate-500">Free</span>
            <div className="font-display text-2xl font-bold text-slate-900">0 €</div>
            <Link to="/registrati" data-testid="choice-free-cta" onClick={() => trackEvent("pricing_cta_click", { plan: "free", where: "table" })}
              className="w-full max-w-[180px] inline-flex items-center justify-center h-10 px-4 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold transition-all active:scale-[0.98]">Crea account</Link>
          </div>

          {/* PLUS (evidenziato) */}
          <div className="flex flex-col items-center gap-2 text-center p-4 border-t border-slate-100 sm:border-t-0 bg-tiffany-light/40 sm:border-x sm:border-tiffany/30">
            <span className="sm:hidden inline-flex items-center gap-1 text-xs font-bold uppercase tracking-wide text-tiffany-fg"><Zap className="w-3 h-3" fill="currentColor" />Plus</span>
            <div>
              <span className="font-display text-2xl font-bold text-slate-900">{prices.plus} €</span>
              <span className="text-slate-500 text-xs font-medium ml-1">+ IVA</span>
              <div className="text-xs text-slate-400">/ evento</div>
            </div>
            <Link to="/registrati" data-testid="choice-plus-cta" onClick={() => trackEvent("pricing_cta_click", { plan: "plus", where: "table" })}
              className="w-full max-w-[180px] inline-flex items-center justify-center h-10 px-4 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm transition-all active:scale-[0.98]">Scegli Plus</Link>
          </div>

          {/* PREMIUM */}
          <div className="flex flex-col items-center gap-2 text-center p-4 border-t border-slate-100 sm:border-t-0">
            <span className="sm:hidden text-xs font-bold uppercase tracking-wide text-slate-500">Premium</span>
            <div>
              <span className="font-display text-2xl font-bold text-slate-900">{prices.premium} €</span>
              <span className="text-slate-500 text-xs font-medium ml-1">+ IVA</span>
              <div className="text-xs text-slate-400">/ evento</div>
            </div>
            <Link to="/registrati" data-testid="choice-premium-cta" onClick={() => trackEvent("pricing_cta_click", { plan: "premium", where: "table" })}
              className="w-full max-w-[180px] inline-flex items-center justify-center h-10 px-4 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-sm font-semibold transition-all active:scale-[0.98]">Scegli Premium</Link>
          </div>
        </div>
      </div>
      <p className="text-xs text-slate-400 mt-4 text-center">FREE = gestione staff · PLUS = gestione completa dell'evento · PREMIUM = tutto Plus + organizzazione avanzata + marketing/social.</p>
    </section>
  );
}

function PriceBlock({ amount }) {
  if (amount === 0) {
    return (
      <div className="flex items-baseline gap-1.5">
        <span className="font-display text-5xl font-bold text-slate-900" data-testid="price-value">0 €</span>
      </div>
    );
  }
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
        <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap" data-testid="plan-plus-badge">
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
        {plan.cta}
      </Link>
    </div>
  );
}

export default function Pricing() {
  const [tier, setTier] = useState("small"); // small = fino a 3 eventi | large = più di 3
  const [open, setOpen] = useState(false);
  const prices = PRICING[tier];
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
      <section className="max-w-3xl mx-auto px-6 pt-16 pb-6 text-center">
        <div className="inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold mb-5">
          <Sparkles className="w-3.5 h-3.5" />14 giorni di prova gratuita · Nessuna carta richiesta
        </div>
        <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">Scegli il piano giusto per il tuo evento.</h1>
        <p className="text-base md:text-lg text-slate-500 mt-4 max-w-xl mx-auto">Dalla gestione dello staff all'organizzazione completa e alla promozione: paghi in base a quanti eventi organizzi.</p>
      </section>

      {/* Selettore numero eventi */}
      <section className="max-w-3xl mx-auto px-6 pb-2">
        <div className="flex flex-col items-center gap-3" data-testid="pricing-selector">
          <label htmlFor="events-select" className="text-sm font-semibold text-slate-800">Quanti eventi organizzi?</label>
          <div className="relative w-full sm:w-72">
            <select
              id="events-select"
              data-testid="pricing-events-selector"
              value={tier}
              onChange={(e) => { setTier(e.target.value); trackEvent("pricing_tier_change", { tier: e.target.value }); }}
              className="w-full h-12 appearance-none rounded-xl border-2 border-tiffany bg-white px-4 pr-11 text-sm font-semibold text-slate-900 shadow-sm focus:outline-none focus:ring-2 focus:ring-tiffany/40 cursor-pointer"
            >
              <option value="small">Fino a 3 eventi</option>
              <option value="large">Più di 3 eventi</option>
            </select>
            <ChevronDown className="w-5 h-5 text-tiffany-active absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>
      </section>

      {/* 3 piani */}
      <section className="max-w-6xl mx-auto px-6 pt-10 pb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 lg:gap-8 items-stretch">
          <PlanCard plan={PLANS.free} amount={0} highlighted={false} />
          <PlanCard plan={PLANS.plus} amount={prices.plus} highlighted={true} />
          <PlanCard plan={PLANS.premium} amount={prices.premium} highlighted={false} />
        </div>
        <p className="text-xs text-slate-400 mt-8 text-center max-w-2xl mx-auto">
          Prezzi IVA esclusa, per evento. Il trattamento IVA sarà applicato secondo la normativa vigente in base alla configurazione fiscale definita all'attivazione dell'abbonamento.
        </p>
      </section>

      {/* Tabella di confronto completa (FASE 1) */}
      <ComparisonTable prices={prices} />

      {/* Final CTA */}
      <section className="max-w-3xl mx-auto px-6 py-16 mt-6 text-center">
        <h2 className="font-display text-3xl font-bold">Inizia oggi, senza pensieri.</h2>
        <p className="text-slate-500 mt-3">14 giorni gratis con il piano Free. Nessuna carta richiesta. Passa a Plus o Premium quando vuoi.</p>
        <div className="mt-7 flex justify-center">
          <Link to="/registrati" data-testid="pricing-cta-bottom"
            className="inline-flex items-center justify-center gap-2 h-12 px-7 rounded-xl bg-tiffany hover:bg-tiffany-hover text-slate-900 text-base font-semibold shadow-sm transition-all active:scale-[0.98]">
            <Sparkles className="w-5 h-5" />Crea account gratis
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
