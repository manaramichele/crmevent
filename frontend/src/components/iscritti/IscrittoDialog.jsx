import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const FIELDS = ["nome", "cognome", "email", "cellulare", "data_nascita", "sesso", "nazionalita", "societa", "codice_fiscale", "numero_tessera", "federazione"];
const EMPTY = { ...Object.fromEntries(FIELDS.map((f) => [f, ""])), note: "", consenso_marketing: false, consenso_fonte: "", custom: {} };
const SEL = "h-10 rounded-md border border-slate-200 px-3 text-sm bg-white w-full min-w-0";

// Scheda iscritto: dati, consenso con storico, storico partecipazioni; nuovo iscritto se id è null.
export function IscrittoDialog({ id, open, onClose, meta, edizioni, onChanged }) {
  const [p, setP] = useState(null);
  const [f, setF] = useState(EMPTY);
  const [part, setPart] = useState({ edizione_id: "", gara: "", stato: "confermata" });
  const edit = meta.can_edit;
  useEffect(() => {
    if (!open) { return; }
    setPart({ edizione_id: "", gara: "", stato: "confermata" });
    if (!id) { setP({ partecipazioni: [], consent_history: [] }); setF(EMPTY); return; }
    api.get(`/iscritti/${id}`).then(({ data }) => { setP(data); setF({ ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, data[k] ?? EMPTY[k]])) }); }).catch(err);
  }, [id, open]);
  const save = async () => {
    const body = { ...f, partecipazione: part.edizione_id ? part : null };
    try {
      if (id) { const { data } = await api.put(`/iscritti/${id}`, body); setP(data); } else { await api.post("/iscritti", body); onClose(); }
      toast.success("Iscritto salvato"); onChanged();
    } catch (e) { err(e); }
  };
  const act = async (kind) => {
    if (!window.confirm(kind === "anon" ? "Anonimizzare definitivamente i dati personali di questo iscritto?" : "Cancellare definitivamente l'iscritto e le sue partecipazioni?")) return;
    try { if (kind === "anon") { await api.post(`/iscritti/${id}/anonymize`); } else { await api.delete(`/iscritti/${id}`); } toast.success("Operazione completata"); onClose(); onChanged(); } catch (e) { err(e); }
  };
  if (!p) return null;
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto" data-testid="iscritto-dialog">
        <DialogTitle>{id ? `${p.nome || ""} ${p.cognome || ""}`.trim() || p.email || "Iscritto" : "Aggiungi iscritto"}</DialogTitle>
        <DialogDescription>{p.anonymized ? "Dati anonimizzati." : "Anagrafica unica: le partecipazioni a eventi ed edizioni restano separate."}</DialogDescription>
        <div className="grid sm:grid-cols-2 gap-2">
          {FIELDS.map((k) => <Input key={k} disabled={!edit || p.anonymized} placeholder={meta.labels[k]} aria-label={meta.labels[k]} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`iscritto-${k}`} />)}
          {meta.custom_fields.map((c) => <Input key={c.key} disabled={!edit} placeholder={c.label} value={f.custom[c.key] || ""} onChange={(e) => setF({ ...f, custom: { ...f.custom, [c.key]: e.target.value } })} data-testid={`iscritto-custom-${c.key}`} />)}
        </div>
        <Textarea disabled={!edit} placeholder="Note" rows={2} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="iscritto-note" />
        <div className="rounded-lg border border-slate-200 p-3 space-y-2">
          <label className="flex items-center gap-2 text-sm font-semibold"><Checkbox disabled={!edit} checked={f.consenso_marketing} onCheckedChange={(v) => setF({ ...f, consenso_marketing: !!v })} data-testid="iscritto-consenso" />Consenso a comunicazioni promozionali</label>
          {edit && <Input placeholder="Fonte del consenso (es. modulo iscrizione 2025)" value={f.consenso_fonte} onChange={(e) => setF({ ...f, consenso_fonte: e.target.value })} data-testid="iscritto-consenso-fonte" />}
          {p.consenso_data && <p className="text-xs text-slate-500">Ultimo aggiornamento: {p.consenso_data} · {p.consenso_fonte}{p.unsubscribed ? " · disiscritto" : ""} · Brevo: {p.brevo_status}</p>}
          {p.consent_history?.length > 0 && <ul className="text-xs text-slate-500" data-testid="iscritto-consent-history">{p.consent_history.map((h, i) => <li key={i}>{h.at.slice(0, 10)} · {h.value ? "concesso" : "revocato"} · {h.source}</li>)}</ul>}
        </div>
        <div>
          <div className="text-sm font-semibold mb-1">Storico partecipazioni</div>
          {p.partecipazioni.length === 0 ? <p className="text-xs text-slate-500">Nessuna partecipazione.</p> : (
            <ul className="text-sm space-y-1" data-testid="iscritto-partecipazioni">{p.partecipazioni.map((x) => <li key={x.id} className="flex flex-wrap gap-2 border-b border-slate-100 pb-1"><strong>{x.event_nome}</strong>{x.anno} {x.edizione}<span className="text-slate-500">{x.gara || "—"} · {x.stato}{x.data_iscrizione ? ` · ${x.data_iscrizione}` : ""}</span></li>)}</ul>
          )}
          {edit && !p.anonymized && (
            <div className="grid sm:grid-cols-3 gap-2 mt-2">
              <select className={SEL} value={part.edizione_id} onChange={(e) => setPart({ ...part, edizione_id: e.target.value })} data-testid="iscritto-add-edizione"><option value="">+ Aggiungi a edizione...</option>{edizioni.map((e) => <option key={e.id} value={e.id}>{e.event_nome} {e.anno} {e.edizione}</option>)}</select>
              <Input placeholder="Gara/distanza" value={part.gara} onChange={(e) => setPart({ ...part, gara: e.target.value })} data-testid="iscritto-add-gara" />
              <select className={SEL} value={part.stato} onChange={(e) => setPart({ ...part, stato: e.target.value })} data-testid="iscritto-add-stato">{meta.stati.map((s) => <option key={s}>{s}</option>)}</select>
            </div>
          )}
        </div>
        {edit && !p.anonymized && (
          <div className="flex flex-wrap gap-2 justify-between pt-2">
            <div className="flex gap-2">{id && <><Button variant="outline" onClick={() => act("anon")} data-testid="iscritto-anonymize">Anonimizza</Button><Button variant="outline" className="text-red-600" onClick={() => act("del")} data-testid="iscritto-delete">Cancella</Button></>}</div>
            <Button onClick={save} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="iscritto-save">Salva</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
