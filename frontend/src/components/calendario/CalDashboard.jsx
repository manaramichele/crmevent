import { useEffect, useState } from "react";
import api from "@/lib/api";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { calApi, err, DISC_LABEL } from "./shared";

const Kpi = ({ l, v, id }) => (
  <div className="bg-white border border-slate-200 rounded-xl p-3" data-testid={`cal-kpi-${id}`}><div className="text-xs text-slate-500">{l}</div><div className="text-xl font-bold text-slate-900">{v ?? "—"}</div></div>
);
const Chart = ({ title, data, x, id }) => (
  <div className="bg-white border border-slate-200 rounded-2xl p-4 min-w-0" data-testid={`cal-chart-${id}`}>
    <div className="font-semibold text-slate-900 text-sm">{title}</div>
    <div className="h-56 mt-2"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ left: -20, right: 4 }}>
      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E2E8F0" /><XAxis dataKey={x} tick={{ fontSize: 10 }} interval={0} angle={data.length > 8 ? -35 : 0} textAnchor={data.length > 8 ? "end" : "middle"} height={data.length > 8 ? 50 : 24} />
      <YAxis tick={{ fontSize: 10 }} allowDecimals={false} /><Tooltip /><Bar dataKey="n" fill="#0ABAB5" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
  </div>
);

export function CalDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get(calApi("/dashboard")).then(({ data }) => setD(data)).catch(err); }, []);
  if (!d) return <p className="text-sm text-slate-500">Caricamento...</p>;
  const k = d.kpi;
  return (
    <div className="space-y-4" data-testid="cal-dashboard">
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-2">
        <Kpi id="eventi" l="Eventi censiti" v={k.eventi} /><Kpi id="anno" l={`Eventi ${d.anni[0]}`} v={k.anno_corrente} /><Kpi id="prossimo" l={`Eventi ${d.anni[1]}`} v={k.anno_prossimo} />
        <Kpi id="org" l="Organizzatori unici" v={k.organizzatori} /><Kpi id="email" l="Organizzatori con email" v={k.con_email} /><Kpi id="verificare" l="Contatti da verificare" v={k.da_verificare} />
        <Kpi id="idonei" l="Idonei alla comunicazione" v={k.idonei} /><Kpi id="programmate" l="Email programmate" v={k.email_programmate} /><Kpi id="inviate" l="Email inviate" v={k.email_inviate} />
        <Kpi id="demo" l="Demo richieste" v={k.demo_richieste} /><Kpi id="clienti" l="Clienti acquisiti" v={k.clienti} /><Kpi id="dup" l="Duplicati / conflitti aperti" v={`${k.duplicati_aperti} / ${k.conflitti_aperti}`} />
      </div>
      <p className="text-xs text-slate-400">Email, aperture, clic e risposte verranno conteggiate dalla Fase 3 (integrazione Brevo). Nessun invio è attivo.</p>
      <div className="grid lg:grid-cols-2 gap-4">
        <Chart id="mese" title={`Eventi per mese (${d.anni.join("–")})`} data={d.per_mese} x="mese" />
        <Chart id="disciplina" title="Eventi per disciplina" data={d.per_disciplina.map((x) => ({ ...x, k: DISC_LABEL[x.k] || x.k }))} x="k" />
        <Chart id="regione" title="Eventi per regione" data={d.per_regione} x="k" />
        <Chart id="distanza" title="Distribuzione per distanza" data={d.per_distanza} x="k" />
      </div>
    </div>
  );
}
