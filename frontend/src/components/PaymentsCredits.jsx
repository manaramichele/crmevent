import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { RefreshCw, ChevronDown } from "lucide-react";

const TIPO_COLOR = { Cliente: "blue", Trial: "orange", Test: "gray", Interna: "gray" };
const PAY = { paid: ["green", "Pagato"], pending: ["orange", "In attesa"], unpaid: ["red", "Non pagato"], no_payment_required: ["gray", "Non richiesto"], expired: ["gray", "Scaduto"], failed: ["red", "Fallito"] };
const SDI = { accettato: ["green", "Accettata"], consegnato: ["green", "Consegnata"], inviato: ["blue", "Inviata allo SDI"], in_invio: ["orange", "In invio"], in_consegna: ["orange", "In consegna"],
  non_inviato: ["gray", "Non inviata allo SDI"], decorrenza_termini: ["blue", "Decorrenza termini"], rifiutato: ["red", "Rifiutata"], scartato: ["red", "Scartata SDI"], non_consegnato: ["red", "Non consegnata"],
  errore: ["red", "Errore"], simulato_test: ["gray", "TEST"], dry_run_validato: ["gray", "Validata (test)"] };
const DOC = { emessa: ["green", "Emessa"], da_emettere: ["orange", "Da emettere"], errore_emissione: ["red", "Errore emissione"], creato_test: ["gray", "TEST"], simulato_test: ["gray", "TEST"] };
const badge = (map, k, testid) => (k ? <StatusBadge color={(map[k] || ["gray"])[0]} data-testid={testid}>{(map[k] || [null, k])[1]}</StatusBadge> : <span className="text-slate-400">—</span>);
const d = (iso) => (iso ? new Date(iso).toLocaleDateString("it-IT") : "—");
const eur = (v) => (v == null ? "—" : `${Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2 })} €`);

function payState(lp) {
  if (!lp) return null;
  if (lp.is_test) return "test";
  return lp.stripe_payment_status || (lp.status === "paid" ? "paid" : lp.status);
}
const payBadge = (lp, id) => (payState(lp) === "test" ? <StatusBadge color="gray">TEST</StatusBadge> : badge(PAY, payState(lp), `pay-status-${id}`));

function Row({ o, onRefresh, busy }) {
  const lp = o.last_purchase, inv = o.invoice;
  return (
    <tr className="border-b border-slate-100 align-top" data-testid={`payments-row-${o.id}`}>
      <td className="py-2.5 px-4 font-medium text-slate-800">{o.nome}</td>
      <td className="py-2.5 px-4">{badge(Object.fromEntries(Object.entries(TIPO_COLOR).map(([k, c]) => [k, [c, k]])), o.tipo)}</td>
      <td className="py-2.5 px-4 text-right font-semibold" data-testid={`payments-balance-${o.id}`}>{o.balance}</td>
      <td className="py-2.5 px-4 text-slate-600">{lp ? `${d(lp.date)} · ${lp.credits_total} cr` : "—"}</td>
      <td className="py-2.5 px-4 text-right text-slate-600">{lp ? eur(lp.amount_gross) : "—"}</td>
      <td className="py-2.5 px-4">{payBadge(lp, o.id)}</td>
      <td className="py-2.5 px-4">{inv ? <div className="space-y-0.5">{badge(DOC, inv.is_test ? "simulato_test" : inv.stato_documento, `doc-status-${o.id}`)}{inv.numero && <div className="text-xs text-slate-500">n. {inv.numero}</div>}</div> : "—"}</td>
      <td className="py-2.5 px-4">{inv ? badge(SDI, inv.is_test ? "simulato_test" : inv.stato_sdi, `sdi-status-${o.id}`) : "—"}</td>
      <td className="py-2.5 px-4 text-right"><Button size="sm" variant="outline" disabled={busy} onClick={() => onRefresh(o.id)} data-testid={`payments-refresh-${o.id}`}><RefreshCw className="w-3.5 h-3.5" /></Button></td>
    </tr>
  );
}

function Card({ o, onRefresh, busy }) {
  const lp = o.last_purchase, inv = o.invoice;
  return (
    <div className="p-4 border-b border-slate-100" data-testid={`payments-card-${o.id}`}>
      <div className="flex items-start justify-between gap-2"><div className="font-semibold text-slate-900 break-words">{o.nome}</div><StatusBadge color={TIPO_COLOR[o.tipo] || "gray"}>{o.tipo}</StatusBadge></div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm">
        <span className="text-slate-500">Saldo</span><span className="text-right font-semibold">{o.balance} crediti</span>
        <span className="text-slate-500">Ultimo acquisto</span><span className="text-right">{lp ? `${d(lp.date)} · ${eur(lp.amount_gross)}` : "—"}</span>
        <span className="text-slate-500">Pagamento</span><span className="text-right">{payBadge(lp, `m-${o.id}`)}</span>
        <span className="text-slate-500">Fattura</span><span className="text-right">{inv ? badge(DOC, inv.is_test ? "simulato_test" : inv.stato_documento) : "—"}</span>
        <span className="text-slate-500">SDI</span><span className="text-right">{inv ? badge(SDI, inv.is_test ? "simulato_test" : inv.stato_sdi) : "—"}</span>
      </div>
      <Button size="sm" variant="outline" className="mt-3 w-full" disabled={busy} onClick={() => onRefresh(o.id)} data-testid={`payments-refresh-m-${o.id}`}><RefreshCw className="w-3.5 h-3.5 mr-1.5" />Aggiorna stato</Button>
    </div>
  );
}

export function LegacySubscriptions({ subs }) {
  const [open, setOpen] = useState(false);
  const rows = subs.filter((s) => s.stripe_subscription_id || s.stripe_customer_id);
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden mt-4" data-testid="legacy-subscriptions">
      <button type="button" onClick={() => setOpen((x) => !x)} className="w-full flex items-center justify-between px-5 py-3 text-sm font-semibold text-slate-700" data-testid="legacy-subscriptions-toggle">
        Storico abbonamenti (vecchio modello) · {rows.length}<ChevronDown className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (rows.length === 0 ? <p className="px-5 pb-4 text-sm text-slate-500">Nessun abbonamento Stripe registrato.</p> : (
        <div className="overflow-x-auto border-t border-slate-100"><table className="w-full text-xs">
          <thead><tr className="text-left text-slate-500"><th className="py-2 px-4">Organizzazione</th><th className="py-2 px-4">Stato</th><th className="py-2 px-4">Ciclo</th><th className="py-2 px-4">Stripe Customer</th><th className="py-2 px-4">Stripe Subscription</th></tr></thead>
          <tbody>{rows.map((s) => <tr key={s.id} className="border-t border-slate-100"><td className="py-2 px-4">{s.nome}</td><td className="py-2 px-4">{s.status}</td><td className="py-2 px-4">{s.billing_cycle || "—"}</td><td className="py-2 px-4 font-mono">{s.stripe_customer_id || "—"}</td><td className="py-2 px-4 font-mono">{s.stripe_subscription_id || "—"}</td></tr>)}</tbody>
        </table></div>
      ))}
    </div>
  );
}

export default function PaymentsCredits() {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/platform/payments").then(({ data }) => setRows(data)).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load]);
  const refresh = async (orgId) => {
    setBusy(true);
    try {
      const { data } = await api.post("/platform/payments/refresh", { org_id: orgId || null });
      toast[data.errors.length ? "warning" : "success"](`Stato aggiornato · Stripe ${data.stripe_checked} · Fatture in Cloud ${data.fic_checked}`, data.errors.length ? { description: data.errors.slice(0, 4).join("\n") } : undefined);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden mt-8" data-testid="platform-payments">
      <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2">
        <div><div className="font-semibold text-sm text-slate-800">Pagamenti e Crediti</div><div className="text-xs text-slate-400">"Aggiorna stato" legge Stripe e Fatture in Cloud in sola lettura: non crea pagamenti, fatture, accrediti o invii SDI.</div></div>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => refresh(null)} data-testid="payments-refresh-all"><RefreshCw className={`w-4 h-4 mr-1.5 ${busy ? "animate-spin" : ""}`} />Aggiorna tutte</Button>
      </div>
      {rows === null ? <p className="p-5 text-sm text-slate-400">Caricamento...</p> : (
        <>
          <div className="md:hidden" data-testid="payments-mobile">{rows.map((o) => <Card key={o.id} o={o} onRefresh={refresh} busy={busy} />)}</div>
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm" data-testid="payments-table">
              <thead><tr className="border-b border-slate-200 text-left text-slate-500">
                {["Organizzazione", "Tipo"].map((h) => <th key={h} className="py-2.5 px-4 font-semibold">{h}</th>)}
                <th className="py-2.5 px-4 font-semibold text-right">Saldo crediti</th><th className="py-2.5 px-4 font-semibold">Ultimo acquisto</th>
                <th className="py-2.5 px-4 font-semibold text-right">Importo</th><th className="py-2.5 px-4 font-semibold">Pagamento Stripe</th>
                <th className="py-2.5 px-4 font-semibold">Fattura FIC</th><th className="py-2.5 px-4 font-semibold">Stato SDI</th><th className="py-2.5 px-4" />
              </tr></thead>
              <tbody>{rows.length === 0 ? <tr><td colSpan={9} className="py-8 text-center text-slate-400">Nessuna organizzazione.</td></tr> : rows.map((o) => <Row key={o.id} o={o} onRefresh={refresh} busy={busy} />)}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
