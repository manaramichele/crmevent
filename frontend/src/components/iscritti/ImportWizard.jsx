import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Upload, CheckCircle2 } from "lucide-react";

const SEL = "h-10 rounded-md border border-slate-200 px-3 text-sm bg-white w-full min-w-0";
const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const STEPS = ["Caricamento", "Associazione", "Collegamento campi", "Anteprima", "Importazione"];

function Stat({ label, v, id, tone = "" }) {
  return <div className={`rounded-lg border p-3 ${tone}`} data-testid={`import-stat-${id}`}><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-bold">{v}</div></div>;
}

export function ImportWizard({ open, onClose, meta, edizioni, onDone }) {
  const [step, setStep] = useState(0);
  const [up, setUp] = useState(null);
  const [ed, setEd] = useState({ edizione_id: "", gara: "" });
  const [map, setMap] = useState({});
  const [newF, setNewF] = useState({});
  const [pv, setPv] = useState(null);
  const [mode, setMode] = useState("update");
  const [tpl, setTpl] = useState("");
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setStep(0); setUp(null); setPv(null); setJob(null); setNewF({}); setEd({ edizione_id: "", gara: "" }); } }, [open]);
  useEffect(() => {
    if (!job || job.status !== "in_corso") { return undefined; }
    const t = setInterval(() => api.get(`/iscritti/imports/${job.id}`).then(({ data }) => { setJob(data); if (data.status !== "in_corso") { onDone(); } }).catch(() => {}), 1500);
    return () => clearInterval(t);
  }, [job, onDone]);
  const upload = async (file) => {
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try { const { data } = await api.post("/iscritti/imports/upload", fd); setUp(data); setMap(data.suggested); setStep(1); } catch (e) { err(e); }
    setBusy(false);
  };
  const fieldOpts = [...Object.entries(meta.labels).map(([k, l]) => [k, l]), ...meta.custom_fields.map((c) => [`custom:${c.key}`, `${c.label} (personalizzato)`])];
  const preview = async () => {
    setBusy(true);
    const mapping = { ...map };
    const nf = Object.entries(newF).filter(([, v]) => v).map(([col]) => col);
    try { const { data } = await api.post(`/iscritti/imports/${up.id}/preview`, { ...ed, mapping, new_fields: nf }); setPv(data); setStep(3); } catch (e) { err(e); }
    setBusy(false);
  };
  const run = async () => {
    setBusy(true);
    try { await api.post(`/iscritti/imports/${up.id}/run`, { mode, template_name: tpl || null }); setJob({ id: up.id, status: "in_corso" }); setStep(4); } catch (e) { err(e); }
    setBusy(false);
  };
  const edSel = edizioni.find((e) => e.id === ed.edizione_id);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto" data-testid="import-wizard">
        <DialogTitle>Importa iscritti</DialogTitle>
        <DialogDescription>Fase {step + 1} di 5 · {STEPS[step]}. L'importazione non invia nessuna comunicazione e non vale come consenso marketing.</DialogDescription>
        <div className="flex gap-1">{STEPS.map((s, i) => <div key={s} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-[#0ABAB5]" : "bg-slate-200"}`} />)}</div>
        {step === 0 && (
          <label className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-slate-300 rounded-xl p-8 cursor-pointer hover:border-[#0ABAB5]" data-testid="import-dropzone">
            <Upload className="w-8 h-8 text-[#0ABAB5]" /><span className="font-semibold">{busy ? "Lettura del file..." : "Scegli un file XLSX, XLS o CSV"}</span><span className="text-xs text-slate-500">Massimo 25 MB · prima riga = intestazioni</span>
            <input type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => e.target.files[0] && upload(e.target.files[0])} data-testid="import-file-input" />
          </label>
        )}
        {step === 1 && (
          <div className="space-y-3">
            <p className="text-sm">File <strong>{up.filename}</strong> · {up.total_rows} righe{up.template && <> · modello «{up.template}» applicato</>}</p>
            <select className={SEL} value={ed.edizione_id} onChange={(e) => setEd({ edizione_id: e.target.value, gara: "" })} data-testid="import-edizione">
              <option value="">Evento · anno · edizione...</option>
              {edizioni.map((e) => <option key={e.id} value={e.id}>{e.event_nome} · {e.anno} {e.edizione}</option>)}
            </select>
            {edizioni.length === 0 && <p className="text-xs text-amber-700">Crea prima un'edizione (anche storica) nella scheda "Edizioni".</p>}
            <Input placeholder="Gara o distanza per tutte le righe (facoltativo, se non presente nel file)" value={ed.gara} list="gare-list" onChange={(e) => setEd({ ...ed, gara: e.target.value })} data-testid="import-gara" />
            <datalist id="gare-list">{(edSel?.gare || []).map((g) => <option key={g} value={g} />)}</datalist>
            <div className="flex justify-end"><Button disabled={!ed.edizione_id} onClick={() => setStep(2)} data-testid="import-next-1">Avanti</Button></div>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-2">
            <div className="text-xs text-slate-500">Corrispondenze suggerite automaticamente: modificale o ignora le colonne non necessarie.</div>
            {up.columns.map((c, i) => (
              <div key={c} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-center border-b border-slate-100 pb-2" data-testid={`import-map-row-${i}`}>
                <div className="text-sm min-w-0"><div className="font-semibold truncate">{c}</div><div className="text-xs text-slate-500 truncate">{up.sample.map((r) => r[i]).filter(Boolean).slice(0, 2).join(" · ")}</div></div>
                <select className={SEL} value={newF[c] ? "__new" : map[c] || ""} onChange={(e) => { const v = e.target.value; setNewF({ ...newF, [c]: v === "__new" }); setMap({ ...map, [c]: v === "__new" ? "" : v }); }} data-testid={`import-map-${i}`}>
                  <option value="">— Ignora colonna —</option>
                  {fieldOpts.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  <option value="__new">+ Nuovo campo personalizzato «{c}»</option>
                </select>
              </div>
            ))}
            <div className="flex justify-between"><Button variant="outline" onClick={() => setStep(1)}>Indietro</Button><Button disabled={busy} onClick={preview} data-testid="import-preview">{busy ? "Analisi..." : "Anteprima"}</Button></div>
          </div>
        )}
        {step === 3 && pv && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <Stat id="total" label="Righe totali" v={pv.stats.total} />
              <Stat id="new" label="Nuovi iscritti" v={pv.stats.new} tone="bg-emerald-50" />
              <Stat id="existing" label="Già presenti" v={pv.stats.existing} />
              <Stat id="duplicates" label="Duplicati nel file" v={pv.stats.duplicates} />
              <Stat id="errors" label="Righe con errori" v={pv.stats.errors} tone={pv.stats.errors ? "bg-red-50" : ""} />
              <Stat id="already" label="Già iscritti all'edizione" v={pv.stats.already_in_edition} />
            </div>
            {Object.keys(pv.missing).length > 0 && <p className="text-xs text-amber-800" data-testid="import-missing">Campi mancanti: {Object.entries(pv.missing).map(([k, n]) => `${meta.labels[k]} in ${n} righe`).join(" · ")}</p>}
            {pv.errors.length > 0 && <ul className="text-xs max-h-32 overflow-y-auto bg-slate-50 rounded p-2" data-testid="import-errors">{pv.errors.map((e) => <li key={e.row} className={e.warning ? "text-amber-700" : "text-red-700"}>Riga {e.row}: {e.errors.join(", ")}{e.warning ? " (importata senza il dato)" : ""}</li>)}</ul>}
            <div className="space-y-1 text-sm">
              <label className="flex items-center gap-2"><input type="radio" checked={mode === "update"} onChange={() => setMode("update")} data-testid="import-mode-update" />Aggiorna i dati degli iscritti già presenti</label>
              <label className="flex items-center gap-2"><input type="radio" checked={mode === "skip"} onChange={() => setMode("skip")} data-testid="import-mode-skip" />Non modificare gli iscritti già presenti (aggiungi solo la partecipazione)</label>
            </div>
            <Input placeholder="Salva le associazioni come modello (nome, facoltativo)" value={tpl} onChange={(e) => setTpl(e.target.value)} data-testid="import-template-name" />
            <div className="flex justify-between"><Button variant="outline" onClick={() => setStep(2)}>Indietro</Button><Button disabled={busy} onClick={run} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="import-run">Importa</Button></div>
          </div>
        )}
        {step === 4 && job && (
          <div className="space-y-2" data-testid="import-report">
            {job.status === "in_corso" ? <p className="text-sm">Importazione in corso in background{job.progress ? ` · ${job.progress} righe elaborate` : ""}... puoi chiudere questa finestra.</p> : (
              <>
                <p className="font-semibold flex items-center gap-2"><CheckCircle2 className="w-5 h-5 text-emerald-600" />{job.status === "completato" ? "Importazione completata" : `Errore: ${job.error}`}</p>
                {job.result && <p className="text-sm" data-testid="import-result">Creati {job.result.created} · aggiornati {job.result.updated} · invariati {job.result.unchanged} · nuove partecipazioni {job.result.participations} · già presenti {job.result.skipped_participations} · duplicati {job.result.duplicates} · errori {job.result.errors}</p>}
                <div className="flex justify-end"><Button onClick={onClose} data-testid="import-close">Chiudi</Button></div>
              </>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
