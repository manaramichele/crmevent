import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { calApi, err, SEL, Pill } from "./shared";

const SC = { inviato: "#16A34A", simulato: "#6366F1", saltato: "#D97706", errore: "#DC2626" };
const SL = { inviato: "Inviato", simulato: "Simulato", saltato: "Saltato", errore: "Errore" };
const fmtDT = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

export function CommsPanel() {
  const [f, setF] = useState({ status: "", q: "" });
  const [d, setD] = useState(null);
  const [camps, setCamps] = useState([]);
  const load = useCallback(() => {
    api.get(calApi("/comms"), { params: f }).then(({ data }) => setD(data)).catch(err);
    api.get(calApi("/campaigns")).then(({ data }) => setCamps(data.campaigns)).catch(err);
  }, [f]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <p className="text-sm text-slate-500">Caricamento...</p>;
  return (
    <div className="space-y-4" data-testid="cal-comms">
      <div className="flex flex-wrap gap-2 text-xs">{Object.entries(SL).map(([k, l]) => <Pill key={k} color={SC[k]} testid={`cal-comms-tot-${k}`}>{l}: {d.totali[k] || 0}</Pill>)}</div>
      <div className="bg-white border border-slate-200 rounded-xl p-4 text-xs" data-testid="cal-campaigns-log"><div className="font-semibold text-sm mb-2">Campagne</div>
        {!camps.length && <p className="text-slate-500">Nessuna campagna.</p>}
        {camps.map((c) => <div key={c.id} className="border-t border-slate-100 py-1">{fmtDT(c.created_at)} · {c.template_nome} · {c.simulazione ? "simulazione" : "invio reale"} · {c.status} · {c.inviati}/{c.destinatari} ok, {c.errori} errori · {c.created_by}</div>)}
      </div>
      <div className="flex flex-wrap gap-2">
        <select className={SEL} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid="cal-comms-status"><option value="">Tutti gli esiti</option>{Object.entries(SL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <Input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="Cerca organizzatore, evento, email" className="h-9 max-w-xs" data-testid="cal-comms-search" />
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[760px] text-sm" data-testid="cal-comms-table">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Data", "Organizzatore", "Evento", "Template", "Esito"].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
        <tbody>{d.rows.map((c) => <tr key={c.id} className="border-t border-slate-100" data-testid={`cal-comm-${c.id}`}>
          <td className="px-3 py-2 text-xs">{fmtDT(c.at)}</td><td className="px-3 py-2">{c.organizzatore}<div className="text-[11px] text-slate-400">{c.email}</div></td>
          <td className="px-3 py-2">{c.evento}</td><td className="px-3 py-2 text-xs">{c.template_nome}</td>
          <td className="px-3 py-2"><Pill color={SC[c.status]}>{SL[c.status] || c.status}</Pill>{c.errore && <div className="text-[11px] text-red-600">{c.errore}</div>}</td></tr>)}</tbody>
      </table>{!d.rows.length && <p className="p-4 text-xs text-slate-500">Nessuna comunicazione.</p>}</div>
    </div>
  );
}
