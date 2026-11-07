import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { calApi, err, fmtD, Pill, SEL } from "./shared";
import { FindingsReview } from "./FindingsReview";

const RS = { da_analizzare: ["Da analizzare", "#64748B"], in_corso: ["In corso", "#0EA5E9"], eventi_trovati: ["Eventi trovati", "#16A34A"],
  nessun_evento: ["Non trovato", "#D97706"], dati_insufficienti: ["Dati insufficienti", "#94A3B8"], errore: ["Errore", "#DC2626"] };
export const FS = { verificato: ["Verificato", "#16A34A"], approvato: ["Approvato", "#0A8F8B"], da_verificare: ["Da verificare", "#D97706"],
  data_da_confermare: ["Data da confermare", "#6366F1"], scartato: ["Scartato", "#94A3B8"] };
const JL = { running: "in corso", sospeso: "sospesa", completato: "completata", annullato: "annullata" };
const KL = { test: "Test 20 contatti", gruppo: "Gruppo", tutti: "Intero database", aggiornamento: "Aggiorna date", notturno: "Aggiornamento notturno" };
const fmtDT = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

function ImportDialog({ onClose, onDone }) {
  const [lists, setLists] = useState(null);
  const [msg, setMsg] = useState("");
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(calApi("/reverse/brevo/lists")).then(({ data }) => setLists(data.lists)).catch((e) => { setLists([]); setMsg(e.response?.data?.detail || "Impossibile leggere le liste da Brevo"); }); }, []);
  const go = async () => {
    setBusy(true);
    try { const { data } = await api.post(calApi("/reverse/import"), { list_ids: sel }); toast.success(`Importati: ${data.nuovi} nuovi, ${data.aggiornati} aggiornati`); onDone(); } catch (e) { err(e); }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="rv-import-dialog">
      <DialogHeader><DialogTitle>Importa contatti da Brevo</DialogTitle></DialogHeader>
      <p className="text-xs text-slate-500">Sola lettura: liste, consensi e automazioni su Brevo non vengono modificati. I contatti importati partono come "da verificare" per le comunicazioni.</p>
      {!lists ? <p className="text-sm text-slate-500">Caricamento liste...</p> : <div className="space-y-1 max-h-80 overflow-y-auto">
        {!lists.length && <p className="text-sm text-amber-700" data-testid="rv-import-msg">{msg || "Nessuna lista disponibile."}</p>}
        {lists.map((l) => <label key={l.id} className="flex items-center gap-2 text-sm py-1" data-testid={`rv-list-${l.id}`}>
          <input type="checkbox" checked={sel.includes(l.id)} onChange={(e) => setSel(e.target.checked ? [...sel, l.id] : sel.filter((x) => x !== l.id))} />
          {l.name} <span className="text-xs text-slate-400">({l.contatti} contatti)</span></label>)}
      </div>}
      <Button onClick={go} disabled={!sel.length || busy} className="w-full bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="rv-import-confirm">{busy ? "Importazione..." : `Importa ${sel.length} liste`}</Button>
    </DialogContent></Dialog>
  );
}

function JobBar({ job, reload }) {
  const act = async (a) => { try { await api.post(calApi(`/reverse/jobs/${job.id}/${a}`)); reload(); } catch (e) { err(e); } };
  const pct = job.total ? Math.round((job.pos / job.total) * 100) : 0;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-3 text-sm space-y-2" data-testid="rv-job">
      <div className="flex flex-wrap items-center gap-2"><b>{KL[job.kind] || job.kind}</b><span className="text-xs text-slate-500">{JL[job.status]} · {job.pos}/{job.total} · errori {job.errori}</span>
        <div className="ml-auto flex gap-2">
          {job.status === "running" && <Button size="sm" variant="outline" onClick={() => act("pausa")} data-testid="rv-job-pause">Sospendi</Button>}
          {job.status === "sospeso" && <Button size="sm" onClick={() => act("riprendi")} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="rv-job-resume">Riprendi</Button>}
          {["running", "sospeso"].includes(job.status) && <Button size="sm" variant="ghost" className="text-red-600" onClick={() => act("annulla")} data-testid="rv-job-cancel">Annulla</Button>}
        </div></div>
      <div className="h-2 rounded-full bg-slate-100 overflow-hidden"><div className="h-full bg-[#0ABAB5] transition-[width] duration-500" style={{ width: `${pct}%` }} data-testid="rv-job-progress" /></div>
      {(job.motivo || job.ultimo_errore) && <p className="text-xs text-amber-700">{job.motivo || job.ultimo_errore}</p>}
    </div>
  );
}

function ContactRow({ c }) {
  const [open, setOpen] = useState(false);
  const [l, col] = RS[c.stato_ricerca] || [c.stato_ricerca, "#64748B"];
  return (<>
    <tr className="border-t border-slate-100 align-top" data-testid={`rv-contact-${c.id}`}>
      <td className="px-3 py-2">{c.email}<div className="text-[11px] text-slate-400">{[c.nome, c.cognome].filter(Boolean).join(" ")}</div></td>
      <td className="px-3 py-2">{c.organizzatore_identificato || c.societa || "—"}{c.sito_ufficiale && <div className="text-[11px] text-slate-400 break-all">{c.sito_ufficiale}</div>}</td>
      <td className="px-3 py-2 text-xs">{c.eventi.length ? c.eventi.map((e) => <div key={e.id}>{e.nome} <Pill color={(FS[e.stato] || [])[1]}>{(FS[e.stato] || [e.stato])[0]}</Pill></div>) : "—"}</td>
      <td className="px-3 py-2 text-xs">{c.eventi.map((e) => <div key={e.id}>{e.data_inizio ? fmtD(e.data_inizio) : "data da confermare"}</div>)}</td>
      <td className="px-3 py-2"><Pill color={col} testid={`rv-contact-state-${c.id}`}>{l}</Pill>
        {!!((c.fonti || []).length || c.nota || c.errore) && <button className="block text-[11px] text-[#0A8F8B] underline mt-1" onClick={() => setOpen(!open)} data-testid={`rv-contact-sources-${c.id}`}>{open ? "Nascondi fonti" : "Fonti consultate"}</button>}</td>
    </tr>
    {open && <tr className="bg-slate-50"><td colSpan={5} className="px-3 py-2 text-xs text-slate-600 space-y-0.5" data-testid={`rv-contact-fonti-${c.id}`}>
      {c.nota && <div className="italic">{c.nota}</div>}
      {c.fonti.map((f, i) => <div key={i}>{f.tipo === "ricerca" ? `Ricerca: "${f.query}" · ${f.risultati} risultati` : <>Pagina: <a href={f.url} target="_blank" rel="noreferrer" className="underline break-all">{f.url}</a> · {f.esito}</>}</div>)}
      {c.errore && <div className="text-red-600">{c.errore}</div>}
    </td></tr>}
  </>);
}

function Settings({ s, reload }) {
  const [f, setF] = useState(s);
  const save = async () => { try { await api.put(calApi("/reverse/settings"), f); toast.success("Impostazioni salvate"); reload(); } catch (e) { err(e); } };
  const num = (k) => (e) => setF({ ...f, [k]: Number(e.target.value) });
  return (
    <div className="flex flex-wrap items-end gap-3 text-xs text-slate-600" data-testid="rv-settings">
      <label className="flex items-center gap-2"><input type="checkbox" checked={f.aggiornamento_notturno} onChange={(e) => setF({ ...f, aggiornamento_notturno: e.target.checked })} data-testid="rv-set-nightly" />Aggiornamento notturno (04:00)</label>
      <label>Ricontrolla ogni (giorni)<Input type="number" value={f.intervallo_giorni} onChange={num("intervallo_giorni")} className="h-8 w-20" data-testid="rv-set-interval" /></label>
      <label>Max contatti per notte<Input type="number" value={f.max_per_notte} onChange={num("max_per_notte")} className="h-8 w-24" data-testid="rv-set-max" /></label>
      <label>Cache ricerche (giorni)<Input type="number" value={f.cache_giorni} onChange={num("cache_giorni")} className="h-8 w-20" data-testid="rv-set-cache" /></label>
      <Button size="sm" variant="outline" onClick={save} data-testid="rv-set-save">Salva</Button>
    </div>
  );
}

export function ReversePanel() {
  const [st, setSt] = useState(null);
  const [rows, setRows] = useState(null);
  const [f, setF] = useState({ stato: "", q: "" });
  const [dlg, setDlg] = useState(false);
  const [review, setReview] = useState(false);
  const [size, setSize] = useState(100);
  const load = useCallback(() => {
    api.get(calApi("/reverse/status")).then(({ data }) => setSt(data)).catch(err);
    api.get(calApi("/reverse/contacts"), { params: { ...f, limit: 100 } }).then(({ data }) => setRows(data)).catch(err);
  }, [f]);
  useEffect(() => { load(); }, [load]);
  const running = st?.jobs?.find((j) => j.status === "running");
  useEffect(() => { if (!running) return undefined; const t = setInterval(load, 4000); return () => clearInterval(t); }, [running, load]);
  const run = async (scope) => {
    try { const { data } = await api.post(calApi(scope === "update" ? "/reverse/update" : "/reverse/search"), scope === "update" ? {} : { scope, size }); toast.success(`Elaborazione avviata su ${data.contatti} contatti`); load(); } catch (e) { err(e); }
  };
  if (!st) return <p className="text-sm text-slate-500">Caricamento...</p>;
  const k = st.kpi;
  const job = st.jobs.find((j) => ["running", "sospeso"].includes(j.status));
  const KPI = [["Totale contatti", k.totale_contatti, "tot"], ["Contatti analizzati", k.analizzati, "analizzati"], ["Organizzatori identificati", k.organizzatori_identificati, "org"],
    ["Eventi trovati", k.eventi_trovati, "trovati"], ["Eventi verificati", k.eventi_verificati, "verificati"], ["Eventi da verificare", k.eventi_da_verificare, "daverificare"],
    ["Contatti senza eventi", k.senza_eventi, "senza"], ["Errori di ricerca", k.errori, "errori"]];
  return (
    <div className="space-y-4" data-testid="rv-panel">
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="text-xs text-slate-600" data-testid="rv-lists">Liste Brevo selezionate: <b>{st.liste.length ? st.liste.map((l) => l.name || l.id).join(", ") : "nessuna"}</b>
          {st.ultima_importazione && ` · ultima importazione ${fmtDT(st.ultima_importazione.at)} (${st.ultima_importazione.nuovi} nuovi, ${st.ultima_importazione.aggiornati} aggiornati)`}</div>
        {!st.brave_configurato && <div className="text-xs text-amber-700" data-testid="rv-brave-missing">Motore di ricerca non configurato: manca la chiave Brave Search.</div>}
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setDlg(true)} variant="outline" data-testid="rv-btn-import">IMPORTA DA BREVO</Button>
          <Button onClick={() => run("test")} disabled={!!running} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="rv-btn-test">CERCA EVENTI · test 20 contatti</Button>
          <div className="flex flex-wrap items-center gap-1"><select className={SEL} value={size} onChange={(e) => setSize(Number(e.target.value))} disabled={!st.test_completato} data-testid="rv-group-size">{[50, 100, 250, 500].map((n) => <option key={n} value={n}>{n} contatti</option>)}</select>
            <Button variant="outline" onClick={() => run("gruppo")} disabled={!!running || !st.test_completato} data-testid="rv-btn-group">CERCA EVENTI · gruppo</Button>
            <Button variant="outline" onClick={() => run("tutti")} disabled={!!running || !st.test_completato} data-testid="rv-btn-all">Tutti i restanti</Button></div>
          <Button variant="outline" onClick={() => run("update")} disabled={!!running} data-testid="rv-btn-update">AGGIORNA DATE</Button>
          <Button variant={review ? "default" : "outline"} onClick={() => setReview(!review)} data-testid="rv-btn-review">VERIFICA RISULTATI</Button>
        </div>
        {!st.test_completato && <p className="text-[11px] text-slate-500">L'elaborazione a gruppi si sblocca dopo aver completato il test su 20 contatti. Nessuna campagna viene creata da questa sezione.</p>}
        <Settings key={JSON.stringify(st.settings)} s={st.settings} reload={load} />
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{KPI.map(([l, v, id]) => <div key={id} className="bg-white border border-slate-200 rounded-xl p-3" data-testid={`rv-kpi-${id}`}><div className="text-[11px] text-slate-500">{l}</div><div className="text-2xl font-semibold">{v}</div></div>)}</div>
      {job && <JobBar job={job} reload={load} />}
      {review ? <FindingsReview onChange={load} /> : <>
        <div className="flex flex-wrap gap-2">
          <select className={SEL} value={f.stato} onChange={(e) => setF({ ...f, stato: e.target.value })} data-testid="rv-filter-state"><option value="">Tutti gli stati</option>{Object.entries(RS).map(([x, [l]]) => <option key={x} value={x}>{l}</option>)}</select>
          <Input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="Cerca email o organizzatore" className="h-9 max-w-xs" data-testid="rv-filter-q" />
          <span className="text-xs text-slate-500 self-center">{rows?.total ?? 0} contatti</span>
        </div>
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[860px] text-sm" data-testid="rv-contacts-table">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Email", "Organizzatore", "Eventi associati", "Date", "Stato ricerca"].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
          <tbody>{(rows?.rows || []).map((c) => <ContactRow key={c.id} c={c} />)}</tbody>
        </table>{!rows?.rows?.length && <p className="p-4 text-xs text-slate-500">Nessun contatto importato.</p>}</div>
      </>}
      {dlg && <ImportDialog onClose={() => setDlg(false)} onDone={() => { setDlg(false); load(); }} />}
    </div>
  );
}
