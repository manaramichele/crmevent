import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { trackEvent } from "@/lib/analytics";
import Footer from "@/components/Footer";
import PlansSection from "@/components/PlansSection";
import PlannerDemoSection from "@/components/landing/PlannerDemoSection";
import EventMapSection from "@/components/landing/EventMapSection";
import { toast } from "sonner";
import {
  CalendarDays, Building2, Handshake, UserCog, Users2, Clock, Map as MapIcon, Film,
  CalendarCheck2, ArrowRight, Check, Menu, X, MapPin, Navigation, Sparkles,
} from "lucide-react";

const NAV = [
  ["Funzionalità", "funzionalita"], ["Staff & Volontari", "staff"], ["Sponsor", "sponsor"], ["Event Planner", "event-planner"],
  ["Event Map", "event-map"], ["Come funziona", "come-funziona"], ["Prezzi", "prezzi"],
];

const GAP = 48; // spazio visibile tra header sticky e inizio contenuti
const targetTop = (el) => {
  const headerH = document.querySelector("[data-testid='landing-header']")?.getBoundingClientRect().height || 0;
  const padTop = parseFloat(getComputedStyle(el).paddingTop) || 0;
  return el.getBoundingClientRect().top + window.scrollY + padTop - headerH - GAP;
};
const scrollTo = (id, behavior = "smooth") => {
  const el = document.getElementById(id);
  if (!el) return;
  window.scrollTo({ top: targetTop(el), behavior });
  // corregge eventuali spostamenti dovuti a immagini caricate durante lo scorrimento
  [700, 1400].forEach((ms) => setTimeout(() => {
    const t = targetTop(el);
    if (Math.abs(t - window.scrollY) > 4) window.scrollTo({ top: t, behavior: "auto" });
  }, ms));
};

function BrowserFrame({ children, url = "app.crmevent.it" }) {
  return (
    <div className="rounded-xl border border-slate-200 shadow-2xl shadow-slate-300/40 overflow-hidden bg-white">
      <div className="h-9 bg-slate-50 border-b border-slate-200 flex items-center px-3 gap-1.5">
        <span className="w-3 h-3 rounded-full bg-red-300" /><span className="w-3 h-3 rounded-full bg-amber-300" /><span className="w-3 h-3 rounded-full bg-emerald-300" />
        <div className="ml-3 flex-1 h-5 rounded bg-white border border-slate-200 text-[10px] text-slate-400 flex items-center px-2 min-w-0"><span className="truncate">{url}</span></div>
      </div>
      <div className="bg-slate-50/60">{children}</div>
    </div>
  );
}

function PipelineMock() {
  const cols = [["Prospect", [["Sport Point Toscana", "Stand expo", "€ 2.000"], ["Bici & Run Store", "Area sponsor", "€ 1.500"]], "border-t-slate-300"],
    ["Proposta inviata", [["Acqua Fonte Alta", "Fornitore ristoro", "€ 4.000"]], "border-t-amber-400"],
    ["In trattativa", [["Energy Bar Italia", "Pacco gara", "€ 6.000"], ["Auto Pisa Mobility", "Auto ufficiale", "€ 8.000"]], "border-t-tiffany"],
    ["Confermato", [["Banca del Territorio", "Title sponsor", "€ 25.000"]], "border-t-emerald-400"]];
  return (
    <div className="text-left" data-testid="home-sponsor-pipeline">
      <div className="px-4 pt-3 flex items-center justify-between"><span className="text-xs font-semibold text-slate-700">Sponsor · Maratona di Pisa (esempio)</span><span className="text-[11px] text-slate-500">Pipeline € 46.500</span></div>
      <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
        {cols.map(([t, cards, b]) => (
          <div key={t} className={`bg-slate-50 rounded-lg border border-slate-200 border-t-4 ${b}`}>
            <div className="px-2 py-2 text-[10px] font-semibold text-slate-600">{t}</div>
            <div className="p-1.5 space-y-1.5">
              {cards.map(([n, p, v]) => (<div key={n} className="bg-white rounded border border-slate-200 p-2">
                <div className="text-[10px] font-semibold text-slate-800 leading-tight">{n}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{p}</div><div className="text-[10px] font-semibold text-tiffany-active mt-0.5">{v}</div></div>))}
            </div>
          </div>))}
      </div>
    </div>
  );
}

function PhoneFrame({ children }) {
  return (
    <div className="mx-auto w-[260px] rounded-[2rem] border-[10px] border-slate-900 bg-slate-900 shadow-2xl shadow-slate-400/40">
      <div className="rounded-[1.3rem] overflow-hidden bg-slate-50">{children}</div>
    </div>
  );
}

function VolunteerMock() {
  const rows = [[Clock, "Turno", "13 Dic · 07:30–13:30"], [MapPin, "Luogo", "Area arrivo"], [UserCog, "Ruolo", "Addetto ristoro"], [Users2, "Team", "Volontari percorso"], [Navigation, "Ritrovo", "Gazebo segreteria · 07:15"]];
  return (
    <div className="text-left" data-testid="home-volunteer-mock">
      <div className="bg-slate-900 p-4 text-white">
        <div className="text-[10px] text-tiffany font-semibold uppercase">Prossimo evento</div>
        <div className="font-display font-bold">Maratona di Pisa</div>
        <div className="text-[10px] text-slate-300 mt-1 flex items-center gap-1"><CalendarDays className="w-3 h-3" />Domenica 13 Dic 2026 · esempio</div>
      </div>
      <div className="p-3 space-y-2">
        {rows.map(([Icon, l, v]) => (<div key={l} className="flex items-center gap-2 bg-white rounded-lg border border-slate-200 p-2">
          <Icon className="w-4 h-4 text-tiffany-active" /><span className="text-[10px] text-slate-400 w-12">{l}</span><span className="text-[11px] font-medium text-slate-800">{v}</span></div>))}
        <div className="bg-tiffany rounded-lg p-2 text-center text-[11px] font-semibold text-slate-900">Aggiungi a Google Calendar</div>
      </div>
    </div>
  );
}

const FEATURES = [
  [CalendarDays, "Eventi", "Gestisci tutte le edizioni dei tuoi eventi da un unico spazio."],
  [Building2, "Aziende e referenti", "Ogni azienda con i suoi referenti in un'unica scheda, senza duplicazioni."],
  [Handshake, "Sponsor & Partner", "Prospect, trattative e partnership in una pipeline commerciale."],
  [UserCog, "Staff & Volontari", "Assegna persone, ruoli, aree operative e responsabilità."],
  [Users2, "Team", "Crea squadre operative e mostra subito chi lavora con chi."],
  [Clock, "Turni", "Organizza giorni, orari, punti di ritrovo e attività."],
  [MapIcon, "Mappe & Percorsi", "Condividi percorsi, mappe operative e punti di riferimento."],
  [MapIcon, "Event Planner", "Progetta percorsi, strutture e spazi del tuo evento direttamente sulla mappa."],
  [CalendarCheck2, "Google Calendar", "Porta eventi e turni nel calendario degli utenti."],
  [Film, "Event Map", "Genera dalla traccia GPX un video animato del percorso, pronto per i social."],
];

function DemoForm() {
  const [f, setF] = useState({ nome: "", cognome: "", organizzazione: "", email: "", telefono: "", tipologia_eventi: "", eventi_anno: "", messaggio: "", privacy: false, marketing_consent: false, demo_data: "", demo_ora: "" });
  const minDay = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const ch = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.privacy) return toast.error("Accetta la privacy policy per continuare");
    setBusy(true);
    try {
      const { data } = await api.post("/leads", { ...f, demo_data: f.demo_data || null, demo_ora: f.demo_ora || null, source: "richiedi_demo_form" });
      try { localStorage.setItem("crmevent_lead", JSON.stringify({ id: data.id, email: f.email, nome: f.nome, cognome: f.cognome, ts: Date.now() })); } catch {}
      trackEvent("generate_lead");
      toast.success("Richiesta inviata! Apriamo la demo interattiva…");
      window.location.assign("/demo");
    }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); } finally { setBusy(false); }
  };
  const inp = "w-full h-11 px-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm";
  if (sent) return (
    <div className="bg-white rounded-2xl border border-slate-200 p-10 text-center shadow-sm">
      <div className="w-14 h-14 rounded-full bg-tiffany-light flex items-center justify-center mx-auto mb-4"><Check className="w-7 h-7 text-tiffany-active" /></div>
      <h3 className="font-display text-xl font-bold text-slate-900">Grazie, richiesta ricevuta!</h3>
      <p className="text-slate-500 mt-2 text-sm">Il team <strong className="font-semibold text-slate-700">CRMEvent</strong> ti contatterà al più presto per organizzare la demo.</p>
    </div>
  );
  return (
    <form onSubmit={submit} className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 shadow-sm grid grid-cols-1 sm:grid-cols-2 gap-4">
      <input className={inp} placeholder="Nome*" value={f.nome} onChange={ch("nome")} required data-testid="lead-nome" />
      <input className={inp} placeholder="Cognome" value={f.cognome} onChange={ch("cognome")} data-testid="lead-cognome" />
      <input className={`${inp} sm:col-span-2`} placeholder="Organizzazione / Azienda" value={f.organizzazione} onChange={ch("organizzazione")} data-testid="lead-org" />
      <input className={inp} type="email" placeholder="Email*" value={f.email} onChange={ch("email")} required data-testid="lead-email" />
      <input className={inp} placeholder="Telefono" value={f.telefono} onChange={ch("telefono")} data-testid="lead-tel" />
      <select className={inp} value={f.tipologia_eventi} onChange={ch("tipologia_eventi")} data-testid="lead-tipologia">
        <option value="">Tipologia di eventi organizzati</option>
        {["Sportivi", "Running / Trail", "Festival", "Fiere / Congressi", "Aziendali", "Associazioni / No profit", "Altro"].map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <select className={inp} value={f.eventi_anno} onChange={ch("eventi_anno")} data-testid="lead-anno">
        <option value="">Eventi all'anno</option>
        {["1–2", "3–5", "6–10", "10+"].map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <div className="sm:col-span-2 grid grid-cols-2 gap-4">
        <label className="text-xs text-slate-500 space-y-1"><span>Giorno preferito per la demo</span>
          <input className={inp} type="date" min={minDay} value={f.demo_data} onChange={ch("demo_data")} data-testid="lead-demo-data" /></label>
        <label className="text-xs text-slate-500 space-y-1"><span>Orario preferito</span>
          <select className={inp} value={f.demo_ora} onChange={ch("demo_ora")} disabled={!f.demo_data} data-testid="lead-demo-ora">
            <option value="">Scegli</option>{["09:30", "10:30", "11:30", "14:30", "15:30", "16:30", "17:30"].map((o) => <option key={o} value={o}>{o}</option>)}
          </select></label>
        {f.demo_data && <p className="col-span-2 text-xs text-slate-400">La data è da confermare: riceverai un'email di conferma dal team CRMEvent.</p>}
      </div>
      <textarea className="sm:col-span-2 min-h-[90px] p-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm" placeholder="Messaggio" value={f.messaggio} onChange={ch("messaggio")} data-testid="lead-msg" />
      <label className="sm:col-span-2 flex items-start gap-2 text-xs text-slate-500">
        <input type="checkbox" checked={f.privacy} onChange={ch("privacy")} className="mt-0.5 accent-tiffany" data-testid="lead-privacy" />
        Ho letto e accetto la <Link to="/privacy-policy" className="text-tiffany-active underline">Privacy Policy</Link> e acconsento al trattamento dei dati per essere ricontattato.
      </label>
      <label className="sm:col-span-2 flex items-start gap-2 text-xs text-slate-500">
        <input type="checkbox" checked={f.marketing_consent} onChange={ch("marketing_consent")} className="mt-0.5 accent-tiffany" data-testid="lead-marketing" />
        Acconsento a ricevere comunicazioni commerciali e informative su CRMEvent (facoltativo, revocabile in qualsiasi momento).
      </label>
      <button type="submit" disabled={busy} data-testid="lead-submit" className="sm:col-span-2 h-12 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.99]">
        {busy ? "Invio..." : "Richiedi una demo"}
      </button>
    </form>
  );
}

const Section = ({ id, children, className = "" }) => <section id={id} className={`px-6 ${className}`}><div className="max-w-6xl mx-auto">{children}</div></section>;
const Eyebrow = ({ children }) => <div className="text-tiffany-active font-semibold text-sm uppercase tracking-wide mb-3">{children}</div>;
const H2 = ({ children }) => <h2 className="font-display text-3xl md:text-4xl font-bold text-slate-900 tracking-tight">{children}</h2>;

export default function LandingPage() {
  const [open, setOpen] = useState(false);
  useEffect(() => { document.title = "CRMEvent | Il CRM per organizzare eventi"; }, []);
  useEffect(() => {
    const go = () => { const id = decodeURIComponent(window.location.hash.slice(1)); if (id) setTimeout(() => scrollTo(id, "auto"), 300); };
    go();
    window.addEventListener("hashchange", go);
    return () => window.removeEventListener("hashchange", go);
  }, []);
  const goMobile = (id) => { setOpen(false); requestAnimationFrame(() => requestAnimationFrame(() => scrollTo(id))); };

  return (
    <div className="bg-white text-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#FFFFFF] border-b border-slate-100 pt-[env(safe-area-inset-top)]" data-testid="landing-header">
        <div className="max-w-6xl mx-auto px-6 min-h-[4.75rem] py-2.5 flex items-center justify-between">
          <Link to="/" data-testid="landing-logo"><img src="/logo-crmevent-header.png?v=1" alt="CRMEvent" className="h-14 sm:h-16 w-auto" /></Link>
          <nav className="hidden xl:flex items-center gap-6 mx-6">
            {NAV.map(([l, id]) => <button key={id} onClick={() => scrollTo(id)} className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors whitespace-nowrap">{l}</button>)}
          </nav>
          <div className="hidden xl:flex items-center gap-4 shrink-0">
            <Link to="/login" data-testid="landing-login" className="text-sm font-semibold text-slate-700 hover:text-slate-900">Accedi</Link>
            <Link to="/registrati" data-testid="landing-try-cta" className="cta-shimmer h-10 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm transition-all active:scale-[0.98] flex items-center">Registrati gratis</Link>
          </div>
          <button className="xl:hidden" onClick={() => setOpen((o) => !o)} data-testid="landing-menu">{open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}</button>
        </div>
        {open && (
          <div className="xl:hidden border-t border-slate-100 bg-[#FFFFFF] px-6 py-4 space-y-3" data-testid="landing-mobile-menu">
            {NAV.map(([l, id]) => <button key={id} onClick={() => goMobile(id)} className="block text-sm font-medium text-slate-600">{l}</button>)}
            <div className="flex gap-3 pt-2"><Link to="/login" className="flex-1 h-10 rounded-lg border border-slate-200 flex items-center justify-center text-sm font-semibold">Accedi</Link>
              <Link to="/registrati" onClick={() => setOpen(false)} data-testid="landing-mobile-try-cta" className="cta-shimmer flex-1 h-10 rounded-lg bg-tiffany text-slate-900 text-sm font-semibold flex items-center justify-center">Registrati gratis</Link></div>
          </div>
        )}
      </header>

      {/* Hero */}
      <Section className="pt-16 pb-20 lg:pt-24">
        <div className="grid lg:grid-cols-[1fr_1.1fr] gap-12 items-center">
          <div className="animate-fade-up">
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.05]">Organizza il tuo evento. <span className="text-tiffany-active">Tutto in un'unica piattaforma.</span></h1>
            <p className="text-lg text-slate-500 mt-6 max-w-xl">Gestisci eventi, staff, volontari, sponsor, turni e tutte le informazioni operative del tuo evento con <strong className="font-semibold text-slate-700">CRMEvent</strong>.</p>
            <div className="flex flex-wrap gap-3 mt-8">
              <Link to="/registrati" data-testid="hero-cta-start-free" className="cta-shimmer h-12 px-6 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.98] inline-flex items-center gap-2">Registrati gratis <ArrowRight className="w-4 h-4" /></Link>
            </div>
            <div className="mt-5 flex items-center gap-2 text-sm text-slate-500" data-testid="hero-credits-note">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1.5 font-semibold"><Sparkles className="w-4 h-4" />14 giorni di prova gratuita</span>
              <span>· Nessuna carta richiesta</span>
            </div>
          </div>
          <div className="animate-fade-up" data-testid="hero-planner-image">
            <BrowserFrame url="app.crmevent.it/eventi/maratona-di-pisa/planner">
              <picture>
                <source srcSet="/media/hero-event-planner.webp" type="image/webp" />
                <img src="/media/hero-event-planner.jpg" width="672" height="570" fetchPriority="high" alt="Event Planner di CRMEvent: area arrivo della Maratona di Pisa con segreteria, arco di arrivo, corridoio transennato, ristoro, palco premiazioni e stand sponsor" className="block w-full h-auto" />
              </picture>
            </BrowserFrame>
            <p className="mt-2 text-xs text-slate-400 text-right">Event Planner · esempio con percorso dimostrativo</p>
          </div>
        </div>
      </Section>

      {/* Funzionalità */}
      <Section id="funzionalita" className="py-20 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Funzionalità</Eyebrow><H2>Un'unica piattaforma per tutto il tuo evento</H2></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 mt-12" data-testid="home-features">
          {FEATURES.map(([Icon, t, d, badge]) => (
            <div key={t} className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-lg hover:-translate-y-0.5 transition-[transform,box-shadow]">
              <div className="w-10 h-10 rounded-lg bg-tiffany-light flex items-center justify-center mb-3"><Icon className="w-5 h-5 text-tiffany-active" /></div>
              <h3 className="font-display font-bold text-slate-900 flex items-center gap-2 flex-wrap">{t}{badge && <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 ring-1 ring-amber-200">{badge}</span>}</h3>
              <p className="text-sm text-slate-500 mt-1.5 leading-relaxed">{d}</p>
            </div>))}
        </div>
      </Section>

      {/* Staff & Volontari */}
      <Section id="staff" className="py-20 bg-slate-900 rounded-none">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div><div className="text-tiffany font-semibold text-sm uppercase tracking-wide mb-3">Staff & Volontari</div>
            <h2 className="font-display text-3xl md:text-4xl font-bold text-white tracking-tight">Ogni volontario sa cosa deve fare.</h2>
            <p className="text-slate-300 mt-5 max-w-lg">Ogni membro dello staff accede alla propria area personale e trova tutte le informazioni necessarie per l'evento.</p>
            <div className="grid grid-cols-2 gap-3 mt-8 max-w-lg">
              {[["Quando", "Data e ora di arrivo"], ["Dove", "Luogo e punto di ritrovo"], ["Cosa", "Ruolo e attività"], ["Con chi", "Team e colleghi"], ["Turni", "Programma personale"], ["Mappe", "Percorsi e info operative"]].map(([t, d]) => (
                <div key={t} className="bg-white/5 rounded-lg p-3 ring-1 ring-white/10"><div className="text-tiffany text-sm font-semibold">{t}</div><div className="text-slate-300 text-xs mt-0.5">{d}</div></div>))}
            </div>
            <button onClick={() => scrollTo("registrati")} className="mt-8 inline-flex items-center gap-2 text-tiffany font-semibold hover:gap-3 transition-all">Scopri la gestione Staff & Volontari <ArrowRight className="w-4 h-4" /></button>
          </div>
          <PhoneFrame><VolunteerMock /></PhoneFrame>
        </div>
      </Section>

      {/* Sponsor */}
      <Section id="sponsor" className="py-20">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div><Eyebrow>Sponsor & Partner</Eyebrow><H2>Dai contatti alle partnership.</H2>
            <p className="text-slate-500 mt-5 max-w-lg">Gestisci aziende e referenti, invia proposte commerciali e segui ogni trattativa fino alla partnership firmata: title sponsor, fornitori del ristoro, stand expo e pacco gara in un'unica pipeline.</p>
            <div className="flex flex-wrap gap-2 mt-6">
              {["Prospect", "Proposta inviata", "In trattativa", "Confermato"].map((s, i) => (
                <span key={s} className={`px-3 py-1.5 rounded-full text-xs font-semibold ${i === 3 ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" : "bg-tiffany-light text-tiffany-fg ring-1 ring-tiffany-border"}`}>{s}</span>))}
            </div>
            <div className="grid grid-cols-2 gap-3 mt-6 max-w-md text-sm">
              {[["Valore pipeline", "€ 46.500"], ["Confermato", "€ 25.000"], ["Aziende in pipeline", "6 aziende"], ["Evento", "Maratona di Pisa"]].map(([l, v]) => (
                <div key={l} className="bg-white rounded-lg border border-slate-200 p-3"><div className="text-[11px] text-slate-400 uppercase font-semibold">{l}</div><div className="font-semibold text-slate-800">{v}</div></div>))}
            </div>
          </div>
          <BrowserFrame><PipelineMock /></BrowserFrame>
        </div>
      </Section>

      <PlannerDemoSection />
      <EventMapSection />

      {/* Come funziona */}
      <Section id="come-funziona" className="py-20 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Come funziona</Eyebrow><H2>Parti in pochi minuti.</H2></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-12">
          {[["Registrati a CRMEvent", "Crea il tuo account gratuito in pochi secondi, senza carta di credito."], ["Crea il tuo evento", "Inserisci date, luogo e informazioni principali."], ["Configura le funzionalità", "Attiva solo ciò che ti serve: staff, sponsor, turni, mappe, Event Planner."], ["Organizza e coordina il team", "Assegna ruoli, team e turni: ognuno sa dove essere e quando."]].map(([t, d], i) => (
            <div key={t} className="relative bg-white rounded-xl border border-slate-200 p-6">
              <div className="w-9 h-9 rounded-lg bg-tiffany text-slate-900 font-bold font-display flex items-center justify-center mb-4">{i + 1}</div>
              <h3 className="font-display font-bold text-slate-900">{t}</h3><p className="text-sm text-slate-500 mt-1.5">{d}</p></div>))}
        </div>
      </Section>

      {/* CTA finale + Demo */}
      <Section id="registrati" className="py-16 sm:py-20">
        <div className="rounded-3xl bg-[#0ABAB5] shadow-[0_20px_50px_-20px_rgba(10,186,181,0.55)] overflow-hidden grid lg:grid-cols-2 items-center" data-testid="home-register-cta">
          <div className="p-7 sm:p-12 text-center lg:text-left">
            <h2 className="font-display text-3xl sm:text-4xl font-bold tracking-tight text-slate-900">Organizza il tuo prossimo evento con CRMEvent</h2>
            <p className="mt-4 text-slate-900/80 text-sm sm:text-base max-w-lg mx-auto lg:mx-0">Eventi, staff, volontari, sponsor e tutte le informazioni operative in un'unica piattaforma. Inizia gratuitamente e scopri quanto può essere semplice organizzare.</p>
            <Link to="/registrati" data-testid="home-register-cta-btn" className="mt-7 inline-flex h-12 items-center gap-2 rounded-xl bg-white px-7 font-semibold text-slate-900 shadow-md transition-[transform,box-shadow] hover:shadow-lg hover:-translate-y-0.5 active:scale-[0.98]">Registrati gratis <ArrowRight className="w-4 h-4" /></Link>
            <p className="mt-3 text-xs sm:text-sm text-slate-900/75" data-testid="home-register-cta-note">14 giorni di prova gratuita. Nessuna carta di credito richiesta.</p>
          </div>
          <div className="px-6 pb-6 lg:p-8">
            <img src="/home-cta-eventi.jpg" alt="Team che coordina l'organizzazione di un evento" loading="lazy" className="w-full max-h-56 sm:max-h-72 lg:max-h-none object-cover rounded-2xl shadow-lg" />
          </div>
        </div>
      </Section>
      <span id="demo" />

      {/* Piani e prezzi */}
      <Section id="prezzi" className="py-20 bg-slate-50">
        <PlansSection claim="14 giorni di prova gratuita. Nessuna carta di credito richiesta." />
      </Section>
      {/* Footer */}
      <Footer />
    </div>
  );
}
