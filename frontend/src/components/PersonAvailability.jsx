import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { RotateCcw } from "lucide-react";

const SL = { mattina: "Mattina", pomeriggio: "Pomeriggio" };
const longDay = (iso) => { const s = new Date(`${iso}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); return s.charAt(0).toUpperCase() + s.slice(1); };
const hrs = (s) => (s.start && s.end ? ` (${s.start}–${s.end})` : "");

function initState(days, prefDays) {
  const st = {};
  (prefDays || []).forEach((d) => {
    if (!d.date || d.disponibile === false) return;
    if (d.fasce?.length) { st[d.date] = { sel: d.fasce.map((f) => f.id), legacy: null, keep: false }; return; }
    const opts = days.find((x) => x.date === d.date)?.fasce || [];
    const one = opts.find((s) => s.start && s.start === d.dalle && s.end === d.alle);
    const [m, p] = [opts.find((s) => s.id === "mattina"), opts.find((s) => s.id === "pomeriggio")];
    if (one) st[d.date] = { sel: [one.id], legacy: d, keep: false, proposed: true };
    else if (m && p && m.start && m.start === d.dalle && p.end === d.alle && m.end === p.start) st[d.date] = { sel: ["mattina", "pomeriggio"], legacy: d, keep: false, proposed: true };
    else st[d.date] = { sel: [], legacy: d, keep: true };
  });
  return st;
}

const toPayload = (st) => Object.entries(st).sort(([a], [b]) => a.localeCompare(b))
  .map(([date, v]) => ((v.legacy && v.keep) || v.proposed ? { date, keep: true } : v.sel.length ? { date, fasce: ["mattina", "pomeriggio"].filter((x) => v.sel.includes(x)) } : null)).filter(Boolean);

function DayRow({ eid, day, v, onSet }) {
  const lg = v?.legacy;
  const toggle = (id, on) => { const sel = on ? [...(v?.sel || []), id] : (v?.sel || []).filter((x) => x !== id); onSet({ sel, legacy: lg || null, keep: lg ? (sel.length === 0 && v.keep) : false }); };
  return (
    <div className="rounded-lg border border-slate-200 px-3 py-2" data-testid={`mask-avail-${eid}-${day.date}`}>
      <div className="text-sm font-medium text-slate-800">{longDay(day.date)}</div>
      <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1">
        {(day.fasce || []).map((s) => (
          <label key={s.id} className="flex items-center gap-1.5 text-sm text-slate-700">
            <input type="checkbox" checked={(v?.sel || []).includes(s.id)} onChange={(e) => toggle(s.id, e.target.checked)} data-testid={`mask-avail-${eid}-${day.date}-${s.id}`} />{SL[s.id]}{hrs(s)}
          </label>))}
        {!(day.fasce || []).length && <span className="text-xs text-slate-400">Nessuna fascia attiva in questo giorno</span>}
      </div>
      {lg && (
        <div className={`mt-1.5 text-xs rounded px-2 py-1 flex flex-wrap items-center gap-2 ${v.keep ? "bg-amber-50 text-amber-800" : "bg-slate-50 text-slate-500"}`} data-testid={`mask-avail-legacy-${eid}-${day.date}`}>
          {v.keep ? <><span className="rounded bg-amber-200 px-1.5 py-0.5 font-semibold" data-testid={`mask-avail-legacy-badge-${eid}-${day.date}`}>Da aggiornare</span> Vecchio modulo, orario comunicato: <b>{lg.dalle || lg.alle ? `${lg.dalle || "?"}–${lg.alle || "?"}` : "non indicato"}</b> · seleziona Mattina e/o Pomeriggio e salva per aggiornarla</>
            : v.proposed ? <><span className="rounded bg-amber-200 px-1.5 py-0.5 font-semibold" data-testid={`mask-avail-legacy-badge-${eid}-${day.date}`}>Da aggiornare</span> Il vecchio orario {lg.dalle}–{lg.alle} corrisponde alla fascia proposta: finché non confermi resta invariato
              <button type="button" className="underline font-semibold" onClick={() => onSet({ sel: v.sel, legacy: lg, keep: false })} data-testid={`mask-avail-confirm-${eid}-${day.date}`}>Conferma proposta</button></>
            : v.sel.length ? <>Sostituirà l'orario originale {lg.dalle || "?"}–{lg.alle || "?"}</> : <>L'orario originale {lg.dalle || "?"}–{lg.alle || "?"} verrà rimosso</>}
          {!v.keep && !v.proposed && <button type="button" className="inline-flex items-center gap-1 underline" onClick={() => onSet({ sel: [], legacy: lg, keep: true })} data-testid={`mask-avail-restore-${eid}-${day.date}`}><RotateCcw className="w-3 h-3" />Mantieni originale</button>}
        </div>)}
    </div>
  );
}

function EventAvail({ eid, name, prefDays, onChange }) {
  const [days, setDays] = useState(null);
  const [st, setSt] = useState({});
  const [init, setInit] = useState("[]");
  useEffect(() => {
    api.get(`/events/${eid}/fasce-giorni`).then(({ data }) => { const s = initState(data.days, prefDays); setDays(data.days); setSt(s); setInit(JSON.stringify(toPayload(s))); }).catch(() => setDays([]));
  }, [eid]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (days) { const p = toPayload(st); onChange(eid, p, JSON.stringify(p) !== init); } }, [st, days]); // eslint-disable-line react-hooks/exhaustive-deps
  const all = useMemo(() => {
    if (!days) return [];
    const extra = Object.keys(st).filter((d) => !days.some((x) => x.date === d)).map((d) => ({ date: d, fasce: [] }));
    return [...days, ...extra].sort((a, b) => a.date.localeCompare(b.date));
  }, [days, st]);
  return (
    <div className="space-y-2" data-testid={`mask-avail-${eid}`}>
      <div className="text-xs font-semibold text-slate-600">{name || "Evento"}</div>
      {!days ? <div className="text-xs text-slate-400">Caricamento…</div> : !all.length ? <div className="text-xs text-slate-400">Imposta le date dell'evento per gestire le disponibilità.</div>
        : all.map((d) => <DayRow key={d.date} eid={eid} day={d} v={st[d.date]} onSet={(nv) => setSt((cur) => ({ ...cur, [d.date]: nv }))} />)}
    </div>
  );
}

export default function PersonAvailability({ eventIds, events, prefs, onChange }) {
  if (!eventIds.length) return <p className="text-sm text-slate-400" data-testid="mask-avail-none">Associa un evento per indicare le disponibilità.</p>;
  return eventIds.map((eid) => <EventAvail key={eid} eid={eid} name={events.find((e) => e.id === eid)?.nome}
    prefDays={(prefs || []).find((p) => p.evento_id === eid)?.days} onChange={onChange} />);
}
