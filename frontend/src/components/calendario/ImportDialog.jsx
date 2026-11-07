import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { calApi, err, SEL } from "./shared";

const LBL = { nome: "Nome manifestazione", disciplina: "Disciplina", specialita: "Specialità", distanza: "Distanza", edizione: "Edizione", anno: "Anno",
  data_inizio: "Data inizio", data_fine: "Data fine", regione: "Regione", provincia: "Provincia", comune: "Comune", indirizzo: "Indirizzo", lat: "Latitudine",
  lng: "Longitudine", sito_web: "Sito web", pagina_iscrizioni: "Pagina iscrizioni", email: "Email", telefono: "Telefono", partecipanti: "Partecipanti",
  note: "Note", organizzatore: "Organizzatore", ext_id: "ID nella fonte" };

export function ImportDialog({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [pv, setPv] = useState(null);
  const [map, setMap] = useState({});
  const [job, setJob] = useState(null);
  const pick = async (fl) => {
    setFile(fl);
    const fd = new FormData(); fd.append("file", fl);
    try { const { data } = await api.post(calApi("/import/preview"), fd); setPv(data); setMap(data.mapping); } catch (e) { err(e); }
  };
  const poll = (id) => {
    const t = setInterval(async () => {
      const { data } = await api.get(calApi(`/import/${id}`));
      setJob(data);
      if (data.status === "done") { clearInterval(t); toast.success("Importazione completata"); onDone(); }
    }, 1500);
  };
  const run = async () => {
    const fd = new FormData(); fd.append("file", file); fd.append("mapping", JSON.stringify(map)); fd.append("source", "manuale");
    try { const { data } = await api.post(calApi("/import"), fd); setJob({ status: "running", total: data.total, progress: 0 }); poll(data.job_id); } catch (e) { err(e); }
  };
  const r = job?.result || {};
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid="cal-import-dialog">
        <DialogTitle>Importa eventi da Excel/CSV</DialogTitle>
        <DialogDescription>Le righe già presenti vengono collegate all'evento esistente; i casi dubbi finiscono in "Possibili duplicati".</DialogDescription>
        {!job && <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => e.target.files[0] && pick(e.target.files[0])} data-testid="cal-import-file" />}
        {pv && !job && (
          <div className="space-y-2 text-xs">
            <div>{pv.total} righe trovate. Associa le colonne:</div>
            <div className="grid sm:grid-cols-2 gap-2">{pv.columns.map((c) => (
              <label key={c} className="flex items-center gap-2"><span className="w-32 truncate font-medium" title={c}>{c}</span>
                <select className={`${SEL} flex-1`} value={map[c] || ""} onChange={(e) => setMap({ ...map, [c]: e.target.value })} data-testid={`cal-map-${c}`}>
                  <option value="">Ignora</option>{pv.fields.map((f) => <option key={f} value={f}>{LBL[f] || f}</option>)}</select></label>))}</div>
            <Button onClick={run} disabled={!Object.values(map).includes("nome")} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-import-run">Importa</Button>
          </div>
        )}
        {job && (
          <div className="text-sm space-y-1" data-testid="cal-import-result">
            <div>{job.status === "done" ? "Completata" : `In corso: ${job.progress || 0}/${job.total}`}</div>
            <div>Nuovi: <b>{r.created || 0}</b> · Collegati a eventi esistenti: <b>{r.linked || 0}</b> · Possibili duplicati: <b>{r.possible_duplicates || 0}</b> · Errori: <b>{r.errors || 0}</b></div>
            {(job.errors || []).slice(0, 10).map((e) => <div key={e.row} className="text-xs text-red-600">Riga {e.row}: {e.error}</div>)}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
