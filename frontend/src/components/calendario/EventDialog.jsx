import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { calApi, err, fmtD, SEL, STATO_EVENTO, STATO_COMM, DISC_LABEL } from "./shared";

const F = [["nome", "Nome manifestazione"], ["specialita", "Specialità"], ["distanza", "Distanza"], ["edizione", "Edizione"], ["anno", "Anno"],
  ["data_inizio", "Data inizio", "date"], ["data_fine", "Data fine", "date"], ["regione", "Regione"], ["provincia", "Provincia"], ["comune", "Comune"],
  ["indirizzo", "Indirizzo"], ["sito_web", "Sito web"], ["pagina_iscrizioni", "Pagina iscrizioni"], ["email", "Email pubblica"], ["telefono", "Telefono pubblico"],
  ["partecipanti", "Partecipanti (se verificabile)"], ["note", "Note interne"]];

export function EventDialog({ id, meta, onClose, onSaved }) {
  const [f, setF] = useState(id ? null : { disciplina: "running", stato: "da_verificare", stato_commerciale: "da_qualificare" });
  const [orgs, setOrgs] = useState([]);
  useEffect(() => {
    if (id) { api.get(calApi(`/events/${id}`)).then(({ data }) => setF(data)).catch(err); }
    api.get(calApi("/organizers"), { params: { limit: 500 } }).then(({ data }) => setOrgs(data.rows)).catch(() => {});
  }, [id]);
  const save = async () => {
    const body = { ...f, anno: f.anno ? Number(f.anno) : null, partecipanti: f.partecipanti ? Number(f.partecipanti) : null };
    ["id", "sources", "history", "organizer", "duplicates", "manual_fields", "nome_key", "merged_into", "created_at", "updated_at"].forEach((k) => delete body[k]);
    try { await (id ? api.put(calApi(`/events/${id}`), body) : api.post(calApi("/events"), body)); toast.success("Evento salvato"); onSaved(); } catch (e) { err(e); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid="cal-event-dialog">
        <DialogTitle>{id ? "Scheda evento" : "Nuovo evento"}</DialogTitle>
        {!f ? <p className="text-sm text-slate-500">Caricamento...</p> : (
          <div className="space-y-4">
            {f.data_da_verificare && <div className="rounded-md bg-amber-50 border border-amber-200 p-2 text-xs font-semibold text-amber-800" data-testid="cal-event-date-conflict">DATA DA VERIFICARE: le fonti riportano date diverse. Nessuna comunicazione commerciale verrà programmata.</div>}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
              <label>Disciplina<select className={`${SEL} w-full`} value={f.disciplina} onChange={(e) => setF({ ...f, disciplina: e.target.value, specialita: "" })} data-testid="cal-ev-disciplina">{Object.keys(meta.discipline).map((k) => <option key={k} value={k}>{DISC_LABEL[k]}</option>)}</select></label>
              <label>Stato manifestazione<select className={`${SEL} w-full`} value={f.stato} onChange={(e) => setF({ ...f, stato: e.target.value })} data-testid="cal-ev-stato">{Object.entries(STATO_EVENTO).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
              <label>Stato commerciale<select className={`${SEL} w-full`} value={f.stato_commerciale} onChange={(e) => setF({ ...f, stato_commerciale: e.target.value })} data-testid="cal-ev-comm">{Object.entries(STATO_COMM).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
              <label className="sm:col-span-3">Organizzatore<select className={`${SEL} w-full`} value={f.organizer_id || ""} onChange={(e) => setF({ ...f, organizer_id: e.target.value || null })} data-testid="cal-ev-org"><option value="">— Nessuno —</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}</select></label>
              {F.map(([k, l, t]) => (
                <label key={k} className={k === "nome" || k === "note" ? "sm:col-span-3" : ""}>{l}
                  {k === "specialita" ? <select className={`${SEL} w-full`} value={f.specialita || ""} onChange={(e) => setF({ ...f, specialita: e.target.value })} data-testid="cal-ev-specialita"><option value="">—</option>{meta.discipline[f.disciplina].map((s) => <option key={s}>{s}</option>)}</select>
                    : <Input type={t || "text"} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} className="h-9" data-testid={`cal-ev-${k}`} />}
                </label>
              ))}
            </div>
            {id && (
              <div className="grid sm:grid-cols-2 gap-3 text-xs">
                <div className="rounded-lg border border-slate-200 p-2" data-testid="cal-ev-sources"><div className="font-semibold mb-1">Fonti</div>
                  {(f.sources || []).map((s, i) => <div key={i}>{s.source}{s.ext_id ? ` · ID ${s.ext_id}` : ""} · {fmtD((s.seen_at || "").slice(0, 10))}{s.url ? <> · <a className="text-[#088F8A]" href={s.url} target="_blank" rel="noopener noreferrer">link</a></> : ""}</div>)}
                  <div className="mt-1 text-slate-500">Comunicazione prevista: <b>{f.data_comunicazione ? fmtD(f.data_comunicazione) : "non calcolabile (evento non confermato o data incerta)"}</b></div>
                </div>
                <div className="rounded-lg border border-slate-200 p-2 max-h-40 overflow-y-auto" data-testid="cal-ev-history"><div className="font-semibold mb-1">Cronologia modifiche</div>
                  {(f.history || []).length ? f.history.map((h) => <div key={h.id}>{fmtD(h.at.slice(0, 10))} · {h.field}: {String(h.old ?? "—")} → {String(h.new ?? "—")} · {h.source} ({h.mode})</div>) : <div className="text-slate-400">Nessuna modifica</div>}
                </div>
              </div>
            )}
            <Button onClick={save} disabled={!f.nome} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-ev-save">Salva</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
