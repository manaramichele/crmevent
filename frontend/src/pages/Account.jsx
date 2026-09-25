import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { CreditCard, CalendarClock, CheckCircle2, AlertTriangle, Building2 } from "lucide-react";

const STATUS_LABEL = { trial: "Prova gratuita", active: "Attivo", expired: "Scaduto", canceled: "Cancellato", past_due: "Pagamento non riuscito", suspended: "Sospeso" };
const STATUS_COLOR = { trial: "tiffany", active: "green", expired: "red", canceled: "gray", past_due: "orange", suspended: "orange" };

export default function Account() {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get("/account/subscription").then(({ data }) => setData(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, []);

  if (!data) return <div className="text-slate-400">Caricamento...</div>;
  const s = data.subscription;
  const trial = s.status === "trial";
  const limited = s.access !== "full";

  return (
    <div className="max-w-3xl animate-fade-up" data-testid="account-page">
      <h1 className="font-display text-3xl font-bold text-slate-900">Account e abbonamento</h1>
      <p className="text-slate-500 mt-1 mb-6">Gestisci il piano della tua organizzazione.</p>

      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
        <div className="flex items-center gap-2 text-slate-500 text-sm"><Building2 className="w-4 h-4" />Organizzazione</div>
        <div className="text-xl font-semibold text-slate-900 mt-1" data-testid="account-org-name">{data.organization.nome}</div>
      </div>

      <div className={`rounded-xl p-6 border ${limited ? "border-red-200 bg-red-50" : trial ? "border-tiffany-border bg-tiffany-light/40" : "border-emerald-200 bg-emerald-50"}`} data-testid="account-subscription">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500">Stato abbonamento</span>
              <StatusBadge color={STATUS_COLOR[s.status] || "gray"} data-testid="account-status">{STATUS_LABEL[s.status] || s.status}</StatusBadge>
            </div>
            <div className="text-2xl font-bold text-slate-900 mt-2 font-display">
              Piano CRMEvent {s.billing_cycle === "yearly" ? "· Annuale" : s.billing_cycle === "monthly" ? "· Mensile" : ""}
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-slate-900">{s.billing_cycle === "yearly" ? "199 €" : "19,90 €"}</div>
            <div className="text-xs text-slate-500">{s.billing_cycle === "yearly" ? "/ anno" : "/ mese"} + IVA</div>
          </div>
        </div>

        {trial && (
          <div className="mt-5 flex items-center gap-2 text-tiffany-fg font-semibold" data-testid="account-trial-remaining">
            <CalendarClock className="w-5 h-5" />Prova gratuita – {s.days_left} giorni rimanenti
          </div>
        )}
        {trial && s.trial_end && <div className="text-sm text-slate-500 mt-1">Scadenza prova: {new Date(s.trial_end).toLocaleDateString("it-IT")}</div>}
        {s.status === "active" && s.current_period_end && <div className="text-sm text-slate-600 mt-3 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-500" />Prossimo rinnovo: {new Date(s.current_period_end).toLocaleDateString("it-IT")}</div>}
        {limited && (
          <div className="mt-4 flex items-start gap-2 text-red-700 text-sm" data-testid="account-expired-note">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            Il periodo di prova è terminato. I tuoi dati sono conservati. Attiva l'abbonamento per continuare a usare CRMEvent senza limitazioni.
          </div>
        )}

        <div className="mt-6">
          <Button data-testid="account-activate-btn" onClick={() => toast.info("L'attivazione dei pagamenti sarà disponibile a breve. Ti avviseremo appena pronta.")}
            className="h-11 px-6 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">
            <CreditCard className="w-4 h-4 mr-2" />Attiva CRMEvent
          </Button>
          <p className="text-xs text-slate-400 mt-2">Pagamenti sicuri gestiti tramite Stripe. Cancella quando vuoi.</p>
        </div>
      </div>
    </div>
  );
}
