import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { calApi, err, SEL } from "./shared";

const FORMATI = { csv: "CSV", xlsx: "Excel (XLSX)", json: "JSON", ics: "Calendario ICS" };
const Field = ({ label, children }) => <label className="block text-xs text-slate-600 space-y-1"><span>{label}</span>{children}</label>;

export function VerificaDialog({ src, onClose, onSaved }) {
  const v = src.verifica || {};
  const [f, setF] = useState({ esito: v.esito || "da_verificare", metodo: v.metodo || "", prova: v.prova || "", note: v.note || "" });
  const save = async () => {
    try { await api.put(calApi(`/sources/${src.id}/verifica`), f); toast.success("Verifica registrata"); onSaved(); } catch (e) { err(e); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-w-lg" data-testid="cal-verifica-dialog">
      <DialogHeader><DialogTitle>Verifica accesso — {src.nome}</DialogTitle></DialogHeader>
      <div className="space-y-3">
        <Field label="Esito"><select className={`${SEL} w-full`} value={f.esito} onChange={(e) => setF({ ...f, esito: e.target.value })} data-testid="cal-verifica-esito">
          <option value="consentita">Consentita</option><option value="non_consentita">Non consentita</option><option value="da_verificare">Da verificare</option></select></Field>
        <Field label="Metodo di accesso autorizzato (es. API ufficiale, feed partner, accordo di esportazione)"><Input value={f.metodo} onChange={(e) => setF({ ...f, metodo: e.target.value })} data-testid="cal-verifica-metodo" /></Field>
        <Field label="Prova dell'autorizzazione (riferimento accordo, licenza, link documentazione API)"><Textarea rows={2} value={f.prova} onChange={(e) => setF({ ...f, prova: e.target.value })} data-testid="cal-verifica-prova" /></Field>
        <Field label="Note"><Textarea rows={2} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="cal-verifica-note" /></Field>
        <p className="text-[11px] text-slate-500">"Consentita" richiede metodo e prova. Con esito diverso la fonte resta scollegata.</p>
        <Button onClick={save} className="w-full bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-verifica-save">Salva verifica</Button>
      </div>
    </DialogContent></Dialog>
  );
}

export function ConnDialog({ src, onClose, onSaved }) {
  const [f, setF] = useState({ feed_url: src.feed_url || "", formato: src.formato || "csv", attiva: src.attiva ?? true });
  const [prev, setPrev] = useState(null);
  const save = async () => {
    try { await api.put(calApi(`/sources/${src.id}/connessione`), f); toast.success("Collegamento salvato"); onSaved(); } catch (e) { err(e); }
  };
  const test = async () => {
    try { await api.put(calApi(`/sources/${src.id}/connessione`), f); const { data } = await api.post(calApi(`/sources/${src.id}/test`)); setPrev(data); } catch (e) { err(e); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-w-lg" data-testid="cal-conn-dialog">
      <DialogHeader><DialogTitle>Collegamento — {src.nome}</DialogTitle></DialogHeader>
      <div className="space-y-3">
        <Field label="Indirizzo del feed autorizzato"><Input value={f.feed_url} onChange={(e) => setF({ ...f, feed_url: e.target.value })} placeholder="https://..." data-testid="cal-conn-url" /></Field>
        <Field label="Formato"><select className={`${SEL} w-full`} value={f.formato} onChange={(e) => setF({ ...f, formato: e.target.value })} data-testid="cal-conn-formato">
          {Object.entries(FORMATI).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.attiva} onChange={(e) => setF({ ...f, attiva: e.target.checked })} data-testid="cal-conn-attiva" />Fonte attiva (inclusa nella sincronizzazione delle 03:00)</label>
        {prev && <div className="rounded-lg bg-slate-50 border border-slate-200 p-2 text-xs" data-testid="cal-conn-preview">Letti <b>{prev.total}</b> eventi · colonne: {prev.columns.join(", ")}
          {!Object.values(prev.mapping).includes("nome") && <div className="text-red-600 mt-1">Nessuna colonna riconosciuta come nome manifestazione.</div>}</div>}
        <div className="flex gap-2"><Button variant="outline" onClick={test} className="flex-1" data-testid="cal-conn-test">Prova lettura</Button>
          <Button onClick={save} className="flex-1 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-conn-save">Salva</Button></div>
      </div>
    </DialogContent></Dialog>
  );
}

export function NewSourceDialog({ onClose, onSaved }) {
  const [f, setF] = useState({ nome: "", disciplina: "running", url: "", feed_url: "", formato: "csv", metodo: "", prova: "", note: "" });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { await api.post(calApi("/sources"), f); toast.success("Fonte autorizzata aggiunta"); onSaved(); } catch (e) { err(e); }
  };
  return (
    <Dialog open onOpenChange={onClose}><DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="cal-newsource-dialog">
      <DialogHeader><DialogTitle>Aggiungi fonte autorizzata</DialogTitle></DialogHeader>
      <div className="space-y-3">
        <Field label="Nome fonte"><Input value={f.nome} onChange={set("nome")} data-testid="cal-newsource-nome" /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Disciplina"><select className={`${SEL} w-full`} value={f.disciplina} onChange={set("disciplina")} data-testid="cal-newsource-disciplina">
            <option value="running">Running</option><option value="trail">Trail</option><option value="triathlon">Triathlon</option><option value="*">Tutte</option></select></Field>
          <Field label="Formato"><select className={`${SEL} w-full`} value={f.formato} onChange={set("formato")} data-testid="cal-newsource-formato">
            {Object.entries(FORMATI).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
        </div>
        <Field label="Sito della fonte"><Input value={f.url} onChange={set("url")} placeholder="https://..." data-testid="cal-newsource-url" /></Field>
        <Field label="Indirizzo del feed autorizzato"><Input value={f.feed_url} onChange={set("feed_url")} placeholder="https://..." data-testid="cal-newsource-feed" /></Field>
        <Field label="Metodo di accesso autorizzato"><Input value={f.metodo} onChange={set("metodo")} placeholder="es. feed ufficiale concesso con accordo del..." data-testid="cal-newsource-metodo" /></Field>
        <Field label="Prova dell'autorizzazione"><Textarea rows={2} value={f.prova} onChange={set("prova")} data-testid="cal-newsource-prova" /></Field>
        <Field label="Note"><Textarea rows={2} value={f.note} onChange={set("note")} data-testid="cal-newsource-note" /></Field>
        <Button onClick={save} className="w-full bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-newsource-save">Aggiungi fonte</Button>
      </div>
    </DialogContent></Dialog>
  );
}
