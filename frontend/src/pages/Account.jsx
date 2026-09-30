import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import EventPlanManager from "@/components/EventPlanManager";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CalendarClock, CheckCircle2, AlertTriangle, Building2, Save, ReceiptText } from "lucide-react";

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
  const [saving, setSaving] = useState(false);
  const [invoices, setInvoices] = useState([]);
  const [simBusy, setSimBusy] = useState(null);
  const [sim, setSim] = useState(null);

  const load = useCallback(async () => {
    const [a, b, inv] = await Promise.all([api.get("/account/subscription"), api.get("/account/billing"), api.get("/account/invoices")]);
    setData(a.data);
    setBilling({ tipo: "azienda", paese: "IT", ...(b.data || {}) });
    setInvoices(inv.data || []);
  }, []);

  const simulateInvoice = async (id) => {
    setSimBusy(id); setSim(null);
    try { const { data } = await api.post(`/fic/simulate/${id}`); setSim(data); toast.success("Fattura simulata (TEST) — nessun documento reale su Fatture in Cloud"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSimBusy(null); }
  };

  useEffect(() => {
    load().catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [load]);

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

  return (
    <div className="max-w-3xl animate-fade-up" data-testid="account-page">
      <h1 className="font-display text-3xl font-bold text-slate-900">Account e licenze</h1>
      <p className="text-slate-500 mt-1 mb-6">Ogni evento ha la sua licenza. Gestisci prova, piani per evento e dati di fatturazione.</p>

      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
        <div className="flex items-center gap-2 text-slate-500 text-sm"><Building2 className="w-4 h-4" />Organizzazione</div>
        <div className="text-xl font-semibold text-slate-900 mt-1" data-testid="account-org-name">{data.organization.nome}</div>
      </div>

      {/* Subscription status */}
      <div className={`rounded-xl p-6 border mb-4 ${s.access !== "full" ? "border-red-200 bg-red-50" : s.status === "trial" ? "border-tiffany-border bg-tiffany-light/40" : "border-emerald-200 bg-emerald-50"}`} data-testid="account-subscription">
        <div className="flex items-center gap-2"><span className="text-sm text-slate-500">Stato organizzazione</span>
          <StatusBadge color={STATUS_COLOR[s.status] || "gray"} data-testid="account-status">{STATUS_LABEL[s.status] || s.status}</StatusBadge></div>
        {s.status === "trial"
          ? <>
              <div className="text-2xl font-bold text-slate-900 mt-2 font-display">Prova gratuita CRMEvent Premium</div>
              <div className="mt-3 flex items-center gap-2 text-tiffany-fg font-semibold" data-testid="account-trial-remaining"><CalendarClock className="w-5 h-5" />{s.days_left} giorni rimanenti · tutte le funzionalità Premium</div>
              <p className="text-sm text-slate-600 mt-2">Alla fine della prova i tuoi dati restano al sicuro. Per continuare a operare un evento, attiva un piano dedicato qui sotto.</p>
            </>
          : <>
              <div className="text-2xl font-bold text-slate-900 mt-2 font-display">Licenze per evento</div>
              <div className="mt-2 flex items-start gap-2 text-slate-700 text-sm"><CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-500 shrink-0" />Nessun abbonamento. Ogni evento si attiva con Starter, Professional o Premium.</div>
              {s.access !== "full" && <div className="mt-3 flex items-start gap-2 text-red-700 text-sm" data-testid="account-expired-note"><AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />La prova gratuita è terminata. I tuoi dati sono conservati. Attiva un piano per ciascun evento per continuare a operarlo.</div>}
            </>}
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

      {/* Piani e acquisti (per evento) */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 mt-4" data-testid="account-plans-purchases">
        <div className="flex items-center gap-2 mb-1"><ReceiptText className="w-4 h-4 text-tiffany-active" /><h2 className="font-semibold text-slate-800">Piani e acquisti</h2></div>
        <p className="text-xs text-slate-400 mb-4">Stato commerciale di ogni evento. Il piano si attiva solo dopo conferma del pagamento (Stripe TEST).</p>
        <EventPlanManager />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6 mt-4" data-testid="invoices-card">
        <div className="flex items-center gap-2 mb-1"><ReceiptText className="w-4 h-4 text-tiffany-active" /><h2 className="font-semibold text-slate-800">Fatture</h2></div>
        <p className="text-xs text-slate-400 mb-4">La <b>simulazione (TEST)</b> verifica il documento internamente: <b>nessun</b> documento reale su Fatture in Cloud e <b>nessun</b> invio SDI.</p>
        {invoices.length === 0 ? (
          <p className="text-sm text-slate-500" data-testid="invoices-empty">Nessuna fattura ancora. Dopo un pagamento Stripe TEST comparirà qui.</p>
        ) : (
          <div className="space-y-2">
            {invoices.map((iv) => (
              <div key={iv.id} className="flex items-center justify-between border border-slate-100 rounded-lg px-3 py-2" data-testid={`invoice-row-${iv.id}`}>
                <div className="min-w-0 text-sm">
                  <div className="font-medium text-slate-800">{iv.numero_stripe || iv.fic_numero || iv.id.slice(0, 8)} · {(iv.totale ?? 0).toFixed(2)} {(iv.valuta || "eur").toUpperCase()}</div>
                  <div className="text-xs text-slate-500">{(iv.data || "").slice(0, 10)} · {iv.payment_status || "—"} · FIC: {iv.fic_stato_documento || "da_emettere"}</div>
                </div>
                <Button size="sm" variant="outline" onClick={() => simulateInvoice(iv.id)} disabled={simBusy === iv.id} data-testid={`invoice-simulate-${iv.id}`}>{simBusy === iv.id ? "Simulo…" : "Simula fattura (TEST)"}</Button>
              </div>
            ))}
          </div>
        )}
        {sim && (
          <div className="mt-4 rounded-lg border border-tiffany-border bg-tiffany-light/40 p-4 text-sm" data-testid="sim-result">
            <div className="font-semibold text-slate-800 mb-2">SIMULAZIONE TEST · nessun documento FIC / nessun SDI</div>
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-slate-700">
              <div><span className="text-slate-500">Intestazione:</span> {sim.intestazione || "—"}</div>
              <div><span className="text-slate-500">Numero simulato:</span> {sim.numero_simulato}</div>
              <div><span className="text-slate-500">Data simulata:</span> {sim.data_simulata}</div>
              <div><span className="text-slate-500">Piano:</span> {sim.piano || "—"}</div>
              <div><span className="text-slate-500">Imponibile:</span> {Number(sim.imponibile ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
              <div><span className="text-slate-500">Aliquota IVA:</span> {Number(sim.aliquota_iva ?? 0).toFixed(0)}%</div>
              <div><span className="text-slate-500">Importo IVA:</span> {Number(sim.importo_iva ?? sim.iva ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
              <div><span className="text-slate-500">Totale:</span> {Number(sim.totale ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
              <div><span className="text-slate-500">Stato:</span> {sim.stato_fattura || "—"}</div>
              <div><span className="text-slate-500">Coerenza (imponibile + IVA = totale):</span> {sim.coerente ? <span className="text-green-700 font-medium" data-testid="sim-coherent">OK ✓</span> : <span className="text-red-700 font-medium" data-testid="sim-incoherent">INCOERENTE</span>}</div>
              <div className="sm:col-span-2"><span className="text-slate-500">Rif. Stripe:</span> {sim.riferimento_stripe?.numero_stripe || sim.riferimento_stripe?.stripe_invoice_id || "—"}</div>
            </div>
            <details className="mt-2">
              <summary className="text-xs text-tiffany-active cursor-pointer">Payload FIC che sarebbe stato inviato (sicuro, senza secret)</summary>
              <pre className="mt-2 text-[11px] bg-white border border-slate-200 rounded p-2 overflow-x-auto" data-testid="sim-payload">{JSON.stringify(sim.fic_payload_preview, null, 2)}</pre>
            </details>
          </div>
        )}
      </div>
    </div>
  );
}
