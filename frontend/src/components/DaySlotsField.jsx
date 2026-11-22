import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Copy, RefreshCw, AlertTriangle } from "lucide-react";

const SLOTS = [["mattina", "Mattina"], ["pomeriggio", "Pomeriggio"]];
const empty = { attiva: true, start: "", end: "" };

export const slotErrors = (val) => {
  const errs = [];
  Object.entries(val || {}).forEach(([d, cfg]) => {
    const m = { ...empty, ...(cfg.mattina || {}) };
    const p = { ...empty, ...(cfg.pomeriggio || {}) };
    [[m, "Mattina"], [p, "Pomeriggio"]].forEach(([s, l]) => { if (s.attiva && s.start && s.end && s.end <= s.start) errs.push(`${d} ${l}: fine prima dell'inizio`); });
    if (m.attiva && p.attiva && m.end && p.start && p.start < m.end) errs.push(`${d}: Mattina e Pomeriggio si sovrappongono`);
  });
  return errs;
};

function Stale({ eventId }) {
  const [n, setN] = useState(0);
  const load = () => api.get(`/events/${eventId}/fasce-stale`).then(({ data }) => setN(data.stale)).catch(() => {});
  useEffect(() => { load(); }, [eventId]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!n) return null;
  const sync = async () => {
    if (!window.confirm(`Aggiornare gli orari di ${n} disponibilità già raccolte ai nuovi orari salvati? Le scelte Mattina/Pomeriggio restano invariate.`)) return;
    try { const { data } = await api.post(`/events/${eventId}/fasce-sync`); toast.success(`${data.updated} disponibilità aggiornate`); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="dayslots-stale">
      <AlertTriangle className="w-4 h-4" />{n} disponibilità già raccolte hanno orari diversi da quelli salvati ora.
      <Button type="button" size="sm" variant="outline" className="h-7" onClick={sync} data-testid="dayslots-sync"><RefreshCw className="w-3.5 h-3.5 mr-1" />Aggiorna orari</Button>
    </div>
  );
}

export default function DaySlotsField({ days, value, onChange, eventId }) {
  const val = value || {};
  const get = (d, s) => ({ ...empty, ...((val[d] || {})[s] || {}) });
  const set = (d, s, patch) => onChange({ ...val, [d]: { mattina: get(d, "mattina"), pomeriggio: get(d, "pomeriggio"), [s]: { ...get(d, s), ...patch } } });
  const copyAll = (d) => onChange(Object.fromEntries(days.map((x) => [x.date, { mattina: get(d, "mattina"), pomeriggio: get(d, "pomeriggio") }])));
  if (!days.length) return <div className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg p-3" data-testid="dayslots-empty">Imposta le date dell'evento per configurare le fasce Mattina e Pomeriggio.</div>;
  const errs = slotErrors(val);
  return (
    <div className="space-y-2" data-testid="field-fasce_disponibilita">
      {eventId && <Stale eventId={eventId} />}
      {days.map((d) => (
        <div key={d.date} className="rounded-lg border border-slate-200 p-2.5 flex flex-col lg:flex-row lg:items-center gap-2" data-testid={`dayslots-${d.date}`}>
          <div className="text-xs font-medium text-slate-600 capitalize lg:w-44">{d.label}</div>
          {SLOTS.map(([s, l]) => {
            const c = get(d.date, s);
            return (
              <div key={s} className={`flex items-center gap-1.5 ${c.attiva ? "" : "opacity-50"}`}>
                <label className="flex items-center gap-1 text-xs text-slate-700 w-24"><input type="checkbox" checked={c.attiva} onChange={(e) => set(d.date, s, { attiva: e.target.checked })} data-testid={`dayslots-${d.date}-${s}-on`} />{l}</label>
                <Input type="time" className="h-8 w-[104px]" disabled={!c.attiva} value={c.start || ""} onChange={(e) => set(d.date, s, { start: e.target.value })} data-testid={`dayslots-${d.date}-${s}-start`} />
                <span className="text-slate-400">–</span>
                <Input type="time" className="h-8 w-[104px]" disabled={!c.attiva} value={c.end || ""} onChange={(e) => set(d.date, s, { end: e.target.value })} data-testid={`dayslots-${d.date}-${s}-end`} />
              </div>);
          })}
          {days.length > 1 && <Button type="button" variant="ghost" size="sm" className="h-8 text-xs lg:ml-auto" onClick={() => copyAll(d.date)} data-testid={`dayslots-copy-${d.date}`}><Copy className="w-3.5 h-3.5 mr-1" />Copia su tutti i giorni</Button>}
        </div>))}
      {errs.length > 0 && <ul className="text-xs text-red-600 list-disc pl-5" data-testid="dayslots-errors">{errs.map((e) => <li key={e}>{e}</li>)}</ul>}
      <p className="text-[11px] text-slate-400">Il volontario sceglie solo Mattina e/o Pomeriggio: gli orari sono informativi. Le fasce non attive non compaiono nel modulo.</p>
    </div>
  );
}
