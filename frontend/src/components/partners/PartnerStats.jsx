import { useEffect, useState } from "react";
import api from "@/lib/api";
import { eur, Card } from "@/components/partners/shared";

const KPI = [["clicks", "Click"], ["visitors", "Visitatori unici"], ["registrations", "Registrazioni"], ["trial", "In prova"], ["active", "Abbonamenti attivi"], ["conversion_rate", "Conversione %"], ["revenue_cents", "Fatturato generato"]];

export default function PartnerStats() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/platform/partner-stats").then(({ data }) => setD(data)).catch(() => setD(false)); }, []);
  if (d === false) return <p className="text-sm text-red-600" data-testid="partner-stats-error">Impossibile caricare le statistiche.</p>;
  if (!d) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const v = (k, x) => (k === "revenue_cents" ? eur(x[k]) : k === "conversion_rate" ? `${x[k]}%` : x[k]);
  return (
    <div className="space-y-5" data-testid="partner-stats">
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {KPI.map(([k, l]) => <div key={k} className="bg-white border border-slate-200 rounded-xl p-3" data-testid={`partner-kpi-${k}`}><div className="text-xs text-slate-500">{l}</div><div className="text-xl font-bold text-slate-900">{v(k, d.totals)}</div></div>)}
      </div>
      <Card title="Performance per partner" testid="partner-stats-table">
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-xs text-slate-500 bg-slate-50"><tr><th className="text-left p-2 pl-4">Partner</th>{KPI.map(([k, l]) => <th key={k} className="text-right p-2">{l}</th>)}</tr></thead>
          <tbody>{d.partners.map((p) => <tr key={p.partner_id} className="border-t border-slate-100"><td className="p-2 pl-4 font-medium">{p.name} <span className="text-xs text-slate-400">{p.code}</span></td>{KPI.map(([k]) => <td key={k} className="p-2 text-right tabular-nums">{v(k, p)}</td>)}</tr>)}</tbody></table></div>
        {!d.partners.length && <p className="p-4 text-sm text-slate-500">Nessun dato.</p>}
      </Card>
      <Card title="Performance campagne" testid="partner-campaign-table">
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-xs text-slate-500 bg-slate-50"><tr><th className="text-left p-2 pl-4">Partner</th><th className="text-left p-2">Campagna</th><th className="text-right p-2">Click</th><th className="text-right p-2">Visitatori</th><th className="text-right p-2">Registrazioni</th><th className="text-right p-2 pr-4">Conversioni</th></tr></thead>
          <tbody>{d.campaigns.map((c) => <tr key={`${c.partner_id}-${c.campaign}`} className="border-t border-slate-100"><td className="p-2 pl-4">{c.name}</td><td className="p-2">{c.campaign}</td><td className="p-2 text-right">{c.clicks}</td><td className="p-2 text-right">{c.visitors}</td><td className="p-2 text-right">{c.registrations}</td><td className="p-2 pr-4 text-right">{c.converted}</td></tr>)}</tbody></table></div>
        {!d.campaigns.length && <p className="p-4 text-sm text-slate-500">Nessuna campagna con traffico.</p>}
      </Card>
    </div>
  );
}
