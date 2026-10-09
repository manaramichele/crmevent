import { Link } from "react-router-dom";
import { ArrowRight, Link2, BadgePercent, LayoutDashboard, ShieldCheck } from "lucide-react";
import { Button, Logo } from "@/components/ui";
import Simulator from "@/components/Simulator";

const STEPS = [
  [Link2, "Condividi il tuo link", "Ricevi un link personale da inviare a organizzatori di eventi, associazioni, società sportive e agenzie."],
  [BadgePercent, "Guadagni sugli incassi", "Ogni cliente che si abbona tramite il tuo link ti riconosce una commissione sugli abbonamenti effettivamente pagati."],
  [LayoutDashboard, "Tutto sotto controllo", "Nella dashboard vedi clienti portati, commissioni maturate e pagamenti ricevuti."],
];

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
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-20 grid lg:grid-cols-[1.1fr_1fr] gap-12 items-center">
          <div>
            <span className="fade-up inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold">Programma Partner CRMEvent</span>
            <h1 className="fade-up d1 mt-5 text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.05]">Porta CRMEvent agli organizzatori di eventi. <span className="text-tiffany">Guadagna su ogni abbonamento.</span></h1>
            <p className="fade-up d2 mt-6 text-base md:text-lg text-slate-600 max-w-xl">Consulenti, agenzie, professionisti o semplici appassionati: consiglia la piattaforma che organizza staff, volontari, turni e sponsor, e ricevi una commissione sui primi 12 mesi di abbonamento dei clienti che porti.</p>
            <div className="fade-up d3 mt-8 flex flex-wrap gap-3">
              <Link to="/registrati" data-testid="hero-register"><Button className="h-12 px-6">Diventa Partner <ArrowRight className="w-4 h-4" /></Button></Link>
              <a href="#simulatore" data-testid="hero-simulator"><Button variant="outline" className="h-12 px-6">Calcola il guadagno</Button></a>
            </div>
            <p className="mt-5 text-xs text-slate-500 flex items-center gap-1.5"><ShieldCheck className="w-4 h-4 text-tiffany" />Ogni candidatura viene verificata e approvata dal team CRMEvent.</p>
          </div>
          <div className="fade-up d2" id="simulatore"><Simulator /></div>
        </div>
      </section>

      <section className="bg-ink text-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
          <h2 className="text-base md:text-lg font-semibold text-tiffany">Come funziona</h2>
          <div className="mt-8 grid md:grid-cols-3 gap-5">
            {STEPS.map(([Icon, t, d], i) => (
              <div key={t} className="rounded-3xl border border-white/10 bg-white/5 p-6 transition-transform duration-200 hover:-translate-y-1" data-testid={`step-${i}`}>
                <div className="w-11 h-11 rounded-2xl bg-tiffany text-ink grid place-items-center"><Icon className="w-5 h-5" /></div>
                <div className="mt-5 text-xs text-slate-400">0{i + 1}</div>
                <h3 className="mt-1 text-xl font-bold">{t}</h3>
                <p className="mt-2 text-sm text-slate-300 leading-relaxed">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-20 grid md:grid-cols-[1fr_auto] gap-6 items-center">
        <div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight">Pronto a iniziare?</h2>
          <p className="mt-3 text-slate-600 max-w-2xl">Registrati con email o Google, completa il profilo fiscale (privato, professionista o azienda) e attendi l'approvazione. Riceverai subito il tuo link referral.</p>
        </div>
        <Link to="/registrati" data-testid="cta-register"><Button className="h-12 px-6">Crea il tuo account partner <ArrowRight className="w-4 h-4" /></Button></Link>
      </section>

      <footer className="border-t border-slate-100 py-8 text-center text-xs text-slate-500">© {new Date().getFullYear()} CRMEvent · <a href="https://crmevent.it" className="hover:text-ink">crmevent.it</a></footer>
    </div>
  );
}
