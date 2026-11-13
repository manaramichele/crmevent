import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

const FIELDS = [["titolo", "Titolo sezione"], ["sottotitolo", "Sottotitolo", true], ["cta_demo", "Pulsante demo"], ["cta_funzioni", "Pulsante funzionalità"],
  ["cta_funzioni_link", "Collegamento pulsante funzionalità (es. #funzionalita o https://...)"], ["nudge_titolo", "Invito alla registrazione: titolo"],
  ["nudge_testo", "Invito alla registrazione: testo", true], ["nudge_cta", "Invito alla registrazione: pulsante"]];
const STATS = [["view", "Visualizzazioni sezione"], ["start", "Avvii demo"], ["nudge", "Inviti mostrati"], ["cta_register", "Click su registrazione"],
  ["signup", "Registrazioni dalla demo"], ["import", "Progetti demo importati"], ["cta_features", "Click su funzionalità"], ["fullscreen", "Aperture a schermo intero"]];
const DETAIL = [["scenario", "Eventi dimostrativi scelti"], ["tool", "Strumenti usati"], ["place", "Oggetti più inseriti"]];
const TOOL = { select: "Seleziona", point: "Punto", line: "Percorso", polygon: "Area", rect: "Rettangolo" };

function Stats() {
  const [giorni, setGiorni] = useState(30);
  const [s, setS] = useState(null);
  useEffect(() => { api.get(`/planner-demo/stats?giorni=${giorni}`).then(({ data }) => setS(data)).catch(() => setS({ totali: {}, dettaglio: {} })); }, [giorni]);
  if (!s) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const t = s.totali;
  return (
    <div className="space-y-4" data-testid="pdemo-stats">
      <div className="flex items-center gap-2 text-sm">Periodo
        <select value={giorni} onChange={(e) => setGiorni(+e.target.value)} className="h-9 rounded-md border border-slate-200 bg-white px-2" data-testid="pdemo-stats-period">
          {[7, 30, 90, 365].map((g) => <option key={g} value={g}>Ultimi {g} giorni</option>)}</select></div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {STATS.map(([k, l]) => <div key={k} className="rounded-xl border border-slate-200 bg-white p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-2xl font-bold" data-testid={`pdemo-stat-${k}`}>{t[k] || 0}</div></div>)}
      </div>
      <p className="text-xs text-slate-500">Conversione avvii → registrazioni: <b>{t.start ? `${(((t.signup || 0) / t.start) * 100).toFixed(1)}%` : "—"}</b>. Conteggi anonimi aggregati per giorno: nessun cookie, nessun dato personale.</p>
      <div className="grid gap-3 md:grid-cols-3">
        {DETAIL.map(([k, l]) => { const rows = Object.entries(s.dettaglio[k] || {}).sort((a, b) => b[1] - a[1]).slice(0, 10); return (
          <div key={k} className="rounded-xl border border-slate-200 bg-white p-3 text-sm"><div className="mb-2 text-xs font-semibold">{l}</div>
            {rows.length ? rows.map(([v, n]) => <div key={v} className="flex justify-between border-b border-slate-100 py-1 last:border-0"><span className="truncate">{TOOL[v] || v}</span><b>{n}</b></div>) : <span className="text-xs text-slate-400">Nessun dato</span>}
          </div>); })}
      </div>
    </div>
  );
}

export default function PlannerDemoAdmin() {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/planner-demo/settings").then(({ data }) => setF(data)), []);
  useEffect(() => { load(); }, [load]);
  if (!f) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    try { const { scenari, ...body } = f; await api.put("/planner-demo/settings", { ...body, soglia_interazioni: +f.soglia_interazioni }); toast.success("Impostazioni salvate"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="max-w-5xl space-y-8" data-testid="pdemo-admin">
      <div><h1 className="font-display text-2xl font-bold">Event Planner in homepage</h1>
        <p className="text-sm text-slate-500">Sezione e demo pubblica di Event Planner su crmevent.it. Le modifiche sono visibili subito, senza toccare il codice.</p></div>
      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
        <label className="flex items-center gap-3 text-sm font-medium"><Switch checked={f.abilitata} onCheckedChange={(v) => setF({ ...f, abilitata: v })} data-testid="pdemo-enabled" />
          {f.abilitata ? "Sezione e demo visibili in homepage" : "Sezione nascosta in homepage"}</label>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-xs text-slate-500">Evento dimostrativo predefinito
            <select value={f.scenario_default} onChange={set("scenario_default")} className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-900" data-testid="pdemo-scenario">
              {Object.entries(f.scenari || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="text-xs text-slate-500">Mostra l'invito alla registrazione dopo N interazioni
            <Input type="number" min={1} max={50} value={f.soglia_interazioni} onChange={set("soglia_interazioni")} className="mt-1 text-sm text-slate-900" data-testid="pdemo-threshold" /></label>
          {FIELDS.map(([k, l, long]) => <label key={k} className={`text-xs text-slate-500 ${long ? "md:col-span-2" : ""}`}>{l}
            {long ? <Textarea value={f[k]} onChange={set(k)} rows={3} className="mt-1 text-sm text-slate-900" data-testid={`pdemo-${k}`} /> : <Input value={f[k]} onChange={set(k)} className="mt-1 text-sm text-slate-900" data-testid={`pdemo-${k}`} />}</label>)}
        </div>
        <Button onClick={save} disabled={busy} className="bg-tiffany text-slate-900 hover:bg-tiffany-hover" data-testid="pdemo-save">{busy ? "Salvataggio..." : "Salva impostazioni"}</Button>
      </div>
      <div><h2 className="mb-3 font-display text-lg font-bold">Statistiche della demo</h2><Stats /></div>
    </div>
  );
}
