import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CreditCard, CalendarClock, CheckCircle2, AlertTriangle, Building2, Save, Settings2, ReceiptText } from "lucide-react";

const STATUS_LABEL = { trial: "Prova gratuita", active: "Attivo", expired: "Scaduto", canceled: "Cancellato", past_due: "Pagamento non riuscito", suspended: "Sospeso" };
const STATUS_COLOR = { trial: "tiffany", active: "green", expired: "red", canceled: "gray", past_due: "orange", suspended: "orange" };
const PAESI = ["IT", "SM", "VA", "FR", "DE", "ES", "CH", "AT", "GB", "US", "Altro"];

const BFIELDS = [
  ["indirizzo", "Indirizzo", false], ["cap", "CAP", false], ["citta", "Città", false],
  ["provincia", "Provincia", false], ["codice_fiscale", "Codice Fiscale", false],
  ["partita_iva", "Partita IVA", false], ["codice_sdi", "Codice Destinatario (SDI)", false],
  ["pec", "PEC", false], ["email_fatturazione", "Email fatturazione", false],
];

export default function Account() {
  const [data, setData] = useState(null);
  const [billing, setBilling] = useState(null);
  const [cycle, setCycle] = useState("yearly");
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [params, setParams] = useSearchParams();

  const load = useCallback(async () => {
    const [a, b] = await Promise.all([api.get("/account/subscription"), api.get("/account/billing")]);
    setData(a.data);
    setBilling({ tipo: "azienda", paese: "IT", ...(b.data || {}) });
  }, []);

  useEffect(() => {
    load().catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [load]);

  useEffect(() => {
    const c = params.get("checkout");
    if (c === "success") {
      toast.success("Pagamento ricevuto! Sincronizzo l'abbonamento...");
      api.post("/account/sync-subscription").then(() => load()).catch(() => {});
      params.delete("checkout"); params.delete("session_id"); setParams(params, { replace: true });
    } else if (c === "cancel") {
      toast.info("Checkout annullato.");
      params.delete("checkout"); setParams(params, { replace: true });
    }
  }, [params, setParams, load]);

  if (!data || !billing) return <div className="text-slate-400">Caricamento...</div>;
  const s = data.subscription;
  const isItaly = (billing.paese || "IT") === "IT";
  const isAzienda = billing.tipo === "azienda";

  const ch = (k) => (e) => setBilling((f) => ({ ...f, [k]: e.target.value }));

  const saveBilling = async () => {
    setSaving(true);
    try { const { data } = await api.put("/account/billing", billing); setBilling((f) => ({ ...f, ...data })); toast.success("Dati di fatturazione salvati"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const checkout = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/account/checkout", { billing_cycle: cycle, origin_url: window.location.origin });
      window.location.href = data.checkout_url;
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };

  const manage = async () => {
    setBusy(true);
    try { const { data } = await api.post("/account/portal", { origin_url: window.location.origin }); window.location.href = data.url; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };

  const canPay = !!(billing.paese && billing.indirizzo && billing.citta && (isAzienda ? billing.ragione_sociale : (billing.nome && billing.cognome)));
  const hasSub = s.status === "active" || s.status === "past_due" || !!data.subscription.stripe_subscription_id;

  return (
    <div className="max-w-3xl animate-fade-up" data-testid="account-page">
      <h1 className="font-display text-3xl font-bold text-slate-900">Account e abbonamento</h1>
      <p className="text-slate-500 mt-1 mb-6">Gestisci il piano e i dati di fatturazione della tua organizzazione.</p>

      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
        <div className="flex items-center gap-2 text-slate-500 text-sm"><Building2 className="w-4 h-4" />Organizzazione</div>
        <div className="text-xl font-semibold text-slate-900 mt-1" data-testid="account-org-name">{data.organization.nome}</div>
      </div>

      {/* Subscription status */}
      <div className={`rounded-xl p-6 border mb-4 ${s.access !== "full" ? "border-red-200 bg-red-50" : s.status === "trial" ? "border-tiffany-border bg-tiffany-light/40" : "border-emerald-200 bg-emerald-50"}`} data-testid="account-subscription">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2"><span className="text-sm text-slate-500">Stato</span>
              <StatusBadge color={STATUS_COLOR[s.status] || "gray"} data-testid="account-status">{STATUS_LABEL[s.status] || s.status}</StatusBadge></div>
            <div className="text-2xl font-bold text-slate-900 mt-2 font-display">Piano CRMEvent {s.billing_cycle === "yearly" ? "· Annuale" : s.billing_cycle === "monthly" ? "· Mensile" : ""}</div>
          </div>
          <div className="text-right"><div className="text-3xl font-bold text-slate-900">{s.billing_cycle === "yearly" ? "199 €" : "19,90 €"}</div><div className="text-xs text-slate-500">{s.billing_cycle === "yearly" ? "/ anno" : "/ mese"} + IVA</div></div>
        </div>
        {s.status === "trial" && <div className="mt-4 flex items-center gap-2 text-tiffany-fg font-semibold" data-testid="account-trial-remaining"><CalendarClock className="w-5 h-5" />Prova gratuita – {s.days_left} giorni rimanenti</div>}
        {s.status === "active" && s.current_period_end && <div className="text-sm text-slate-600 mt-3 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-500" />Prossimo rinnovo: {new Date(s.current_period_end).toLocaleDateString("it-IT")}</div>}
        {s.access !== "full" && s.status !== "active" && <div className="mt-4 flex items-start gap-2 text-red-700 text-sm" data-testid="account-expired-note"><AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />Il periodo di prova è terminato. I tuoi dati sono conservati. Attiva l'abbonamento per continuare senza limitazioni.</div>}
      </div>

      {/* Billing details */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4" data-testid="billing-form">
        <div className="flex items-center gap-2 mb-4"><ReceiptText className="w-4 h-4 text-tiffany-active" /><h2 className="font-semibold text-slate-800">Dati di fatturazione</h2></div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="space-y-1.5"><Label>Tipo</Label>
            <select value={billing.tipo} onChange={ch("tipo")} data-testid="billing-tipo" className="w-full h-10 rounded-md border border-slate-200 px-3 text-sm bg-white">
              <option value="azienda">Azienda / Ente</option><option value="privato">Privato</option></select></div>
          <div className="space-y-1.5"><Label>Paese</Label>
            <select value={billing.paese} onChange={ch("paese")} data-testid="billing-paese" className="w-full h-10 rounded-md border border-slate-200 px-3 text-sm bg-white">
              {PAESI.map((p) => <option key={p} value={p}>{p}</option>)}</select></div>
          {isAzienda
            ? <div className="space-y-1.5 sm:col-span-2"><Label>Ragione sociale</Label><Input value={billing.ragione_sociale || ""} onChange={ch("ragione_sociale")} data-testid="billing-ragione" /></div>
            : (<><div className="space-y-1.5"><Label>Nome</Label><Input value={billing.nome || ""} onChange={ch("nome")} data-testid="billing-nome" /></div>
                 <div className="space-y-1.5"><Label>Cognome</Label><Input value={billing.cognome || ""} onChange={ch("cognome")} data-testid="billing-cognome" /></div></>)}
          {BFIELDS.filter(([k]) => {
            if (!isItaly && (k === "codice_sdi" || k === "pec" || k === "codice_fiscale")) return false;
            if (!isAzienda && k === "partita_iva") return false;
            return true;
          }).map(([k, label]) => (
            <div key={k} className="space-y-1.5"><Label>{label}</Label><Input value={billing[k] || ""} onChange={ch(k)} data-testid={`billing-${k}`} /></div>
          ))}
        </div>
        {isItaly && isAzienda && <p className="text-xs text-slate-400 mt-3">Per le aziende italiane indica Codice Destinatario SDI oppure PEC per la fatturazione elettronica.</p>}
        <Button onClick={saveBilling} disabled={saving} data-testid="billing-save" className="mt-4 bg-slate-900 hover:bg-slate-800 text-white"><Save className="w-4 h-4 mr-2" />{saving ? "Salvataggio..." : "Salva dati"}</Button>
      </div>

      {/* Activate / manage */}
      <div className="bg-white border border-slate-200 rounded-xl p-6" data-testid="activate-card">
        {hasSub ? (
          <>
            <h2 className="font-semibold text-slate-800 mb-2">Gestisci abbonamento</h2>
            <p className="text-sm text-slate-500 mb-4">Modifica il metodo di pagamento, cambia piano o annulla tramite il portale Stripe.</p>
            <Button onClick={manage} disabled={busy} data-testid="manage-subscription-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Settings2 className="w-4 h-4 mr-2" />Gestisci abbonamento</Button>
          </>
        ) : (
          <>
            <h2 className="font-semibold text-slate-800 mb-3">Attiva CRMEvent</h2>
            <div className="inline-flex bg-slate-100 rounded-full p-1 mb-4" data-testid="account-cycle-toggle">
              <button onClick={() => setCycle("monthly")} data-testid="account-cycle-monthly" className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all ${cycle === "monthly" ? "bg-white shadow text-slate-900" : "text-slate-500"}`}>Mensile · 19,90 €</button>
              <button onClick={() => setCycle("yearly")} data-testid="account-cycle-yearly" className={`px-4 py-1.5 rounded-full text-sm font-semibold transition-all ${cycle === "yearly" ? "bg-white shadow text-slate-900" : "text-slate-500"}`}>Annuale · 199 €</button>
            </div>
            {!canPay && <p className="text-xs text-amber-600 mb-3">Completa e salva i dati di fatturazione prima di procedere al pagamento.</p>}
            <div><Button onClick={checkout} disabled={busy || !canPay} data-testid="account-activate-btn" className="h-11 px-6 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><CreditCard className="w-4 h-4 mr-2" />{busy ? "Reindirizzamento..." : "Attiva CRMEvent"}</Button></div>
            <p className="text-xs text-slate-400 mt-2">Pagamenti sicuri gestiti tramite Stripe · Rinnovo automatico · Cancella quando vuoi.</p>
          </>
        )}
      </div>
    </div>
  );
}
