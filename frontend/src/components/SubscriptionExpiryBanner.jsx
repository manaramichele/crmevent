import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { isOrgAdmin } from "@/lib/perms";

export default function SubscriptionExpiryBanner() {
  const { user } = useAuth();
  const s = user?.saas;
  const can = isOrgAdmin(user) || !!user?.permissions?.subscription_manage;
  if (!s?.enabled || user?.role === "superadmin" || !can || s.sub_status !== "expiring") return null;
  const end = s.expires_at ? new Date(s.expires_at).toLocaleDateString("it-IT") : "";
  const msg = s.stripe_status === "past_due" ? "Il pagamento dell'abbonamento non è riuscito: aggiorna il metodo di pagamento per evitare interruzioni."
    : s.days_to_expiry === 0 ? `Il tuo abbonamento ${s.plan_label || ""} scade oggi.` : `Il tuo abbonamento ${s.plan_label || ""} scade tra ${s.days_to_expiry} giorni (${end}) e il rinnovo automatico non è attivo.`;
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" data-testid="subscription-expiry-banner">
      <AlertTriangle className="w-5 h-5 shrink-0" /><span className="flex-1">{msg}</span>
      <Link to="/profilo?tab=abbonamento" className="inline-flex h-9 items-center justify-center rounded-md bg-[#0ABAB5] px-4 font-semibold text-slate-900 hover:bg-[#09A8A3]" data-testid="subscription-expiry-banner-renew">Rinnova abbonamento</Link>
    </div>
  );
}
