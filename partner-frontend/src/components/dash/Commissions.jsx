import { eur } from "@/lib/api";

const ST = { maturata: ["Maturata", "bg-sky-50 text-sky-700"], liquidabile: ["Liquidabile", "bg-tiffany-light text-tiffany-fg"], in_liquidazione: ["In liquidazione", "bg-orange-50 text-orange-700"], pagata: ["Pagata", "bg-emerald-50 text-emerald-700"], stornata: ["Stornata", "bg-slate-100 text-slate-500"] };
const KIND = { prima_sottoscrizione: "Prima sottoscrizione", rinnovo: "Rinnovo", upgrade: "Upgrade" };
const dt = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");

export default function Commissions({ d }) {
  return (
    <div className="space-y-5">
      {!d.partner.iban && <p className="rounded-2xl bg-orange-50 text-orange-800 text-sm p-4" data-testid="iban-missing">Per ricevere le liquidazioni inserisci il tuo IBAN nella sezione Profilo.</p>}
      <div className="rounded-3xl border border-slate-200 bg-white overflow-hidden" data-testid="commissions-list">
        <h3 className="font-bold p-5 border-b border-slate-100">Commissioni</h3>
        {!d.commissions.length ? <p className="p-5 text-sm text-slate-500" data-testid="commissions-empty">Nessuna commissione maturata.</p> : d.commissions.map((c) => (
          <div key={c.id} className="px-5 py-3 border-b border-slate-100 last:border-0 flex items-center justify-between gap-3 text-sm">
            <div className="min-w-0"><div className="font-medium truncate">{c.org_name}</div><div className="text-xs text-slate-500">{dt(c.paid_at)} · {KIND[c.kind] || "Pagamento"} · {(c.plan || "").toUpperCase()} · {c.commission_pct}% di {eur(c.base_cents)}{c.refunded_cents ? " · rettificata per rimborso" : ""}</div></div>
            <div className="text-right shrink-0"><div className="font-semibold tabular-nums">{eur(c.commission_net_cents)}</div><span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${ST[c.status]?.[1]}`}>{ST[c.status]?.[0]}</span></div>
          </div>))}
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white overflow-hidden" data-testid="payouts-list">
        <h3 className="font-bold p-5 border-b border-slate-100">Storico liquidazioni</h3>
        {!d.payouts.length ? <p className="p-5 text-sm text-slate-500" data-testid="payouts-empty">Nessuna liquidazione. Liquidazione {d.settings.payout_frequency} delle commissioni con almeno {d.settings.hold_days} giorni dal pagamento.</p> : d.payouts.map((p) => (
          <div key={p.id} className="px-5 py-3 border-b border-slate-100 last:border-0 flex items-center justify-between text-sm"><span>{p.period} · {p.commission_ids.length} commissioni</span><span className="text-right"><b>{eur(p.amount_cents)}</b><div className="text-xs text-slate-500">{p.status === "pagata" ? `Pagata il ${dt(p.paid_at)}` : p.status === "annullata" ? "Annullata" : "In preparazione"}</div></span></div>))}
      </div>
    </div>
  );
}
