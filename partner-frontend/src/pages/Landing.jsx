import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, UserPlus, Link2, Users, Wallet, CalendarDays, UsersRound, Handshake, BedDouble, ChevronDown, ShieldCheck } from "lucide-react";
import { Button, Logo } from "@/components/ui";
import Simulator from "@/components/Simulator";

const FEATURES = [[CalendarDays, "Eventi e attività", "Pianificazione, scadenze e documenti in un unico posto."], [UsersRound, "Staff, volontari e turni", "Team, turni e coperture sempre sotto controllo."],
  [Handshake, "Sponsor e partner", "Pipeline commerciale e aziende collegate agli eventi."], [BedDouble, "Ospitalità", "Camere, ospiti e logistica senza fogli Excel."]];
const STEPS = [[UserPlus, "Registrati gratis", "Compila la candidatura: il team CRMEvent la verifica e la approva."], [Link2, "Condividi il tuo link", "Usa il link personale o crea link diversi per ogni campagna."],
  [Users, "I clienti si abbonano", "Gli organizzatori provano CRMEvent gratis e scelgono BRONZE, SILVER o GOLD."], [Wallet, "Ricevi le commissioni", "10% sugli abbonamenti incassati per 24 mesi, liquidati ogni trimestre."]];
const FAQ = [["Quanto costa diventare partner?", "Nulla: la registrazione è gratuita e senza vincoli."],
  ["Quanto guadagno?", "Il 10% dell'importo dell'abbonamento effettivamente incassato, imposte escluse, per 24 mesi dal primo pagamento del cliente, compresi rinnovi e upgrade."],
  ["Come viene attribuito un cliente?", "Il cliente deve registrarsi dal tuo link entro 30 giorni dalla visita. Ogni organizzazione può avere un solo partner e l'attribuzione resta valida anche dopo la registrazione."],
  ["Quando vengo pagato?", "Le commissioni diventano liquidabili alla chiusura del trimestre, trascorsi almeno 30 giorni dal pagamento. Ti chiederemo l'IBAN prima della prima liquidazione."],
  ["Cosa è escluso?", "Gli acquisti Marketplace, gli importi rimborsati o stornati e i pagamenti non incassati."],
  ["Chi può partecipare?", "Professionisti, consulenti, influencer, agenzie, organizzatori di eventi e società sportive, come privati, professionisti o aziende."]];

function Faq() {
  const [open, setOpen] = useState(0);
  return (
    <div className="divide-y divide-slate-200 border-y border-slate-200" data-testid="faq">
      {FAQ.map(([q, a], i) => (
        <div key={q}>
          <button type="button" onClick={() => setOpen(open === i ? -1 : i)} className="w-full flex items-center justify-between gap-4 py-5 text-left font-semibold" aria-expanded={open === i} data-testid={`faq-${i}`}>
            {q}<ChevronDown className={`w-5 h-5 shrink-0 text-tiffany transition-transform ${open === i ? "rotate-180" : ""}`} />
          </button>
          {open === i && <p className="pb-5 -mt-1 text-slate-600 text-sm leading-relaxed">{a}</p>}
        </div>
      ))}
    </div>
  );
}

export default function Landing() {
  return (
    <div className="min-h-screen" data-testid="landing-page">
      <header className="sticky top-0 z-30 bg-white/80 backdrop-blur-md border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <Logo className="text-base sm:text-lg" />
          <nav className="flex items-center gap-1 sm:gap-2">
            <Link to="/login" className="h-10 px-3 sm:px-4 inline-flex items-center rounded-full text-sm font-semibold text-slate-700 hover:bg-slate-100 transition-colors" data-testid="nav-login">Accedi</Link>
            <Link to="/registrati" data-testid="nav-register"><Button className="h-10 px-3 sm:px-4"><span className="sm:hidden">Diventa</span><span className="hidden sm:inline">Diventa Partner</span></Button></Link>
          </nav>
        </div>
      </header>

      <section className="relative overflow-hidden grain">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-20 grid lg:grid-cols-[1.05fr_1fr] gap-12 items-center">
          <div>
            <span className="fade-up inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold">Programma CRMEvent Partner · registrazione gratuita</span>
            <h1 className="fade-up d1 mt-5 text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.05]">Condividi CRMEvent. <span className="text-tiffany">Cresci insieme a noi.</span></h1>
            <p className="fade-up d2 mt-6 text-base md:text-lg text-slate-600 max-w-xl">Consiglia il gestionale che aiuta gli organizzatori a coordinare eventi, staff, volontari e sponsor. Ricevi il <b className="text-ink">10% per 24 mesi</b> sugli abbonamenti dei clienti che porti.</p>
            <div className="fade-up d3 mt-8 flex flex-wrap gap-3">
              <Link to="/registrati" data-testid="hero-register"><Button className="h-12 px-6">Diventa Partner <ArrowRight className="w-4 h-4" /></Button></Link>
              <Link to="/login" data-testid="hero-login"><Button variant="outline" className="h-12 px-6">Accedi</Button></Link>
            </div>
            <p className="mt-5 text-xs text-slate-500 flex items-center gap-1.5"><ShieldCheck className="w-4 h-4 text-tiffany" />Ogni candidatura viene verificata e approvata dal team CRMEvent.</p>
          </div>
          <div className="fade-up d2" id="simulatore"><Simulator /></div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-20" data-testid="features">
        <h2 className="text-base md:text-lg font-semibold text-tiffany-fg">Cosa proponi ai tuoi contatti</h2>
        <p className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight max-w-2xl">CRMEvent, il CRM per organizzare eventi senza caos.</p>
        <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map(([Icon, t, d]) => (
            <div key={t} className="rounded-3xl border border-slate-200 p-6 transition-[transform,box-shadow] duration-200 hover:-translate-y-1 hover:shadow-lg">
              <Icon className="w-6 h-6 text-tiffany" /><h3 className="mt-4 font-bold">{t}</h3><p className="mt-1 text-sm text-slate-600">{d}</p>
            </div>))}
        </div>
      </section>

      <section className="bg-ink text-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
          <h2 className="text-base md:text-lg font-semibold text-tiffany">Come funziona</h2>
          <p className="mt-2 text-3xl sm:text-4xl font-extrabold tracking-tight">Quattro passaggi, nessun costo.</p>
          <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STEPS.map(([Icon, t, d], i) => (
              <div key={t} className="rounded-3xl border border-white/10 bg-white/5 p-6 transition-transform duration-200 hover:-translate-y-1" data-testid={`step-${i}`}>
                <div className="w-11 h-11 rounded-2xl bg-tiffany text-ink grid place-items-center"><Icon className="w-5 h-5" /></div>
                <div className="mt-5 text-xs text-slate-400">0{i + 1}</div><h3 className="mt-1 text-lg font-bold">{t}</h3><p className="mt-2 text-sm text-slate-300 leading-relaxed">{d}</p>
              </div>))}
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-20 grid lg:grid-cols-[1fr_1.4fr] gap-10">
        <div><h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">Domande frequenti</h2><p className="mt-3 text-slate-600">Hai altre domande? Scrivi a <a href="mailto:support@crmevent.it" className="underline">support@crmevent.it</a>.</p></div>
        <Faq />
      </section>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 pb-20">
        <div className="rounded-[2rem] bg-tiffany p-8 sm:p-12 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div><h2 className="text-3xl font-extrabold text-ink">Pronto a crescere con noi?</h2><p className="mt-2 text-ink/80">Registrazione gratuita, approvazione rapida, commissioni per 24 mesi.</p></div>
          <div className="flex gap-3 flex-wrap"><Link to="/registrati" data-testid="cta-register"><Button variant="dark" className="h-12 px-6">Diventa Partner</Button></Link><Link to="/login" data-testid="cta-login"><Button variant="outline" className="h-12 px-6">Accedi</Button></Link></div>
        </div>
      </section>

      <footer className="border-t border-slate-100 py-8 text-center text-xs text-slate-500">© {new Date().getFullYear()} CRMEvent · <a href="https://crmevent.it" className="hover:text-ink">crmevent.it</a> · <a href="https://crmevent.it/privacy" className="hover:text-ink">Privacy</a></footer>
    </div>
  );
}
