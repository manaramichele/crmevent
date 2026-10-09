import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, SectionCard } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import { Save, Pencil, Search } from "lucide-react";
import SubscriptionEditDialog from "@/components/SubscriptionEditDialog";
import { FormulaBadge, BILLING } from "@/components/PlanBadge";

const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");
const MODE = { trial: "Prova gratuita", active: "Attivo", past_due: "Pagamento in sospeso", canceled: "Scaduto", expired: "Scaduto", suspended: "Sospeso" };
const err = (e) => toast.error(formatApiError(e.response?.data?.detail));

function PlanEditor({ k, p, catalog, onChange }) {
  const set = (f, v) => onChange({ ...p, [f]: v });
  const toggle = (f) => set("features", p.features.includes(f) ? p.features.filter((x) => x !== f) : [...p.features, f]);
  return (
    <div className="rounded-xl border border-slate-200 p-4 space-y-3" style={{ borderTop: `5px solid ${p.color}` }} data-testid={`saas-plan-${k}`}>
      <div className="flex items-center justify-between"><b style={{ color: p.color }}>{p.label}</b>
        <label className="text-xs flex items-center gap-1.5"><input type="checkbox" checked={p.active} onChange={(e) => set("active", e.target.checked)} data-testid={`saas-plan-active-${k}`} />In vendita</label></div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <label>Mensile €<Input type="number" step="0.01" value={p.monthly} onChange={(e) => set("monthly", parseFloat(e.target.value))} data-testid={`saas-monthly-${k}`} /></label>
        <label>Annuale €<Input type="number" step="0.01" value={p.yearly} onChange={(e) => set("yearly", parseFloat(e.target.value))} data-testid={`saas-yearly-${k}`} /></label>
        <label>Video/mese<Input type="number" value={p.video_quota} onChange={(e) => set("video_quota", parseInt(e.target.value, 10))} data-testid={`saas-video-${k}`} /></label>
        <label>Max eventi<Input type="number" value={p.max_events ?? -1} onChange={(e) => set("max_events", parseInt(e.target.value, 10))} data-testid={`saas-max-events-${k}`} /></label>
        <label>Max utenti<Input type="number" value={p.max_users ?? -1} onChange={(e) => set("max_users", parseInt(e.target.value, 10))} data-testid={`saas-max-users-${k}`} /></label>
      </div>
      <p className="text-[11px] text-slate-400">Videochiamate: 0 = solo email, -1 = illimitate. Eventi/utenti: -1 = illimitati (utenti = account con accesso, esclusi staff e volontari).</p>
      <div className="flex flex-wrap gap-1.5">{catalog.map((f) => (
        <button key={f.key} type="button" onClick={() => toggle(f.key)} data-testid={`saas-feature-${k}-${f.key}`}
          className={`rounded-full px-2.5 py-1 text-xs border ${p.features.includes(f.key) ? "bg-[#0ABAB5]/15 border-[#0ABAB5] text-slate-900" : "border-slate-200 text-slate-400"}`}>{f.label}</button>
      ))}</div>
    </div>
  );
}

function ConfigTab() {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/platform/saas/config").then(({ data }) => setCfg(data)).catch(err); }, []);
  if (!cfg) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const save = async () => {
    if (!window.confirm("Salvare la configurazione? I nuovi prezzi valgono solo per i nuovi abbonamenti: quelli esistenti mantengono il prezzo sottoscritto.")) return;
    setBusy(true);
    try { const { data } = await api.put("/platform/saas/config", { trial_days: cfg.trial_days, trial_video_quota: cfg.trial_video_quota, plans: cfg.plans }); setCfg(data); toast.success("Configurazione salvata"); }
    catch (e) { err(e); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      <div className="text-xs text-slate-500" data-testid="saas-stripe-mode">Stripe: <b>{cfg.stripe_mode?.toUpperCase()}</b>{cfg.stripe_mode === "live" && !cfg.live_enabled ? " · abbonamenti LIVE disattivati (SAAS_STRIPE_LIVE_ENABLED=0)" : ""} · versione {cfg.version}</div>
      <div className="grid grid-cols-2 gap-3 max-w-md text-xs">
        <label>Durata prova (giorni)<Input type="number" value={cfg.trial_days} onChange={(e) => setCfg({ ...cfg, trial_days: parseInt(e.target.value, 10) })} data-testid="saas-trial-days" /></label>
        <label>Videochiamate in prova<Input type="number" value={cfg.trial_video_quota} onChange={(e) => setCfg({ ...cfg, trial_video_quota: parseInt(e.target.value, 10) })} data-testid="saas-trial-video" /></label>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">{["bronze", "silver", "gold"].map((k) => (
        <PlanEditor key={k} k={k} p={cfg.plans[k]} catalog={cfg.feature_catalog} onChange={(p) => setCfg({ ...cfg, plans: { ...cfg.plans, [k]: p } })} />
      ))}</div>
      <Button onClick={save} disabled={busy} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="saas-config-save"><Save className="w-4 h-4 mr-1.5" />Salva configurazione</Button>
    </div>
  );
}

const TYPE = { cliente: "Cliente", interna: "Interna", internal: "Interna", test: "Test" };
const formulaOf = (r) => (r.mode === "trial" ? (r.purchased ? r.paid_plan : null) : r.plan || r.assigned_plan || r.admin?.plan || r.paid_plan || null);

function OrgsFilters({ q, setQ, fp, setFp, fs, setFs, fe, setFe, ft, setFt }) {
  const s = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";
  return (
    <div className="flex flex-wrap gap-2 mb-3" data-testid="saas-filters">
      <div className="relative w-full sm:w-64"><Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca organizzazione" className="pl-8 h-9" data-testid="saas-search" /></div>
      <select value={ft} onChange={(e) => setFt(e.target.value)} className={s} data-testid="saas-filter-type"><option value="">Tutti i tipi</option><option value="cliente">Cliente</option><option value="interna">Interna</option><option value="test">Test</option></select>
      <select value={fp} onChange={(e) => setFp(e.target.value)} className={s} data-testid="saas-filter-plan"><option value="">Tutte le formule</option><option value="none">Nessuna formula</option><option value="bronze">BRONZE</option><option value="silver">SILVER</option><option value="gold">GOLD</option></select>
      <select value={fs} onChange={(e) => setFs(e.target.value)} className={s} data-testid="saas-filter-status"><option value="">Tutti gli stati</option><option value="trial">Prova gratuita</option><option value="active">Attivo</option><option value="expired">Scaduto</option><option value="suspended">Sospeso</option></select>
      <select value={fe} onChange={(e) => setFe(e.target.value)} className={s} data-testid="saas-filter-expiry"><option value="">Qualsiasi scadenza</option><option value="7">Entro 7 giorni</option><option value="30">Entro 30 giorni</option><option value="past">Già scaduti</option></select>
    </div>
  );
}
const endOf = (r) => r.expires_at;
const stOf = (r) => (r.mode === "canceled" ? "expired" : r.mode === "past_due" ? "active" : r.mode);

function OrgsTab() {
  const [rows, setRows] = useState(null);
  const [edit, setEdit] = useState(null);
  const [q, setQ] = useState(""); const [fp, setFp] = useState(""); const [fs, setFs] = useState(""); const [fe, setFe] = useState(""); const [ft, setFt] = useState("");
  const load = useCallback(() => api.get("/platform/saas/organizations").then(({ data }) => setRows(data)).catch(err), []);
  useEffect(() => { load(); }, [load]);
  const post = async (url, body, msg) => { try { await api.post(url, body); toast.success(msg); load(); } catch (e) { err(e); } };
  if (!rows) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const now = Date.now();
  const shown = rows.filter((r) => (!q || (r.nome || "").toLowerCase().includes(q.toLowerCase())) && (!ft || (TYPE[r.type] || "").toLowerCase() === ft) && (!fp || (formulaOf(r) || "none") === fp)
    && (!fs || stOf(r) === fs) && (!fe || (() => { const e = endOf(r); if (!e) return false; const dd = (new Date(e) - now) / 864e5; return fe === "past" ? dd < 0 : dd >= 0 && dd <= Number(fe); })()));
  return (
    <>
    <OrgsFilters {...{ q, setQ, fp, setFp, fs, setFs, fe, setFe, ft, setFt }} />
    {edit && <SubscriptionEditDialog row={edit} onClose={() => setEdit(null)} onSaved={load} />}
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white" data-testid="saas-orgs-table">
      <table className="w-full min-w-[1100px] text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Organizzazione", "Tipo", "Formula", "Stato", "Condizione", "Periodicità", "Data inizio", "Data scadenza", "Prossimo rinnovo", "Utenti", "Eventi", "Pagamenti", "Videochiamate", "Azioni"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr></thead>
        <tbody>{shown.map((r) => (
          <tr key={r.id} className="border-t border-slate-100" data-testid={`saas-org-${r.id}`}>
            <td className="px-3 py-2 font-medium">{r.nome}{r.admin?.comp ? <span className="ml-1 text-[10px] rounded bg-emerald-50 text-emerald-700 px-1">Omaggio</span> : null}</td>
            <td className="px-3 py-2" data-testid={`saas-type-${r.id}`}>{TYPE[r.type] || "Cliente"}</td>
            <td className="px-3 py-2">{r.model === "abbonamento" ? <FormulaBadge plan={formulaOf(r)} testid={`saas-badge-${r.id}`} /> : "—"}{r.pending_change ? ` → ${r.pending_change.plan.toUpperCase()}` : ""}</td>
            <td className="px-3 py-2" data-testid={`saas-status-${r.id}`}>{r.mode ? MODE[r.mode] : r.model === "abbonamento" ? "Accesso completo" : "—"}{r.mode === "trial" ? ` (${r.days_left} gg)` : ""}{r.cancel_at_period_end ? " · annullato a fine periodo" : ""}</td>
            <td className="px-3 py-2" data-testid={`saas-billing-${r.id}`}>{BILLING[r.billing] || "—"}</td>
            <td className="px-3 py-2">{(r.admin?.billing_cycle || r.billing_cycle) === "yearly" ? "Annuale" : (r.admin?.billing_cycle || r.billing_cycle) === "monthly" ? "Mensile" : "—"}</td>
            <td className="px-3 py-2">{d(r.mode === "trial" ? r.trial_start : r.admin?.access_start || r.current_period_start || r.activated_at)}</td>
            <td className="px-3 py-2" data-testid={`saas-expiry-${r.id}`}>{endOf(r) ? d(endOf(r)) : r.billing === "free" ? "Nessuna scadenza" : "—"}</td>
            <td className="px-3 py-2">{r.billing === "free" ? "Nessun addebito" : d(r.admin?.renewal_date || (r.stripe_status === "active" ? r.current_period_end : null))}</td>
            <td className="px-3 py-2">{r.users_count ?? "—"}{r.limits?.max_users > 0 ? `/${r.limits.max_users}` : ""}</td>
            <td className="px-3 py-2">{r.events_count ?? "—"}{r.limits?.max_events > 0 ? `/${r.limits.max_events}` : ""}</td>
            <td className="px-3 py-2">{r.payments_count ?? "—"}{r.payments_total ? ` · €${r.payments_total}` : ""}</td>
            <td className="px-3 py-2">{r.model !== "abbonamento" ? "—" : r.video_unlimited ? `${r.video_used ?? 0} · illimitate` : r.video_quota ? `${r.video_used ?? 0}/${r.video_quota}` : "Email"}</td>
            <td className="px-3 py-2 whitespace-nowrap space-x-1">
              {r.model === "abbonamento" && <Button size="sm" variant="outline" onClick={() => setEdit(r)} data-testid={`saas-edit-${r.id}`}><Pencil className="w-3.5 h-3.5 mr-1" />Modifica</Button>}
              {r.model !== "abbonamento"
                ? <Button size="sm" variant="outline" onClick={() => window.confirm(`Passare ${r.nome} al modello ad abbonamento con prova GOLD? Operazione non reversibile dall'interfaccia.`) && post(`/platform/saas/orgs/${r.id}/enable-trial`, {}, "Prova GOLD attivata")} data-testid={`saas-enable-${r.id}`}>Attiva prova</Button>
                : <>
                  {r.type === "cliente" && <Button size="sm" variant="outline" onClick={() => post(`/platform/saas/orgs/${r.id}/extend-trial`, { days: 7 }, "Prova estesa di 7 giorni")} data-testid={`saas-extend-${r.id}`}>+7 gg prova</Button>}
                  {r.video_quota && r.video_used > 0 ? <Button size="sm" variant="outline" onClick={() => post(`/platform/saas/orgs/${r.id}/video-adjust`, { delta: -1, note: "rettifica" }, "Videochiamata restituita")} data-testid={`saas-video-minus-${r.id}`}>-1 video</Button> : null}
                </>}
            </td>
          </tr>
        ))}</tbody>
      </table>
    </div>
    </>
  );
}

function MigrationTab() {
  const [r, setR] = useState(null);
  useEffect(() => { api.get("/platform/saas/migration-report").then(({ data }) => setR(data)).catch(err); }, []);
  if (!r) return <p className="text-sm text-slate-400">Analisi in corso...</p>;
  const t = r.totals;
  return (
    <div className="space-y-4" data-testid="saas-migration">
      <p className="text-sm text-slate-600">Analisi in sola lettura del modello a crediti: nessun dato viene modificato o convertito.</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        {[["Organizzazioni a crediti", t.orgs_credits], ["Saldo crediti totale", t.balance], ["Crediti acquistati", t.purchased_credits], ["Eventi attivi", t.events_active], ["Rinnovi programmati", t.renewals_scheduled], ["Utilizzi IA", t.ai_uses], ["Fatture registrate", t.invoices]].map(([l, v]) => (
          <div key={l} className="rounded-lg border border-slate-200 bg-white p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-lg font-bold">{v}</div></div>
        ))}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[800px] text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Organizzazione", "Modello", "Saldo", "Acquistati", "Promozionali", "Eventi", "Attivi", "Rinnovi", "IA", "Fatture"].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
        <tbody>{r.orgs.map((o) => <tr key={o.id} className="border-t border-slate-100"><td className="px-3 py-2">{o.nome}</td><td className="px-3 py-2">{o.model}</td><td className="px-3 py-2">{o.balance}</td><td className="px-3 py-2">{o.purchased_credits}</td><td className="px-3 py-2">{o.promo_credits}</td><td className="px-3 py-2">{o.events_total}</td><td className="px-3 py-2">{o.events_active}</td><td className="px-3 py-2">{o.renewals_scheduled}</td><td className="px-3 py-2">{o.ai_uses}</td><td className="px-3 py-2">{o.invoices}</td></tr>)}</tbody>
      </table></div>
    </div>
  );
}

export default function SaasAdmin({ embedded = false }) {
  return (
    <div className="animate-fade-up space-y-4" data-testid="saas-admin-page">
      {!embedded && <PageHeader title="Abbonamenti" subtitle="Piani BRONZE, SILVER e GOLD: prezzi, funzionalità, prova gratuita e stato delle organizzazioni" />}
      <Tabs defaultValue="orgs">
        <TabsList className="mb-4 w-full sm:w-auto overflow-x-auto justify-start h-auto flex-nowrap">
          <TabsTrigger value="orgs" data-testid="saas-tab-orgs">Organizzazioni</TabsTrigger>
          <TabsTrigger value="config" data-testid="saas-tab-config">Piani e prezzi</TabsTrigger>
        </TabsList>
        <TabsContent value="orgs"><SectionCard title="Stato abbonamenti"><OrgsTab /></SectionCard></TabsContent>
        <TabsContent value="config"><SectionCard title="Configurazione piani"><ConfigTab /></SectionCard></TabsContent>
      </Tabs>
    </div>
  );
}
