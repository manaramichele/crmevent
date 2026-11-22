import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { AlertTriangle, UsersRound } from "lucide-react";
import { TeamSlotDialog, LegacyDialog, MansioneWarnings } from "./CoverageFasceDialogs";
import CoverageBulkDialog from "./CoverageBulkDialog";
import { Button } from "@/components/ui/button";

export const fmtDayLong = (d) => { const s = new Date(`${d}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "2-digit" }); return s.charAt(0).toUpperCase() + s.slice(1); };
const key = (r) => `${r.date}|${r.fascia}|${r.team_id}`;
const tid = (r) => `${r.date}-${r.fascia}-${r.team_id}`;

function NeedInput({ row, eventoId, onSaved }) {
  const [v, setV] = useState(row.needed ?? "");
  useEffect(() => { setV(row.needed ?? ""); }, [row.needed]);
  const save = async () => {
    const n = v === "" ? 0 : Number(v);
    if (Number.isNaN(n) || n < 0 || !Number.isInteger(n)) { toast.error("Inserisci un numero intero maggiore o uguale a 0"); setV(row.needed ?? ""); return; }
    if (n === (row.needed || 0)) return;
    try { await api.put("/staff-coverage/team-needs", { evento_id: eventoId, date: row.date, fascia: row.fascia, team_id: row.team_id, needed: n }); onSaved(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return <input type="number" min={0} value={v} onChange={(e) => setV(e.target.value)} onBlur={save} onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
    placeholder="—" className="w-16 h-8 rounded border border-slate-200 px-2 text-sm tabular-nums" data-testid={`fx-need-${tid(row)}`} />;
}

function Row({ r, first, eventoId, onOpen, onSaved }) {
  return (
    <tr className={`border-t ${first ? "border-slate-300" : "border-slate-100"}`} data-testid={`fx-row-${tid(r)}`}>
      <td className="px-3 py-2 whitespace-nowrap text-slate-700">{first ? fmtDayLong(r.date) : ""}</td>
      <td className="px-3 py-2 whitespace-nowrap">{first && <><b className="text-slate-800">{r.label}</b> <span className="text-xs text-slate-500 tabular-nums">{r.start && r.end ? `${r.start}–${r.end}` : "orario non impostato"}</span></>}</td>
      <td className="px-3 py-2 sticky left-0 bg-white sm:static"><button type="button" onClick={onOpen} className="font-medium text-tiffany-fg underline-offset-2 hover:underline text-left" data-testid={`fx-open-${tid(r)}`}>{r.team}</button></td>
      <td className="px-3 py-2 tabular-nums" data-testid={`fx-avail-${tid(r)}`}><b>{r.available}</b>
        {r.partial > 0 && <span className="ml-1.5 text-xs text-slate-500">+{r.partial} parziali</span>}
        {r.tbc > 0 && <span className="ml-1.5 text-xs text-amber-700">+{r.tbc} da verificare</span>}</td>
      <td className="px-3 py-2 tabular-nums" data-testid={`fx-assigned-${tid(r)}`}>{r.assigned}{r.orphans > 0 && <span className="ml-1.5 text-xs text-red-600" title="Assegnazioni di persone non più confermate o non più nel Team: non contate">· {r.orphans} da verificare</span>}</td>
      <td className="px-3 py-2"><NeedInput row={r} eventoId={eventoId} onSaved={onSaved} /></td>
      <td className={`px-3 py-2 tabular-nums font-semibold ${r.missing ? "text-red-600" : r.needed ? "text-emerald-700" : "text-slate-400"}`} data-testid={`fx-missing-${tid(r)}`}>{r.missing ?? "—"}</td>
    </tr>
  );
}

export default function CoverageFasce({ params, day, version, onOpenPerson, onChanged }) {
  const [bulk, setBulk] = useState(false);
  const [data, setData] = useState(null);
  const [pick, setPick] = useState(null);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    api.get("/staff-coverage/fasce", { params }).then(({ data: d }) => setData(d)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [params, version, tick]);
  if (!data) return <div className="text-sm text-slate-400">Caricamento…</div>;
  const rows = data.rows.filter((r) => !day || r.date === day);
  const open = (pid) => { setPick(null); setLegacyOpen(false); onOpenPerson(pid); };
  const refresh = () => setTick((t) => t + 1);
  return (
    <div className="space-y-3" data-testid="cov-fasce">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setBulk(true)} disabled={!data.rows.length} data-testid="cov-bulk-open"><UsersRound className="w-4 h-4 mr-1" />Disponibilità per Team</Button>
        {data.legacy.length > 0 && (
          <button type="button" onClick={() => setLegacyOpen(true)} className="w-full sm:w-auto inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 hover:bg-amber-100" data-testid="cov-legacy-indicator">
            <AlertTriangle className="w-4 h-4" />Disponibilità da aggiornare: <b data-testid="cov-legacy-count">{data.legacy.length}</b>
          </button>)}
      </div>
      <MansioneWarnings w={data.warnings} onOpenPerson={open} />
      <CoverageBulkDialog open={bulk} onClose={() => setBulk(false)} eventoId={params.evento_id} rows={data.rows} teams={data.teams} onDone={() => { refresh(); onChanged?.(); }} />
      <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]" data-testid="cov-fasce-table">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
            <tr>{["Giorno", "Fascia", "Team", "Disponibili", "Assegnati", "Necessari", "Mancanti"].map((h) => <th key={h} className="text-left font-medium px-3 py-2">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => <Row key={key(r)} r={r} first={i === 0 || rows[i - 1].date !== r.date || rows[i - 1].fascia !== r.fascia} eventoId={params.evento_id} onOpen={() => setPick(key(r))} onSaved={refresh} />)}
            {!rows.length && <tr><td colSpan={7} className="px-3 py-8 text-center text-slate-400" data-testid="fx-empty">{data.teams.length ? "Nessuna fascia attiva: configura Mattina e Pomeriggio nella scheda dell'evento." : "Nessun Team per questo evento: crea i Team nella linguetta Team."}</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-500">Disponibili = membri confermati del Team che coprono l'intera fascia (parziali e da verificare indicati a parte). Assegnati = persone assegnate al Team in quella fascia. Mancanti = Necessari meno Assegnati. Le persone Da classificare o non confermate non sono conteggiate.</p>
      <TeamSlotDialog row={data.rows.find((r) => key(r) === pick)} eventoId={params.evento_id} onClose={() => setPick(null)} onOpenPerson={open} onChanged={refresh} />
      <LegacyDialog open={legacyOpen} list={data.legacy} onClose={() => setLegacyOpen(false)} onOpenPerson={open} />
    </div>
  );
}
