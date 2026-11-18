import { useEffect, useState } from "react";
import { Users, IdCard, Wallet, HeartPulse, CalendarClock } from "lucide-react";
import api from "@/lib/api";
import { SectionCard } from "@/components/crm";
import { apiErr, fmtEur } from "@/components/asd/asdShared";
import { DeadlineList } from "@/components/asd/AsdScadenze";

function Kpi({ icon: Icon, label, value, sub, id, onClick, alert }) {
  return (
    <button type="button" onClick={onClick} className="text-left bg-white border border-slate-200 rounded-xl p-4 hover:border-slate-400 transition-colors" data-testid={`asd-kpi-${id}`}>
      <div className="flex items-center gap-2 text-xs text-slate-500"><Icon className="w-4 h-4" />{label}</div>
      <div className={`text-2xl font-bold mt-1 ${alert ? "text-red-600" : "text-slate-900"}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </button>
  );
}

export function AsdDashboard({ go, refreshKey }) {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/asd/dashboard").then(({ data }) => setD(data)).catch(apiErr); }, [refreshKey]);
  if (!d) return <p className="text-sm text-slate-500" data-testid="asd-dashboard-loading">Caricamento…</p>;
  const c = d.certificati;
  return (
    <div className="space-y-5" data-testid="asd-dashboard">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi icon={Users} id="soci" label="Soci attivi" value={d.soci_attivi} sub={`${d.soci_totali} in anagrafica`} onClick={() => go("soci")} />
        <Kpi icon={IdCard} id="tesserati" label="Tesserati validi" value={d.tesserati_validi} sub="soci attivi con tessera valida" onClick={() => go("tesseramenti")} />
        <Kpi icon={Wallet} id="quote" label="Da incassare" value={fmtEur(d.quote_da_incassare)} sub={`Incassato ${fmtEur(d.quote_incassate)} · ${d.quote_scadute} scadute`} alert={d.quote_scadute > 0} onClick={() => go("quote")} />
        <Kpi icon={HeartPulse} id="certificati" label="Certificati da sistemare" value={c.scaduto + c.mancante} sub={`${c.scaduto} scaduti · ${c.mancante} mancanti · ${c.in_scadenza} in scadenza`} alert={c.scaduto + c.mancante > 0} onClick={() => go("certificati")} />
        <Kpi icon={CalendarClock} id="scadenze" label="Scadenze superate" value={d.scadenze_scadute} sub="da gestire" alert={d.scadenze_scadute > 0} onClick={() => go("scadenze")} />
      </div>
      <SectionCard title="Scadute e prossimi 30 giorni" action={<button type="button" className="text-sm text-tiffany-active hover:underline" onClick={() => go("scadenze")} data-testid="asd-dashboard-all-deadlines">Tutte le scadenze</button>}>
        <DeadlineList rows={d.prossime_scadenze} testid="asd-dashboard-deadlines" />
      </SectionCard>
    </div>
  );
}
