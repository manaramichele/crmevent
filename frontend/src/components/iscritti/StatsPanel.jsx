import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, LineChart, Line } from "recharts";

const COLORS = ["#0ABAB5", "#0F172A", "#F59E0B", "#E11D48", "#6366F1", "#10B981", "#64748B", "#A855F7"];
const SEL = "h-10 rounded-md border border-slate-200 px-3 text-sm bg-white min-w-0";
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("it-IT"));

function Card({ title, sub, children, id }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4 min-w-0" data-testid={`stats-chart-${id}`}>
      <div className="font-semibold text-slate-900">{title}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
      <div className="h-64 sm:h-72 mt-3">{children}</div>
    </div>
  );
}

function Kpi({ label, v, id, hint }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-3" data-testid={`stats-kpi-${id}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-bold text-slate-900">{v}</div>
      {hint && <div className="text-[11px] text-slate-400 truncate">{hint}</div>}
    </div>
  );
}

const ax = { tick: { fontSize: 11, fill: "#64748B" }, tickLine: false, axisLine: false };
const short = (v) => String(v).replace(/ · (\d)ª edizione$/, " · $1ª");
const Bars = ({ data, xKey, keys, stacked, unit }) => (
  <ResponsiveContainer width="100%" height="100%">
    <BarChart key={keys.join("|")} data={data} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
      <XAxis dataKey={xKey} {...ax} tickFormatter={short} minTickGap={2} angle={data.length > 4 ? -35 : 0} textAnchor={data.length > 4 ? "end" : "middle"} height={data.length > 4 ? 56 : 30} />
      <YAxis {...ax} unit={unit} />
      <Tooltip formatter={(v) => `${fmt(v)}${unit || ""}`} />
      {keys.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
      {keys.map((k, i) => <Bar key={k} dataKey={k} stackId={stacked ? "s" : undefined} fill={COLORS[i % COLORS.length]} radius={stacked ? 0 : [4, 4, 0, 0]} />)}
    </BarChart>
  </ResponsiveContainer>
);

function StatsFilters({ f, setF, eds, org }) {
  const events = [...new Map(eds.map((e) => [e.event_id, e.event_nome])).entries()];
  const anni = [...new Set(eds.filter((e) => !f.event_id || e.event_id === f.event_id).map((e) => e.anno))].sort();
  const gare = [...new Set(eds.flatMap((e) => e.gare || []))];
  const toggle = (a) => setF({ ...f, anni: f.anni.includes(a) ? f.anni.filter((x) => x !== a) : [...f.anni, a], edizione_id: "" });
  return (
    <div className="space-y-2" data-testid="stats-filters">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <select className={SEL} disabled value="" data-testid="stats-filter-org"><option value="">{org || "Organizzazione"}</option></select>
        <select className={SEL} value={f.event_id} onChange={(e) => setF({ ...f, event_id: e.target.value, edizione_id: "" })} data-testid="stats-filter-event"><option value="">Tutti gli eventi</option>{events.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>
        <select className={SEL} value={f.edizione_id} onChange={(e) => setF({ ...f, edizione_id: e.target.value })} data-testid="stats-filter-edizione"><option value="">Tutte le edizioni</option>{eds.filter((e) => (!f.event_id || e.event_id === f.event_id) && (!f.anni.length || f.anni.includes(e.anno))).map((e) => <option key={e.id} value={e.id}>{e.event_nome} {e.anno} {e.edizione}</option>)}</select>
        <select className={SEL} value={f.gara} onChange={(e) => setF({ ...f, gara: e.target.value })} data-testid="stats-filter-gara"><option value="">Tutte le distanze</option>{gare.map((g) => <option key={g}>{g}</option>)}</select>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="stats-filter-anni">
        <span className="text-slate-500">Anni:</span>
        {anni.map((a) => (
          <button key={a} type="button" onClick={() => toggle(a)} data-testid={`stats-anno-${a}`}
            className={`h-8 px-3 rounded-full border text-xs font-semibold transition-colors ${f.anni.includes(a) ? "bg-[#0ABAB5] border-[#0ABAB5] text-slate-900" : "border-slate-200 text-slate-600 hover:border-[#0ABAB5]"}`}>{a}</button>
        ))}
        {f.anni.length > 0 && <button type="button" className="text-xs text-[#088F8A] font-semibold" onClick={() => setF({ ...f, anni: [] })} data-testid="stats-anni-reset">Tutti</button>}
      </div>
    </div>
  );
}

export function StatsPanel({ eds }) {
  const [f, setF] = useState({ event_id: "", anni: [], edizione_id: "", gara: "" });
  const [mode, setMode] = useState("days");
  const [d, setD] = useState(null);
  const params = useMemo(() => ({ ...Object.fromEntries(Object.entries(f).filter(([k, v]) => k !== "anni" && v)), ...(f.anni.length ? { anni: f.anni.join(",") } : {}), mode }), [f, mode]);
  useEffect(() => {
    const t = setTimeout(() => { api.get("/iscritti/stats", { params }).then(({ data }) => setD(data)).catch(() => setD(null)); }, 200);
    return () => clearTimeout(t);
  }, [params]);
  const k = d?.kpi;
  return (
    <div className="space-y-4" data-testid="iscritti-stats">
      {d?.demo && <div className="rounded-xl bg-amber-50 border border-amber-200 px-3 py-2 text-xs font-semibold text-amber-800" data-testid="stats-demo-badge">DEMO · dati fittizi a scopo dimostrativo, mai sincronizzati con Brevo</div>}
      <StatsFilters f={f} setF={setF} eds={eds} org={d?.org_nome} />
      {!d ? <p className="text-sm text-slate-500">Caricamento statistiche...</p> : !k.totale ? <p className="text-sm text-slate-500" data-testid="stats-empty">Nessuna partecipazione per questi filtri.</p> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
            <Kpi id="totale" label="Totale iscritti" v={fmt(k.totale)} hint={`${fmt(k.unici)} persone uniche`} />
            <Kpi id="variazione" label="Variazione vs precedente" v={k.variazione == null ? "—" : `${k.variazione > 0 ? "+" : ""}${k.variazione.toLocaleString("it-IT")}%`} hint={[...k.variazione_rif].reverse().join(" vs ")} />
            <Kpi id="ricorrenti" label="Partecipanti ricorrenti" v={fmt(k.ricorrenti)} />
            <Kpi id="genere" label="Uomini / Donne" v={`${k.uomini_pct.toLocaleString("it-IT")}% / ${k.donne_pct.toLocaleString("it-IT")}%`} />
            <Kpi id="eta" label="Età media" v={k.eta_media == null ? "—" : `${k.eta_media.toLocaleString("it-IT")} anni`} />
            <Kpi id="nazionalita" label="Nazionalità" v={fmt(k.nazionalita)} />
            <Kpi id="distanza" label="Distanza più scelta" v={k.distanza_top || "—"} />
          </div>
          <div className="grid lg:grid-cols-2 gap-4">
            <Card id="evoluzione" title="Evoluzione iscritti" sub="Iscritti per edizione"><Bars data={d.evolution} xKey="label" keys={["n"]} /></Card>
            <Card id="distanze" title="Iscritti per distanza" sub="Confronto per anno e distanza"><Bars data={d.distance} xKey="label" keys={d.gare} /></Card>
            <Card id="genere" title="Uomini e donne" sub="Distribuzione percentuale per edizione"><Bars data={d.gender} xKey="label" keys={["Uomini", "Donne"]} stacked unit="%" /></Card>
            <Card id="eta" title="Fasce d'età" sub="Età nell'anno dell'edizione"><Bars data={d.ages} xKey="fascia" keys={d.labels} /></Card>
            <Card id="nazionalita" title="Nazionalità" sub="Principali nazionalità per edizione"><Bars data={d.nationalities} xKey="nazionalita" keys={d.labels} /></Card>
            <Card id="ricorrenti" title="Nuovi e ricorrenti" sub="Ricorrente = già iscritto a un'edizione precedente dello stesso evento"><Bars data={d.new_recurring} xKey="label" keys={["Nuovi", "Ricorrenti"]} stacked /></Card>
          </div>
          <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="stats-chart-andamento">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div><div className="font-semibold text-slate-900">Andamento iscrizioni</div><div className="text-xs text-slate-500">Iscrizioni cumulative prima dell'evento, edizioni allineate sulla data di gara</div></div>
              <div className="flex rounded-full border border-slate-200 p-0.5 text-xs font-semibold" data-testid="stats-trend-mode">
                {[["days", "Giorni mancanti"], ["months", "Mesi"]].map(([m, l]) => <button key={m} type="button" onClick={() => setMode(m)} data-testid={`stats-trend-${m}`} className={`h-8 px-3 rounded-full transition-colors ${mode === m ? "bg-[#0ABAB5] text-slate-900" : "text-slate-600"}`}>{l}</button>)}
              </div>
            </div>
            <div className="h-72 sm:h-80 mt-3">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={d.trend} margin={{ top: 4, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" />
                  <XAxis dataKey="x" {...ax} minTickGap={24} />
                  <YAxis {...ax} />
                  <Tooltip formatter={(v) => fmt(v)} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {d.labels.map((l, i) => <Line key={l} type="monotone" dataKey={l} stroke={COLORS[i % COLORS.length]} strokeWidth={2.5} dot={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
