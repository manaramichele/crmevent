import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Coins, Save, Search, Users2, AlertTriangle, PlayCircle, Wallet, Plus, Minus, Building2, Settings2, ShieldCheck, CheckCircle2, XCircle } from "lucide-react";
import OrgUsers from "@/components/OrgUsers";
import { StatusBadge } from "@/components/crm";

const fmtDate = (s) => (s ? new Date(s).toLocaleString("it-IT") : "—");
const TABS = [["servizi", "Servizi"], ["ricariche", "Ricariche"], ["org", "Organizzazioni"], ["fatture", "Fatture & Integrazioni"], ["migrazione", "Migrazione"]];
const REASON_PRESETS = ["Bonus commerciale", "Assistenza cliente", "Correzione saldo", "Promozione"];
const REASON_LABELS = {
  manual_adjustment: "Rettifica Super Admin", signup_bonus: "Bonus registrazione",
  event_activation: "Attivazione evento", event_maintenance: "Mantenimento evento",
  event_pipeline_pro: "Pipeline Evento Pro", ai_assistant: "Assistente CRMEvent",
  ai_content: "Generazione contenuti", purchase: "Acquisto crediti",
  image_generation: "Generazione immagini",
};
const norm = (s) => (s || "").toString().trim().toLowerCase();

// Catalogo semplificato: Servizio | Descrizione completa | Costo in crediti. La logica di consumo resta interna.
function ServicesTab() {
  const [rows, setRows] = useState([]);
  const [edits, setEdits] = useState({});
  const load = () => api.get("/platform/credit-services").then(({ data }) => setRows((data.services || []).filter((s) => s.linked && s.visible !== false).sort((a, b) => (a.name || "").localeCompare(b.name || "", "it", { sensitivity: "base" })))).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => { load(); }, []);
  const set = (k, f, v) => setEdits((s) => ({ ...s, [k]: { ...s[k], [f]: v } }));
  const save = async (svc) => {
    const body = edits[svc.key] || {};
    if (body.unit_cost !== undefined && (body.unit_cost === null || body.unit_cost < 0 || !Number.isInteger(body.unit_cost))) return toast.error("Inserisci un numero intero di crediti (0 o superiore)");
    try { await api.put(`/platform/credit-services/${svc.key}`, body); toast.success(`Servizio "${svc.name}" aggiornato`); setEdits((s) => ({ ...s, [svc.key]: undefined })); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div data-testid="svc-list">
      <div className="hidden md:grid grid-cols-[220px_1fr_150px] gap-4 px-1 pb-2 text-xs uppercase text-slate-400 border-b border-slate-100"><span>Servizio</span><span>Descrizione completa</span><span>Costo in crediti</span></div>
      <div className="divide-y divide-slate-100">
        {rows.map((s) => {
          const e = edits[s.key] || {};
          const v = (f) => (e[f] !== undefined ? e[f] : s[f]);
          return (
            <div key={s.key} className="py-4 grid grid-cols-1 md:grid-cols-[220px_1fr_150px] gap-3 md:gap-4 md:items-start" data-testid={`svc-row-${s.key}`}>
              <div className="font-semibold text-slate-900" data-testid={`svc-name-${s.key}`}>{s.name}
                {s.key === "video_support" && (
                  <label className="mt-2 flex items-center gap-2 text-xs font-normal text-slate-600">
                    <input type="checkbox" className="accent-tiffany w-4 h-4" checked={!!v("active")} onChange={(ev) => { set(s.key, "active", ev.target.checked); set(s.key, "consumo_active", ev.target.checked); }} data-testid="svc-active-video_support" />
                    Prenotabile dagli organizzatori
                  </label>
                )}
              </div>
              <div>
                <label className="md:hidden text-[11px] uppercase tracking-wide text-slate-400">Descrizione completa</label>
                <textarea rows={4} value={v("description") ?? ""} onChange={(ev) => set(s.key, "description", ev.target.value)} data-testid={`svc-desc-${s.key}`}
                  className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm text-slate-700 leading-relaxed focus:outline-none focus:ring-2 focus:ring-tiffany/40" />
              </div>
              <div className="flex md:flex-col items-end md:items-stretch gap-2">
                <div className="flex-1 md:flex-none">
                  <label className="md:hidden text-[11px] uppercase tracking-wide text-slate-400">Costo in crediti</label>
                  <div className="flex items-center gap-2"><Input type="number" min={0} step={1} inputMode="numeric" className="h-10 w-24" value={v("unit_cost") ?? ""} onChange={(ev) => set(s.key, "unit_cost", ev.target.value === "" ? null : Number(ev.target.value))} data-testid={`svc-cost-${s.key}`} /><span className="text-sm text-slate-500">crediti</span></div>
                </div>
                <Button disabled={!edits[s.key]} onClick={() => save(s)} data-testid={`svc-save-${s.key}`} className="h-10 bg-slate-900 text-white"><Save className="w-4 h-4 mr-1.5" />Salva</Button>
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-slate-400 mt-3">Il nuovo costo vale dalle operazioni successive; lo storico resta invariato. La descrizione è solo informativa: il modo in cui il servizio scala i crediti è definito internamente e non cambia.</p>
    </div>
  );
}

const fmtEur = (v) => Number(v).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function PackagesTab() {
  const [rows, setRows] = useState([]);
  const [edits, setEdits] = useState({});
  const [unit, setUnit] = useState(null);
  const load = () => api.get("/platform/credit-packages").then(({ data }) => { setRows(data.packages || []); setUnit(data.credit_unit_eur ?? null); }).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
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
    {unit != null && <p className="text-xs text-slate-400 mt-3" data-testid="pkg-credit-unit">1 credito = € {fmtEur(unit)}. Acquista crediti da utilizzare per i servizi di CRMEvent.</p>}
    </div>
  );
}

function Stat3({ label, value, testid, tone }) {
  return (
    <div className={`rounded-xl border p-3 ${tone === "tiffany" ? "border-tiffany-border bg-tiffany-light/30" : "border-slate-200"}`}>
      <div className="text-[11px] text-slate-400 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-bold text-slate-900 mt-0.5" data-testid={testid}>{value}</div>
    </div>
  );
}

function OrgsTab() {
  const [overview, setOverview] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [selId, setSelId] = useState(null);
  const [data, setData] = useState(null);
  const [manage, setManage] = useState(null);
  const [lf, setLf] = useState({ from: "", to: "", type: "all", service: "all" });

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get("/platform/orgs-overview"); setOverview(data.organizations || []); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { loadOverview(); }, [loadOverview]);

  const loadCredits = useCallback(async (id) => {
    try { const { data } = await api.get(`/platform/orgs/${id}/credits`); setData(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setData(null); }
  }, []);
  const select = async (row) => { setSelId(row.id); setData(null); setQ(""); setLf({ from: "", to: "", type: "all", service: "all" }); await loadCredits(row.id); };

  const match = (o, t) => [o.nome, o.admin_name, o.admin_email, o.admin_phone, o.id].some((f) => norm(f).includes(t));
  const term = norm(q);
  const results = term.length >= 2 ? overview.filter((o) => match(o, term)).slice(0, 8) : [];
  const tableRows = term ? overview.filter((o) => match(o, term)) : overview;

  const selRow = overview.find((o) => o.id === selId) || null;
  const bal = data?.credits?.balance ?? selRow?.balance ?? 0;
  const used = data?.credits?.lifetime_spent ?? selRow?.lifetime_spent ?? 0;
  const granted = data?.credits?.lifetime_granted ?? selRow?.lifetime_granted ?? 0;

  const services = Array.from(new Set((data?.ledger || []).map((m) => m.reason_code))).filter(Boolean);
  const ledger = (data?.ledger || []).filter((m) => {
    if (lf.type === "credit" && !(m.amount > 0)) return false;
    if (lf.type === "debit" && !(m.amount < 0)) return false;
    if (lf.service !== "all" && m.reason_code !== lf.service) return false;
    const d = (m.created_at || "").slice(0, 10);
    if (lf.from && d < lf.from) return false;
    if (lf.to && d > lf.to) return false;
    return true;
  });

  const amount = manage ? (manage.mode === "add" ? 1 : -1) * Math.abs(Number(manage.qty) || 0) : 0;
  const newBal = bal + amount;
  const canConfirm = !!manage && Math.abs(Number(manage.qty) || 0) > 0 && !!(manage.reason || "").trim() && newBal >= 0;
  const doAdjust = async () => {
    if (!canConfirm) return;
    try {
      await api.post(`/platform/orgs/${selId}/credits/adjust`, { amount, note: manage.reason.trim() });
      toast.success(`Movimento registrato: ${amount > 0 ? "+" : ""}${amount} crediti`);
      setManage(null); await loadCredits(selId); loadOverview();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div data-testid="orgs-tab">
      <div className="relative max-w-2xl">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca organizzazione, referente o email..." className="pl-9" data-testid="org-search-input" />
        {results.length > 0 && (
          <div className="absolute z-20 mt-1 w-full bg-white border border-slate-200 rounded-xl shadow-lg overflow-hidden" data-testid="org-search-results">
            {results.map((o) => (
              <button key={o.id} onClick={() => select(o)} className="w-full text-left px-4 py-2.5 hover:bg-slate-50 border-b border-slate-50 last:border-0" data-testid={`org-result-${o.id}`}>
                <div className="font-semibold text-slate-800 text-sm">{o.nome || "—"}</div>
                <div className="text-xs text-slate-500">{o.admin_name || "—"} · {o.admin_email || "—"}</div>
                <div className="text-xs text-tiffany-active font-medium">{o.balance} crediti disponibili</div>
              </button>
            ))}
          </div>
        )}
      </div>

      {selId && selRow && (
        <div className="mt-5 space-y-4" data-testid="org-selected-card">
          <div className="rounded-2xl border border-slate-200 p-4 sm:p-5 bg-white">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-slate-900 font-bold text-lg"><Building2 className="w-5 h-5 text-tiffany-active" />{selRow.nome || "—"}</div>
                <div className="text-sm text-slate-600 mt-1">Admin: <span className="font-medium">{selRow.admin_name || "—"}</span></div>
                <div className="text-sm text-slate-500 break-all">{selRow.admin_email || "—"}{selRow.admin_phone ? ` · ${selRow.admin_phone}` : ""}</div>
                <div className="text-[11px] text-slate-300 mt-1">ID tecnico: {selRow.id}</div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => { setSelId(null); setData(null); }} data-testid="org-deselect">Chiudi</Button>
                <Button onClick={() => setManage({ mode: "add", qty: "", reason: "" })} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="org-manage-credits"><Wallet className="w-4 h-4 mr-1.5" />Gestisci crediti</Button>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-4">
              <Stat3 label="Crediti disponibili" value={bal} testid="org-balance" tone="tiffany" />
              <Stat3 label="Acquistati / accreditati" value={granted} testid="org-granted" />
              <Stat3 label="Crediti utilizzati" value={used} testid="org-used" />
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 p-4 sm:p-5 bg-white">
            <div className="flex items-center gap-2 mb-3 font-semibold text-slate-800"><Users2 className="w-4 h-4 text-tiffany-active" />Utenti dell'organizzazione</div>
            <OrgUsers orgId={selId} allowProfileEdit />
          </div>

          <div className="rounded-2xl border border-slate-200 p-4 sm:p-5 bg-white">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
              <div className="font-semibold text-slate-800">Storico movimenti ({ledger.length})</div>
              <div className="flex flex-wrap gap-2">
                <input type="date" value={lf.from} onChange={(e) => setLf((s) => ({ ...s, from: e.target.value }))} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="ledger-from" />
                <input type="date" value={lf.to} onChange={(e) => setLf((s) => ({ ...s, to: e.target.value }))} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="ledger-to" />
                <select value={lf.type} onChange={(e) => setLf((s) => ({ ...s, type: e.target.value }))} className="h-9 rounded-md border border-slate-200 px-2 text-sm bg-white" data-testid="ledger-type">
                  <option value="all">Tutti i tipi</option><option value="credit">Accrediti</option><option value="debit">Addebiti</option>
                </select>
                <select value={lf.service} onChange={(e) => setLf((s) => ({ ...s, service: e.target.value }))} className="h-9 rounded-md border border-slate-200 px-2 text-sm bg-white" data-testid="ledger-service">
                  <option value="all">Tutti i servizi</option>
                  {services.map((s) => <option key={s} value={s}>{REASON_LABELS[s] || s}</option>)}
                </select>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="ledger-table">
                <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-100"><th className="py-2 pr-3">Data</th><th className="py-2 pr-3">Movimento</th><th className="py-2 pr-3 text-right">Crediti</th><th className="py-2 text-right">Saldo</th></tr></thead>
                <tbody>
                  {ledger.length === 0 && <tr><td colSpan={4} className="py-6 text-center text-slate-400">Nessun movimento con questi filtri.</td></tr>}
                  {ledger.map((m) => (
                    <tr key={m.id} className="border-b border-slate-50"><td className="py-2 pr-3 text-slate-500 whitespace-nowrap">{fmtDate(m.created_at)}</td><td className="py-2 pr-3 text-slate-700">{REASON_LABELS[m.reason_code] || m.reason_code}{m.note ? ` · ${m.note}` : ""}</td><td className={`py-2 pr-3 text-right font-semibold ${m.amount > 0 ? "text-emerald-600" : "text-slate-800"}`}>{m.amount > 0 ? "+" : ""}{m.amount}</td><td className="py-2 text-right text-slate-500">{m.balance_after ?? "—"}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div className="mt-6">
        <div className="flex items-center gap-2 mb-2 text-sm font-semibold text-slate-700"><Users2 className="w-4 h-4 text-tiffany-active" />Tutte le organizzazioni ({tableRows.length})</div>
        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-sm" data-testid="orgs-table">
            <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-100 bg-slate-50/60">
              <th className="py-2.5 px-3">Organizzazione</th><th className="py-2.5 px-3">Admin</th><th className="py-2.5 px-3">Email</th><th className="py-2.5 px-3 text-right">Crediti</th><th className="py-2.5 px-3 text-right">Utilizzati</th><th className="py-2.5 px-3"></th></tr></thead>
            <tbody>
              {loading && <tr><td colSpan={6} className="py-6 text-center text-slate-400">Caricamento…</td></tr>}
              {!loading && tableRows.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-slate-400">Nessuna organizzazione trovata.</td></tr>}
              {tableRows.map((o) => (
                <tr key={o.id} className="border-b border-slate-50 hover:bg-slate-50/50" data-testid={`orgs-row-${o.id}`}>
                  <td className="py-2.5 px-3 font-medium text-slate-800">{o.nome || "—"}{o.type && o.type !== "cliente" ? <span className="ml-1.5 text-[10px] uppercase text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">{o.type}</span> : null}</td>
                  <td className="py-2.5 px-3 text-slate-600">{o.admin_name || "—"}</td>
                  <td className="py-2.5 px-3 text-slate-500 break-all">{o.admin_email || "—"}</td>
                  <td className="py-2.5 px-3 text-right font-semibold text-slate-800">{o.balance}</td>
                  <td className="py-2.5 px-3 text-right text-slate-500">{o.lifetime_spent}</td>
                  <td className="py-2.5 px-3 text-right"><Button size="sm" variant="outline" onClick={() => select(o)} data-testid={`orgs-manage-${o.id}`}><Settings2 className="w-3.5 h-3.5 mr-1" />Gestisci</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={!!manage} onOpenChange={(o) => !o && setManage(null)}>
        <DialogContent className="max-w-md" data-testid="manage-credits-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Wallet className="w-5 h-5 text-tiffany-active" />Gestisci crediti</DialogTitle>
            <DialogDescription>{selRow?.nome} · saldo attuale {bal} crediti</DialogDescription>
          </DialogHeader>
          {manage && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2">
                <button onClick={() => setManage((s) => ({ ...s, mode: "add" }))} className={`flex items-center justify-center gap-1.5 rounded-lg border py-2 text-sm font-semibold ${manage.mode === "add" ? "border-emerald-400 bg-emerald-50 text-emerald-700" : "border-slate-200 text-slate-500"}`} data-testid="manage-mode-add"><Plus className="w-4 h-4" />Aggiungi crediti</button>
                <button onClick={() => setManage((s) => ({ ...s, mode: "remove" }))} className={`flex items-center justify-center gap-1.5 rounded-lg border py-2 text-sm font-semibold ${manage.mode === "remove" ? "border-red-400 bg-red-50 text-red-700" : "border-slate-200 text-slate-500"}`} data-testid="manage-mode-remove"><Minus className="w-4 h-4" />Rimuovi crediti</button>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Quantità crediti</label>
                <Input type="number" min="1" value={manage.qty} onChange={(e) => setManage((s) => ({ ...s, qty: e.target.value }))} placeholder="es. 50" data-testid="manage-qty" />
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-slate-700">Motivazione (obbligatoria)</label>
                <div className="flex flex-wrap gap-1.5">
                  {REASON_PRESETS.map((r, i) => (
                    <button key={r} onClick={() => setManage((s) => ({ ...s, reason: r }))} className={`text-xs rounded-full px-2.5 py-1 border ${manage.reason === r ? "border-tiffany bg-tiffany-light/40 text-slate-800" : "border-slate-200 text-slate-500 hover:border-slate-300"}`} data-testid={`manage-reason-${i}`}>{r}</button>
                  ))}
                </div>
                <Input value={manage.reason} onChange={(e) => setManage((s) => ({ ...s, reason: e.target.value }))} placeholder="Motivazione (testo libero)" data-testid="manage-reason-input" />
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm space-y-1" data-testid="manage-preview">
                <div className="flex justify-between"><span className="text-slate-500">Saldo attuale</span><span className="font-semibold">{bal}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Variazione</span><span className={`font-semibold ${amount > 0 ? "text-emerald-600" : amount < 0 ? "text-red-600" : "text-slate-500"}`}>{amount > 0 ? "+" : ""}{amount}</span></div>
                <div className="flex justify-between border-t border-slate-200 pt-1"><span className="text-slate-500">Nuovo saldo</span><span className="font-bold" data-testid="manage-newbal">{newBal}</span></div>
              </div>
              {manage.mode === "remove" && newBal < 0 && <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-xs text-red-700">Non è possibile portare il saldo sotto zero.</div>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setManage(null)}>Annulla</Button>
            <Button disabled={!canConfirm} onClick={doAdjust} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="manage-confirm">{amount >= 0 ? "Conferma accredito" : "Conferma rimozione"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MigrationTab() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get("/platform/credits/migration-dryrun"); setD(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const Table = ({ rows, testid }) => (
    <div className="overflow-x-auto mt-2"><table className="w-full text-sm" data-testid={testid}>
      <thead><tr className="text-left text-xs uppercase text-slate-400 border-b border-slate-100">
        <th className="py-2 pr-3">Organizzazione</th><th className="py-2 pr-3">Tipo</th><th className="py-2 pr-3 text-right">Saldo attuale</th><th className="py-2 pr-3 text-right">Saldo simulato</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.id} className="border-b border-slate-50">
          <td className="py-2 pr-3"><div className="font-medium text-slate-800">{r.nome || "—"}</div><div className="text-xs text-slate-400">{r.id}</div></td>
          <td className="py-2 pr-3 text-slate-500">{r.type || "—"}</td>
          <td className="py-2 pr-3 text-right text-slate-600">{r.balance}</td>
          <td className={`py-2 pr-3 text-right font-semibold ${r.projected_balance !== r.balance ? "text-emerald-600" : "text-slate-500"}`}>{r.projected_balance}{r.projected_balance !== r.balance ? " (+100)" : ""}</td>
        </tr>
      ))}</tbody>
    </table></div>
  );

  return (
    <div data-testid="migration-tab">
      <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 mb-4">
        <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
        <div><b>Dry-run (sola lettura).</b> Regola: +100 crediti una tantum alle organizzazioni reali che non hanno mai ricevuto il bonus. Org Test/Demo/interne sono escluse. La migrazione NON viene eseguita finché non la si conferma esplicitamente.</div>
      </div>
      <Button size="sm" variant="outline" onClick={load} disabled={loading} data-testid="migration-refresh">{loading ? "Calcolo…" : "Ricalcola dry-run"}</Button>
      {d && (
        <div className="mt-4 space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-xl border border-slate-200 p-4"><div className="text-xs text-slate-400 uppercase">Org totali</div><div className="text-2xl font-bold text-slate-900" data-testid="mig-total">{d.total_orgs}</div></div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4"><div className="text-xs text-emerald-600 uppercase">Idonee (+100)</div><div className="text-2xl font-bold text-emerald-700" data-testid="mig-eligible">{d.eligible_count}</div></div>
            <div className="rounded-xl border border-slate-200 p-4"><div className="text-xs text-slate-400 uppercase">Escluse (test/interne)</div><div className="text-2xl font-bold text-slate-900" data-testid="mig-excluded">{d.excluded_count}</div></div>
            <div className="rounded-xl border border-slate-200 p-4"><div className="text-xs text-slate-400 uppercase">Già col bonus</div><div className="text-2xl font-bold text-slate-900" data-testid="mig-already">{d.already_granted_count}</div></div>
          </div>
          <div className="rounded-xl border border-tiffany-border bg-tiffany-light/40 p-4 text-sm text-slate-700">
            Crediti totali che verrebbero accreditati: <b data-testid="mig-credits-total">{d.total_credits_to_grant}</b> ({d.eligible_count} org × {d.bonus_amount})
          </div>
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><Users2 className="w-4 h-4 text-emerald-600" />Idonee ({d.eligible_count})</div>
            {d.eligible.length ? <Table rows={d.eligible} testid="mig-eligible-table" /> : <p className="text-sm text-slate-400 mt-1">Nessuna org idonea.</p>}
          </div>
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-700"><AlertTriangle className="w-4 h-4 text-amber-500" />Escluse (Test/Demo/interne) ({d.excluded_count})</div>
            {d.excluded.length ? <Table rows={d.excluded} testid="mig-excluded-table" /> : <p className="text-sm text-slate-400 mt-1">Nessuna.</p>}
          </div>
          {d.already_granted_count > 0 && (
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">Già col bonus ({d.already_granted_count})</div>
              <Table rows={d.already_granted} testid="mig-already-table" />
            </div>
          )}
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
            <PlayCircle className="w-4 h-4 shrink-0" />L'esecuzione della migrazione è in attesa di autorizzazione. Verrà abilitata dopo approvazione del dry-run.
          </div>
        </div>
      )}
    </div>
  );
}
function IntegrationBadge({ ok, mode }) {
  const live = mode === "live";
  const color = !ok ? "red" : (live ? "green" : "amber");
  return <StatusBadge color={color}>{!ok ? "Non connesso / Errore" : (live ? "Produzione" : "Test")} · {ok ? "Connesso" : "—"}</StatusBadge>;
}

const FIC_STATO = {
  da_emettere: ["amber", "Da emettere"], creato_test: ["blue", "Creata (test/dry-run)"],
  emessa: ["green", "Emessa"], errore_emissione: ["red", "Errore"], simulato_test: ["blue", "Simulata (test)"],
};

function StripeLiveDiagnostics() {
  const LABELS = [
    ["secret_key_live", "Secret Key LIVE"],
    ["account_live", "Account Stripe LIVE"],
    ["publishable_key_live", "Publishable Key LIVE"],
    ["tax_rate_live", "Tax Rate IVA 22% LIVE"],
    ["webhook_live", "Webhook LIVE"],
    ["signing_secret", "Signing Secret"],
  ];
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.get("/platform/stripe/live-diagnostics");
      setRes(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="rounded-xl border border-slate-200 p-4 mb-5" data-testid="stripe-live-diagnostics">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-slate-500" /><span className="text-sm font-semibold text-slate-700">Diagnostica Stripe LIVE</span></div>
        <Button size="sm" onClick={run} disabled={busy} className="bg-slate-900 text-white" data-testid="stripe-live-diag-run">{busy ? "Verifica…" : "Verifica configurazione Stripe LIVE"}</Button>
      </div>
      {res && (
        <div className="mt-4 space-y-1.5" data-testid="stripe-live-diag-result">
          {LABELS.map(([key, label]) => {
            const c = res.checks?.[key];
            const okv = c?.status === "OK";
            return (
              <div key={key} className="flex items-start justify-between gap-3 text-sm" data-testid={`diag-${key}`}>
                <span className="text-slate-600">{label}</span>
                <span className="flex items-center gap-1.5 text-right">
                  {okv ? <CheckCircle2 className="w-4 h-4 text-green-600" /> : <XCircle className="w-4 h-4 text-red-500" />}
                  <span className={`font-semibold ${okv ? "text-green-700" : "text-red-600"}`}>{c?.status || "—"}</span>
                  {!okv && c?.detail && <span className="text-xs text-slate-400">— {c.detail}</span>}
                </span>
              </div>
            );
          })}
          <div className="flex items-center justify-between gap-3 pt-2 mt-2 border-t border-slate-100 text-sm" data-testid="diag-overall">
            <span className="font-semibold text-slate-700">Configurazione complessiva</span>
            <span className={`font-bold ${res.overall === "PRONTA" ? "text-green-700" : "text-red-600"}`}>{res.overall}</span>
          </div>
        </div>
      )}
    </div>
  );
}


function InvoicesTab() {
  const [st, setSt] = useState(null);
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(null);
  const [sim, setSim] = useState(null);
  const [simBusy, setSimBusy] = useState(null);
  const [genBusy, setGenBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const [s, i] = await Promise.all([api.get("/platform/integrations/status"), api.get("/platform/credit-invoices")]);
      setSt(s.data); setRows(i.data.invoices || []);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const retry = async (id) => {
    if (!id) return;
    setBusy(id);
    try { const { data } = await api.post(`/platform/invoices/${id}/retry-emit`); toast[data.fic_error ? "warning" : "success"](data.fic_error ? `Errore: ${data.fic_error}` : `Fattura ${data.fic_stato_documento}`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(null); }
  };
  const simulate = async (invId) => {
    if (!invId) return;
    setSimBusy(invId); setSim(null);
    try { const { data } = await api.post(`/platform/invoices/${invId}/simulate`); setSim(data); toast.success("Fattura simulata (TEST) — nessun documento reale su Fatture in Cloud"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setSimBusy(null); }
  };
  const genTest = async () => {
    setGenBusy(true);
    try { const { data } = await api.post("/platform/credit-invoices/test", {}); toast.success(`Transazione TEST creata (${data.org_name || "org"})`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setGenBusy(false); }
  };
  const delTest = async (pid) => {
    try { await api.delete(`/platform/credit-invoices/test/${pid}`); toast.success("Transazione TEST eliminata"); setSim(null); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const eur = (n) => `€ ${Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return (
    <div data-testid="invoices-tab">
      <StripeLiveDiagnostics />
      <div className="grid sm:grid-cols-2 gap-3 mb-5">
        <div className="rounded-xl border border-slate-200 p-4" data-testid="stripe-status">
          <div className="text-sm font-semibold text-slate-700 mb-1">Stripe</div>
          {st ? <IntegrationBadge ok={st.stripe.config_ok} mode={st.stripe.mode} /> : <span className="text-xs text-slate-400">…</span>}
          {st && !st.stripe.config_ok && <ul className="mt-2 text-xs text-red-600 list-disc pl-4">{st.stripe.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>}
        </div>
        <div className="rounded-xl border border-slate-200 p-4" data-testid="fic-status">
          <div className="text-sm font-semibold text-slate-700 mb-1">Fatture in Cloud</div>
          {st ? <IntegrationBadge ok={st.fic.connected} mode={st.fic.mode} /> : <span className="text-xs text-slate-400">…</span>}
        </div>
      </div>
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-semibold text-slate-700">Ricariche crediti</div>
        <Button size="sm" variant="outline" onClick={genTest} disabled={genBusy} data-testid="gen-test-recharge">{genBusy ? "Creo…" : "Genera transazione TEST"}</Button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm min-w-[820px]" data-testid="credit-invoices-table">
          <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase">
            <th className="text-left px-3 py-2.5">Organizzazione</th><th className="text-left px-3 py-2.5">Importo</th><th className="text-left px-3 py-2.5">Pagamento</th><th className="text-left px-3 py-2.5">Crediti</th><th className="text-left px-3 py-2.5">Fattura</th><th className="text-right px-3 py-2.5">Azioni</th>
          </tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">Nessuna ricarica.</td></tr>}
            {rows.map((r) => {
              const fs = FIC_STATO[r.fic_stato] || ["gray", r.fic_stato];
              return (
                <tr key={r.purchase_id} className={`border-t border-slate-100 ${r.is_test ? "bg-amber-50/40" : ""}`} data-testid={`ci-row-${r.purchase_id}`}>
                  <td className="px-3 py-2.5 font-medium text-slate-800">
                    <span className="inline-flex items-center gap-1.5">{r.org_name || "—"}{r.is_test && <span className="text-[10px] font-bold uppercase tracking-wide text-amber-700 bg-amber-100 border border-amber-300 px-1.5 py-0.5 rounded" data-testid={`ci-test-badge-${r.purchase_id}`}>TEST</span>}</span>
                  </td>
                  <td className="px-3 py-2.5 text-slate-600 whitespace-nowrap">{eur(r.amount_gross)} <span className="text-xs text-slate-400">({r.credits_total} cr)</span></td>
                  <td className="px-3 py-2.5"><StatusBadge color={r.is_test ? "gray" : (r.payment_status === "paid" ? "green" : "amber")}>{r.is_test ? "TEST (no Stripe)" : (r.payment_status === "paid" ? "Pagato" : r.payment_status)}</StatusBadge></td>
                  <td className="px-3 py-2.5"><StatusBadge color={r.is_test ? "gray" : (r.credits_granted ? "green" : "gray")}>{r.is_test ? "No (test)" : (r.credits_granted ? "Accreditati" : "No")}</StatusBadge></td>
                  <td className="px-3 py-2.5"><StatusBadge color={fs[0]}>{fs[1]}</StatusBadge>{r.fic_error && <div className="text-[11px] text-red-500 mt-0.5 max-w-[220px] truncate" title={r.fic_error}>{r.fic_error}</div>}</td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="inline-flex items-center gap-1.5 justify-end">
                      {r.invoice_id && <Button size="sm" variant="outline" disabled={simBusy === r.invoice_id} onClick={() => simulate(r.invoice_id)} data-testid={`ci-simulate-${r.purchase_id}`}>{simBusy === r.invoice_id ? "Simulo…" : "Simula fattura (TEST)"}</Button>}
                      {r.is_test
                        ? <Button size="sm" variant="ghost" className="text-red-500 hover:text-red-600" onClick={() => delTest(r.purchase_id)} data-testid={`ci-del-${r.purchase_id}`}>Elimina</Button>
                        : ((r.fic_stato === "errore_emissione" || r.fic_stato === "da_emettere") && r.invoice_id
                            ? <Button size="sm" variant="outline" disabled={busy === r.invoice_id} onClick={() => retry(r.invoice_id)} data-testid={`ci-retry-${r.purchase_id}`}>{busy === r.invoice_id ? "…" : "Riprova emissione"}</Button>
                            : null)}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {sim && (
        <div className="mt-4 rounded-lg border border-tiffany-border bg-tiffany-light/40 p-4 text-sm" data-testid="platform-sim-result">
          <div className="font-semibold text-slate-800 mb-2">SIMULAZIONE TEST · nessun documento FIC / nessun SDI</div>
          <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-slate-700">
            <div><span className="text-slate-500">Intestazione:</span> {sim.intestazione || "—"}</div>
            <div className="sm:col-span-2"><span className="text-slate-500">Dati cliente:</span> {[sim.cliente?.vat_number && `P.IVA ${sim.cliente.vat_number}`, sim.cliente?.tax_code && `CF ${sim.cliente.tax_code}`, [sim.cliente?.address_street, sim.cliente?.address_postal_code, sim.cliente?.address_city, sim.cliente?.address_province].filter(Boolean).join(" "), sim.cliente?.ei_code && `SDI ${sim.cliente.ei_code}`, sim.cliente?.certified_email && `PEC ${sim.cliente.certified_email}`].filter(Boolean).join(" · ") || "—"}</div>
            <div><span className="text-slate-500">Descrizione:</span> {sim.descrizione || "—"}</div>
            <div><span className="text-slate-500">Piano / servizio:</span> {sim.piano_label || sim.piano || "—"}</div>
            <div><span className="text-slate-500">Ciclo:</span> {({ una_tantum: "Una tantum", monthly: "Mensile", yearly: "Annuale" })[sim.ciclo_fatturazione] || "—"}</div>
            <div><span className="text-slate-500">Modalità di pagamento:</span> {sim.modalita_pagamento || "—"}</div>
            <div><span className="text-slate-500">Imponibile:</span> {Number(sim.imponibile ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
            <div><span className="text-slate-500">Aliquota IVA:</span> {Number(sim.aliquota_iva ?? 0).toFixed(0)}%</div>
            <div><span className="text-slate-500">Importo IVA:</span> {Number(sim.importo_iva ?? sim.iva ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
            <div><span className="text-slate-500">Totale:</span> {Number(sim.totale ?? 0).toFixed(2)} {(sim.valuta || "eur").toUpperCase()}</div>
            <div><span className="text-slate-500">Coerenza:</span> {sim.coerente ? <span className="text-green-700 font-medium" data-testid="platform-sim-coherent">OK ✓</span> : <span className="text-red-700 font-medium">INCOERENTE</span>}</div>
          </div>
          <details className="mt-2">
            <summary className="text-xs text-tiffany-active cursor-pointer">Payload completo Fatture in Cloud che sarebbe stato inviato</summary>
            <pre className="mt-2 text-[11px] bg-white border border-slate-200 rounded p-2 overflow-x-auto" data-testid="platform-sim-payload">{JSON.stringify(sim.fic_payload_preview, null, 2)}</pre>
          </details>
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
        {tab === "fatture" && <InvoicesTab />}
        {tab === "migrazione" && <MigrationTab />}
      </div>
    </div>
  );
}
