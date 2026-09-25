import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Building2, Users, CalendarDays, Wallet, TrendingUp, Inbox } from "lucide-react";

const STATUS_LABEL = { trial: "Trial", active: "Attivo", expired: "Scaduto", canceled: "Cancellato", past_due: "Pag. fallito", suspended: "Sospeso" };
const STATUS_COLOR = { trial: "tiffany", active: "green", expired: "red", canceled: "gray", past_due: "orange", suspended: "orange" };

function Stat({ icon: Icon, label, value, tone = "slate" }) {
  const tones = { slate: "bg-slate-100 text-slate-700", tiffany: "bg-tiffany-light text-tiffany-fg", green: "bg-emerald-50 text-emerald-700", red: "bg-red-50 text-red-600", blue: "bg-sky-50 text-sky-700" };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`platform-stat-${label}`}>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center mb-2 ${tones[tone]}`}><Icon className="w-5 h-5" /></div>
      <div className="text-2xl font-bold text-slate-900">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

export default function Platform() {
  const [stats, setStats] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [subs, setSubs] = useState([]);

  useEffect(() => {
    Promise.all([api.get("/platform/stats"), api.get("/platform/organizations"), api.get("/platform/subscriptions")])
      .then(([a, b, c]) => { setStats(a.data); setOrgs(b.data); setSubs(c.data); })
      .catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, []);

  return (
    <div className="animate-fade-up" data-testid="platform-page">
      <h1 className="font-display text-3xl font-bold text-slate-900">Piattaforma CRMEvent</h1>
      <p className="text-slate-500 mt-1 mb-6">Panoramica delle organizzazioni registrate e dello stato degli abbonamenti.</p>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-8">
          <Stat icon={Building2} label="Organizzazioni" value={stats.organizations} tone="tiffany" />
          <Stat icon={CalendarDays} label="In trial" value={stats.trial} tone="blue" />
          <Stat icon={Users} label="Attive" value={stats.active} tone="green" />
          <Stat icon={Users} label="Scadute" value={stats.expired} tone="red" />
          <Stat icon={Wallet} label="MRR (€)" value={stats.mrr} />
          <Stat icon={TrendingUp} label="ARR (€)" value={stats.arr} />
          <Stat icon={Inbox} label="Lead" value={stats.leads} />
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Organizzazioni</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2.5 px-4 font-semibold">Organizzazione</th><th className="py-2.5 px-4 font-semibold">Titolare</th>
              <th className="py-2.5 px-4 font-semibold">Stato</th><th className="py-2.5 px-4 font-semibold">Trial/Rinnovo</th>
              <th className="py-2.5 px-4 font-semibold text-center">Utenti</th><th className="py-2.5 px-4 font-semibold text-center">Eventi</th>
              <th className="py-2.5 px-4 font-semibold">Registrata</th>
            </tr></thead>
            <tbody>
              {orgs.length === 0 ? (
                <tr><td colSpan={7} className="py-8 text-center text-slate-400">Nessuna organizzazione registrata.</td></tr>
              ) : orgs.map((o) => (
                <tr key={o.id} className="border-b border-slate-100" data-testid={`platform-org-${o.id}`}>
                  <td className="py-2.5 px-4 font-medium text-slate-800">{o.nome}</td>
                  <td className="py-2.5 px-4 text-slate-600"><div>{o.owner_name}</div><div className="text-xs text-slate-400">{o.owner_email}</div></td>
                  <td className="py-2.5 px-4"><StatusBadge color={STATUS_COLOR[o.subscription.status] || "gray"}>{STATUS_LABEL[o.subscription.status] || o.subscription.status}</StatusBadge></td>
                  <td className="py-2.5 px-4 text-slate-600">{o.subscription.status === "trial" ? `${o.subscription.days_left} gg rimanenti` : (o.subscription.current_period_end ? new Date(o.subscription.current_period_end).toLocaleDateString("it-IT") : "—")}</td>
                  <td className="py-2.5 px-4 text-center text-slate-600">{o.members}</td>
                  <td className="py-2.5 px-4 text-center text-slate-600">{o.events}</td>
                  <td className="py-2.5 px-4 text-slate-500">{o.created_at ? new Date(o.created_at).toLocaleDateString("it-IT") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Abbonamenti */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden mt-8" data-testid="platform-subscriptions">
        <div className="px-5 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Abbonamenti</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2.5 px-4 font-semibold">Organizzazione</th><th className="py-2.5 px-4 font-semibold">Stato</th>
              <th className="py-2.5 px-4 font-semibold">Ciclo</th><th className="py-2.5 px-4 font-semibold text-right">Importo</th>
              <th className="py-2.5 px-4 font-semibold">Prossimo rinnovo</th><th className="py-2.5 px-4 font-semibold">Stripe Customer</th>
              <th className="py-2.5 px-4 font-semibold">Stripe Subscription</th><th className="py-2.5 px-4 font-semibold">Fatturazione</th>
            </tr></thead>
            <tbody>
              {subs.length === 0 ? (
                <tr><td colSpan={8} className="py-8 text-center text-slate-400">Nessun abbonamento.</td></tr>
              ) : subs.map((o) => (
                <tr key={o.id} className="border-b border-slate-100" data-testid={`platform-sub-${o.id}`}>
                  <td className="py-2.5 px-4 font-medium text-slate-800">{o.nome}</td>
                  <td className="py-2.5 px-4"><StatusBadge color={STATUS_COLOR[o.status] || "gray"}>{STATUS_LABEL[o.status] || o.status}</StatusBadge></td>
                  <td className="py-2.5 px-4 text-slate-600">{o.billing_cycle === "yearly" ? "Annuale" : o.billing_cycle === "monthly" ? "Mensile" : "—"}</td>
                  <td className="py-2.5 px-4 text-right text-slate-600">{o.amount ? `${o.amount} €` : "—"}</td>
                  <td className="py-2.5 px-4 text-slate-600">{o.status === "trial" ? `Trial · ${o.days_left} gg` : (o.current_period_end ? new Date(o.current_period_end).toLocaleDateString("it-IT") : "—")}</td>
                  <td className="py-2.5 px-4 text-slate-400 text-xs font-mono">{o.stripe_customer_id || "—"}</td>
                  <td className="py-2.5 px-4 text-slate-400 text-xs font-mono">{o.stripe_subscription_id || "—"}</td>
                  <td className="py-2.5 px-4 text-slate-500 text-xs">{o.fatturazione}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
