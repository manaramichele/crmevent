import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { LogOut, Clock, Ban, MousePointerClick, Eye, UserPlus, FlaskConical, BadgeCheck, Percent, Wallet } from "lucide-react";
import api, { eur } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Logo } from "@/components/ui";
import Simulator from "@/components/Simulator";
import Links from "@/components/dash/Links";
import Commissions from "@/components/dash/Commissions";
import { Materials, Profile } from "@/components/dash/More";

const TABS = [["panoramica", "Panoramica"], ["link", "Link e campagne"], ["commissioni", "Commissioni"], ["simulatore", "Simulatore"], ["materiali", "Materiali"], ["profilo", "Profilo"]];

function Stat({ icon: Icon, label, value, testid }) {
  return <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid={testid}><Icon className="w-5 h-5 text-tiffany" /><div className="mt-3 font-display text-2xl font-extrabold tabular-nums">{value}</div><div className="text-xs text-slate-500">{label}</div></div>;
}

function Overview({ d }) {
  const s = d.stats;
  const ST = { abbonato: "bg-emerald-50 text-emerald-700", prova: "bg-sky-50 text-sky-700", non_attivo: "bg-slate-100 text-slate-500" };
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat icon={MousePointerClick} label="Click" value={s.clicks} testid="stat-clicks" /><Stat icon={Eye} label="Visitatori unici" value={s.visitors} testid="stat-visitors" />
        <Stat icon={UserPlus} label="Registrazioni" value={s.registrations} testid="stat-registrations" /><Stat icon={FlaskConical} label="In prova gratuita" value={s.trial} testid="stat-trial" />
        <Stat icon={BadgeCheck} label="Abbonamenti attivati" value={s.converted} testid="stat-converted" /><Stat icon={Percent} label="Tasso di conversione" value={`${s.conversion_rate}%`} testid="stat-conversion" />
        <Stat icon={Wallet} label="Commissioni maturate" value={eur(s.maturate_cents)} testid="stat-maturate" /><Stat icon={Wallet} label="Liquidabili · pagate" value={`${eur(s.liquidabili_cents)} · ${eur(s.pagate_cents)}`} testid="stat-liquidabili" />
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white overflow-hidden" data-testid="referrals-list">
        <h3 className="font-bold p-5 border-b border-slate-100">Organizzazioni acquisite</h3>
        {!d.referrals.length ? <p className="p-5 text-sm text-slate-500" data-testid="referrals-empty">Nessuna organizzazione ancora. Condividi il tuo link per iniziare.</p> : d.referrals.map((r) => (
          <div key={r.id} className="px-5 py-3 border-b border-slate-100 last:border-0 flex items-center justify-between gap-3 text-sm">
            <div className="min-w-0"><div className="font-medium truncate">{r.org_name}</div><div className="text-xs text-slate-500">Registrata il {new Date(r.created_at).toLocaleDateString("it-IT")}{r.campaign ? ` · ${r.campaign}` : ""}{r.commission_until ? ` · commissioni fino al ${new Date(r.commission_until).toLocaleDateString("it-IT")}` : ""}</div></div>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${ST[r.stato]}`}>{r.stato === "abbonato" ? (r.plan || "").toUpperCase() : r.stato === "prova" ? "In prova" : "Non attivo"}</span>
          </div>))}
      </div>
    </div>
  );
}

function Pending({ status }) {
  const rej = status === "rejected" || status === "suspended";
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 max-w-2xl" data-testid="partner-pending">
      {rej ? <Ban className="w-8 h-8 text-red-500" /> : <Clock className="w-8 h-8 text-tiffany" />}
      <h2 className="mt-4 text-2xl font-extrabold">{rej ? "Account partner non attivo" : "Candidatura in verifica"}</h2>
      <p className="mt-2 text-slate-600">{rej ? "Il tuo account partner non è attivo. Per informazioni scrivi a support@crmevent.it." : "Il team CRMEvent sta verificando la tua candidatura: riceverai un'email all'approvazione. Poi troverai qui il link referral e le commissioni."}</p>
    </div>
  );
}

export default function Dashboard() {
  const { partner, logout } = useAuth();
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);
  const [tab, setTab] = useState("panoramica");
  const approved = partner.status === "approved";
  const load = () => { setErr(false); api.get("/partner/dashboard").then(({ data }) => setD(data)).catch(() => setErr(true)); };
  useEffect(() => { if (approved) load(); }, [approved, partner]); // eslint-disable-line react-hooks/exhaustive-deps
  const body = { panoramica: d && <Overview d={d} />, link: d && <Links d={d} reload={load} />, commissioni: d && <Commissions d={d} />, simulatore: <div className="max-w-2xl"><Simulator /></div>, materiali: <Materials />, profilo: <Profile /> };
  return (
    <div className="min-h-screen bg-slate-50" data-testid="dashboard-page">
      <header className="sticky top-0 z-30 bg-white/85 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <Link to="/"><Logo className="text-base sm:text-lg" /></Link>
          <div className="flex items-center gap-2 min-w-0">
            <span className="hidden sm:block text-sm text-slate-600 truncate max-w-[200px]" data-testid="partner-name">{partner.nome} {partner.cognome}</span>
            <button onClick={logout} className="h-10 w-10 sm:w-auto sm:px-3 inline-flex items-center justify-center gap-1.5 rounded-full hover:bg-slate-100 text-sm text-slate-600" data-testid="logout-button" aria-label="Esci"><LogOut className="w-4 h-4" /><span className="hidden sm:inline">Esci</span></button>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-10 space-y-6 fade-up">
        <div><h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">Ciao {partner.nome || ""}</h1><p className="mt-1 text-slate-500">La tua area CRMEvent Partner.</p></div>
        {!approved ? <Pending status={partner.status} /> : (<>
          <div role="tablist" className="flex gap-1 overflow-x-auto -mx-1 px-1 pb-1" data-testid="dashboard-tabs">
            {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`tab-${k}`} className={`shrink-0 h-10 px-4 rounded-full text-sm font-semibold transition-colors ${tab === k ? "bg-ink text-white" : "text-slate-600 hover:bg-white"}`}>{l}</button>)}
          </div>
          {err ? <p className="text-sm text-red-600" data-testid="dashboard-error">Impossibile caricare i dati. <button onClick={load} className="underline font-semibold" data-testid="dashboard-retry">Riprova</button></p>
            : !d && !["simulatore", "materiali", "profilo"].includes(tab) ? <p className="text-slate-400" data-testid="dashboard-loading">Caricamento...</p> : body[tab]}
        </>)}
      </main>
    </div>
  );
}
