import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Download, FileSpreadsheet, Upload, ShieldCheck } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, SectionCard } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { SEL, SearchSelect, download } from "@/components/import/shared";
import { Dropzone, MappingTable, PipelineSetup, ConfigBar, PreviewPanel } from "@/components/import/WizardParts";
import { ImportHistory } from "@/components/import/ImportHistory";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const PERSON_TARGETS = ["persone", "soci"];

function Wizard({ target, info, onClose, onDone, initialEvent }) {
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState("");
  const [header, setHeader] = useState(1);
  const [layout, setLayout] = useState("rows");
  const [read, setRead] = useState(null);
  const [mapping, setMapping] = useState({});
  const [mode, setMode] = useState("both");
  const [eventId, setEventId] = useState(initialEvent || "");
  const [cats, setCats] = useState({});
  const [resp, setResp] = useState({});
  const [evMap, setEvMap] = useState({});
  const [sheets, setSheets] = useState([]);
  const [overwrite, setOverwrite] = useState(false);
  const [configName, setConfigName] = useState(null);
  const [prev, setPrev] = useState(null);
  const [result, setResult] = useState(null);
  const [people, setPeople] = useState([]);
  const pipe = target.key === "pipeline";
  useEffect(() => { if (pipe) { api.get("/persons").then(({ data }) => setPeople(data)).catch(() => setPeople([])); } }, [pipe]);
  const upload = async (file) => {
    setBusy(true);
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post("/imports/upload", fd, { headers: { "Content-Type": "multipart/form-data" } }); setJob(data); setSheet(data.sheets[0].name); setSheets([]); }
    catch (e) { err(e); } finally { setBusy(false); }
  };
  const doRead = useCallback(async (keepMapping) => {
    if (!job) return;
    try {
      const { data } = await api.post(`/imports/jobs/${job.id}/read`, { sheet, header_row: Number(header) || 1, layout }, { params: { target: target.key } });
      setRead(data); setPrev(null);
      if (!keepMapping) setMapping(data.suggested);
      if (pipe && (job.sheets.length === 1 || !sheets.some((s) => s.sheet === sheet))) setSheets([{ sheet, event_id: (data.pipeline?.fogli.find((f) => f.sheet === sheet) || {}).event_id || "" }]);
    } catch (e) { err(e); }
  }, [job, sheet, header, layout, target.key]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { doRead(false); }, [doRead]);
  const options = () => ({ event_id: eventId || undefined, fasi: cats, responsabili: resp, eventi: evMap, sovrascrivi_modificate: overwrite, config_name: configName,
    sheets: pipe && sheets.length ? sheets.map((s) => ({ ...s, event_id: s.event_id || eventId || undefined })) : undefined, layout, header_row: header, mode });
  const body = () => ({ target: target.key, sheet, header_row: Number(header) || 1, layout, mapping, mode, options: options() });
  const preview = async () => { setBusy(true); try { const { data } = await api.post(`/imports/jobs/${job.id}/preview`, body()); setPrev(data); } catch (e) { err(e); } finally { setBusy(false); } };
  const run = async () => {
    if (!window.confirm("Confermi l'importazione? Verranno applicate esattamente le azioni mostrate in anteprima.")) return;
    setBusy(true);
    try { const { data } = await api.post(`/imports/jobs/${job.id}/run`, body()); setResult(data); onDone(); toast.success("Importazione completata"); } catch (e) { err(e); } finally { setBusy(false); }
  };
  const loadConfig = (c) => { setMapping({ ...mapping, ...c.mapping }); setConfigName(c.name); const o = c.options || {}; if (o.layout) setLayout(o.layout); if (o.header_row) setHeader(o.header_row); if (o.mode) setMode(o.mode); if (o.fasi) setCats(o.fasi); };
  const evOpts = [{ value: "", label: pipe ? "Evento dal file / dal foglio" : "Nessun evento (solo anagrafica)" }, ...info.events.map((e) => ({ value: e.id, label: e.nome, hint: e.edizione || (e.data_inizio || "").slice(0, 10) }))];
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="w-[96vw] max-w-5xl max-h-[92vh] overflow-y-auto overflow-x-hidden" data-testid="import-wizard">
        <DialogHeader><DialogTitle className="font-display">Importa in {target.label}</DialogTitle>
          <DialogDescription>{info.org.nome}{!target.active && " · modulo non attivo: i dati vengono salvati ma restano invisibili all'organizzazione finché non lo attiva"}</DialogDescription></DialogHeader>
        {result ? (
          <div className="space-y-3" data-testid="import-result">
            <p className="text-sm">Creati <b>{result.creati}</b> · aggiornati <b>{result.aggiornati}</b> · ignorati <b>{result.ignorati}</b> · segnalazioni <b>{result.errori.length}</b></p>
            {result.pipeline && <p className="text-sm">Schede {result.pipeline.schede} · fasi create {result.pipeline.fasi_create} · collegamenti {result.pipeline.collegamenti}</p>}
            <div className="flex gap-2"><Button onClick={onClose} data-testid="import-result-close">Chiudi</Button></div>
          </div>
        ) : !job ? <Dropzone onFile={upload} busy={busy} /> : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-end gap-3 text-sm">
              <div><div className="text-xs text-slate-500">File</div><div className="font-medium">{job.filename}{job.sheets[0].sep && ` · separatore «${job.sheets[0].sep === "\t" ? "tab" : job.sheets[0].sep}»`}</div></div>
              {job.sheets.length > 1 && <label className="text-xs text-slate-500">Foglio<select className={`${SEL} block mt-1`} value={sheet} onChange={(e) => setSheet(e.target.value)} data-testid="import-sheet-select">{job.sheets.map((s) => <option key={s.name} value={s.name}>{s.name} ({s.rows})</option>)}</select></label>}
              <label className="text-xs text-slate-500">Riga intestazioni<input type="number" min={1} max={30} className={`${SEL} block mt-1 w-24`} value={header} onChange={(e) => setHeader(e.target.value)} data-testid="import-header-row" /></label>
              {pipe && <label className="text-xs text-slate-500">Struttura<select className={`${SEL} block mt-1`} value={layout} onChange={(e) => setLayout(e.target.value)} data-testid="import-layout"><option value="rows">Una riga per attività</option><option value="columns">Colonne = fasi</option></select></label>}
              <label className="text-xs text-slate-500">Modalità<select className={`${SEL} block mt-1`} value={mode} onChange={(e) => setMode(e.target.value)} data-testid="import-mode"><option value="new">Solo nuovi</option><option value="update">Aggiorna esistenti</option><option value="both">Nuovi + aggiornamento</option></select></label>
              {(pipe || PERSON_TARGETS.includes(target.key) || ["sponsor", "pernottamenti", "pasti"].includes(target.key)) && target.key !== "soci" &&
                <div className="w-full sm:w-auto sm:min-w-[240px] min-w-0"><div className="text-xs text-slate-500 mb-1">Evento per tutte le righe</div><SearchSelect value={eventId} onChange={setEventId} options={evOpts} testid="import-default-event" /></div>}
            </div>
            {read && <>
              <p className="text-xs text-slate-500" data-testid="import-total">{read.total} record trovati · anteprima delle prime {Math.min(20, read.total)} righe</p>
              {layout === "rows" && <ConfigBar target={target.key} mapping={mapping} options={{ layout, header_row: header, mode, fasi: cats }} onLoad={loadConfig} superadmin={info.superadmin} />}
              {layout === "rows" ? <MappingTable read={read} fields={target.fields} mapping={mapping} setMapping={setMapping} /> : <p className="text-sm text-slate-600">Ogni colonna diventa una fase e ogni cella non vuota una scheda di quella fase.</p>}
              {pipe && <PipelineSetup read={read} events={info.events} cats={cats} setCats={setCats} resp={resp} setResp={setResp} evMap={evMap} setEvMap={setEvMap} sheets={sheets} setSheets={setSheets} allSheets={job.sheets} people={people} />}
              {pipe && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} data-testid="import-overwrite" />Aggiorna anche le attività già modificate dagli utenti</label>}
              <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={preview} disabled={busy} data-testid="import-preview-btn">Calcola anteprima</Button>
                {prev && <Button onClick={run} disabled={busy || !(prev.actions.crea + prev.actions.aggiorna + prev.items.filter((x) => x.action === "collega").length)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="import-run-btn">Conferma e importa</Button>}</div>
              {prev && <PreviewPanel prev={prev} ctx={{ org: info.org.nome, module: target.label, active: target.active, file: job.filename, sheet }} />}
            </>}
          </div>)}
      </DialogContent>
    </Dialog>
  );
}

export default function Importazione() {
  const [params] = useSearchParams();
  const [info, setInfo] = useState(null);
  const [open, setOpen] = useState(null);
  const [reload, setReload] = useState(0);
  const load = () => api.get("/imports/targets").then(({ data }) => { setInfo(data); const t = data.targets.find((x) => x.key === params.get("target")); if (t && !open) setOpen(t); }).catch((e) => { err(e); setInfo(false); });
  useEffect(() => { load(); }, [reload]); // eslint-disable-line react-hooks/exhaustive-deps
  if (info === false) return <div className="p-6 text-sm text-slate-600" data-testid="import-unavailable">Importazione non disponibile: seleziona un'organizzazione con la tendina Org attiva.</div>;
  if (!info) return <div className="p-6 text-sm text-slate-500">Caricamento…</div>;
  return (
    <div className="animate-fade-up" data-testid="import-page">
      <PageHeader title="Importazione dati" subtitle={`Excel e CSV per ${info.org.nome}: abbina le colonne, controlla i duplicati e conferma.`} />
      {info.superadmin && <p className="mb-4 inline-flex items-center gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800" data-testid="import-superadmin-note"><ShieldCheck className="w-4 h-4" />Super Admin: puoi importare anche nei moduli non attivi. L'importazione non attiva moduli e non modifica l'abbonamento.</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-8">
        {info.targets.map((t) => (
          <div key={t.key} className="rounded-xl border border-slate-200 bg-white p-4 flex flex-col gap-2" data-testid={`import-target-${t.key}`}>
            <div className="flex items-start gap-2"><FileSpreadsheet className="w-5 h-5 text-slate-400 shrink-0" /><div className="font-semibold text-slate-900 text-sm">{t.label}</div></div>
            <div className="flex flex-wrap gap-1 text-[11px]">
              <span className={`rounded-full px-2 py-0.5 font-semibold ${t.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`} data-testid={`import-target-state-${t.key}`}>{t.active ? "Attivo" : "Non attivo"}</span>
              {!t.active && t.has_data && <span className="rounded-full px-2 py-0.5 bg-amber-50 text-amber-700 font-semibold">dati importati</span>}
            </div>
            <div className="mt-auto flex flex-wrap gap-2 pt-1">
              <Button size="sm" onClick={() => setOpen(t)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid={`import-open-${t.key}`}><Upload className="w-4 h-4 mr-1" />Carica file</Button>
              <Button size="sm" variant="ghost" onClick={() => download(`/imports/templates/${t.key}`, `modello-${t.key}.xlsx`).catch(err)} data-testid={`import-template-${t.key}`}><Download className="w-4 h-4 mr-1" />Modello</Button>
            </div>
          </div>))}
        <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-600" data-testid="import-target-iscritti">
          <div className="font-semibold text-slate-900 mb-1">Elenco Iscritti</div>Ha già la sua importazione guidata con edizioni e gare: si apre dalla sezione Elenco Iscritti.
        </div>
      </div>
      <SectionCard title="Storico importazioni"><ImportHistory reloadKey={reload} /></SectionCard>
      {open && <Wizard target={open} info={info} initialEvent={params.get("event") || ""} onClose={() => setOpen(null)} onDone={() => setReload((x) => x + 1)} />}
    </div>
  );
}
