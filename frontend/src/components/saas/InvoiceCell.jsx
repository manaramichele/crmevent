import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { FileText, FilePlus2, ExternalLink, AlertTriangle, RotateCw } from "lucide-react";

export const FIC_STATE = {
  creata: ["Fattura creata", "bg-emerald-50 text-emerald-700"],
  da_fatturare: ["Da fatturare", "bg-amber-50 text-amber-700"],
  dati_mancanti: ["Dati mancanti", "bg-red-50 text-red-700"],
  errore: ["Errore fatturazione", "bg-red-50 text-red-700"],
  non_disponibile: ["Non disponibile", "bg-slate-100 text-slate-500"],
};
const PRIORITY = ["errore", "dati_mancanti", "da_fatturare", "creata", "non_disponibile"];
export const orgFicState = (r) => PRIORITY.find((s) => (r.fatture || []).some((f) => f.state === s)) || "non_disponibile";

const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");
const eur = (v, c) => `${Number(v || 0).toFixed(2).replace(".", ",")} ${c === "EUR" ? "€" : c}`;
const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const FIELDS = [["tipo", "Tipo (azienda/privato)"], ["ragione_sociale", "Ragione sociale"], ["nome", "Nome"], ["cognome", "Cognome"], ["partita_iva", "Partita IVA"],
  ["codice_fiscale", "Codice fiscale"], ["indirizzo", "Indirizzo"], ["cap", "CAP"], ["citta", "Comune"], ["provincia", "Provincia"], ["paese", "Nazione (es. IT)"],
  ["email_fatturazione", "Email"], ["pec", "PEC"], ["codice_sdi", "Codice destinatario SDI"]];

export const Badge = ({ s, testid }) => <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${FIC_STATE[s][1]}`} data-testid={testid}>{FIC_STATE[s][0]}</span>;

function BillingForm({ f, onSaved }) {
  const [b, setB] = useState(null);
  const [busy, setBusy] = useState(false);
  const open = async () => { try { const { data } = await api.get(`/platform/invoices/${f.id}/fic`); setB(data.billing); } catch (e) { err(e); } };
  const save = async () => {
    setBusy(true);
    try { const { data } = await api.put(`/platform/invoices/${f.id}/billing`, b); toast.success(data.missing.length ? `Mancano ancora: ${data.missing.join(", ")}` : "Dati di fatturazione completi"); onSaved(); setB(null); }
    catch (e) { err(e); }
    setBusy(false);
  };
  if (!b) return <Button size="sm" variant="outline" onClick={open} data-testid={`fic-complete-${f.id}`}>Completa dati</Button>;
  return (
    <div className="w-full mt-2 grid grid-cols-2 gap-2 text-xs" data-testid={`fic-billing-form-${f.id}`}>
      {FIELDS.map(([k, l]) => <label key={k}>{l}<Input value={b[k] || ""} onChange={(e) => setB({ ...b, [k]: e.target.value })} className="h-8" data-testid={`fic-billing-${k}`} /></label>)}
      <Button size="sm" disabled={busy} onClick={save} className="col-span-2 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid={`fic-billing-save-${f.id}`}>Salva dati di fatturazione</Button>
    </div>
  );
}

function PaymentRow({ f, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [pv, setPv] = useState(null);
  const preview = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/platform/invoices/${f.id}/fic-preview`); setPv(data); } catch (e) { err(e); }
    setBusy(false);
  };
  const gen = async () => {
    if (!window.confirm(`Creare ora la fattura in BOZZA su Fatture in Cloud per ${eur(f.totale, f.valuta)}? Nessun invio allo SDI.`)) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/platform/invoices/${f.id}/fic-generate`);
      if (data.state === "creata") toast.success(`Fattura creata in bozza su Fatture in Cloud${data.numero ? ` (n. ${data.numero})` : ""}`);
      else toast.error(data.error || (data.missing ? `Dati mancanti: ${data.missing.join(", ")}` : "Fattura non creata"));
      onChanged();
    } catch (e) { err(e); }
    setBusy(false);
  };
  return (
    <div className="rounded-lg border border-slate-200 p-3 text-sm" data-testid={`fic-payment-${f.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="font-medium text-slate-800 truncate">{f.descrizione || "Pagamento"}</div>
          <div className="text-xs text-slate-500">Pagato il {d(f.data)} · {eur(f.totale, f.valuta)}{f.periodo_inizio ? ` · periodo ${d(f.periodo_inizio)} – ${d(f.periodo_fine)}` : ""}{f.is_test ? " · TEST" : ""}</div>
          <div className="text-[11px] text-slate-400 truncate">Stripe {f.stripe_invoice_id}</div>
        </div>
        <div className="flex items-center gap-2">
          <Badge s={f.state} testid={`fic-state-${f.id}`} />
          {f.numero && <span className="text-xs font-semibold" data-testid={`fic-numero-${f.id}`}>n. {f.numero}</span>}
          {f.state === "creata" && f.url && <a href={f.url} target="_blank" rel="noopener noreferrer" data-testid={`fic-view-${f.id}`}><Button size="sm" variant="outline"><ExternalLink className="w-3.5 h-3.5 mr-1" />Visualizza fattura</Button></a>}
          {["da_fatturare", "errore", "dati_mancanti"].includes(f.state) && (
            <Button size="sm" variant="outline" disabled={busy} onClick={preview} data-testid={`fic-preview-${f.id}`}>Verifica</Button>
          )}
          {["da_fatturare", "errore", "dati_mancanti"].includes(f.state) && (
            <Button size="sm" disabled={busy} onClick={gen} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid={`fic-generate-${f.id}`}>
              {f.state === "errore" ? <RotateCw className="w-3.5 h-3.5 mr-1" /> : <FilePlus2 className="w-3.5 h-3.5 mr-1" />}{busy ? "Verifica Stripe..." : f.state === "errore" ? "Riprova" : "Genera fattura"}
            </Button>
          )}
        </div>
      </div>
      {pv && (
        <div className="mt-2 rounded-md bg-slate-50 p-2 text-xs text-slate-600 space-y-0.5" data-testid={`fic-preview-box-${f.id}`}>
          <div><b>Stripe:</b> {pv.stripe.payment_ref} · {eur(pv.stripe.amount, pv.stripe.currency)} · pagato il {d(pv.stripe.paid_at)}</div>
          <div><b>Riga:</b> {pv.riga} · {eur(pv.importo, pv.stripe.currency)}</div>
          <div data-testid={`fic-preview-vat-${f.id}`}><b>Aliquota FIC:</b> {pv.vat.description || "—"} (ID {pv.vat.id}{pv.vat.ei_type ? ` · ${pv.vat.ei_type}` : ""})</div>
          <div><b>Bollo:</b> {pv.bollo ? `2,00 € virtuale a carico dell'emittente (il totale resta ${eur(pv.importo, pv.stripe.currency)})` : "non dovuto"}</div>
          <div className={pv.existing ? "text-amber-700 font-semibold" : ""}>{pv.existing ? `Documento già presente su FIC (n. ${pv.existing.number}): verrà collegato, non duplicato` : "Nessun documento esistente per questo pagamento"}</div>
          {pv.missing?.length > 0 && <div className="text-red-600">Dati mancanti: {pv.missing.join(", ")}</div>}
          <div>Invio SDI: no (solo manuale da Fatture in Cloud)</div>
        </div>
      )}
      {f.error && f.state !== "creata" && <div className="mt-2 flex gap-1 text-xs text-red-600" data-testid={`fic-error-${f.id}`}><AlertTriangle className="w-3.5 h-3.5 shrink-0" />{f.error}</div>}
      {f.state === "dati_mancanti" && f.missing?.length > 0 && <div className="mt-2 text-xs text-red-600" data-testid={`fic-missing-${f.id}`}>Da completare: {f.missing.join(", ")}</div>}
      {f.state === "dati_mancanti" && <BillingForm f={f} onSaved={onChanged} />}
    </div>
  );
}

export function InvoiceCell({ r, onChanged }) {
  const [open, setOpen] = useState(false);
  const [sync, setSync] = useState(false);
  const fs = r.fatture || [];
  const s = orgFicState(r);
  const openDlg = async () => {
    setOpen(true); setSync(true);
    try { const { data } = await api.post("/platform/invoices/reconcile", null, { params: { org_id: r.id } }); if (data.added || data.fixed) { toast.success(`Pagamenti Stripe recuperati: ${data.added + data.fixed}`); } await onChanged(); }
    catch (e) { err(e); }
    setSync(false);
  };
  const todo = fs.filter((f) => ["da_fatturare", "errore", "dati_mancanti"].includes(f.state)).length;
  const last = fs.find((f) => f.numero);
  return (
    <>
      <button type="button" onClick={openDlg} className="flex flex-col items-start gap-0.5 text-left" data-testid={`saas-fic-${r.id}`}>
        <span className="flex items-center gap-1"><FileText className="w-3.5 h-3.5 text-slate-400" /><Badge s={s} /></span>
        <span className="text-[11px] text-slate-500">{!fs.length ? "Verifica su Stripe" : `${todo ? `${todo} da gestire · ` : ""}${last ? `ultima n. ${last.numero}` : `${fs.length} pagament${fs.length === 1 ? "o" : "i"}`}`}</span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid={`saas-fic-dialog-${r.id}`}>
          <DialogTitle>Fatture · {r.nome}</DialogTitle>
          <DialogDescription>Ogni pagamento Stripe confermato genera una sola fattura in bozza su Fatture in Cloud. L'invio allo SDI si fa solo manualmente da Fatture in Cloud.</DialogDescription>
          {sync && <p className="text-xs text-slate-500" data-testid="fic-reconcile-loading">Verifica dei pagamenti su Stripe in corso...</p>}
          {!sync && !fs.length && <p className="text-sm text-slate-500" data-testid="fic-no-payments">Nessun pagamento Stripe confermato per questa organizzazione.</p>}
          <div className="space-y-2">{fs.map((f) => <PaymentRow key={f.id} f={f} onChanged={onChanged} />)}</div>
        </DialogContent>
      </Dialog>
    </>
  );
}
