import { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Printer, FileSpreadsheet, CalendarDays, Clock } from "lucide-react";
import CoverageSlotDialog from "./CoverageSlotDialog";
import CoverageNeeds from "./CoverageNeeds";
import CoverageMatrix from "./CoverageMatrix";

const fsel = "h-10 w-full sm:w-auto sm:min-w-[150px] rounded-md border border-slate-200 bg-white px-2 text-sm";
const STATUS_BAR = { green: "bg-emerald-500", yellow: "bg-amber-400", red: "bg-red-500" };
const fmtDay = (d) => new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "2-digit" });

export async function downloadCoverage(params, fallback) {
  try {
    const res = await api.get("/staff-coverage/export", { params, responseType: "blob" });
    const cd = res.headers?.["content-disposition"] || "";
    const url = URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url; a.download = (cd.match(/filename="([^"]+)"/) || [])[1] || fallback;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  } catch (e) {
    let msg = e.response?.data;
    if (msg instanceof Blob) { try { msg = JSON.parse(await msg.text()).detail; } catch { msg = null; } }
    toast.error(formatApiError(msg) || "Esportazione non riuscita");
  }
}

function Kpi({ label, value, id }) {
  return <div className="bg-white border border-slate-200 rounded-xl p-3" data-testid={`cov-kpi-${id}`}><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-bold text-slate-900 mt-0.5">{value ?? "—"}</div></div>;
}

function Bars({ data, onPick }) {
  const max = Math.max(1, ...data.slots.map((s) => Math.max(s.available, s.needed || 0)));
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-1.5" data-testid="cov-bars">
      <div className="flex flex-wrap gap-4 text-xs text-slate-500 mb-2">
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded bg-tiffany" />Intera fascia</span>
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 rounded bg-tiffany/40" />Parziale</span>
        <span className="inline-flex items-center gap-1"><span className="w-0.5 h-3 bg-slate-800" />Necessari</span>
        <span>Disponibili | Assegnati | Necessari</span>
      </div>
      {data.slots.map((s) => (
        <button key={s.start} type="button" onClick={() => onPick(s)} className="w-full grid grid-cols-[86px_1fr_auto] items-center gap-2 text-left rounded hover:bg-slate-50 px-1 py-0.5" data-testid={`cov-slot-${s.start}`}>
          <span className="text-xs font-medium text-slate-600 tabular-nums">{s.start}–{s.end}</span>
          <span className="relative h-5 bg-slate-100 rounded overflow-hidden">
            <span className="absolute inset-y-0 left-0 bg-tiffany/40" style={{ width: `${(s.available / max) * 100}%` }} />
            <span className="absolute inset-y-0 left-0 bg-tiffany" style={{ width: `${(s.full.length / max) * 100}%` }} />
            {s.needed && <span className="absolute inset-y-0 w-0.5 bg-slate-800" style={{ left: `${(s.needed / max) * 100}%` }} />}
          </span>
          <span className="text-xs tabular-nums whitespace-nowrap flex items-center gap-1.5" data-testid={`cov-slot-nums-${s.start}`}>
            {s.status && <span className={`w-2.5 h-2.5 rounded-full ${STATUS_BAR[s.status]}`} data-testid={`cov-status-${s.start}-${s.status}`} />}
            <b>{s.available}</b>{s.partial.length > 0 && <span className="text-slate-400">({s.partial.length} parz.)</span>} | {s.assigned} | {s.needed ?? "—"}
          </span>
        </button>))}
    </div>
  );
}

export default function CoverageTab({ events, teams, settings, version, onOpenPerson }) {
  const [f, setF] = useState({ evento_id: events.length === 1 ? events[0].id : "", date: "", mansione: "", team_id: "", gruppo: "", cat: "all", step: 60 });
  const [view, setView] = useState("day");
  const [data, setData] = useState(null);
  const [slot, setSlot] = useState(null);
  const [tick, setTick] = useState(0);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: k === "step" ? Number(e.target.value) : e.target.value, ...(k === "evento_id" ? { date: "", team_id: "" } : {}) }));
  const params = useMemo(() => Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "" && v !== null)), [f]);
  useEffect(() => {
    if (!f.evento_id) { setData(null); return; }
    api.get("/staff-coverage", { params }).then(({ data: d }) => { setData(d); if (!f.date) setF((p) => ({ ...p, date: d.date })); })
      .catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [params, version, tick]); // eslint-disable-line react-hooks/exhaustive-deps
  const evTeams = teams.filter((t) => t.evento_id === f.evento_id);
  const groups = settings?.gruppi_appartenenza || [];
  const ev = events.find((e) => e.id === f.evento_id);
  return (
    <div className="space-y-4" data-testid="coverage-tab">
      <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2">
        <select className={fsel} value={f.evento_id} onChange={set("evento_id")} data-testid="cov-event"><option value="">Seleziona evento…</option>{events.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</select>
        {view === "day" && <select className={fsel} value={f.date} onChange={set("date")} data-testid="cov-date" disabled={!data}>{(data?.days || []).map((d) => <option key={d} value={d}>{fmtDay(d)}</option>)}{data && !data.days.includes(f.date) && f.date && <option value={f.date}>{fmtDay(f.date)}</option>}</select>}
        <select className={fsel} value={f.mansione} onChange={set("mansione")} data-testid="cov-mansione"><option value="">Tutte le mansioni</option>{(data?.mansioni || []).map((m) => <option key={m} value={m}>{m}</option>)}</select>
        <select className={fsel} value={f.team_id} onChange={set("team_id")} data-testid="cov-team"><option value="">Tutti i team</option>{evTeams.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}</select>
        <select className={fsel} value={f.gruppo} onChange={set("gruppo")} data-testid="cov-gruppo"><option value="">Tutti i gruppi</option>{groups.map((g) => <option key={g} value={g}>{g}</option>)}</select>
        <select className={fsel} value={f.cat} onChange={set("cat")} data-testid="cov-cat"><option value="all">Staff e Volontari</option><option value="staff">Solo Staff</option><option value="volontari">Solo Volontari</option></select>
        <select className={fsel} value={f.step} onChange={set("step")} data-testid="cov-step"><option value={60}>60 minuti</option><option value={30}>30 minuti</option><option value={15}>15 minuti</option></select>
      </div>
      {!f.evento_id ? <div className="bg-white border border-dashed border-slate-300 rounded-xl p-10 text-center text-slate-500" data-testid="cov-pick-event">Seleziona un evento per vedere la copertura oraria.</div> : data && (<>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
            <button type="button" onClick={() => setView("day")} className={`px-3 py-1.5 text-sm rounded-md ${view === "day" ? "bg-slate-900 text-white" : "text-slate-600"}`} data-testid="cov-view-day"><Clock className="w-4 h-4 inline mr-1" />Giornata</button>
            <button type="button" onClick={() => setView("matrix")} className={`px-3 py-1.5 text-sm rounded-md ${view === "matrix" ? "bg-slate-900 text-white" : "text-slate-600"}`} data-testid="cov-view-matrix"><CalendarDays className="w-4 h-4 inline mr-1" />Più giorni</button>
          </div>
          <div className="flex flex-wrap gap-2 sm:ml-auto">
            <Button variant="outline" size="sm" onClick={() => downloadCoverage({ ...params, kind: "pdf", mode: "summary" }, "Copertura.pdf")} data-testid="cov-print-summary"><Printer className="w-4 h-4 mr-1" />Riepilogo giornaliero</Button>
            <Button variant="outline" size="sm" onClick={() => downloadCoverage({ ...params, kind: "pdf", mode: "by_mansione" }, "Copertura.pdf")} data-testid="cov-print-mansione"><Printer className="w-4 h-4 mr-1" />Per mansione</Button>
            <Button variant="outline" size="sm" onClick={() => downloadCoverage({ ...params, kind: "pdf", mode: "names" }, "Copertura.pdf")} data-testid="cov-print-names"><Printer className="w-4 h-4 mr-1" />Elenco per fascia</Button>
            <Button variant="outline" size="sm" onClick={() => downloadCoverage({ ...params, kind: "xlsx" }, "Disponibilita.xlsx")} data-testid="cov-export-xlsx"><FileSpreadsheet className="w-4 h-4 mr-1" />Excel</Button>
          </div>
        </div>
        {view === "day" ? (<>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
            <Kpi id="day" label="Disponibili nel giorno" value={data.kpis.day_people} />
            <Kpi id="max" label="Max contemporanei" value={data.kpis.max} />
            <Kpi id="min" label="Min contemporanei" value={data.kpis.min} />
            <Kpi id="best" label="Fascia migliore" value={data.kpis.best} />
            <Kpi id="worst" label="Fascia più scoperta" value={data.kpis.worst} />
            <Kpi id="tbc" label="Orario da confermare" value={data.kpis.tbc} />
          </div>
          <Bars data={data} onPick={setSlot} />
          {data.tbc.length > 0 && <button type="button" onClick={() => setSlot({ tbc: true })} className="text-sm text-amber-700 underline" data-testid="cov-open-tbc">Vedi {data.tbc.length} persone con orario da confermare</button>}
          <CoverageNeeds eventoId={f.evento_id} date={data.date} mansioni={data.mansioni} pct={data.yellow_margin_pct} onChanged={() => setTick((t) => t + 1)} />
        </>) : <CoverageMatrix params={params} version={`${version}-${tick}`} onPick={(d) => { setF((p) => ({ ...p, date: d })); setView("day"); }} />}
        <CoverageSlotDialog slot={slot} data={data} eventName={ev?.nome} onClose={() => setSlot(null)} onOpenPerson={onOpenPerson} />
      </>)}
    </div>
  );
}
