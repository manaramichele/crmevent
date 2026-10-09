import { useEffect, useState } from "react";
import api, { API, formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import { eur, dt, C_ST, KIND, Card } from "@/components/partners/shared";

function Payouts({ payouts, onChange }) {
  const paid = async (p) => {
    const reference = window.prompt("Riferimento del bonifico (facoltativo):");
    if (reference === null) return;
    try { await api.post(`/platform/partner-payouts/${p.id}/paid`, { reference }); toast.success("Liquidazione segnata come pagata"); onChange(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const cancel = async (p) => { if (!window.confirm("Annullare la liquidazione? Le commissioni tornano liquidabili.")) return; try { await api.post(`/platform/partner-payouts/${p.id}/cancel`); onChange(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  return (
    <Card title="Storico liquidazioni" testid="partner-payouts">
      {!payouts.length ? <p className="p-4 text-sm text-slate-500">Nessuna liquidazione.</p> : payouts.map((p) => (
        <div key={p.id} className="px-4 py-3 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center gap-2 text-sm" data-testid={`payout-${p.id}`}>
          <div className="flex-1"><b>{p.partner_name}</b> · {p.period} · {eur(p.amount_cents)} · {p.commission_ids.length} commissioni<div className="text-xs text-slate-500">IBAN {p.iban_snapshot} · creata il {dt(p.created_at)}{p.paid_at ? ` · pagata il ${dt(p.paid_at)}` : ""}{p.reference ? ` · rif. ${p.reference}` : ""}</div></div>
          <StatusBadge color={p.status === "pagata" ? "green" : p.status === "annullata" ? "gray" : "orange"}>{p.status.replace("_", " ")}</StatusBadge>
          {p.status === "in_preparazione" && <><Button size="sm" onClick={() => paid(p)} className="bg-[#0ABAB5] text-slate-900" data-testid={`payout-paid-${p.id}`}>Segna pagata</Button><Button size="sm" variant="outline" onClick={() => cancel(p)} data-testid={`payout-cancel-${p.id}`}>Annulla</Button></>}
        </div>))}
    </Card>
  );
}

export default function PartnerCommissions() {
  const [rows, setRows] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [st, setSt] = useState("");
  const load = () => Promise.all([api.get("/platform/partner-commissions", { params: { status: st || undefined } }), api.get("/platform/partner-payouts")])
    .then(([a, b]) => { setRows(a.data); setPayouts(b.data); }).catch(() => setRows([]));
  useEffect(() => { load(); }, [st]); // eslint-disable-line react-hooks/exhaustive-deps
  const sum = (s) => (rows || []).filter((c) => c.status === s).reduce((a, c) => a + (c.commission_net_cents || 0), 0);
  const liquidabili = [...new Set((rows || []).filter((c) => c.status === "liquidabile").map((c) => c.partner_id))];
  const createPayout = async (pid) => { try { const { data } = await api.post("/platform/partner-payouts", { partner_id: pid }); toast.success(`Liquidazione ${eur(data.amount_cents)} creata`); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const adjust = async (c) => {
    const v = window.prompt("Rettifica in euro (es. -5,00 oppure 3,50):"); if (!v) return;
    const note = window.prompt("Motivo della rettifica:"); if (!note) return;
    try { await api.post(`/platform/partner-commissions/${c.id}/adjust`, { amount_cents: Math.round(parseFloat(v.replace(",", ".")) * 100), note }); toast.success("Rettifica registrata"); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const csv = `${API}/platform/partner-commissions.csv${st ? `?status=${st}` : ""}`;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {["maturata", "liquidabile", "in_liquidazione", "pagata"].map((s) => <div key={s} className="bg-white border border-slate-200 rounded-xl p-3" data-testid={`com-total-${s}`}><div className="text-xs text-slate-500">{C_ST[s][1]}</div><div className="text-xl font-bold">{eur(sum(s))}</div></div>)}
      </div>
      {liquidabili.length > 0 && <Card title="Pronte per la liquidazione trimestrale" testid="payout-ready">{liquidabili.map((pid) => { const c = rows.find((x) => x.partner_id === pid); return (
        <div key={pid} className="px-4 py-2 border-t border-slate-100 flex items-center justify-between text-sm"><span>{c.partner_name}</span><Button size="sm" onClick={() => createPayout(pid)} className="bg-[#0ABAB5] text-slate-900" data-testid={`payout-create-${pid}`}>Crea liquidazione</Button></div>); })}</Card>}
      <Card title={`Registro commissioni (${rows?.length ?? "…"})`} testid="partner-commissions" right={
        <div className="flex gap-2 font-normal"><select value={st} onChange={(e) => setSt(e.target.value)} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="com-status-filter"><option value="">Tutti gli stati</option>{Object.entries(C_ST).map(([k, [, l]]) => <option key={k} value={k}>{l}</option>)}</select>
          <a href={csv} className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md border border-slate-200 text-sm hover:bg-slate-50" data-testid="com-export-csv"><Download className="w-4 h-4" />Esporta CSV/Excel</a></div>}>
        {rows && !rows.length && <p className="p-4 text-sm text-slate-500">Nessuna commissione.</p>}
        {(rows || []).map((c) => (
          <div key={c.id} className="px-4 py-3 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center gap-2 text-sm" data-testid={`commission-row-${c.id}`}>
            <div className="flex-1 min-w-0"><b>{c.partner_name}</b> · {c.org_name} · {dt(c.paid_at)} · {KIND[c.kind] || c.kind} · {(c.plan || "").toUpperCase()}
              <div className="text-xs text-slate-500">Pagamento {c.stripe_invoice_id} · base {eur(c.base_cents)} × {c.commission_pct}% = {eur(c.commission_cents)} · netta <b>{eur(c.commission_net_cents)}</b>{c.refunded_cents ? ` · rimborsati ${eur(c.refunded_cents)}` : ""}{c.recupero_cents ? ` · da recuperare ${eur(c.recupero_cents)}` : ""} · regime CRMEvent {c.crmevent_tax_regime}</div>
              {(c.adjustments || []).length > 1 && <div className="text-xs text-slate-400 mt-0.5">Storico: {c.adjustments.map((a) => `${dt(a.at)} ${a.type} ${eur(a.amount_cents)}`).join(" · ")}</div>}</div>
            <StatusBadge color={C_ST[c.status]?.[0]}>{C_ST[c.status]?.[1]}</StatusBadge>
            {["maturata", "liquidabile"].includes(c.status) && <Button size="sm" variant="outline" onClick={() => adjust(c)} data-testid={`commission-adjust-${c.id}`}>Rettifica</Button>}
          </div>))}
      </Card>
      <Payouts payouts={payouts} onChange={load} />
    </div>
  );
}
