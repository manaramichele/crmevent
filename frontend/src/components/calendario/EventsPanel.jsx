import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Upload, Download, ChevronLeft, ChevronRight } from "lucide-react";
import { calApi, err, fmtD, SEL, Pill, download, DISC_COLOR, DISC_LABEL, STATO_EVENTO, STATO_COMM } from "./shared";
import { EventDialog } from "./EventDialog";
import { ImportDialog } from "./ImportDialog";

const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function Filters({ f, setF, meta }) {
  const y = new Date().getFullYear();
  const s = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2" data-testid="cal-filters">
      <Input placeholder="Cerca evento, comune, organizzatore" value={f.q} onChange={s("q")} className="h-9 col-span-2" data-testid="cal-filter-q" />
      <select className={SEL} value={f.anno} onChange={s("anno")} data-testid="cal-filter-anno"><option value="">Anno</option>{[y - 2, y - 1, y, y + 1, y + 2].map((a) => <option key={a}>{a}</option>)}</select>
      <select className={SEL} value={f.mese} onChange={s("mese")} data-testid="cal-filter-mese"><option value="">Mese</option>{MESI.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select>
      <select className={SEL} value={f.disciplina} onChange={s("disciplina")} data-testid="cal-filter-disciplina"><option value="">Disciplina</option>{Object.keys(meta.discipline).map((k) => <option key={k} value={k}>{DISC_LABEL[k]}</option>)}</select>
      <Input placeholder="Distanza" value={f.distanza} onChange={s("distanza")} className="h-9" data-testid="cal-filter-distanza" />
      <Input placeholder="Regione" value={f.regione} onChange={s("regione")} className="h-9" data-testid="cal-filter-regione" />
      <Input placeholder="Provincia" value={f.provincia} onChange={s("provincia")} className="h-9" data-testid="cal-filter-provincia" />
      <select className={SEL} value={f.stato} onChange={s("stato")} data-testid="cal-filter-stato"><option value="">Stato evento</option>{Object.entries(STATO_EVENTO).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <select className={SEL} value={f.stato_commerciale} onChange={s("stato_commerciale")} data-testid="cal-filter-comm"><option value="">Stato commerciale</option>{Object.entries(STATO_COMM).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <select className={SEL} value={f.has_email} onChange={s("has_email")} data-testid="cal-filter-email"><option value="">Email: tutte</option><option value="1">Con email</option><option value="0">Senza email</option></select>
      <select className={SEL} value={f.sort} onChange={s("sort")} data-testid="cal-filter-sort"><option value="asc">Data crescente</option><option value="desc">Data decrescente</option></select>
    </div>
  );
}

function Table({ rows, open }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[980px] text-sm" data-testid="cal-table">
      <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Evento", "Data", "Località", "Disciplina", "Organizzatore", "Email", "Stato", "Data invio Brevo", ""].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
      <tbody>{rows.map((e) => (
        <tr key={e.id} className="border-t border-slate-100" data-testid={`cal-row-${e.id}`}>
          <td className="px-3 py-2 font-medium">{e.nome}<div className="text-[11px] text-slate-400">{[e.specialita, e.distanza, e.edizione].filter(Boolean).join(" · ")}</div></td>
          <td className="px-3 py-2 whitespace-nowrap">{fmtD(e.data_inizio)}{e.data_da_verificare && <div><Pill color="#D97706">Data da verificare</Pill></div>}</td>
          <td className="px-3 py-2">{[e.comune, e.provincia].filter(Boolean).join(" (") + (e.provincia && e.comune ? ")" : "")}<div className="text-[11px] text-slate-400">{e.regione}</div></td>
          <td className="px-3 py-2"><Pill color={DISC_COLOR[e.disciplina]}>{DISC_LABEL[e.disciplina] || e.disciplina}</Pill></td>
          <td className="px-3 py-2">{e.organizzatore_nome || "—"}</td>
          <td className="px-3 py-2 text-xs">{e.email || "—"}</td>
          <td className="px-3 py-2 text-xs">{STATO_EVENTO[e.stato]}<div className="text-slate-400">{STATO_COMM[e.stato_commerciale]}</div></td>
          <td className="px-3 py-2 text-xs">{e.data_comunicazione ? fmtD(e.data_comunicazione) : "—"}</td>
          <td className="px-3 py-2"><Button size="sm" variant="outline" onClick={() => open(e.id)} data-testid={`cal-open-${e.id}`}>Apri</Button></td>
        </tr>))}</tbody>
    </table></div>
  );
}

function CalendarView({ rows, view, cursor, setCursor, open }) {
  const by = useMemo(() => rows.reduce((m, e) => ((m[e.data_inizio] = [...(m[e.data_inizio] || []), e]), m), {}), [rows]);
  const move = (n) => { const d = new Date(cursor); if (view === "year") d.setFullYear(d.getFullYear() + n); else if (view === "week") d.setDate(d.getDate() + 7 * n); else d.setMonth(d.getMonth() + n); setCursor(d); };
  const Ev = ({ e }) => <button type="button" onClick={() => open(e.id)} className="block w-full truncate rounded px-1 text-left text-[10px] font-semibold text-white" style={{ background: DISC_COLOR[e.disciplina] }} title={e.nome}>{e.nome}</button>;
  let body;
  if (view === "year") {
    body = <div className="grid grid-cols-2 md:grid-cols-4 gap-2">{MESI.map((m, i) => { const n = rows.filter((e) => e.data_inizio?.slice(5, 7) === String(i + 1).padStart(2, "0")).length;
      return <button key={m} type="button" onClick={() => setCursor(new Date(cursor.getFullYear(), i, 1))} className="rounded-xl border border-slate-200 bg-white p-3 text-left" data-testid={`cal-year-${i + 1}`}><div className="font-semibold">{m}</div><div className="text-2xl font-bold text-[#088F8A]">{n}</div><div className="text-[11px] text-slate-400">eventi</div></button>; })}</div>;
  } else {
    const start = new Date(cursor);
    if (view === "month") start.setDate(1);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    const days = Array.from({ length: view === "week" ? 7 : 42 }, (_, i) => { const d = new Date(start); d.setDate(d.getDate() + i); return d; });
    body = <div className="grid grid-cols-7 gap-1 text-xs">{["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map((d) => <div key={d} className="text-center text-slate-400">{d}</div>)}
      {days.map((d) => (<div key={iso(d)} className={`min-h-[64px] ${view === "week" ? "sm:min-h-[200px]" : ""} rounded-md border border-slate-100 bg-white p-1 ${d.getMonth() !== cursor.getMonth() && view === "month" ? "opacity-40" : ""}`}>
        <div className="text-[10px] text-slate-500">{d.getDate()}</div><div className="space-y-0.5">{(by[iso(d)] || []).slice(0, view === "week" ? 20 : 3).map((e) => <Ev key={e.id} e={e} />)}
        {view === "month" && (by[iso(d)] || []).length > 3 && <div className="text-[10px] text-slate-400">+{by[iso(d)].length - 3}</div>}</div></div>))}</div>;
  }
  return (
    <div className="space-y-2" data-testid={`cal-view-${view}`}>
      <div className="flex items-center gap-2"><Button size="sm" variant="outline" onClick={() => move(-1)} data-testid="cal-prev"><ChevronLeft className="w-4 h-4" /></Button>
        <div className="font-semibold text-sm" data-testid="cal-cursor">{view === "year" ? cursor.getFullYear() : `${MESI[cursor.getMonth()]} ${cursor.getFullYear()}`}</div>
        <Button size="sm" variant="outline" onClick={() => move(1)} data-testid="cal-next"><ChevronRight className="w-4 h-4" /></Button>
        <div className="ml-auto flex gap-2 text-[11px]">{Object.entries(DISC_LABEL).map(([k, l]) => <Pill key={k} color={DISC_COLOR[k]}>{l}</Pill>)}</div></div>
      {body}
    </div>
  );
}

const EMPTY = { q: "", anno: "", mese: "", disciplina: "", distanza: "", regione: "", provincia: "", stato: "", stato_commerciale: "", has_email: "", sort: "asc" };

export function EventsPanel({ meta }) {
  const [f, setF] = useState(EMPTY);
  const [mode, setMode] = useState("table");
  const [cursor, setCursor] = useState(new Date());
  const [d, setD] = useState({ total: 0, rows: [] });
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState(undefined);
  const [imp, setImp] = useState(false);
  const params = useMemo(() => {
    const p = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
    if (mode === "table") return { ...p, page, limit: 50 };
    const y = cursor.getFullYear(); const m = cursor.getMonth();
    const range = mode === "year" ? [`${y}-01-01`, `${y}-12-31`] : [iso(new Date(y, m - 1, 20)), iso(new Date(y, m + 1, 12))];
    return { ...p, anno: "", mese: "", dal: range[0], al: range[1], limit: 1000 };
  }, [f, page, mode, cursor]);
  const load = useCallback(() => api.get(calApi("/events"), { params }).then(({ data }) => setD(data)).catch(err), [params]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  return (
    <div className="space-y-3" data-testid="cal-events">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-full border border-slate-200 p-0.5 text-xs font-semibold">{[["table", "Tabella"], ["month", "Mese"], ["week", "Settimana"], ["year", "Anno"]].map(([k, l]) => (
          <button key={k} type="button" onClick={() => setMode(k)} className={`h-8 px-3 rounded-full transition-colors ${mode === k ? "bg-[#0ABAB5] text-slate-900" : "text-slate-600"}`} data-testid={`cal-mode-${k}`}>{l}</button>))}</div>
        <div className="ml-auto flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setOpenId(null)} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="cal-new-event"><Plus className="w-4 h-4 mr-1" />Nuovo evento</Button>
          <Button size="sm" variant="outline" onClick={() => setImp(true)} data-testid="cal-import"><Upload className="w-4 h-4 mr-1" />Importa</Button>
          <Button size="sm" variant="outline" onClick={() => download("/export", { ...f, format: "xlsx" }, "calendario-eventi-italia.xlsx")} data-testid="cal-export-xlsx"><Download className="w-4 h-4 mr-1" />Excel</Button>
          <Button size="sm" variant="outline" onClick={() => download("/export", { ...f, format: "csv" }, "calendario-eventi-italia.csv")} data-testid="cal-export-csv"><Download className="w-4 h-4 mr-1" />CSV</Button>
        </div>
      </div>
      <Filters f={f} setF={(v) => { setF(v); setPage(1); }} meta={meta} />
      <div className="text-xs text-slate-500" data-testid="cal-total">{d.total} eventi</div>
      {mode === "table" ? <>
        {d.rows.length ? <Table rows={d.rows} open={setOpenId} /> : <p className="text-sm text-slate-500" data-testid="cal-empty">Nessun evento. Aggiungilo o importa un file Excel/CSV.</p>}
        {d.total > 50 && <div className="flex gap-2 items-center text-xs"><Button size="sm" variant="outline" disabled={page === 1} onClick={() => setPage(page - 1)}>Precedente</Button>Pagina {page} di {Math.ceil(d.total / 50)}<Button size="sm" variant="outline" disabled={page * 50 >= d.total} onClick={() => setPage(page + 1)}>Successiva</Button></div>}
      </> : <CalendarView rows={d.rows} view={mode} cursor={cursor} setCursor={setCursor} open={setOpenId} />}
      {openId !== undefined && <EventDialog id={openId} meta={meta} onClose={() => setOpenId(undefined)} onSaved={() => { setOpenId(undefined); load(); }} />}
      {imp && <ImportDialog onClose={() => setImp(false)} onDone={load} />}
    </div>
  );
}
