import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/crm";
import { Save, Rocket, FlaskConical, FileText, RefreshCw } from "lucide-react";
import { inputCls, ROLE_OPTIONS, STEP_LABELS } from "./accessShared";

const NUMS = [
  ["inactive_first_days", "Primo promemoria inattivi (giorni senza accesso)"],
  ["inactive_second_extra_days", "Secondo promemoria inattivi (giorni dopo il primo)"],
  ["never_first_days", "Mai entrati: primo promemoria (giorni)"],
  ["never_second_days", "Mai entrati: secondo promemoria (giorni complessivi)"],
  ["inactivity_timeout_min", "Inattività dopo (minuti senza interazioni)"],
  ["run_hour", "Orario giornaliero di esecuzione (0-23, ora italiana)"],
  ["retention_months", "Conservazione storico sessioni (mesi)"],
];

function Num({ k, label, cfg, set }) {
  return (
    <label className="text-sm text-slate-600 space-y-1 block">
      <span>{label}</span>
      <input type="number" data-testid={`access-cfg-${k}`} className={`${inputCls} w-full`} value={cfg[k] ?? ""} onChange={(e) => set(k, e.target.value === "" ? "" : Number(e.target.value))} />
    </label>
  );
}

function MultiCheck({ title, options, value, onChange, id }) {
  const toggle = (v) => onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  return (
    <div className="space-y-1.5" data-testid={id}>
      <div className="text-sm font-medium text-slate-700">{title}</div>
      <div className="flex flex-wrap gap-2">{options.map((o) => (
        <button type="button" key={o.value} onClick={() => toggle(o.value)} data-testid={`${id}-${o.value}`}
          className={`px-3 py-1 rounded-full text-xs border transition-colors ${value.includes(o.value) ? "bg-tiffany/15 border-tiffany text-slate-900" : "bg-white border-slate-200 text-slate-500"}`}>{o.label}</button>))}
      </div>
    </div>
  );
}

function Templates({ cfg, set, tpls, reloadTpls }) {
  const [busy, setBusy] = useState(false);
  const setup = async () => {
    setBusy(true);
    try { await api.post("/platform/access/templates/setup"); toast.success("Template bozza collegati"); reloadTpls(true); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="access-templates">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-700">Template Brevo e tipo di comunicazione</div>
        <Button variant="outline" size="sm" onClick={setup} disabled={busy} data-testid="access-templates-setup"><FileText className="w-4 h-4 mr-1" />Crea/collega bozze in Brevo</Button>
      </div>
      {Object.keys(STEP_LABELS).map((s) => {
        const b = (tpls.find((t) => t.step === s) || {}).brevo;
        return (
          <div key={s} className="grid grid-cols-1 md:grid-cols-[1fr_140px_170px_1fr] gap-2 items-center">
            <span className="text-sm text-slate-700">{STEP_LABELS[s]}</span>
            <input data-testid={`access-tpl-${s}`} placeholder="ID template" className={inputCls} value={cfg.templates[s] ?? ""} onChange={(e) => set("templates", { ...cfg.templates, [s]: e.target.value })} />
            <select data-testid={`access-kind-${s}`} className={inputCls} value={cfg.kinds[s]} onChange={(e) => set("kinds", { ...cfg.kinds, [s]: e.target.value })}>
              <option value="service">Servizio</option><option value="promotional">Promozionale (serve consenso)</option>
            </select>
            <span className="text-xs text-slate-500">{b ? (b.error ? `Errore: ${b.error}` : <>{b.name} · <StatusBadge color={b.active ? "green" : "orange"}>{b.active ? "Attivo" : "Bozza"}</StatusBadge></>) : "—"}</span>
          </div>);
      })}
    </div>
  );
}

function ModeBar({ cfg, onActivate, onDeactivate, onSync }) {
  const live = cfg.enabled && cfg.mode === "live";
  return (
    <div className={`rounded-xl border p-4 flex flex-wrap items-center justify-between gap-3 ${live ? "border-emerald-300 bg-emerald-50" : "border-amber-300 bg-amber-50"}`} data-testid="access-mode-bar">
      <div className="text-sm">
        <div className="font-semibold text-slate-900" data-testid="access-mode-label">{live ? "Invio reale attivo" : "Modalità simulazione: nessuna email viene inviata"}</div>
        {cfg.fake_send && <div className="text-xs text-slate-600">Ambiente di sviluppo: anche in invio reale le email sono solo registrate come prova, non spedite.</div>}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={onSync} data-testid="access-brevo-sync"><RefreshCw className="w-4 h-4 mr-1" />Sincronizza attributi Brevo</Button>
        {live ? <Button variant="outline" size="sm" onClick={onDeactivate} data-testid="access-deactivate-btn"><FlaskConical className="w-4 h-4 mr-1" />Torna alla simulazione</Button>
          : <Button size="sm" onClick={onActivate} data-testid="access-activate-btn" className="bg-slate-900 text-white hover:bg-slate-800"><Rocket className="w-4 h-4 mr-1" />Attiva invio reale</Button>}
      </div>
    </div>
  );
}

export function AccessReminderSettings() {
  const [cfg, setCfg] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [tpls, setTpls] = useState([]);
  const loadTpls = () => api.get("/platform/access/templates").then(({ data }) => setTpls(data)).catch(() => {});
  const reloadTpls = (withCfg) => { loadTpls(); if (withCfg) api.get("/platform/access/config").then(({ data }) => setCfg(data)); };
  useEffect(() => {
    api.get("/platform/access/config").then(({ data }) => setCfg(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
    api.get("/platform/organizations").then(({ data }) => setOrgs(data.map((o) => ({ value: o.id, label: o.nome })))).catch(() => {});
    loadTpls();
  }, []);
  if (!cfg) return <p className="text-sm text-slate-400">Caricamento…</p>;
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));
  const act = async (fn, ok) => { try { const { data } = await fn(); setCfg(data); toast.success(ok); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const save = () => {
    const empty = NUMS.find(([k]) => cfg[k] === "" || cfg[k] === null || Number.isNaN(Number(cfg[k])));
    if (empty) { toast.error(`Inserisci un numero valido: ${empty[1]}`); return; }
    act(() => api.put("/platform/access/config", cfg), "Impostazioni salvate").then(loadTpls);
  };
  const activate = () => { if (window.confirm("Attivare l'invio reale dei promemoria? Le email partiranno all'orario configurato.")) act(() => api.post("/platform/access/activate", { confirm: true }), "Invio reale attivato"); };
  const sync = async () => { try { const { data } = await api.post("/platform/access/brevo-sync"); toast.success(data.skipped ? data.reason : `Sincronizzati ${data.synced} contatti`); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  return (
    <div className="space-y-4" data-testid="access-reminder-settings">
      <ModeBar cfg={cfg} onActivate={activate} onDeactivate={() => act(() => api.post("/platform/access/deactivate"), "Simulazione attiva")} onSync={sync} />
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-5">
        <div className="flex flex-wrap gap-6">
          <label className="flex items-center gap-2 text-sm"><Switch checked={!!cfg.enabled} onCheckedChange={(v) => set("enabled", v)} data-testid="access-cfg-enabled" />Automazione attiva</label>
          <label className="flex items-center gap-2 text-sm"><Switch checked={!!cfg.never_enabled} onCheckedChange={(v) => set("never_enabled", v)} data-testid="access-cfg-never-enabled" />Promemoria per utenti mai entrati</label>
          <label className="flex items-center gap-2 text-sm">Conteggio mai entrati da
            <select data-testid="access-cfg-never-start" className={inputCls} value={cfg.never_start_from} onChange={(e) => set("never_start_from", e.target.value)}>
              <option value="registration">Registrazione account</option><option value="activation">Attivazione account</option>
            </select></label>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">{NUMS.map(([k, l]) => <Num key={k} k={k} label={l} cfg={cfg} set={set} />)}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MultiCheck id="access-roles-include" title="Ruoli inclusi" options={ROLE_OPTIONS} value={cfg.roles_include} onChange={(v) => set("roles_include", v)} />
          <MultiCheck id="access-roles-exclude" title="Ruoli esclusi" options={ROLE_OPTIONS} value={cfg.roles_exclude} onChange={(v) => set("roles_exclude", v)} />
          <MultiCheck id="access-orgs-include" title="Solo queste organizzazioni (vuoto = tutte)" options={orgs} value={cfg.orgs_include} onChange={(v) => set("orgs_include", v)} />
          <MultiCheck id="access-orgs-exclude" title="Organizzazioni escluse" options={orgs} value={cfg.orgs_exclude} onChange={(v) => set("orgs_exclude", v)} />
        </div>
        <Templates cfg={cfg} set={set} tpls={tpls} reloadTpls={reloadTpls} />
        <p className="text-xs text-slate-500">Le comunicazioni promozionali partono solo a chi ha dato il consenso marketing. Sono sempre esclusi gli account disabilitati, chi si è disiscritto e chi è bloccato in Brevo.</p>
        <Button onClick={save} data-testid="access-cfg-save" className="bg-tiffany hover:bg-tiffany/90 text-slate-900"><Save className="w-4 h-4 mr-1" />Salva impostazioni</Button>
      </div>
    </div>
  );
}
