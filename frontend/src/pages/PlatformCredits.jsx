import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Coins, Save, Search } from "lucide-react";

const fmtDate = (s) => (s ? new Date(s).toLocaleString("it-IT") : "—");
const TABS = [["servizi", "Servizi"], ["ricariche", "Ricariche"], ["org", "Organizzazioni"]];

function ServicesTab() {
  const [rows, setRows] = useState([]);
  const [edits, setEdits] = useState({});
  const load = () => api.get("/platform/credit-services").then(({ data }) => setRows(data.services || [])).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, []);
  const set = (k, f, v) => setEdits((s) => ({ ...s, [k]: { ...s[k], [f]: v } }));
  const save = async (svc) => {
    const body = edits[svc.key] || {};
    try { await api.put(`/platform/credit-services/${svc.key}`, body); toast.success(`Servizio "${svc.name}" aggiornato`); setEdits((s) => ({ ...s, [svc.key]: undefined })); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="svc-table">
      <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-100">
        <th className="py-2 pr-3">Servizio</th><th className="py-2 pr-3">Modalità</th><th className="py-2 pr-3">Costo</th><th className="py-2 pr-3">Unità</th><th className="py-2 pr-3">Attivo</th><th className="py-2 pr-3">Ver.</th><th className="py-2"></th></tr></thead>
      <tbody>
        {rows.map((s) => {
          const e = edits[s.key] || {};
          const v = (f) => (e[f] !== undefined ? e[f] : s[f]);
          return (
            <tr key={s.key} className="border-b border-slate-50" data-testid={`svc-row-${s.key}`}>
              <td className="py-2 pr-3"><div className="font-medium text-slate-800">{s.name}</div><div className="text-xs text-slate-400">{s.key}</div></td>
              <td className="py-2 pr-3">
                <select value={v("pricing_mode") || ""} onChange={(ev) => set(s.key, "pricing_mode", ev.target.value || null)} data-testid={`svc-mode-${s.key}`} className="h-9 rounded-md border border-slate-200 px-2 bg-white">
                  <option value="">—</option><option value="flat">Fisso</option><option value="per_unit">A quantità</option>
                </select>
              </td>
              <td className="py-2 pr-3"><Input type="number" className="h-9 w-24" value={v("unit_cost") ?? ""} onChange={(ev) => set(s.key, "unit_cost", ev.target.value === "" ? null : Number(ev.target.value))} data-testid={`svc-cost-${s.key}`} /></td>
              <td className="py-2 pr-3"><Input className="h-9 w-28" value={v("unit_label") ?? ""} onChange={(ev) => set(s.key, "unit_label", ev.target.value)} data-testid={`svc-unit-${s.key}`} /></td>
              <td className="py-2 pr-3"><input type="checkbox" className="accent-tiffany w-4 h-4" checked={!!v("active")} onChange={(ev) => set(s.key, "active", ev.target.checked)} data-testid={`svc-active-${s.key}`} /></td>
              <td className="py-2 pr-3 text-slate-400">{s.version}</td>
              <td className="py-2"><Button size="sm" disabled={!edits[s.key]} onClick={() => save(s)} data-testid={`svc-save-${s.key}`} className="bg-slate-900 text-white"><Save className="w-4 h-4" /></Button></td>
            </tr>
          );
        })}
      </tbody>
    </table>
    <p className="text-xs text-slate-400 mt-3">I consumi reali NON sono ancora collegati alle funzioni CRMEvent (Fase B). L'attivazione abilita solo il servizio nel catalogo.</p>
    </div>
  );
}

function PackagesTab() {
  const [rows, setRows] = useState([]);
  const [edits, setEdits] = useState({});
  const load = () => api.get("/platform/credit-packages").then(({ data }) => setRows(data.packages || [])).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, []);
  const set = (id, f, val) => setEdits((s) => ({ ...s, [id]: { ...s[id], [f]: val } }));
  const save = async (p) => {
    try { await api.put(`/platform/credit-packages/${p.id}`, edits[p.id] || {}); toast.success("Taglio aggiornato"); setEdits((s) => ({ ...s, [p.id]: undefined })); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="pkg-table">
      <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-100">
        <th className="py-2 pr-3">Prezzo €</th><th className="py-2 pr-3">Crediti base</th><th className="py-2 pr-3">Bonus</th><th className="py-2 pr-3">Bonus %</th><th className="py-2 pr-3">Totale</th><th className="py-2 pr-3">Ordine</th><th className="py-2 pr-3">Badge</th><th className="py-2 pr-3">Attivo</th><th className="py-2"></th></tr></thead>
      <tbody>
        {rows.map((p) => {
          const e = edits[p.id] || {};
          const v = (f) => (e[f] !== undefined ? e[f] : p[f]);
          const tot = (Number(v("credits_base")) || 0) + (Number(v("credits_bonus")) || 0);
          return (
            <tr key={p.id} className="border-b border-slate-50" data-testid={`pkg-row-${p.id}`}>
              <td className="py-2 pr-3"><Input type="number" className="h-9 w-24" value={v("price") ?? ""} onChange={(ev) => set(p.id, "price", Number(ev.target.value))} data-testid={`pkg-price-${p.id}`} /></td>
              <td className="py-2 pr-3"><Input type="number" className="h-9 w-24" value={v("credits_base") ?? ""} onChange={(ev) => set(p.id, "credits_base", Number(ev.target.value))} data-testid={`pkg-base-${p.id}`} /></td>
              <td className="py-2 pr-3"><Input type="number" className="h-9 w-20" value={v("credits_bonus") ?? ""} onChange={(ev) => set(p.id, "credits_bonus", Number(ev.target.value))} data-testid={`pkg-bonus-${p.id}`} /></td>
              <td className="py-2 pr-3"><Input type="number" className="h-9 w-16" value={v("bonus_pct") ?? ""} onChange={(ev) => set(p.id, "bonus_pct", Number(ev.target.value))} data-testid={`pkg-pct-${p.id}`} /></td>
              <td className="py-2 pr-3 font-semibold text-slate-800" data-testid={`pkg-total-${p.id}`}>{tot.toLocaleString("it-IT")}</td>
              <td className="py-2 pr-3"><Input type="number" className="h-9 w-16" value={v("sort") ?? ""} onChange={(ev) => set(p.id, "sort", Number(ev.target.value))} data-testid={`pkg-sort-${p.id}`} /></td>
              <td className="py-2 pr-3"><Input className="h-9 w-28" value={v("badge") ?? ""} onChange={(ev) => set(p.id, "badge", ev.target.value)} data-testid={`pkg-badge-${p.id}`} /></td>
              <td className="py-2 pr-3"><input type="checkbox" className="accent-tiffany w-4 h-4" checked={!!v("active")} onChange={(ev) => set(p.id, "active", ev.target.checked)} data-testid={`pkg-active-${p.id}`} /></td>
              <td className="py-2"><Button size="sm" disabled={!edits[p.id]} onClick={() => save(p)} data-testid={`pkg-save-${p.id}`} className="bg-slate-900 text-white"><Save className="w-4 h-4" /></Button></td>
            </tr>
          );
        })}
      </tbody>
    </table>
    <p className="text-xs text-slate-400 mt-3">1 credito = € 0,20. I pagamenti non sono ancora attivi: la modifica aggiorna solo il catalogo mostrato in Area Account.</p>
    </div>
  );
}

function OrgsTab() {
  const [oid, setOid] = useState("");
  const [data, setData] = useState(null);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const load = async (id) => {
    try { const { data } = await api.get(`/platform/orgs/${id}/credits`); setData(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setData(null); }
  };
  const adjust = async () => {
    if (!note.trim()) return toast.error("La causale è obbligatoria");
    if (!amount || Number(amount) === 0) return toast.error("Importo non valido");
    try { await api.post(`/platform/orgs/${data.org_id}/credits/adjust`, { amount: Number(amount), note }); toast.success("Movimento registrato"); setAmount(""); setNote(""); load(data.org_id); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div data-testid="orgs-tab">
      <div className="flex gap-2 max-w-lg">
        <Input placeholder="ID organizzazione" value={oid} onChange={(e) => setOid(e.target.value)} data-testid="org-search-input" />
        <Button onClick={() => load(oid.trim())} disabled={!oid.trim()} data-testid="org-search-btn"><Search className="w-4 h-4 mr-1.5" />Carica</Button>
      </div>
      {data && (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-xl border border-slate-200 p-4"><div className="text-xs text-slate-400 uppercase">Saldo</div><div className="text-2xl font-bold text-slate-900" data-testid="org-balance">{data.credits.balance}</div></div>
            <div className="rounded-xl border border-slate-200 p-4"><div className="text-xs text-slate-400 uppercase">Assegnati</div><div className="text-2xl font-bold text-slate-900">{data.credits.lifetime_granted}</div></div>
            <div className="rounded-xl border border-slate-200 p-4"><div className="text-xs text-slate-400 uppercase">Utilizzati</div><div className="text-2xl font-bold text-slate-900">{data.credits.lifetime_spent}</div></div>
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            <div className="font-semibold text-slate-800 mb-2">Accredito / rettifica manuale</div>
            <div className="flex flex-wrap gap-2 items-center">
              <Input type="number" placeholder="+50 / -20" className="w-32" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="adjust-amount" />
              <Input placeholder="Causale (obbligatoria)" className="flex-1 min-w-[200px]" value={note} onChange={(e) => setNote(e.target.value)} data-testid="adjust-note" />
              <Button onClick={adjust} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="adjust-btn">Registra</Button>
            </div>
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-700 mb-2">Storico ({data.ledger.length})</div>
            <div className="overflow-x-auto"><table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-100"><th className="py-2 pr-3">Data</th><th className="py-2 pr-3">Causale</th><th className="py-2 pr-3 text-right">Crediti</th><th className="py-2 text-right">Saldo</th></tr></thead>
              <tbody>{data.ledger.map((m) => (
                <tr key={m.id} className="border-b border-slate-50"><td className="py-2 pr-3 text-slate-500 whitespace-nowrap">{fmtDate(m.created_at)}</td><td className="py-2 pr-3 text-slate-700">{m.reason_code}{m.note ? ` · ${m.note}` : ""}</td><td className={`py-2 pr-3 text-right font-semibold ${m.amount > 0 ? "text-emerald-600" : "text-slate-800"}`}>{m.amount > 0 ? "+" : ""}{m.amount}</td><td className="py-2 text-right text-slate-500">{m.balance_after ?? "—"}</td></tr>
              ))}</tbody>
            </table></div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PlatformCredits() {
  const [tab, setTab] = useState("servizi");
  return (
    <div className="max-w-5xl animate-fade-up" data-testid="platform-credits-page">
      <div className="flex items-center gap-2 mb-1"><Coins className="w-6 h-6 text-tiffany-active" /><h1 className="font-display text-3xl font-bold text-slate-900">Servizi e crediti</h1></div>
      <p className="text-slate-500 mt-1 mb-6">Catalogo servizi a crediti, tagli di ricarica e gestione crediti per organizzazione. Nessun consumo reale attivo.</p>
      <div className="flex gap-1 border-b border-slate-200 mb-6">
        {TABS.map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} data-testid={`credits-tab-${id}`} className={`px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors ${tab === id ? "border-tiffany text-slate-900" : "border-transparent text-slate-500 hover:text-slate-700"}`}>{label}</button>
        ))}
      </div>
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        {tab === "servizi" && <ServicesTab />}
        {tab === "ricariche" && <PackagesTab />}
        {tab === "org" && <OrgsTab />}
      </div>
    </div>
  );
}
