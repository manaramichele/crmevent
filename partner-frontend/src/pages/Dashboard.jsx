import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Copy, LogOut, Clock, Users, Wallet, CheckCircle2, Ban } from "lucide-react";
import api, { eur } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button, Logo } from "@/components/ui";
import Simulator from "@/components/Simulator";

const CST = { maturata: "bg-tiffany-light text-tiffany-fg", pagata: "bg-emerald-50 text-emerald-700", stornata: "bg-slate-100 text-slate-500" };

function Stat({ icon: Icon, label, value, testid }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid={testid}>
      <Icon className="w-5 h-5 text-tiffany" />
      <div className="mt-3 font-display text-2xl font-extrabold tabular-nums">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

function ReferralLink({ link }) {
  const copy = async () => { try { await navigator.clipboard.writeText(link); toast.success("Link copiato"); } catch { toast.error("Copia non riuscita"); } };
  return (
    <div className="rounded-3xl bg-ink text-white p-5 sm:p-6" data-testid="referral-card">
      <div className="text-sm text-slate-300">Il tuo link referral</div>
      <div className="mt-3 flex flex-col sm:flex-row gap-2">
        <code className="flex-1 min-w-0 truncate rounded-xl bg-white/10 px-4 h-11 flex items-center text-sm" data-testid="referral-link">{link}</code>
        <Button onClick={copy} data-testid="referral-copy"><Copy className="w-4 h-4" />Copia</Button>
      </div>
      <p className="mt-3 text-xs text-slate-400">Chi si registra su CRMEvent da questo link viene associato a te. Le commissioni maturano sugli abbonamenti pagati.</p>
    </div>
  );
}

function Pending({ status }) {
  const rej = status === "rejected" || status === "suspended";
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 max-w-2xl" data-testid="partner-pending">
      {rej ? <Ban className="w-8 h-8 text-red-500" /> : <Clock className="w-8 h-8 text-tiffany" />}
      <h2 className="mt-4 text-2xl font-extrabold">{rej ? "Account partner non attivo" : "Candidatura in verifica"}</h2>
      <p className="mt-2 text-slate-600">{rej ? "Il tuo account partner non è attivo. Per informazioni scrivi a support@crmevent.it." : "Il team CRMEvent sta verificando la tua candidatura. Dopo l'approvazione troverai qui il tuo link referral e le commissioni."}</p>
    </div>
  );
}

export default function Dashboard() {
  const { partner, logout } = useAuth();
  const [d, setD] = useState(null);
  const [err, setErr] = useState(false);
  const approved = partner.status === "approved";
  const load = () => { setErr(false); api.get("/partner/dashboard").then(({ data }) => setD(data)).catch(() => setErr(true)); };
  useEffect(() => { if (approved) load(); }, [approved]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="min-h-screen bg-slate-50" data-testid="dashboard-page">
      <header className="sticky top-0 z-30 bg-white/85 backdrop-blur-md border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-3">
          <Link to="/"><Logo className="text-lg" /></Link>
          <div className="flex items-center gap-2 min-w-0">
            <span className="hidden sm:block text-sm text-slate-600 truncate max-w-[200px]" data-testid="partner-name">{partner.nome} {partner.cognome}</span>
            <button onClick={logout} className="h-10 w-10 sm:w-auto sm:px-3 inline-flex items-center justify-center gap-1.5 rounded-full hover:bg-slate-100 text-sm text-slate-600" data-testid="logout-button" aria-label="Esci"><LogOut className="w-4 h-4" /><span className="hidden sm:inline">Esci</span></button>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-10 space-y-8 fade-up">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">Ciao {partner.nome || ""}</h1>
          <p className="mt-1 text-slate-500">La tua area partner CRMEvent.</p>
        </div>
        {!approved ? <Pending status={partner.status} /> : err ? (
          <p className="text-sm text-red-600" data-testid="dashboard-error">Impossibile caricare i dati. <button onClick={load} className="underline font-semibold" data-testid="dashboard-retry">Riprova</button></p>
        ) : !d ? <p className="text-slate-400" data-testid="dashboard-loading">Caricamento...</p> : (
          <>
            <ReferralLink link={d.partner.referral_link} />
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <Stat icon={Users} label="Clienti portati" value={d.totals.referrals} testid="stat-referrals" />
              <Stat icon={CheckCircle2} label="Clienti paganti" value={d.totals.paganti} testid="stat-paying" />
              <Stat icon={Wallet} label="Commissioni maturate" value={eur(d.totals.maturate_cents)} testid="stat-maturate" />
              <Stat icon={Wallet} label="Commissioni pagate" value={eur(d.totals.pagate_cents)} testid="stat-pagate" />
            </div>
            <section className="grid lg:grid-cols-2 gap-5">
              <div className="rounded-3xl border border-slate-200 bg-white overflow-hidden" data-testid="referrals-list">
                <h2 className="text-base md:text-lg font-bold p-5 border-b border-slate-100">Clienti</h2>
                {!d.referrals.length ? <p className="p-5 text-sm text-slate-500" data-testid="referrals-empty">Nessun cliente ancora. Condividi il tuo link per iniziare.</p> : d.referrals.map((r) => (
                  <div key={r.org_id} className="px-5 py-3 border-b border-slate-100 last:border-0 flex items-center justify-between gap-3 text-sm">
                    <div className="min-w-0"><div className="font-medium truncate">{r.org_name}</div><div className="text-xs text-slate-500">Registrato il {new Date(r.created_at).toLocaleDateString("it-IT")}{r.commission_until ? ` · commissioni fino al ${new Date(r.commission_until).toLocaleDateString("it-IT")}` : ""}</div></div>
                    <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${r.paying ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{r.paying ? (r.plan || "").toUpperCase() : "Non pagante"}</span>
                  </div>
                ))}
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white overflow-hidden" data-testid="commissions-list">
                <h2 className="text-base md:text-lg font-bold p-5 border-b border-slate-100">Commissioni</h2>
                {!d.commissions.length ? <p className="p-5 text-sm text-slate-500" data-testid="commissions-empty">Nessuna commissione maturata.</p> : d.commissions.map((c) => (
                  <div key={c.id} className="px-5 py-3 border-b border-slate-100 last:border-0 flex items-center justify-between gap-3 text-sm">
                    <div className="min-w-0"><div className="font-medium truncate">{c.org_name}</div><div className="text-xs text-slate-500">{new Date(c.paid_at).toLocaleDateString("it-IT")} · {c.commission_pct}% di {eur(c.base_cents)}</div></div>
                    <div className="text-right shrink-0"><div className="font-semibold tabular-nums">{eur(c.commission_net_cents)}</div><span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${CST[c.status]}`}>{c.status}</span></div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
        <section>
          <h2 className="text-base md:text-lg font-bold mb-3">Simulatore commissioni</h2>
          <div className="max-w-2xl"><Simulator /></div>
        </section>
      </main>
    </div>
  );
}
