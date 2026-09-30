import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { BadgeEuro, History, RefreshCw, Save, DatabaseZap, AlertTriangle } from "lucide-react";

const CONFIRM_MSG = "Il nuovo prezzo verrà applicato solamente ai nuovi acquisti. Gli acquisti già effettuati manterranno il prezzo storico.\n\nConfermi la modifica?";
const fmtEUR = (n) => (n == null ? "—" : `${Number(n).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);
const fmtDate = (s) => (s ? new Date(s).toLocaleString("it-IT") : "—");

export default function PricingAdmin() {
  const [plans, setPlans] = useState([]);
  const [history, setHistory] = useState([]);
  const [vat, setVat] = useState(22);
  const [edits, setEdits] = useState({});
  const [busy, setBusy] = useState(false);
  const [migrating, setMigrating] = useState(false);

  const load = () => Promise.allSettled([api.get("/platform/pricing"), api.get("/platform/pricing/history")])
    .then(([p, h]) => {
      if (p.status === "fulfilled") { setPlans(p.value.data.plans); setVat(p.value.data.vat_rate); }
      if (h.status === "fulfilled") setHistory(h.value.data);
      const f = [p, h].find((r) => r.status === "rejected");
      if (f) toast.error(formatApiError(f.reason?.response?.data?.detail));
    });
  useEffect(() => { load(); }, []);

  const key = (p) => `${p.plan}_${p.fascia}`;
  const save = async (p) => {
    const raw = edits[key(p)];
    const net = raw === undefined ? p.net : Number(raw);
    if (!net || net <= 0) return toast.error("Inserisci un prezzo netto valido");
    if (net === p.net) return toast.info("Nessuna variazione");
    if (!window.confirm(CONFIRM_MSG)) return;
    setBusy(true);
    try {
      await api.put(`/platform/pricing/${p.plan}/${p.fascia}`, { net });
      toast.success(`Prezzo aggiornato: ${p.plan_label} · ${p.tier_label}`);
      setEdits((e) => { const n = { ...e }; delete n[key(p)]; return n; });
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const migrate = async () => {
    if (!window.confirm("Eseguo la migrazione FASE 2 (seed listino + account_plan + entitlement eventi). Operazione non distruttiva e idempotente. Procedo?")) return;
    setMigrating(true);
    try {
      const { data } = await api.post("/platform/phase2/migrate");
      toast.success(`Migrazione OK · listino ${data.pricing_plans} · org agg. ${data.org_account_plan_updated}/${data.org_total} · eventi ${data.events_backfilled}/${data.events_total}`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setMigrating(false); }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 lg:px-8 py-8" data-testid="pricing-admin-page">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><BadgeEuro className="w-5 h-5" /></div>
          <div>
            <h1 className="font-display text-2xl font-bold text-slate-900">Piani e prezzi</h1>
            <p className="text-sm text-slate-500">Listino dinamico STARTER / PROFESSIONAL / PREMIUM — prezzo per evento, IVA {vat}% esclusa.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} data-testid="pricing-refresh-btn"><RefreshCw className="w-4 h-4 mr-2" />Aggiorna</Button>
          <Button onClick={migrate} disabled={migrating} data-testid="pricing-migrate-btn" className="bg-slate-900 hover:bg-slate-800 text-white"><DatabaseZap className="w-4 h-4 mr-2" />{migrating ? "Migrazione..." : "Esegui migrazione FASE 2"}</Button>
        </div>
      </div>

      <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-6" data-testid="pricing-stripe-note">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
        Sincronizzazione Stripe NON ancora attiva: le modifiche aggiornano solo il listino nel database. La creazione del nuovo Price Stripe sarà abilitata allo step Stripe.
      </div>

      {/* Listino */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden mb-8">
        <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Listino attuale ({plans.length} prezzi)</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs">
              <tr>
                <th className="text-left px-4 py-2.5">Piano</th>
                <th className="text-left px-4 py-2.5">Fascia eventi</th>
                <th className="text-right px-4 py-2.5">Netto (€)</th>
                <th className="text-right px-4 py-2.5">IVA {vat}%</th>
                <th className="text-right px-4 py-2.5">Totale IVA incl.</th>
                <th className="text-center px-4 py-2.5">Stato</th>
                <th className="text-left px-4 py-2.5">Ultima modifica</th>
                <th className="text-left px-4 py-2.5">Stripe Price</th>
                <th className="text-right px-4 py-2.5">Azione</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => {
                const k = key(p);
                const netVal = edits[k] === undefined ? p.net : edits[k];
                const ivaAmt = (Number(netVal || 0) * vat / 100);
                const gross = Number(netVal || 0) + ivaAmt;
                return (
                  <tr key={k} className="border-t border-slate-100" data-testid={`price-row-${k}`}>
                    <td className="px-4 py-3 font-semibold text-slate-800">{p.plan_label}</td>
                    <td className="px-4 py-3 text-slate-600">{p.tier_label}</td>
                    <td className="px-4 py-3 text-right">
                      <Input type="number" step="0.01" value={netVal} onChange={(e) => setEdits((x) => ({ ...x, [k]: e.target.value }))}
                        className="w-24 h-9 text-right ml-auto" data-testid={`price-input-${k}`} />
                    </td>
                    <td className="px-4 py-3 text-right text-slate-500">{fmtEUR(ivaAmt)}</td>
                    <td className="px-4 py-3 text-right font-semibold text-slate-900">{fmtEUR(gross)}</td>
                    <td className="px-4 py-3 text-center"><span className="inline-block px-2 py-0.5 rounded-full text-xs bg-emerald-50 text-emerald-700">{p.status}</span></td>
                    <td className="px-4 py-3 text-slate-500 text-xs">{fmtDate(p.updated_at)}</td>
                    <td className="px-4 py-3 text-slate-400 text-xs font-mono">{p.stripe_price_id || "—"}</td>
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" disabled={busy} onClick={() => save(p)} data-testid={`price-save-${k}`} className="bg-tiffany hover:bg-tiffany-hover text-slate-900"><Save className="w-4 h-4 mr-1" />Salva</Button>
                    </td>
                  </tr>
                );
              })}
              {plans.length === 0 && <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-400">Nessun prezzo. Esegui la migrazione per popolare il listino.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Storico */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid="pricing-history">
        <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800 flex items-center gap-2"><History className="w-4 h-4 text-slate-400" />Storico variazioni prezzo ({history.length})</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs">
              <tr>
                <th className="text-left px-4 py-2.5">Data/ora</th>
                <th className="text-left px-4 py-2.5">Piano</th>
                <th className="text-left px-4 py-2.5">Fascia</th>
                <th className="text-right px-4 py-2.5">Vecchio</th>
                <th className="text-right px-4 py-2.5">Nuovo</th>
                <th className="text-left px-4 py-2.5">Super Admin</th>
                <th className="text-left px-4 py-2.5">Stripe Price (old → new)</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} className="border-t border-slate-100" data-testid="history-row">
                  <td className="px-4 py-3 text-slate-500 text-xs">{fmtDate(h.created_at)}</td>
                  <td className="px-4 py-3">{h.plan}</td>
                  <td className="px-4 py-3 text-slate-600">{h.fascia}</td>
                  <td className="px-4 py-3 text-right">{fmtEUR(h.old_net)}</td>
                  <td className="px-4 py-3 text-right font-semibold">{fmtEUR(h.new_net)}</td>
                  <td className="px-4 py-3 text-slate-600 text-xs">{h.changed_by_email || "—"}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs font-mono">{(h.old_stripe_price_id || "—")} → {(h.new_stripe_price_id || "—")}</td>
                </tr>
              ))}
              {history.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">Nessuna variazione registrata.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
