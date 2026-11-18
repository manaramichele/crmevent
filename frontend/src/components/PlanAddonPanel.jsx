import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const eur = (n) => `${Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT", { timeZone: "Europe/Rome" }) : "—");
const Row = ({ l, v, t }) => <div className="flex justify-between gap-3 py-1"><span className="text-slate-500">{l}</span><b className="text-slate-800 text-right" data-testid={t}>{v}</b></div>;

export default function PlanAddonPanel() {
  const [q, setQ] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/marketplace/plan-addon/quote").then(({ data }) => setQ(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, []);
  if (!q) return null;
  const buy = async () => {
    setBusy(true);
    try { await api.post("/marketplace/plan-addon/purchase", { confirm_amount: q.amount_due }); toast.success("Modulo attivato"); load(); }
    catch (e) { const det = e.response?.data?.detail; toast.error(formatApiError(det?.message || det)); load(); }
    finally { setBusy(false); }
  };
  const renewal = async (renew) => {
    try { await api.post("/marketplace/plan-addon/renewal", null, { params: { renew } }); toast.success(renew ? "Rinnovo automatico attivato" : "Rinnovo automatico disattivato"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const p = q.purchase;
  return (
    <div className="col-span-2 rounded-lg border border-tiffany-border bg-tiffany-light/40 p-3 text-sm" data-testid="plan-addon-panel">
      <p className="text-slate-600 mb-2" data-testid="plan-addon-note">{q.note}</p>
      {p ? (<>
        <Row l="Stato" v={p.renew === false ? `Attivo fino al ${d(p.current_period_end)} · non si rinnova` : "Attivo · si rinnova con il piano"} t="plan-addon-status" />
        <Row l="Prossimo rinnovo" v={p.renew === false ? "—" : `${d(p.current_period_end)} · ${eur(q.annual_price)} + IVA`} t="plan-addon-next" />
        <Button variant="outline" size="sm" className="mt-2" onClick={() => renewal(p.renew === false)} data-testid="plan-addon-renewal-toggle">{p.renew === false ? "Riattiva rinnovo automatico" : "Disattiva rinnovo automatico"}</Button>
      </>) : q.blocked ? (
        <p className="font-medium text-amber-800" data-testid="plan-addon-blocked">{q.blocked}</p>
      ) : (<>
        <Row l="Prezzo annuale" v={`${eur(q.annual_price)} + IVA`} t="plan-addon-annual" />
        <Row l="Piano attivo" v={`${(q.plan || "").replace(/^./, (c) => c.toUpperCase())} annuale`} t="plan-addon-plan" />
        <Row l="Scadenza del piano" v={d(q.renewal_date)} t="plan-addon-renewal-date" />
        <Row l="Giorni residui" v={`${q.days_left} su ${q.period_days}`} t="plan-addon-days" />
        <Row l="Da pagare oggi" v={q.amount_due != null ? `${eur(q.amount_due)} (IVA inclusa se applicabile)` : `${eur(q.amount)} + IVA (stima)`} t="plan-addon-today" />
        <Row l="Al prossimo rinnovo" v={`${eur(q.annual_price)} + IVA`} t="plan-addon-next-price" />
        {q.purchasable
          ? <Button className="mt-2 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" disabled={busy || q.amount_due == null} onClick={buy} data-testid="plan-addon-buy">{busy ? "Pagamento…" : `Acquista e paga ${eur(q.amount_due)}`}</Button>
          : <p className="mt-2 text-xs font-semibold text-slate-500" data-testid="plan-addon-not-yet">Acquisto non ancora disponibile: il modulo è in preparazione.</p>}
      </>)}
    </div>
  );
}
