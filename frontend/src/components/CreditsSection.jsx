import { useEffect, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Coins, TrendingUp, TrendingDown, AlertTriangle, Zap, CheckCircle2, Receipt, ChevronDown } from "lucide-react";

const VAT_RATE = 22;
const REASON = {
  signup_bonus: "Bonus registrazione", manual_adjustment: "Rettifica manuale",
  ai_analysis: "Assistente IA / analisi", ai_content: "Generazione contenuti",
  ai_briefing: "Generazione briefing", image_generation: "Generazione immagini",
  automation_run: "Automazione", newsletter_email: "Newsletter / email",
  google_calendar: "Google Calendar", whatsapp_send: "WhatsApp", sms_send: "SMS", purchase: "Ricarica crediti",
};
const PURCHASE_STATUS = {
  pending: ["In attesa", "text-amber-700 bg-amber-50 border-amber-200"],
  paid: ["Pagato", "text-emerald-700 bg-emerald-50 border-emerald-200"],
  failed: ["Fallito", "text-red-700 bg-red-50 border-red-200"],
  canceled: ["Annullato", "text-slate-600 bg-slate-100 border-slate-200"],
};
const fmtDate = (s) => (s ? new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const eur = (n) => `€ ${Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const num = (n) => Number(n || 0).toLocaleString("it-IT");

function RechargeDialog({ open, onClose }) {
  const [packs, setPacks] = useState([]);
  const [busy, setBusy] = useState(null);
  useEffect(() => {
    if (!open) return;
    api.get("/credits/packages").then(({ data }) => setPacks(data.packages || [])).catch(() => {});
  }, [open]);

  const buy = async (p) => {
    setBusy(p.id);
    try {
      const { data } = await api.post("/credits/checkout", { package_id: p.id, origin_url: window.location.origin });
      window.location.assign(data.checkout_url);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      setBusy(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl" data-testid="recharge-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Coins className="w-5 h-5 text-tiffany-active" />Ricarica crediti</DialogTitle>
          <DialogDescription>Scegli un taglio. Prezzi IVA esclusa · IVA {VAT_RATE}% applicata al checkout. I crediti non scadono.</DialogDescription>
        </DialogHeader>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {packs.map((p) => {
            const net = Number(p.price) || 0;
            const vat = Math.round(net * VAT_RATE) / 100;
            const gross = Math.round((net + vat) * 100) / 100;
            return (
              <div key={p.id} data-testid={`recharge-pack-${p.id}`} className={`relative rounded-2xl border p-4 flex flex-col ${p.highlight ? "border-tiffany ring-2 ring-tiffany bg-tiffany-light/30" : "border-slate-200 bg-white"}`}>
                {p.badge && <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-tiffany text-slate-900 px-2.5 py-0.5 text-[11px] font-bold shadow">{p.badge}</span>}
                <div className="font-display text-2xl font-bold text-slate-900">{num(p.credits_total)} <span className="text-sm font-semibold text-slate-400">crediti</span></div>
                {p.credits_bonus > 0 && <div className="text-xs font-semibold text-tiffany-fg mt-0.5">{num(p.credits_base)} + {num(p.credits_bonus)} bonus{p.bonus_pct ? ` (+${p.bonus_pct}%)` : ""}</div>}
                <div className="mt-3 space-y-0.5 text-sm">
                  <div className="flex justify-between text-slate-500"><span>Imponibile</span><span data-testid={`recharge-net-${p.id}`}>{eur(net)}</span></div>
                  <div className="flex justify-between text-slate-500"><span>IVA {VAT_RATE}%</span><span data-testid={`recharge-vat-${p.id}`}>{eur(vat)}</span></div>
                  <div className="flex justify-between font-bold text-slate-900 pt-1 border-t border-slate-100"><span>Totale</span><span data-testid={`recharge-gross-${p.id}`}>{eur(gross)}</span></div>
                </div>
                <Button disabled={busy === p.id} onClick={() => buy(p)} data-testid={`recharge-buy-${p.id}`} className="mt-3 w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">
                  {busy === p.id ? "Reindirizzo…" : "Procedi al pagamento"}
                </Button>
              </div>
            );
          })}
        </div>
        <div className="mt-2 flex items-center justify-between flex-wrap gap-2 text-sm">
          <span className="text-slate-500">Ti servono più crediti? <a href="/#demo" className="text-tiffany-active underline">Contattaci</a></span>
          <span className="inline-flex items-center gap-1.5 text-slate-400"><Zap className="w-4 h-4" />Ricarica automatica — prossimamente</span>
        </div>
        <p className="text-xs text-slate-400">Pagamento sicuro tramite Stripe (modalità test). I crediti vengono accreditati dopo la conferma del pagamento.</p>
      </DialogContent>
    </Dialog>
  );
}

function PurchasesHistory() {
  const [rows, setRows] = useState(null);
  const [show, setShow] = useState(false);
  useEffect(() => {
    api.get("/credits/purchases").then(({ data }) => setRows(data.purchases || [])).catch(() => setRows([]));
  }, []);
  if (!rows || rows.length === 0) return null;
  return (
    <div className="mt-5" data-testid="purchases-section">
      <button onClick={() => setShow((v) => !v)} data-testid="purchases-toggle" className="flex items-center gap-1.5 text-sm font-semibold text-slate-700 hover:text-slate-900">
        <Receipt className="w-4 h-4" />Storico acquisti ({rows.length})
        <ChevronDown className={`w-4 h-4 transition-transform ${show ? "rotate-180" : ""}`} />
      </button>
      {show && (
        <div className="overflow-x-auto mt-2"><table className="w-full text-sm" data-testid="purchases-table">
          <thead><tr className="text-left text-xs uppercase tracking-wider text-slate-400 border-b border-slate-100">
            <th className="py-2 pr-3">Data</th><th className="py-2 pr-3">Crediti</th><th className="py-2 pr-3 text-right">Imponibile</th>
            <th className="py-2 pr-3 text-right">IVA</th><th className="py-2 pr-3 text-right">Totale</th><th className="py-2 pr-3">Stato</th><th className="py-2">Documento</th></tr></thead>
          <tbody>
            {rows.map((p) => {
              const [label, cls] = PURCHASE_STATUS[p.status] || [p.status, "text-slate-600 bg-slate-100 border-slate-200"];
              return (
                <tr key={p.id} className="border-b border-slate-50" data-testid={`purchase-row-${p.id}`}>
                  <td className="py-2 pr-3 text-slate-500 whitespace-nowrap">{fmtDate(p.created_at)}</td>
                  <td className="py-2 pr-3 text-slate-700">{num(p.credits_total)}{p.credits_bonus > 0 ? <span className="text-tiffany-fg"> ({num(p.credits_base)}+{num(p.credits_bonus)})</span> : ""}</td>
                  <td className="py-2 pr-3 text-right text-slate-600">{eur(p.amount_net)}</td>
                  <td className="py-2 pr-3 text-right text-slate-600">{eur(p.amount_vat)}</td>
                  <td className="py-2 pr-3 text-right font-semibold text-slate-800">{eur(p.amount_gross)}</td>
                  <td className="py-2 pr-3"><span className={`inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold ${cls}`}>{label}</span></td>
                  <td className="py-2 text-slate-400">{p.invoice_id ? "Fattura disponibile" : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table></div>
      )}
    </div>
  );
}

export default function CreditsSection() {
  const [bal, setBal] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [open, setOpen] = useState(false);
  const [success, setSuccess] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const LIMIT = 10;

  const load = useCallback(async (sk = 0) => {
    const [b, l] = await Promise.all([
      api.get("/credits/balance"),
      api.get(`/credits/ledger?limit=${LIMIT}&skip=${sk}`),
    ]);
    setBal(b.data); setLedger(l.data.items || []); setTotal(l.data.total || 0); setSkip(sk);
  }, []);

  useEffect(() => { load(0).catch((e) => toast.error(formatApiError(e.response?.data?.detail))); }, [load]);

  // Ritorno dal Checkout Stripe: verifica server-side ed eventuale accredito (idempotente).
  useEffect(() => {
    const status = searchParams.get("credits_checkout");
    const sid = searchParams.get("session_id");
    if (!status) return;
    const clean = () => { const sp = new URLSearchParams(searchParams); sp.delete("credits_checkout"); sp.delete("session_id"); setSearchParams(sp, { replace: true }); };
    if (status === "success" && sid) {
      api.get(`/credits/checkout-confirmation?session_id=${sid}`).then(({ data }) => {
        if (data.paid) {
          setSuccess({ credits: data.credits_total, base: data.credits_base, bonus: data.credits_bonus, balance: data.balance });
          toast.success(`Pagamento ricevuto · +${num(data.credits_total)} crediti`);
          load(0);
        } else {
          toast.info("Pagamento in elaborazione. I crediti compariranno a conferma.");
        }
      }).catch((e) => toast.error(formatApiError(e.response?.data?.detail))).finally(clean);
    } else if (status === "cancel") {
      toast.info("Pagamento annullato. Nessun addebito effettuato.");
      clean();
    }
  }, [searchParams, setSearchParams, load]);

  if (!bal) return null;
  const low = bal.low_balance;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 mb-4" data-testid="credits-section">
      <div className="flex items-center gap-2 mb-4"><Coins className="w-4 h-4 text-tiffany-active" /><h2 className="font-semibold text-slate-800">Crediti CRMEvent</h2></div>

      {success && (
        <div className="mb-4 flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4" data-testid="purchase-success-banner">
          <CheckCircle2 className="w-5 h-5 mt-0.5 shrink-0 text-emerald-600" />
          <div className="text-sm text-emerald-800">
            <div className="font-semibold">Pagamento ricevuto</div>
            <div>+{num(success.credits)} crediti{success.bonus > 0 ? ` (${num(success.base)} + ${num(success.bonus)} bonus)` : ""} · Nuovo saldo: <b>{num(success.balance)} crediti</b></div>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-xs text-slate-400 uppercase tracking-wide font-semibold">Saldo disponibile</div>
          <div className="font-display text-4xl font-bold text-slate-900" data-testid="credits-balance">{num(bal.balance)} <span className="text-base font-semibold text-slate-400">crediti</span></div>
          <div className="text-xs text-slate-500 mt-1">I crediti non scadono · Soglia saldo basso: {bal.low_balance_threshold}</div>
        </div>
        <Button onClick={() => setOpen(true)} data-testid="recharge-open-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Coins className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>
      </div>

      {low && (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" data-testid="low-balance-banner">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />Saldo crediti basso. Ricarica per continuare a usare i servizi avanzati quando saranno attivi.
        </div>
      )}

      <div className="mt-5">
        <div className="text-sm font-semibold text-slate-700 mb-2">Storico movimenti</div>
        {ledger.length === 0 ? (
          <p className="text-sm text-slate-400" data-testid="ledger-empty">Nessun movimento.</p>
        ) : (
          <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="credits-ledger">
            <thead><tr className="text-left text-xs uppercase tracking-wider text-slate-400 border-b border-slate-100">
              <th className="py-2 pr-3">Data</th><th className="py-2 pr-3">Causale / Servizio</th><th className="py-2 pr-3">Evento</th>
              <th className="py-2 pr-3 text-right">Crediti</th><th className="py-2 text-right">Saldo</th></tr></thead>
            <tbody>
              {ledger.map((m) => {
                const credit = m.amount > 0;
                return (
                  <tr key={m.id} className="border-b border-slate-50" data-testid={`ledger-row-${m.id}`}>
                    <td className="py-2 pr-3 text-slate-500 whitespace-nowrap">{fmtDate(m.created_at)}</td>
                    <td className="py-2 pr-3 text-slate-700">{REASON[m.reason_code] || m.reason_code}{m.note ? <span className="text-slate-400"> · {m.note}</span> : ""}</td>
                    <td className="py-2 pr-3 text-slate-400">{m.event_id ? m.event_id.slice(0, 8) : "—"}</td>
                    <td className={`py-2 pr-3 text-right font-semibold inline-flex items-center gap-1 justify-end w-full ${credit ? "text-emerald-600" : "text-slate-800"}`}>
                      {credit ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}{credit ? "+" : ""}{m.amount}
                    </td>
                    <td className="py-2 text-right text-slate-500">{m.balance_after ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table></div>
        )}
        {total > LIMIT && (
          <div className="flex items-center justify-between mt-3 text-sm">
            <span className="text-slate-400">{skip + 1}–{Math.min(skip + LIMIT, total)} di {total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={skip === 0} onClick={() => load(Math.max(0, skip - LIMIT))} data-testid="ledger-prev">Precedenti</Button>
              <Button size="sm" variant="outline" disabled={skip + LIMIT >= total} onClick={() => load(skip + LIMIT)} data-testid="ledger-next">Successivi</Button>
            </div>
          </div>
        )}
      </div>

      <PurchasesHistory />

      <RechargeDialog open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
