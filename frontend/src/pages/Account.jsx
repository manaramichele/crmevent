import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import CreditsSection from "@/components/CreditsSection";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Building2, Save, ReceiptText } from "lucide-react";

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
      <h1 className="font-display text-3xl font-bold text-slate-900">Account e crediti</h1>
      <p className="text-slate-500 mt-1 mb-6">Gestisci i tuoi crediti CRMEvent e i dati di fatturazione.</p>

      <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4">
        <div className="flex items-center gap-2 text-slate-500 text-sm"><Building2 className="w-4 h-4" />Organizzazione</div>
        <div className="text-xl font-semibold text-slate-900 mt-1" data-testid="account-org-name">{data.organization.nome}</div>
      </div>

      {/* Crediti CRMEvent */}
      <CreditsSection />

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

      <div className="bg-white border border-slate-200 rounded-xl p-6 mt-4" data-testid="invoices-card">
        <div className="flex items-center gap-2 mb-1"><ReceiptText className="w-4 h-4 text-tiffany-active" /><h2 className="font-semibold text-slate-800">Fatture</h2></div>
        <p className="text-xs text-slate-400 mb-4">La <b>simulazione (TEST)</b> verifica il documento internamente: <b>nessun</b> documento reale su Fatture in Cloud e <b>nessun</b> invio SDI.</p>
        {invoices.length === 0 ? (
          <p className="text-sm text-slate-500" data-testid="invoices-empty">Nessuna fattura ancora. Dopo una ricarica crediti (Stripe TEST) comparirà qui.</p>
        ) : (
          <div className="space-y-2">
            {invoices.map((iv) => (
              <div key={iv.id} className="flex items-center justify-between border border-slate-100 rounded-lg px-3 py-2" data-testid={`invoice-row-${iv.id}`}>
                <div className="min-w-0 text-sm">
                  <div className="font-medium text-slate-800">{iv.numero_stripe || iv.fic_numero || iv.id.slice(0, 8)} · {(iv.totale ?? 0).toFixed(2)} {(iv.valuta || "eur").toUpperCase()}</div>
                  <div className="text-xs text-slate-500">{iv.descrizione ? `${iv.descrizione} · ` : ""}{(iv.data || "").slice(0, 10)} · {iv.payment_status || "—"} · FIC: {iv.fic_stato_documento || "da_emettere"}</div>
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
              <div className="sm:col-span-2"><span className="text-slate-500">Dati cliente:</span> {[sim.cliente?.vat_number && `P.IVA ${sim.cliente.vat_number}`, sim.cliente?.tax_code && `CF ${sim.cliente.tax_code}`, [sim.cliente?.address_street, sim.cliente?.address_postal_code, sim.cliente?.address_city, sim.cliente?.address_province].filter(Boolean).join(" "), sim.cliente?.ei_code && `SDI ${sim.cliente.ei_code}`, sim.cliente?.certified_email && `PEC ${sim.cliente.certified_email}`].filter(Boolean).join(" · ") || "—"}</div>
              <div><span className="text-slate-500">Numero simulato:</span> {sim.numero_simulato}</div>
              <div><span className="text-slate-500">Data simulata:</span> {sim.data_simulata}</div>
              <div><span className="text-slate-500">Descrizione:</span> {sim.descrizione || sim.piano || "—"}</div>
              <div><span className="text-slate-500">Piano / ciclo:</span> {sim.piano_label || sim.piano || "—"}</div>
              <div><span className="text-slate-500">Ciclo:</span> {({ una_tantum: "Una tantum", monthly: "Mensile", yearly: "Annuale" })[sim.ciclo_fatturazione] || "—"}</div>
              <div><span className="text-slate-500">Modalità di pagamento:</span> {sim.modalita_pagamento || "—"}</div>
              <div><span className="text-slate-500">Imponibile:</span> {Number(sim.imponibile ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
              <div><span className="text-slate-500">Aliquota IVA:</span> {Number(sim.aliquota_iva ?? 0).toFixed(0)}%</div>
              <div><span className="text-slate-500">Importo IVA:</span> {Number(sim.importo_iva ?? sim.iva ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
              <div><span className="text-slate-500">Totale:</span> {Number(sim.totale ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
              <div><span className="text-slate-500">Stato:</span> {sim.stato_fattura || "—"}</div>
              <div><span className="text-slate-500">Coerenza (imponibile + IVA = totale):</span> {sim.coerente ? <span className="text-green-700 font-medium" data-testid="sim-coherent">OK ✓</span> : <span className="text-red-700 font-medium" data-testid="sim-incoherent">INCOERENTE</span>}</div>
              <div className="sm:col-span-2"><span className="text-slate-500">Rif. Stripe:</span> {sim.riferimento_stripe?.numero_stripe || sim.riferimento_stripe?.payment_intent || sim.riferimento_stripe?.stripe_invoice_id || "—"}</div>
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
