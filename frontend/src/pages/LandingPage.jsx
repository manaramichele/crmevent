import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { trackEvent } from "@/lib/analytics";
import Footer from "@/components/Footer";
import { toast } from "sonner";
import {
  CalendarDays, Building2, Users, Handshake, UserCog, Users2, Clock, Map as MapIcon,
  BellRing, CalendarCheck2, ArrowRight, Check, Menu, X, MapPin, Navigation, ChevronRight,
} from "lucide-react";

const NAV = [
  ["Funzionalità", "funzionalita"], ["Per chi è", "per-chi"], ["Staff & Volontari", "staff"],
  ["Sponsor", "sponsor"], ["Come funziona", "come-funziona"], ["Contatti", "demo"],
];

const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

function BrowserFrame({ children, url = "app.crmevent.it" }) {
  return (
    <div className="rounded-xl border border-slate-200 shadow-2xl shadow-slate-300/40 overflow-hidden bg-white">
      <div className="h-9 bg-slate-50 border-b border-slate-200 flex items-center px-3 gap-1.5">
        <span className="w-3 h-3 rounded-full bg-red-300" /><span className="w-3 h-3 rounded-full bg-amber-300" /><span className="w-3 h-3 rounded-full bg-emerald-300" />
        <div className="ml-3 flex-1 h-5 rounded bg-white border border-slate-200 text-[10px] text-slate-400 flex items-center px-2">{url}</div>
      </div>
      <div className="bg-slate-50/60">{children}</div>
    </div>
  );
}

function DashboardMock() {
  const kpis = [["Eventi attivi", "2", "tiffany"], ["Valore pipeline", "€ 282k", "tiffany"], ["Confermato", "€ 140k", "green"], ["Volontari", "3", "tiffany"]];
  const bars = [["Prospect", 30], ["Contattato", 45], ["Proposta", 65], ["Trattativa", 50], ["Confermato", 90]];
  return (
    <div className="p-4 grid grid-cols-12 gap-3 text-left">
      <div className="col-span-12 grid grid-cols-4 gap-2">
        {kpis.map(([l, v, c]) => (
          <div key={l} className="bg-white rounded-lg border border-slate-200 p-2.5">
            <div className="text-[9px] uppercase text-slate-400 font-semibold">{l}</div>
            <div className={`text-lg font-bold font-display ${c === "green" ? "text-emerald-600" : "text-slate-900"}`}>{v}</div>
          </div>
        ))}
      </div>
      <div className="col-span-8 bg-white rounded-lg border border-slate-200 p-3">
        <div className="text-xs font-semibold text-slate-700 mb-3">Pipeline commerciale</div>
        <div className="flex items-end gap-2 h-24">
          {bars.map(([l, h]) => (<div key={l} className="flex-1 flex flex-col items-center gap-1">
            <div className="w-full rounded-t bg-tiffany" style={{ height: `${h}%` }} /><span className="text-[8px] text-slate-400">{l}</span></div>))}
        </div>
      </div>
      <div className="col-span-4 bg-white rounded-lg border border-slate-200 p-3">
        <div className="text-xs font-semibold text-slate-700 mb-2">Follow-up di oggi</div>
        {["AutoDrive Motors", "CloudByte", "FinCore"].map((n) => (
          <div key={n} className="flex items-center gap-2 py-1.5 border-b border-slate-50 last:border-0">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400" /><span className="text-[10px] text-slate-600">{n}</span></div>))}
      </div>
    </div>
  );
}

function PipelineMock() {
  const cols = [["Prospect", ["TechNova", "CloudByte"], "border-t-slate-300"], ["Proposta inviata", ["Moda Italia"], "border-t-amber-400"],
    ["In trattativa", ["BioGusto"], "border-t-tiffany"], ["Confermato", ["FinCore · €80k"], "border-t-emerald-400"]];
  return (
    <div className="p-4 grid grid-cols-4 gap-2 text-left">
      {cols.map(([t, cards, b]) => (
        <div key={t} className={`bg-slate-50 rounded-lg border border-slate-200 border-t-4 ${b}`}>
          <div className="px-2 py-2 text-[10px] font-semibold text-slate-600">{t}</div>
          <div className="p-1.5 space-y-1.5">
            {cards.map((c) => (<div key={c} className="bg-white rounded border border-slate-200 p-2 text-[10px] font-medium text-slate-700">{c}</div>))}
          </div>
        </div>))}
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
  const rows = [[Clock, "Arrivo", "15 Set · 08:30"], [MapPin, "Luogo", "Hall 3"], [UserCog, "Ruolo", "Accoglienza"], [Users2, "Team", "Team Ristoro"], [Navigation, "Ritrovo", "Ingresso Est"]];
  return (
    <div className="text-left">
      <div className="bg-slate-900 p-4 text-white">
        <div className="text-[10px] text-tiffany font-semibold uppercase">Prossimo evento</div>
        <div className="font-display font-bold">Green Food Festival</div>
        <div className="text-[10px] text-slate-300 mt-1 flex items-center gap-1"><CalendarDays className="w-3 h-3" />04–06 Lug 2026</div>
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
  [Building2, "Contatti", "Aziende, referenti e persone in un'unica anagrafica senza duplicazioni."],
  [Handshake, "Sponsor & Partner", "Prospect, trattative, follow-up e partnership in una pipeline commerciale."],
  [UserCog, "Staff & Volontari", "Assegna persone, ruoli, aree operative e responsabilità."],
  [Users2, "Team", "Crea squadre operative e mostra subito chi lavora con chi."],
  [Clock, "Turni", "Organizza giorni, orari, punti di ritrovo e attività."],
  [MapIcon, "Mappe & Percorsi", "Condividi percorsi, mappe operative e punti di riferimento."],
  [BellRing, "Follow-up", "Non dimenticare telefonate, attività e contatti importanti."],
  [CalendarCheck2, "Google Calendar", "Porta eventi e turni nel calendario degli utenti."],
];

const TARGETS = ["Running", "Triathlon", "Ciclismo", "Trail", "Eventi sportivi", "Festival", "Fiere", "Congressi", "Manifestazioni", "Eventi aziendali", "Associazioni", "Agenzie eventi"];

function DemoForm() {
  const [f, setF] = useState({ nome: "", cognome: "", organizzazione: "", email: "", telefono: "", tipologia_eventi: "", eventi_anno: "", messaggio: "", privacy: false });
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const ch = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    if (!f.privacy) return toast.error("Accetta la privacy policy per continuare");
    setBusy(true);
    try {
      const { data } = await api.post("/leads", { ...f, source: "richiedi_demo_form" });
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
      <textarea className="sm:col-span-2 min-h-[90px] p-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm" placeholder="Messaggio" value={f.messaggio} onChange={ch("messaggio")} data-testid="lead-msg" />
      <label className="sm:col-span-2 flex items-start gap-2 text-xs text-slate-500">
        <input type="checkbox" checked={f.privacy} onChange={ch("privacy")} className="mt-0.5 accent-tiffany" data-testid="lead-privacy" />
        Ho letto e accetto la <Link to="/privacy" className="text-tiffany-active underline">Privacy Policy</Link> e acconsento al trattamento dei dati per essere ricontattato.
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
  const [prices, setPrices] = useState({ starter: 49, professional: 99, premium: 199 });
  useEffect(() => { document.title = "CRMEvent | Il CRM per organizzare eventi"; }, []);
  useEffect(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/pricing`)
      .then((r) => r.json())
      .then((d) => {
        if (!d || !Array.isArray(d.plans)) return;
        const next = {};
        d.plans.forEach((p) => { if (p.fascia === "small") next[p.plan] = p.net; });
        if (next.starter && next.professional && next.premium) setPrices(next);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="bg-white text-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" data-testid="landing-logo"><img src="/logo-crmevent.png?v=2" alt="CRMEvent" className="h-14 sm:h-16 w-auto" /></Link>
          <nav className="hidden lg:flex items-center gap-7">
            {NAV.map(([l, id]) => <button key={id} onClick={() => scrollTo(id)} className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors">{l}</button>)}
            <Link to="/prezzi" data-testid="landing-pricing" className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors">Prezzi</Link>
          </nav>
          <div className="hidden lg:flex items-center gap-3">
            <Link to="/login" data-testid="landing-login" className="text-sm font-semibold text-slate-700 hover:text-slate-900">Accedi</Link>
            <Link to="/registrati" data-testid="landing-try-cta" className="h-10 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm transition-all active:scale-[0.98] flex items-center">Prova gratis</Link>
          </div>
          <button className="lg:hidden" onClick={() => setOpen((o) => !o)} data-testid="landing-menu">{open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}</button>
        </div>
        {open && (
          <div className="lg:hidden border-t border-slate-100 bg-white px-6 py-4 space-y-3">
            {NAV.map(([l, id]) => <button key={id} onClick={() => { scrollTo(id); setOpen(false); }} className="block text-sm font-medium text-slate-600">{l}</button>)}
            <Link to="/prezzi" onClick={() => setOpen(false)} className="block text-sm font-medium text-slate-600">Prezzi</Link>
            <div className="flex gap-3 pt-2"><Link to="/login" className="flex-1 h-10 rounded-lg border border-slate-200 flex items-center justify-center text-sm font-semibold">Accedi</Link>
              <Link to="/registrati" onClick={() => setOpen(false)} className="flex-1 h-10 rounded-lg bg-tiffany text-slate-900 text-sm font-semibold flex items-center justify-center">Prova gratis</Link></div>
          </div>
        )}
      </header>

      {/* Hero */}
      <Section className="pt-16 pb-20 lg:pt-24">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div className="animate-fade-up">
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.05]">Organizza il tuo evento. <span className="text-tiffany-active">Tutto in un'unica piattaforma.</span></h1>
            <p className="text-lg text-slate-500 mt-6 max-w-xl"><strong className="font-semibold text-slate-700">CRMEvent</strong> riunisce contatti, sponsor, staff, volontari, turni e attività in un'unica piattaforma semplice da usare.</p>
            <div className="flex flex-wrap gap-3 mt-8">
              <button onClick={() => { trackEvent("demo_request_click"); scrollTo("demo"); }} className="h-12 px-6 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.98] inline-flex items-center gap-2">Richiedi una demo <ArrowRight className="w-4 h-4" /></button>
              <button onClick={() => scrollTo("come-funziona")} className="h-12 px-6 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-800 font-semibold transition-colors">Scopri come funziona</button>
            </div>
          </div>
          <div className="animate-fade-up"><BrowserFrame><DashboardMock /></BrowserFrame></div>
        </div>
      </Section>

      {/* Problema */}
      <Section className="py-16 bg-slate-50/60 border-y border-slate-100" id="problema">
        <div className="max-w-3xl">
          <H2>Organizzare un evento significa gestire centinaia di informazioni.</H2>
          <ul className="mt-6 space-y-2 text-slate-600">
            {["Contatti sparsi tra Excel, email e WhatsApp.", "Sponsor da ricontattare.", "Volontari da coordinare.", "Turni da assegnare.", "Mappe e informazioni da distribuire.", "Persone che chiedono continuamente dove devono essere e a che ora."].map((t) => (
              <li key={t} className="flex items-start gap-2"><span className="w-1.5 h-1.5 rounded-full bg-slate-300 mt-2.5" />{t}</li>))}
          </ul>
          <p className="mt-6 text-xl font-display font-bold text-slate-900">CRMEvent mette tutto insieme.</p>
        </div>
      </Section>

      {/* Funzionalità */}
      <Section id="funzionalita" className="py-20">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Funzionalità</Eyebrow><H2>Un'unica piattaforma per tutto il tuo evento</H2></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-12">
          {FEATURES.map(([Icon, t, d]) => (
            <div key={t} className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg hover:-translate-y-0.5 transition-all">
              <div className="w-11 h-11 rounded-lg bg-tiffany-light flex items-center justify-center mb-4"><Icon className="w-5 h-5 text-tiffany-active" /></div>
              <h3 className="font-display font-bold text-slate-900">{t}</h3>
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
            <button onClick={() => scrollTo("demo")} className="mt-8 inline-flex items-center gap-2 text-tiffany font-semibold hover:gap-3 transition-all">Scopri la gestione Staff & Volontari <ArrowRight className="w-4 h-4" /></button>
          </div>
          <PhoneFrame><VolunteerMock /></PhoneFrame>
        </div>
      </Section>

      {/* Sponsor */}
      <Section id="sponsor" className="py-20">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div><Eyebrow>Sponsor & Partner</Eyebrow><H2>Dai contatti alle partnership.</H2>
            <p className="text-slate-500 mt-5 max-w-lg">Gestisci sponsor, partner e prospect senza perdere opportunità tra fogli Excel, email e appunti.</p>
            <div className="flex flex-wrap gap-2 mt-6">
              {["Prospect", "Contattato", "Interessato", "Proposta inviata", "Negoziazione", "Confermato"].map((s, i) => (
                <span key={s} className={`px-3 py-1.5 rounded-full text-xs font-semibold ${i === 5 ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" : "bg-tiffany-light text-tiffany-fg ring-1 ring-tiffany-border"}`}>{s}</span>))}
            </div>
            <div className="grid grid-cols-2 gap-3 mt-6 max-w-md text-sm">
              {[["Valore pipeline", "€ 282.000"], ["Prossimo follow-up", "Oggi"], ["Referente", "Sara Colombo"], ["Storico attività", "12 interazioni"]].map(([l, v]) => (
                <div key={l} className="bg-white rounded-lg border border-slate-200 p-3"><div className="text-[11px] text-slate-400 uppercase font-semibold">{l}</div><div className="font-semibold text-slate-800">{v}</div></div>))}
            </div>
          </div>
          <BrowserFrame><PipelineMock /></BrowserFrame>
        </div>
      </Section>

      {/* Multi-evento */}
      <Section className="py-20 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Multi-evento</Eyebrow><H2>Un contatto. Tutti i tuoi eventi.</H2>
          <p className="text-slate-500 mt-4">Una persona o un'azienda viene registrata una sola volta e associata a eventi differenti, mantenendo ruolo, stato, storico, attività e partnership.</p></div>
        <div className="grid md:grid-cols-2 gap-6 mt-10 max-w-3xl mx-auto">
          {[["AZIENDA X", Building2, [["Evento 2026", "Sponsor", "green"], ["Evento 2027", "Prospect", "orange"], ["Evento 2028", "Partner", "tiffany"]]],
            ["PERSONA Y", Users, [["Evento 2026", "Volontario", "tiffany"], ["Evento 2027", "Coordinatore", "tiffany"], ["Evento 2028", "Team Leader", "green"]]]].map(([name, Icon, rows]) => (
            <div key={name} className="bg-white rounded-xl border border-slate-200 p-5">
              <div className="flex items-center gap-2 mb-4"><div className="w-9 h-9 rounded-lg bg-tiffany-light flex items-center justify-center"><Icon className="w-5 h-5 text-tiffany-active" /></div><span className="font-display font-bold text-slate-900">{name}</span></div>
              {rows.map(([ev, role, c]) => (<div key={ev} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                <span className="text-sm text-slate-500 flex items-center gap-1.5"><ChevronRight className="w-3.5 h-3.5 text-slate-300" />{ev}</span>
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${c === "green" ? "bg-emerald-50 text-emerald-700" : c === "orange" ? "bg-amber-50 text-amber-700" : "bg-tiffany-light text-tiffany-fg"}`}>{role}</span></div>))}
            </div>))}
        </div>
      </Section>

      {/* Come funziona */}
      <Section id="come-funziona" className="py-20">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Come funziona</Eyebrow><H2>Parti in pochi minuti.</H2></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-12">
          {[["Crea il tuo evento", "Inserisci date e informazioni principali."], ["Aggiungi le persone", "Staff, volontari, aziende, sponsor e partner."], ["Organizza", "Assegna ruoli, team, turni, attività e follow-up."], ["Condividi", "Ogni persona trova le informazioni che le servono."]].map(([t, d], i) => (
            <div key={t} className="relative bg-white rounded-xl border border-slate-200 p-6">
              <div className="w-9 h-9 rounded-lg bg-tiffany text-slate-900 font-bold font-display flex items-center justify-center mb-4">{i + 1}</div>
              <h3 className="font-display font-bold text-slate-900">{t}</h3><p className="text-sm text-slate-500 mt-1.5">{d}</p></div>))}
        </div>
      </Section>

      {/* Target */}
      <Section id="per-chi" className="py-20 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Per chi è</Eyebrow><H2>Pensato per chi organizza eventi.</H2>
          <p className="text-slate-500 mt-4">Dallo sport ai festival, dalle fiere agli eventi aziendali: <strong className="font-semibold text-slate-700">CRMEvent</strong> si adatta a ogni tipologia di evento.</p></div>
        <div className="flex flex-wrap justify-center gap-3 mt-10">
          {TARGETS.map((t) => <span key={t} className="px-4 py-2 rounded-full bg-white border border-slate-200 text-sm font-medium text-slate-700 hover:border-tiffany hover:text-tiffany-fg transition-colors">{t}</span>)}
        </div>
      </Section>

      {/* Differenziazione */}
      <Section className="py-20">
        <div className="text-center max-w-2xl mx-auto"><H2>Meno fogli Excel. Meno messaggi. Più controllo.</H2></div>
        <div className="grid md:grid-cols-2 gap-6 mt-10 max-w-4xl mx-auto">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <div className="text-sm font-semibold text-slate-400 uppercase mb-4">Prima</div>
            <div className="flex flex-wrap gap-2">{["Excel", "WhatsApp", "Email", "Google Drive", "Calendari", "Liste volontari", "File sponsor", "Mappe separate"].map((t) => <span key={t} className="px-3 py-1.5 rounded-lg bg-slate-100 text-slate-500 text-sm">{t}</span>)}</div>
          </div>
          <div className="bg-slate-900 rounded-xl p-6 relative overflow-hidden">
            <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-tiffany/20 blur-2xl" />
            <div className="relative"><div className="text-sm font-semibold text-tiffany uppercase mb-4">Con CRMEvent</div>
              <div className="text-2xl font-display font-bold text-white">Un unico spazio di lavoro.</div>
              <p className="text-slate-300 text-sm mt-3"><strong className="font-semibold text-white">CRMEvent</strong> centralizza le informazioni operative del tuo evento: persone, sponsor, staff e attività sempre allineati.</p></div>
          </div>
        </div>
      </Section>

      {/* Screenshots */}
      <Section className="py-20 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Il prodotto</Eyebrow><H2>Guarda CRMEvent in azione</H2></div>
        <div className="grid lg:grid-cols-2 gap-6 mt-12 items-start">
          <BrowserFrame url="app.crmevent.it/app"><DashboardMock /></BrowserFrame>
          <BrowserFrame url="app.crmevent.it/sponsor"><PipelineMock /></BrowserFrame>
          <div className="lg:col-span-2 flex justify-center pt-4"><PhoneFrame><VolunteerMock /></PhoneFrame></div>
        </div>
      </Section>

      {/* CTA finale + Demo */}
      <Section id="demo" className="py-20">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <H2>Il tuo prossimo evento può essere più semplice da gestire.</H2>
            <p className="text-slate-500 mt-5 max-w-lg">Scopri come <strong className="font-semibold text-slate-700">CRMEvent</strong> può aiutarti a organizzare persone, sponsor e attività da un unico posto. Compila il form e ti mostreremo la piattaforma.</p>
            <div className="mt-6 space-y-2">
              {["Demo personalizzata sul tuo tipo di evento", "Nessun impegno", "Ti ricontattiamo entro pochi giorni"].map((t) => (
                <div key={t} className="flex items-center gap-2 text-sm text-slate-600"><Check className="w-4 h-4 text-tiffany-active" />{t}</div>))}
            </div>
          </div>
          <DemoForm />
        </div>
      </Section>

      {/* Prezzi teaser */}
      <Section id="prezzi-teaser" className="py-20 bg-slate-900 text-white">
        <div className="max-w-3xl mx-auto text-center">
          <div className="text-tiffany font-semibold text-sm uppercase tracking-wide mb-3">Prezzi trasparenti</div>
          <h2 className="font-display text-3xl md:text-4xl font-bold tracking-tight">Prova tutto. Poi scegli cosa ti serve.</h2>
          <p className="text-slate-300 mt-4">14 giorni di CRMEvent Premium gratis. Nessuna carta richiesta.</p>
        </div>
        <div className="grid sm:grid-cols-3 gap-5 mt-12 max-w-4xl mx-auto">
          {[
            { id: "starter", name: "Starter", desc: "Gestisci staff, volontari, team e turni.", featured: false },
            { id: "professional", name: "Professional", desc: "Organizza in modo completo il tuo evento.", featured: true },
            { id: "premium", name: "Premium", desc: "Organizza e promuovi con tutti gli strumenti.", featured: false },
          ].map((p) => (
            <div key={p.id} data-testid={`home-plan-${p.id}`} className={`relative rounded-2xl p-6 flex flex-col ${p.featured ? "bg-white text-slate-900 shadow-xl ring-2 ring-tiffany sm:-translate-y-2" : "bg-white/5 border border-white/10 backdrop-blur"}`}>
              {p.featured && <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-tiffany text-slate-900 px-3 py-1 text-xs font-bold shadow">Più scelto</span>}
              <div className={`text-xs font-bold uppercase tracking-wide ${p.featured ? "text-tiffany-fg" : "text-tiffany"}`}>{p.name}</div>
              <div className="mt-3 flex items-baseline gap-1">
                <span className="font-display text-4xl font-bold">{prices[p.id]} €</span>
                <span className={`text-sm mb-0.5 ${p.featured ? "text-slate-500" : "text-slate-300"}`}>+ IVA</span>
              </div>
              <div className="text-xs text-slate-400">/ evento</div>
              <p className={`text-sm mt-3 leading-relaxed ${p.featured ? "text-slate-600" : "text-slate-300"}`}>{p.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-slate-400 mt-6 max-w-xl mx-auto">Prezzi per evento. Nessun abbonamento mensile. Aggiornamenti inclusi. Il prezzo varia in base al numero di eventi che organizzi.</p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link to="/registrati" data-testid="home-pricing-try" className="h-12 px-7 rounded-xl bg-tiffany hover:bg-tiffany-hover text-slate-900 text-base font-semibold shadow-sm transition-all active:scale-[0.98] inline-flex items-center gap-2">Prova gratis 14 giorni</Link>
          <Link to="/prezzi" data-testid="home-pricing-cta" className="h-12 px-7 rounded-xl border border-white/25 hover:bg-white/10 text-white text-base font-semibold transition-all inline-flex items-center gap-2">Confronta i piani<ArrowRight className="w-5 h-5" /></Link>
        </div>
        <div className="mt-6 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-slate-200">
          <div className="flex items-center gap-2"><Check className="w-4 h-4 text-tiffany" />14 giorni di prova gratuita</div>
          <div className="flex items-center gap-2"><Check className="w-4 h-4 text-tiffany" />Nessuna carta richiesta</div>
          <div className="flex items-center gap-2"><Check className="w-4 h-4 text-tiffany" />Aggiornamenti inclusi in tutti i piani</div>
        </div>
      </Section>

      {/* Footer */}
      <Footer />
    </div>
  );
}
