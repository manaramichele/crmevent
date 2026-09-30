import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { trackEvent } from "@/lib/analytics";
import Footer from "@/components/Footer";
import { toast } from "sonner";
import {
  CalendarDays, Users, UserCheck, Handshake, ListChecks, UtensilsCrossed, FileText, Mail,
  ArrowRight, Check, Menu, X, Clock, AlertTriangle, Bot, Send, Coins, ShieldCheck, Sparkles, MessageCircle,
} from "lucide-react";

const NAV = [
  ["Funzionalità", "funzionalita"], ["Come funziona", "come-funziona"], ["Crediti", "crediti"], ["Demo", "demo"],
];

const scrollTo = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });

/* ---------- Product UI mockups ---------- */
function AppFrame({ children, title = "CRMEvent App — Dashboard Evento" }) {
  return (
    <div className="rounded-2xl border border-slate-200/90 shadow-2xl shadow-slate-300/40 overflow-hidden bg-white">
      <div className="h-9 bg-slate-50 border-b border-slate-200 flex items-center px-3 gap-1.5">
        <span className="w-3 h-3 rounded-full bg-red-300" /><span className="w-3 h-3 rounded-full bg-amber-300" /><span className="w-3 h-3 rounded-full bg-emerald-300" />
        <div className="ml-3 flex-1 h-5 rounded bg-white border border-slate-200 text-[10px] text-slate-400 flex items-center px-2 truncate">{title}</div>
      </div>
      <div className="bg-slate-50/60">{children}</div>
    </div>
  );
}

function HeroDashboardMock() {
  const kpis = [["Giorni all'evento", "30", "tiffany"], ["Volontari", "142", "slate"], ["Sponsor", "12", "slate"], ["Turni coperti", "88%", "green"]];
  const items = [
    ["3 attività in ritardo", "bg-red-500"],
    ["2 turni scoperti", "bg-orange-500"],
    ["14 volontari da confermare", "bg-yellow-500"],
    ["4 sponsor da ricontattare", "bg-blue-500"],
  ];
  return (
    <div className="p-4 text-left">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[11px] text-slate-400 font-semibold">Buongiorno, Marco</div>
          <div className="font-display font-bold text-slate-900 text-sm">Milano Trail Run 2026</div>
        </div>
        <span className="text-[10px] font-semibold rounded-full bg-tiffany-light text-tiffany-fg px-2.5 py-1 ring-1 ring-tiffany-border">● In preparazione</span>
      </div>
      <div className="grid grid-cols-4 gap-2 mb-3">
        {kpis.map(([l, v, c]) => (
          <div key={l} className="bg-white rounded-lg border border-slate-200 p-2.5">
            <div className="text-[9px] uppercase text-slate-400 font-semibold leading-tight">{l}</div>
            <div className={`text-lg font-bold font-display ${c === "green" ? "text-emerald-600" : c === "tiffany" ? "text-tiffany-fg" : "text-slate-900"}`}>{v}</div>
          </div>
        ))}
      </div>
      <div className="bg-white rounded-lg border border-slate-200 p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-semibold text-slate-700">Da controllare oggi</div>
          <div className="text-[10px] text-tiffany-fg font-semibold">Vedi tutto</div>
        </div>
        <div className="space-y-1.5">
          {items.map(([t, dot]) => (
            <div key={t} className="flex items-center gap-2 py-1 border-b border-slate-50 last:border-0">
              <span className={`w-2 h-2 rounded-full ${dot}`} /><span className="text-[11px] text-slate-600">{t}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const CHECK_ITEMS = [
  { dot: "bg-red-500", pill: "bg-red-50 text-red-700 border-red-200", label: "3 attività in ritardo", detail: "Permesso AIPO · Ordine pettorali · Piano di sicurezza" },
  { dot: "bg-orange-500", pill: "bg-orange-50 text-orange-800 border-orange-200", label: "2 turni scoperti", detail: "Ristoro km 15 · Incrocio SP12" },
  { dot: "bg-yellow-500", pill: "bg-yellow-50 text-yellow-800 border-yellow-200", label: "14 volontari da confermare", detail: "Sollecito inviato via email" },
  { dot: "bg-blue-500", pill: "bg-blue-50 text-blue-700 border-blue-200", label: "4 sponsor da ricontattare", detail: "Invio bozza banner promozionale" },
];

function ChecklistMock() {
  return (
    <div className="p-4 text-left">
      <div className="flex items-center gap-2 mb-3">
        <Clock className="w-4 h-4 text-tiffany-active" />
        <span className="text-xs font-semibold text-slate-700">Mancano 30 giorni — Milano Trail Run 2026</span>
      </div>
      <div className="space-y-2">
        {CHECK_ITEMS.map((it) => (
          <div key={it.label} data-testid="checklist-item" className="bg-white rounded-lg border border-slate-200 p-3 flex items-start gap-3">
            <span className={`w-2.5 h-2.5 rounded-full mt-1 ${it.dot}`} />
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[13px] font-semibold text-slate-800">{it.label}</span>
                <span className={`text-[10px] font-semibold rounded-full border px-2 py-0.5 ${it.pill}`}>da gestire</span>
              </div>
              <div className="text-[11px] text-slate-400 mt-0.5 truncate">{it.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const PRIORITY_METRICS = [
  { label: "Attività da completare", value: "6", alert: false },
  { label: "Attività in ritardo", value: "2", alert: true },
  { label: "Turni senza responsabile", value: "3", alert: true },
  { label: "Volontari senza turno", value: "17", alert: false },
  { label: "Sponsor da ricontattare", value: "4", alert: false },
];

function PriorityMock() {
  return (
    <div className="p-4 text-left">
      <div className="mb-3">
        <div className="font-display font-bold text-slate-900 text-sm">Buongiorno, Marco.</div>
        <div className="text-[11px] text-slate-400">Mancano 18 giorni all'evento.</div>
      </div>
      <div className="space-y-2">
        {PRIORITY_METRICS.map((m) => (
          <div key={m.label} className={`flex items-center justify-between rounded-lg border p-2.5 ${m.alert ? "bg-red-50 border-red-200" : "bg-white border-slate-200"}`}>
            <span className="text-[12px] text-slate-600 flex items-center gap-2">{m.alert && <AlertTriangle className="w-3.5 h-3.5 text-red-500" />}{m.label}</span>
            <span className={`text-sm font-bold font-display ${m.alert ? "text-red-600" : "text-slate-900"}`}>{m.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CommsMock() {
  const boxes = [["Staff", true], ["Volontari", true], ["Sponsor", false], ["Aziende", false]];
  return (
    <div className="p-4 text-left">
      <div className="text-xs font-semibold text-slate-700 mb-2">Nuova comunicazione</div>
      <div className="text-[11px] text-slate-400 mb-1.5">Invia a:</div>
      <div className="grid grid-cols-2 gap-2 mb-3">
        {boxes.map(([l, c]) => (
          <div key={l} data-testid={`comms-checkbox-${l.toLowerCase()}`} className={`flex items-center gap-2 rounded-lg border p-2 text-[12px] ${c ? "bg-tiffany-light border-tiffany-border text-tiffany-fg font-semibold" : "bg-white border-slate-200 text-slate-500"}`}>
            <span className={`w-4 h-4 rounded flex items-center justify-center ${c ? "bg-tiffany text-slate-900" : "border border-slate-300"}`}>{c && <Check className="w-3 h-3" />}</span>{l}
          </div>
        ))}
      </div>
      <div className="rounded-lg bg-slate-900 text-white p-2.5 text-[11px] mb-3 flex items-center gap-2">
        <Users className="w-3.5 h-3.5 text-tiffany" />Team ristoro km 30 — <span className="font-semibold">18 persone</span>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-2.5">
          <span className="text-[12px] font-medium text-slate-700 flex items-center gap-2"><Mail className="w-4 h-4 text-tiffany-active" />Email & Newsletter</span>
          <span className="text-[10px] font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5">Disponibile</span>
        </div>
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-2.5">
          <span className="text-[12px] font-medium text-slate-400 flex items-center gap-2"><MessageCircle className="w-4 h-4" />WhatsApp</span>
          <span className="text-[10px] font-semibold rounded-full bg-slate-200 text-slate-500 px-2 py-0.5">Prossimamente</span>
        </div>
      </div>
    </div>
  );
}

function AICopilotMock() {
  return (
    <div className="p-4 text-left">
      <div className="flex items-center gap-2 mb-3"><div className="w-7 h-7 rounded-lg bg-tiffany flex items-center justify-center"><Bot className="w-4 h-4 text-slate-900" /></div><span className="text-xs font-semibold text-slate-700">Assistente CRMEvent</span></div>
      <div className="bg-slate-900 rounded-xl p-3 text-white text-[12px] mb-2">Genera il briefing per i <span className="text-tiffany font-semibold">Responsabili Ristoro km 21</span></div>
      <div className="bg-white rounded-xl border border-slate-200 p-3 space-y-1.5">
        {["Orario apertura punto ristoro: 08:15", "Materiali: 400 bicchieri, 12 casse acqua", "Referente: Sara Colombo · 3 volontari", "Smontaggio entro le 13:30"].map((t) => (
          <div key={t} className="text-[11px] text-slate-600 flex items-start gap-2"><Check className="w-3.5 h-3.5 text-tiffany-active mt-0.5 shrink-0" />{t}</div>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-end gap-2 text-[10px] text-slate-400"><Coins className="w-3.5 h-3.5 text-tiffany-active" />Usa crediti CRMEvent</div>
    </div>
  );
}

const FEATURES = [
  [CalendarDays, "Eventi", "Date, informazioni, documenti e percorsi di ogni edizione."],
  [Users, "Persone", "Staff, volontari, referenti e collaboratori in un'unica anagrafica."],
  [UserCheck, "Team e turni", "Organizza le squadre e sai sempre chi fa cosa e quando."],
  [Handshake, "Sponsor e partner", "Contatti, trattative, accordi e follow-up commerciali."],
  [ListChecks, "Attività e checklist", "Scadenze, responsabili e stato di avanzamento."],
  [UtensilsCrossed, "Ospitalità e pasti", "Hotel, camere, assegnazioni e gestione pasti."],
  [FileText, "Briefing", "Raccogli e condividi le informazioni operative."],
  [Mail, "Comunicazioni", "Email, newsletter e nuovi strumenti direttamente dall'evento."],
];

const TARGETS = [
  ["Running", "Maratone, mezze, 10k e podistiche"],
  ["Triathlon", "Sprint, olimpico, medio e Ironman"],
  ["Trail", "Ultratrail, vertical e gare in montagna"],
  ["Nuoto", "Acque libere, traversate e gran fondo"],
];

/* ---------- Demo request form (lead) ---------- */
function DemoForm() {
  const [f, setF] = useState({ nome: "", cognome: "", organizzazione: "", email: "", telefono: "", tipologia_eventi: "", eventi_anno: "", messaggio: "", privacy: false });
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
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); } finally { setBusy(false); }
  };
  const inp = "w-full h-11 px-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm";
  return (
    <form onSubmit={submit} className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 shadow-sm grid grid-cols-1 sm:grid-cols-2 gap-4" data-testid="demo-form">
      <input className={inp} placeholder="Nome*" value={f.nome} onChange={ch("nome")} required data-testid="lead-nome" />
      <input className={inp} placeholder="Cognome" value={f.cognome} onChange={ch("cognome")} data-testid="lead-cognome" />
      <input className={`${inp} sm:col-span-2`} placeholder="Organizzazione / Associazione" value={f.organizzazione} onChange={ch("organizzazione")} data-testid="lead-org" />
      <input className={inp} type="email" placeholder="Email*" value={f.email} onChange={ch("email")} required data-testid="lead-email" />
      <input className={inp} placeholder="Telefono" value={f.telefono} onChange={ch("telefono")} data-testid="lead-tel" />
      <select className={inp} value={f.tipologia_eventi} onChange={ch("tipologia_eventi")} data-testid="lead-tipologia">
        <option value="">Tipologia di eventi organizzati</option>
        {["Running / Trail", "Triathlon", "Nuoto", "Ciclismo", "Altri eventi sportivi"].map((o) => <option key={o} value={o}>{o}</option>)}
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

/* ---------- Layout helpers ---------- */
const Section = ({ id, children, className = "" }) => <section id={id} className={`px-6 ${className}`}><div className="max-w-6xl mx-auto">{children}</div></section>;
const Eyebrow = ({ children }) => <div className="text-tiffany-active font-semibold text-sm uppercase tracking-wide mb-3">{children}</div>;
const H2 = ({ children, light = false }) => <h2 className={`font-display text-3xl md:text-4xl font-bold tracking-tight ${light ? "text-white" : "text-slate-900"}`}>{children}</h2>;

export default function LandingPage() {
  const [open, setOpen] = useState(false);
  useEffect(() => { document.title = "CRMEvent | Organizza i tuoi eventi sportivi"; }, []);
  const go = (id) => { scrollTo(id); setOpen(false); };

  return (
    <div className="bg-white text-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/85 backdrop-blur-md border-b border-slate-100">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" data-testid="landing-logo"><img src="/logo-crmevent.png?v=2" alt="CRMEvent" className="h-14 sm:h-16 w-auto" /></Link>
          <nav className="hidden lg:flex items-center gap-7">
            {NAV.map(([l, id]) => <button key={id} onClick={() => scrollTo(id)} data-testid={`nav-link-${id}`} className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors">{l}</button>)}
          </nav>
          <div className="hidden lg:flex items-center gap-3">
            <Link to="/login" data-testid="landing-login" className="text-sm font-semibold text-slate-700 hover:text-slate-900">Accedi</Link>
            <Link to="/registrati" data-testid="landing-start-free" className="h-10 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 text-sm font-semibold shadow-sm transition-all active:scale-[0.98] flex items-center">Inizia gratuitamente</Link>
          </div>
          <button className="lg:hidden" onClick={() => setOpen((o) => !o)} data-testid="landing-menu">{open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}</button>
        </div>
        {open && (
          <div className="lg:hidden border-t border-slate-100 bg-white px-6 py-4 space-y-3">
            {NAV.map(([l, id]) => <button key={id} onClick={() => go(id)} className="block text-sm font-medium text-slate-600">{l}</button>)}
            <div className="flex gap-3 pt-2">
              <Link to="/login" className="flex-1 h-10 rounded-lg border border-slate-200 flex items-center justify-center text-sm font-semibold">Accedi</Link>
              <Link to="/registrati" onClick={() => setOpen(false)} className="flex-1 h-10 rounded-lg bg-tiffany text-slate-900 text-sm font-semibold flex items-center justify-center">Inizia gratuitamente</Link>
            </div>
          </div>
        )}
      </header>

      {/* 1. HERO */}
      <Section className="pt-16 pb-20 lg:pt-24">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div className="animate-fade-up">
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.1]">Tu organizzi l'evento. <span className="text-tiffany-active">CRMEvent ti aiuta a farlo.</span></h1>
            <p className="text-lg text-slate-500 mt-6 max-w-xl">Staff, volontari, sponsor, attività, turni, ospitalità, briefing e comunicazioni. Tutto in un unico posto.</p>
            <div className="flex flex-wrap gap-3 mt-8">
              <Link to="/registrati" data-testid="hero-cta-start-free" className="h-12 px-6 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.98] inline-flex items-center gap-2">Inizia gratuitamente <ArrowRight className="w-4 h-4" /></Link>
              <Link to="/demo" data-testid="hero-cta-demo" className="h-12 px-6 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-800 font-semibold transition-colors inline-flex items-center">Guarda la demo</Link>
            </div>
            <div className="mt-5 flex items-center gap-2 text-sm text-slate-500" data-testid="hero-credits-note">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1.5 font-semibold"><Coins className="w-4 h-4" />100 crediti inclusi</span>
              <span>{" "}alla registrazione · Nessuna carta richiesta</span>
            </div>
          </div>
          <div className="animate-fade-up"><AppFrame><HeroDashboardMock /></AppFrame></div>
        </div>
      </Section>

      {/* 2. IL PROBLEMA */}
      <Section id="problema" className="py-16 md:py-24 bg-slate-50/60 border-y border-slate-100">
        <div className="max-w-3xl">
          <H2>Organizzare un evento significa tenere insieme centinaia di cose.</H2>
          <p className="text-slate-600 mt-6 leading-relaxed">Permessi da richiedere. Sponsor da ricontattare. Volontari da coordinare. Turni da coprire. Fornitori da confermare. Hotel, pasti, materiali, briefing e scadenze.</p>
          <p className="text-slate-500 mt-4">Quando le informazioni sono sparse tra Excel, email, chat e appunti, qualcosa rischia di perdersi.</p>
          <p className="mt-6 inline-block text-xl font-display font-bold text-tiffany-fg bg-tiffany-light rounded-xl px-5 py-3">CRMEvent mette tutto in ordine.</p>
        </div>
      </Section>

      {/* 3. CHECKLIST */}
      <Section className="py-16 md:py-24">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div>
            <Eyebrow>Checklist evento</Eyebrow>
            <H2>Sai sempre cosa devi fare. E cosa manca.</H2>
            <p className="text-slate-500 mt-5 max-w-lg">CRMEvent ti accompagna nella preparazione con una checklist operativa. Organizza le attività, assegna i responsabili, imposta le scadenze e controlla cosa è stato completato.</p>
            <p className="text-slate-500 mt-3 max-w-lg">Le scadenze possono essere collegate alla data dell'evento, così sai sempre quali attività richiedono attenzione.</p>
            <Link to="/registrati" data-testid="checklist-cta" className="mt-7 inline-flex items-center gap-2 h-11 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold transition-all active:scale-[0.98]">Gestisci il tuo prossimo evento <ArrowRight className="w-4 h-4" /></Link>
          </div>
          <AppFrame title="CRMEvent App — Checklist"><ChecklistMock /></AppFrame>
        </div>
      </Section>

      {/* 4. TUTTO IN UN POSTO */}
      <Section id="funzionalita" className="py-16 md:py-24 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Tutto l'evento in un posto</Eyebrow><H2>Una piattaforma. Tutto quello che serve per organizzare.</H2></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-12">
          {FEATURES.map(([Icon, t, d]) => (
            <div key={t} data-testid={`feature-${t}`} className="bg-white rounded-2xl border border-slate-200 p-6 hover:shadow-md hover:-translate-y-0.5 transition-all">
              <div className="w-11 h-11 rounded-lg bg-tiffany-light flex items-center justify-center mb-4"><Icon className="w-5 h-5 text-tiffany-active" /></div>
              <h3 className="font-display font-bold text-slate-900">{t}</h3>
              <p className="text-sm text-slate-500 mt-1.5 leading-relaxed">{d}</p>
            </div>))}
        </div>
      </Section>

      {/* 5. DASHBOARD PRIORITÀ */}
      <Section className="py-16 md:py-24">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <AppFrame title="CRMEvent App — Priorità"><PriorityMock /></AppFrame>
          <div>
            <Eyebrow>Dashboard</Eyebrow>
            <H2>Apri CRMEvent e sai da dove iniziare.</H2>
            <p className="text-slate-500 mt-5 max-w-lg">La dashboard ti aiuta a capire immediatamente cosa richiede attenzione: attività in ritardo, turni senza responsabile, volontari da assegnare e sponsor da ricontattare.</p>
            <Link to="/registrati" data-testid="dashboard-cta" className="mt-7 inline-flex items-center gap-2 h-11 px-5 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold transition-all active:scale-[0.98]">Vedi le priorità <ArrowRight className="w-4 h-4" /></Link>
          </div>
        </div>
      </Section>

      {/* 6. CRMEVENT PUÒ FARE DI PIÙ */}
      <Section id="come-funziona" className="py-16 md:py-24 bg-slate-900 text-white">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div>
            <div className="text-tiffany font-semibold text-sm uppercase tracking-wide mb-3">CRMEvent può fare di più</div>
            <H2 light>Non solo organizza i dati. Può lavorare insieme a te.</H2>
            <ul className="mt-6 space-y-2.5 max-w-lg">
              {["Analizzare cosa manca prima dell'evento", "Individuare le attività più urgenti", "Preparare briefing operativi", "Creare testi e comunicazioni", "Generare contenuti", "Automatizzare attività", "Inviare comunicazioni tramite servizi integrati"].map((t) => (
                <li key={t} className="flex items-start gap-2.5 text-slate-200"><Sparkles className="w-4 h-4 text-tiffany mt-1 shrink-0" />{t}</li>))}
            </ul>
            <p className="mt-6 inline-flex items-center gap-2 text-sm text-slate-900 bg-tiffany rounded-full px-4 py-2 font-semibold"><Coins className="w-4 h-4" />Questi servizi utilizzano i crediti CRMEvent</p>
          </div>
          <div className="animate-fade-up"><AppFrame title="CRMEvent App — Assistente"><AICopilotMock /></AppFrame></div>
        </div>
      </Section>

      {/* 7. COMUNICAZIONI */}
      <Section className="py-16 md:py-24">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <AppFrame title="CRMEvent App — Comunicazioni"><CommsMock /></AppFrame>
          <div>
            <Eyebrow>Comunicazioni</Eyebrow>
            <H2>Comunica con le persone giuste, direttamente dall'evento.</H2>
            <p className="text-slate-500 mt-5 max-w-lg">CRMEvent conosce già staff, volontari, team, sponsor e aziende. Puoi usare le informazioni dell'evento per comunicazioni mirate, scegliendo i destinatari in un click.</p>
            <p className="text-slate-500 mt-3 max-w-lg">Newsletter ed email possono essere gestite direttamente dalla piattaforma.</p>
            <p className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-slate-500"><MessageCircle className="w-4 h-4 text-tiffany-active" />WhatsApp direttamente da CRMEvent — <span className="text-tiffany-fg">prossimamente</span></p>
          </div>
        </div>
      </Section>

      {/* 8. COME FUNZIONANO I CREDITI */}
      <Section id="crediti" className="py-16 md:py-24 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Come funzionano i crediti</Eyebrow><H2>Parti con 100 crediti CRMEvent.</H2>
          <p className="text-slate-500 mt-4">Usi CRMEvent per organizzare e gestire i tuoi eventi senza consumare crediti. I crediti servono quando chiedi alla piattaforma di fare qualcosa per te.</p></div>
        <div className="grid md:grid-cols-2 gap-6 mt-12 max-w-4xl mx-auto">
          <div className="bg-white rounded-2xl border border-slate-200 p-6" data-testid="credits-free-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display font-bold text-slate-900">Gestisci</h3>
              <span className="text-[11px] font-bold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1">Nessun consumo di crediti</span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {["Eventi", "Persone", "Sponsor", "Turni", "Attività", "Checklist", "Ospitalità", "Pasti"].map((t) => (
                <div key={t} className="flex items-center gap-2 text-sm text-slate-600"><Check className="w-4 h-4 text-emerald-500" />{t}</div>))}
            </div>
          </div>
          <div className="bg-slate-900 rounded-2xl p-6 relative overflow-hidden" data-testid="credits-paid-col">
            <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-tiffany/20 blur-2xl" />
            <div className="relative">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display font-bold text-white">CRMEvent lavora per te</h3>
                <span className="text-[11px] font-bold rounded-full bg-tiffany text-slate-900 px-3 py-1">Utilizzo di crediti</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {["Assistente IA", "Analisi evento", "Generazione briefing", "Contenuti", "Automazioni", "Newsletter", "WhatsApp (in arrivo)", "Altri servizi"].map((t) => (
                  <div key={t} className="flex items-center gap-2 text-sm text-slate-200"><Sparkles className="w-4 h-4 text-tiffany shrink-0" />{t}</div>))}
              </div>
            </div>
          </div>
        </div>
        <p className="text-center text-base font-semibold text-tiffany-fg mt-8 max-w-2xl mx-auto flex items-center justify-center gap-2"><Coins className="w-5 h-5" />Se non utilizzi servizi a consumo, i tuoi crediti restano disponibili.</p>
      </Section>

      {/* 9. NESSUN BLOCCO */}
      <Section className="py-16 md:py-20">
        <div className="max-w-3xl mx-auto bg-white rounded-2xl border border-slate-200 p-8 flex items-start gap-4" data-testid="no-lockout">
          <div className="w-12 h-12 rounded-xl bg-tiffany-light flex items-center justify-center shrink-0"><ShieldCheck className="w-6 h-6 text-tiffany-active" /></div>
          <div>
            <h3 className="font-display text-xl font-bold text-slate-900">I tuoi eventi restano sempre accessibili.</h3>
            <p className="text-slate-500 mt-2">Terminare i crediti non significa perdere l'accesso al proprio lavoro: continui a consultare e gestire i dati dell'evento. Per utilizzare di nuovo i servizi avanzati basta ricaricare i crediti dall'Area Account.</p>
          </div>
        </div>
      </Section>

      {/* 10. PER CHI È */}
      <Section id="per-chi" className="py-16 md:py-24 bg-slate-50/60 border-y border-slate-100">
        <div className="text-center max-w-2xl mx-auto"><Eyebrow>Per chi è</Eyebrow><H2>Pensato per chi organizza eventi.</H2></div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-12">
          {TARGETS.map(([t, d]) => (
            <div key={t} className="bg-white rounded-2xl border border-slate-200 p-6 hover:border-tiffany transition-colors text-center">
              <div className="font-display font-bold text-slate-900 text-lg">{t}</div>
              <p className="text-sm text-slate-500 mt-2">{d}</p>
            </div>))}
        </div>
        <p className="text-center text-slate-500 mt-6">…e altri eventi sportivi: ciclismo, OCR, tornei e manifestazioni.</p>
      </Section>

      {/* 11. CTA FINALE */}
      <Section className="py-16 md:py-24">
        <div className="bg-tiffany rounded-3xl shadow-xl p-10 md:p-16 text-center" data-testid="final-cta">
          <h2 className="font-display text-3xl md:text-5xl font-extrabold tracking-tight text-tiffany-fg">Il prossimo evento parte da qui.</h2>
          <p className="text-tiffany-fg/80 mt-5 max-w-2xl mx-auto text-lg">Metti in ordine persone, attività, sponsor e scadenze. Quando vuoi fare di più, CRMEvent è pronto ad aiutarti. 100 crediti inclusi.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/registrati" data-testid="final-cta-start-free" className="h-12 px-8 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-base font-semibold shadow-sm transition-all active:scale-[0.98] inline-flex items-center gap-2">Inizia gratuitamente <ArrowRight className="w-5 h-5" /></Link>
            <Link to="/demo" data-testid="final-cta-demo" className="h-12 px-8 rounded-xl bg-white/70 hover:bg-white text-tiffany-fg text-base font-semibold transition-all inline-flex items-center">Guarda la demo</Link>
          </div>
          <div className="mt-5 text-sm text-tiffany-fg/80 font-medium">Nessuna carta richiesta</div>
        </div>
      </Section>

      {/* DEMO / Contatti */}
      <Section id="demo" className="pb-20">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <Eyebrow>Demo</Eyebrow>
            <H2>Vuoi vedere CRMEvent sul tuo evento?</H2>
            <p className="text-slate-500 mt-5 max-w-lg">Compila il form: ti mostriamo la piattaforma e apriamo subito la demo interattiva.</p>
            <div className="mt-6 space-y-2">
              {["Demo personalizzata sul tuo tipo di evento", "Nessun impegno", "100 crediti inclusi alla registrazione"].map((t) => (
                <div key={t} className="flex items-center gap-2 text-sm text-slate-600"><Check className="w-4 h-4 text-tiffany-active" />{t}</div>))}
            </div>
          </div>
          <DemoForm />
        </div>
      </Section>

      <Footer />
    </div>
  );
}
