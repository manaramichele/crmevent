import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Handshake, Settings2, Check, Ban, Wallet } from "lucide-react";

const eur = (c) => ((c || 0) / 100).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
const ST = { pending: ["orange", "In attesa"], approved: ["green", "Approvato"], rejected: ["red", "Rifiutato"], suspended: ["gray", "Sospeso"] };
const CST = { maturata: ["tiffany", "Maturata"], pagata: ["green", "Pagata"], stornata: ["gray", "Stornata"] };
const TIPO = { privato: "Privato", professionista: "Professionista", azienda: "Azienda" };

function SettingsCard() {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/platform/partner-settings").then(({ data }) => setS(data)).catch(() => {}); }, []);
  if (!s) return null;
  const save = async () => {
    setBusy(true);
    try { const { data } = await api.put("/platform/partner-settings", { commission_pct: Number(s.commission_pct), duration_months: Number(s.duration_months), crmevent_tax_regime: s.crmevent_tax_regime }); setS(data); toast.success("Impostazioni partner salvate"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-5" data-testid="partner-settings">
      <div className="flex items-center gap-2 font-semibold text-slate-900 mb-3"><Settings2 className="w-4 h-4 text-[#0ABAB5]" />Impostazioni programma partner</div>
      <div className="grid sm:grid-cols-3 gap-3">
        <label className="text-sm">Commissione (%)<Input type="number" min="0" max="100" step="0.5" value={s.commission_pct} onChange={(e) => setS({ ...s, commission_pct: e.target.value })} data-testid="partner-settings-pct" /></label>
        <label className="text-sm">Durata commissione (mesi)<Input type="number" min="1" max="120" value={s.duration_months} onChange={(e) => setS({ ...s, duration_months: e.target.value })} data-testid="partner-settings-months" /></label>
        <label className="text-sm">Regime fiscale CRMEvent
          <select value={s.crmevent_tax_regime} onChange={(e) => setS({ ...s, crmevent_tax_regime: e.target.value })} data-testid="partner-settings-regime" className="mt-0 w-full h-10 rounded-md border border-slate-200 bg-white px-3 text-sm">
            <option value="forfettario">Forfettario</option><option value="ordinario">Ordinario</option>
          </select></label>
      </div>
      <p className="text-xs text-slate-500 mt-2">La commissione si calcola sull'importo dell'abbonamento effettivamente incassato, imposte escluse, al netto dei rimborsi. Marketplace e crediti esclusi. Il regime di CRMEvent è indipendente da quello dei partner e viene registrato su ogni commissione.</p>
      <Button onClick={save} disabled={busy} className="mt-3 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="partner-settings-save">Salva impostazioni</Button>
    </div>
  );
}

export default function PlatformPartners() {
  const [rows, setRows] = useState(null);
  const [coms, setComs] = useState([]);
  const load = () => Promise.all([api.get("/platform/partners"), api.get("/platform/partner-commissions")])
    .then(([a, b]) => { setRows(a.data); setComs(b.data); }).catch((e) => { setRows([]); toast.error(formatApiError(e.response?.data?.detail)); });
  useEffect(() => { load(); }, []);
  const setStatus = async (p, status) => {
    try { await api.post(`/platform/partners/${p.id}/status`, { status }); toast.success(`${p.email}: ${ST[status][1]}`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const markPaid = async (c) => {
    if (!window.confirm(`Segnare come pagata la commissione di ${eur(c.commission_net_cents)}?`)) return;
    try { await api.post(`/platform/partner-commissions/${c.id}/paid`); toast.success("Commissione segnata come pagata"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const name = Object.fromEntries((rows || []).map((p) => [p.id, `${p.nome || ""} ${p.cognome || ""}`.trim() || p.email]));
  return (
    <div className="space-y-5" data-testid="platform-partners">
      <SettingsCard />
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 font-semibold text-slate-900 p-4 border-b border-slate-100"><Handshake className="w-4 h-4 text-[#0ABAB5]" />Partner ({rows?.length ?? "…"})</div>
        {rows && !rows.length && <p className="p-4 text-sm text-slate-500" data-testid="partners-empty">Nessun partner registrato.</p>}
        <div className="divide-y divide-slate-100">
          {(rows || []).map((p) => (
            <div key={p.id} className="p-4 flex flex-col lg:flex-row lg:items-center gap-3" data-testid={`partner-row-${p.id}`}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap"><span className="font-semibold text-slate-900">{name[p.id]}</span><StatusBadge color={ST[p.status]?.[0]}>{ST[p.status]?.[1]}</StatusBadge><span className="text-xs text-slate-500">{TIPO[p.tipo] || "Profilo incompleto"}</span></div>
                <div className="text-xs text-slate-500 mt-0.5 truncate">{p.email} · {p.telefono || "—"} · codice {p.code}{p.partita_iva ? ` · P.IVA ${p.partita_iva}` : ""}{p.codice_fiscale ? ` · CF ${p.codice_fiscale}` : ""}{p.regime_fiscale ? ` · regime ${p.regime_fiscale}` : ""}</div>
                <div className="text-xs text-slate-600 mt-0.5">{p.referrals} clienti · maturate {eur(p.maturate_cents)} · pagate {eur(p.pagate_cents)}</div>
              </div>
              <div className="flex gap-2 flex-wrap">
                {p.status !== "approved" && <Button size="sm" onClick={() => setStatus(p, "approved")} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid={`partner-approve-${p.id}`}><Check className="w-4 h-4 mr-1" />Approva</Button>}
                {p.status === "pending" && <Button size="sm" variant="outline" onClick={() => setStatus(p, "rejected")} data-testid={`partner-reject-${p.id}`}>Rifiuta</Button>}
                {p.status === "approved" && <Button size="sm" variant="outline" className="text-red-600" onClick={() => setStatus(p, "suspended")} data-testid={`partner-suspend-${p.id}`}><Ban className="w-4 h-4 mr-1" />Sospendi</Button>}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid="partner-commissions">
        <div className="flex items-center gap-2 font-semibold text-slate-900 p-4 border-b border-slate-100"><Wallet className="w-4 h-4 text-[#0ABAB5]" />Commissioni ({coms.length})</div>
        {!coms.length && <p className="p-4 text-sm text-slate-500">Nessuna commissione maturata.</p>}
        <div className="divide-y divide-slate-100">
          {coms.map((c) => (
            <div key={c.id} className="p-4 flex flex-col sm:flex-row sm:items-center gap-2 text-sm" data-testid={`commission-row-${c.id}`}>
              <div className="flex-1 min-w-0"><span className="font-medium text-slate-900">{name[c.partner_id] || c.partner_id}</span> · {c.org_name} · {new Date(c.paid_at).toLocaleDateString("it-IT")}
                <div className="text-xs text-slate-500">Base {eur(c.base_cents)} × {c.commission_pct}% = {eur(c.commission_cents)}{c.refunded_cents ? ` · rimborsati ${eur(c.refunded_cents)} · netta ${eur(c.commission_net_cents)}` : ""}{c.recupero_cents ? ` · da recuperare ${eur(c.recupero_cents)}` : ""} · regime CRMEvent {c.crmevent_tax_regime}</div></div>
              <StatusBadge color={CST[c.status]?.[0]}>{CST[c.status]?.[1]}</StatusBadge>
              {c.status === "maturata" && c.commission_net_cents > 0 && <Button size="sm" variant="outline" onClick={() => markPaid(c)} data-testid={`commission-paid-${c.id}`}>Segna pagata</Button>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
