import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Footer from "@/components/Footer";
import { trackEvent } from "@/lib/analytics";
import { useAuth } from "@/context/AuthContext";
import {
  Coins, Sparkles, Check, Menu, X, Gift, Infinity as InfinityIcon, CreditCard,
  CalendarDays, Users, Handshake, ListChecks, BedDouble, Map, LayoutDashboard, UserCog,
  Bot, LineChart, FileText, Megaphone, Zap, Mail, CalendarClock, MessageCircle,
} from "lucide-react";

const eur = (n) => Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
const num = (n) => Number(n || 0).toLocaleString("it-IT");

const FREE_FEATURES = [
  ["Eventi", CalendarDays], ["Persone", Users], ["Staff e volontari", UserCog],
  ["Sponsor e partner", Handshake], ["Team e turni", Users], ["Attività e checklist", ListChecks],
  ["Ospitalità", BedDouble], ["Percorsi", Map], ["Dashboard", LayoutDashboard],
];
const CREDIT_FEATURES = [
  ["Assistente IA", Bot], ["Analisi evento", LineChart], ["Generazione briefing", FileText],
  ["Generazione contenuti", Megaphone], ["Automazioni", Zap], ["Newsletter ed email", Mail],
  ["Google Calendar", CalendarClock], ["WhatsApp — prossimamente", MessageCircle],
];

function PackageCard({ p, authed }) {
  const net = Number(p.price) || 0;
  const vat = Math.round(net * 22) / 100;
  const gross = Math.round((net + vat) * 100) / 100;
  const hasBonus = (p.credits_bonus || 0) > 0;
  return (
    <div data-testid={`credit-pack-${p.id}`}
      className={`relative flex flex-col rounded-2xl p-5 transition-all ${p.highlight ? "bg-white border-2 border-tiffany shadow-lg shadow-tiffany/20 md:-translate-y-2" : "bg-white border border-slate-200 shadow-sm hover:shadow-md hover:-translate-y-1"}`}>
      {p.badge && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-tiffany text-slate-900 px-3 py-1 text-[11px] font-bold shadow-sm">{p.badge}</span>
      )}
      <div className="flex items-baseline gap-1.5">
        <span className="font-display text-3xl font-bold text-slate-900" data-testid={`pack-total-${p.id}`}>{num(p.credits_total)}</span>
        <span className="text-sm font-semibold text-slate-400">crediti</span>
      </div>
      {hasBonus ? (
        <div className="mt-1 text-sm text-slate-500">
          <span className="text-slate-400 line-through">{num(p.credits_base)}</span>
          <span className="mx-1 text-slate-400">→</span>
          <span className="font-semibold text-slate-700">{num(p.credits_total)}</span>
          {p.bonus_pct ? <span className="ml-2 inline-block rounded-full bg-tiffany-light text-tiffany-fg px-2 py-0.5 text-xs font-bold">+{p.bonus_pct}% in più</span> : null}
        </div>
      ) : (
        <div className="mt-1 text-sm text-slate-400">{num(p.credits_base)} crediti</div>
      )}
      <div className="mt-4 flex items-baseline gap-1.5">
        <span className="font-display text-2xl font-bold text-slate-900">€ {eur(net)}</span>
        <span className="text-sm text-slate-500">+ IVA</span>
      </div>
      <div className="text-xs text-slate-400 mt-0.5">IVA 22% € {eur(vat)} · Totale € {eur(gross)}</div>
      <Link to={authed ? "/profilo?tab=crediti" : "/registrati"} data-testid={`pack-cta-${p.id}`}
        onClick={() => trackEvent("credits_pack_cta", { package: p.id, authed })}
        className={`mt-5 inline-flex items-center justify-center h-11 px-5 rounded-xl text-sm font-semibold transition-all active:scale-[0.98] ${p.highlight ? "bg-tiffany hover:bg-tiffany-hover text-slate-900" : "bg-slate-900 hover:bg-slate-800 text-white"}`}>
        {authed ? "Ricarica crediti" : "Inizia gratuitamente"}
      </Link>
    </div>
  );
}

function UsageColumn({ title, subtitle, items, tone }) {
  const free = tone === "free";
  return (
    <div className={`rounded-2xl border p-6 ${free ? "border-emerald-200 bg-emerald-50/50" : "border-tiffany-border bg-tiffany-light/30"}`} data-testid={`usage-col-${tone}`}>
      <h3 className="font-display text-xl font-bold text-slate-900">{title}</h3>
      <p className={`text-sm font-semibold mt-1 ${free ? "text-emerald-700" : "text-tiffany-fg"}`}>{subtitle}</p>
      <ul className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2.5">
        {items.map(([label, Icon]) => (
          <li key={label} className="flex items-center gap-2.5 text-sm text-slate-700">
            <span className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${free ? "bg-emerald-100 text-emerald-600" : "bg-tiffany-light text-tiffany-active"}`}><Icon className="w-4 h-4" /></span>
            <span>{label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function Pricing() {
  const [open, setOpen] = useState(false);
  const [packs, setPacks] = useState([]);
  const [unit, setUnit] = useState(null);
  const { user } = useAuth();
  const authed = !!(user && user.org_id);

  useEffect(() => {
    trackEvent("pricing_view");
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/credits/packages-public`)
      .then((r) => r.json())
      .then((d) => { if (d && Array.isArray(d.packages)) setPacks(d.packages); if (d?.credit_unit_eur != null) setUnit(d.credit_unit_eur); })
      .catch(() => {});
  }, []);

  return (
    <div className="bg-white text-slate-900" data-testid="pricing-page">
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" data-testid="pricing-logo"><img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-14 sm:h-16 w-auto" /></Link>
          <nav className="hidden lg:flex items-center gap-7">
            <Link to="/#funzionalita" className="text-sm font-medium text-slate-600 hover:text-slate-900">Funzionalità</Link>
            <Link to="/prezzi" className="text-sm font-semibold text-slate-900">Crediti</Link>
          </nav>
          <div className="hidden lg:flex items-center gap-3">
            <Link to="/login" className="text-sm font-semibold text-slate-700 hover:text-slate-900">Accedi</Link>
            <Link to="/registrati" data-testid="pricing-header-cta" className="h-10 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm transition-all active:scale-[0.98] flex items-center">Inizia gratuitamente</Link>
          </div>
          <button className="lg:hidden" onClick={() => setOpen((o) => !o)}>{open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}</button>
        </div>
        {open && (
          <div className="lg:hidden border-t border-slate-100 bg-white px-6 py-4 space-y-3">
            <Link to="/#funzionalita" className="block text-sm font-medium text-slate-600">Funzionalità</Link>
            <Link to="/prezzi" className="block text-sm font-semibold text-slate-900">Crediti</Link>
            <div className="flex gap-3 pt-2">
              <Link to="/login" className="flex-1 h-10 rounded-lg border border-slate-200 flex items-center justify-center text-sm font-semibold">Accedi</Link>
              <Link to="/registrati" className="flex-1 h-10 rounded-lg bg-tiffany text-slate-900 text-sm font-semibold flex items-center justify-center">Inizia gratuitamente</Link>
            </div>
          </div>
        )}
      </header>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-6 pt-16 pb-8 text-center">
        <div className="inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold mb-5">
          <Gift className="w-3.5 h-3.5" />100 crediti CRMEvent inclusi alla registrazione
        </div>
        <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">Usa CRMEvent gratuitamente.</h1>
        <p className="text-base md:text-lg text-slate-500 mt-4 max-w-xl mx-auto">Paghi solo i servizi avanzati che utilizzi. La gestione ordinaria del tuo evento non consuma crediti.</p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <Link to={authed ? "/profilo?tab=crediti" : "/registrati"} data-testid="pricing-hero-cta"
            className="inline-flex items-center justify-center gap-2 h-12 px-7 rounded-xl bg-tiffany hover:bg-tiffany-hover text-slate-900 text-base font-semibold shadow-sm transition-all active:scale-[0.98]">
            <Sparkles className="w-5 h-5" />{authed ? "Ricarica crediti" : "Inizia gratuitamente"}
          </Link>
        </div>
        <div className="mt-5 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-slate-500">
          <span className="inline-flex items-center gap-1.5"><CreditCard className="w-4 h-4 text-tiffany-active" />Nessuna carta richiesta</span>
          <span className="inline-flex items-center gap-1.5"><InfinityIcon className="w-4 h-4 text-tiffany-active" />I crediti non scadono</span>
          <span className="inline-flex items-center gap-1.5"><Check className="w-4 h-4 text-tiffany-active" />Gestione evento sempre gratuita</span>
        </div>
      </section>

      {/* Quando utilizzo i crediti */}
      <section className="max-w-5xl mx-auto px-6 pt-6 pb-4" data-testid="usage-section">
        <div className="text-center mb-8">
          <h2 className="font-display text-3xl font-bold">Quando utilizzo i crediti?</h2>
          <p className="text-slate-500 mt-3 text-sm md:text-base">La gestione ordinaria è gratuita. I crediti servono solo per i servizi avanzati.</p>
        </div>
        <div className="grid md:grid-cols-2 gap-5">
          <UsageColumn tone="free" title="Gestisci il tuo evento" subtitle="Nessun consumo di crediti" items={FREE_FEATURES} />
          <UsageColumn tone="credit" title="CRMEvent lavora per te" subtitle="Questi servizi possono utilizzare crediti" items={CREDIT_FEATURES} />
        </div>
      </section>

      {/* Tagli di ricarica */}
      <section className="max-w-6xl mx-auto px-6 pt-12 pb-4" data-testid="packages-section">
        <div className="text-center mb-8">
          <h2 className="font-display text-3xl font-bold">Ricarica quando vuoi</h2>
          <p className="text-slate-500 mt-3 text-sm md:text-base">Scegli il taglio più adatto. Prezzi IVA esclusa, IVA 22% al checkout. I crediti non scadono.</p>
        </div>
        {packs.length === 0 ? (
          <p className="text-center text-slate-400 text-sm">Caricamento tagli…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 lg:gap-6">
            {packs.map((p) => <PackageCard key={p.id} p={p} authed={authed} />)}
          </div>
        )}
        <p className="text-xs text-slate-400 mt-8 text-center max-w-2xl mx-auto">
          {unit != null && <span data-testid="pricing-credit-unit">1 credito = € {Number(unit).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}. </span>}Prezzi IVA esclusa; l'IVA del 22% è aggiunta al momento del pagamento. Il pagamento avviene in modo sicuro tramite Stripe.
        </p>
      </section>

      {/* Final CTA */}
      <section className="max-w-3xl mx-auto px-6 py-16 mt-4 text-center">
        <h2 className="font-display text-3xl font-bold">Inizia oggi, senza pensieri.</h2>
        <p className="text-slate-500 mt-3">Registrati gratuitamente e ricevi 100 crediti CRMEvent. Nessuna carta richiesta.</p>
        <div className="mt-7 flex justify-center">
          <Link to={authed ? "/profilo?tab=crediti" : "/registrati"} data-testid="pricing-cta-bottom"
            className="inline-flex items-center justify-center gap-2 h-12 px-7 rounded-xl bg-tiffany hover:bg-tiffany-hover text-slate-900 text-base font-semibold shadow-sm transition-all active:scale-[0.98]">
            <Sparkles className="w-5 h-5" />{authed ? "Vai all'Area Account" : "Inizia gratuitamente"}
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
