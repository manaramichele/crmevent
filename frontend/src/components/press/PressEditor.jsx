import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Sparkles, Loader2, AlertTriangle, Save, Eye, FileDown, Copy, Send, CheckCircle2, Plus, X, RefreshCw } from "lucide-react";
import { TIPI, MEDIA, StatusPill, pErr, dt, TIFFANY_BTN, SEL, Field } from "@/components/press/pressShared";

export function NewRelease({ events, onClose, onCreated }) {
  const [f, setF] = useState({ event_id: "", tipo: "presentazione", extra: "", tono: "istituzionale" });
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (f.event_id) api.get(`/press/events/${f.event_id}/data`, { params: { tipo: f.tipo } }).then(({ data }) => setInfo(data)).catch(pErr);
  }, [f.event_id, f.tipo]);
  const gen = async () => {
    setBusy(true);
    try { const { data } = await api.post("/press/generate", f); toast.success("Comunicato generato: controlla e completa il testo"); onCreated(data); } catch (e) { pErr(e); }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto" data-testid="press-new-dialog">
        <DialogTitle>Nuovo comunicato</DialogTitle>
        <DialogDescription>L'AI usa solo i dati dell'evento e le informazioni che inserisci: non inventa numeri, risultati o dichiarazioni.</DialogDescription>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Evento *"><select className={`${SEL} w-full`} value={f.event_id} onChange={(e) => setF({ ...f, event_id: e.target.value })} data-testid="press-new-event"><option value="">Seleziona un evento</option>{events.map((e) => <option key={e.id} value={e.id}>{e.nome}{e.data_inizio ? ` · ${e.data_inizio.slice(0, 10)}` : ""}</option>)}</select></Field>
          <Field label="Tipologia *"><select className={`${SEL} w-full`} value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value })} data-testid="press-new-tipo">{Object.entries(TIPI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
        </div>
        {info && (
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs space-y-1" data-testid="press-new-data">
            <div className="font-semibold text-slate-700">Dati recuperati da CRMEvent</div>
            {Object.entries(info.data).map(([k, v]) => <div key={k} className="text-slate-600"><span className="text-slate-400">{k.replace(/_/g, " ")}:</span> {typeof v === "object" ? JSON.stringify(v) : String(v)}</div>)}
            {info.missing.length > 0 && <div className="flex gap-1.5 text-amber-700 pt-1" data-testid="press-new-missing"><AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />Da completare qui sotto, se disponibili: {info.missing.join(", ")}</div>}
          </div>
        )}
        <Field label="Informazioni aggiuntive (verificate)" hint="Es. numero iscritti, risultati, vincitori, dichiarazioni testuali con autore, programma, logistica."><Textarea rows={5} value={f.extra} onChange={(e) => setF({ ...f, extra: e.target.value })} data-testid="press-new-extra" /></Field>
        <Field label="Tono"><select className={`${SEL} w-full`} value={f.tono} onChange={(e) => setF({ ...f, tono: e.target.value })} data-testid="press-new-tono"><option value="istituzionale">Istituzionale</option><option value="sportivo">Sportivo / dinamico</option><option value="sobrio">Sobrio e sintetico</option></select></Field>
        <Button disabled={busy || !f.event_id} onClick={gen} className={`w-full h-11 ${TIFFANY_BTN}`} data-testid="press-generate">{busy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}{busy ? "Generazione in corso..." : "Genera comunicato"}</Button>
      </DialogContent>
    </Dialog>
  );
}

function ListEditor({ items, setItems, fields, addLabel, testid }) {
  return (
    <div className="space-y-2" data-testid={testid}>
      {items.map((it, i) => (
        <div key={i} className="flex gap-2 items-start">
          {fields.map(([k, ph]) => <Input key={k} placeholder={ph} value={it[k] || ""} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, [k]: e.target.value } : x)))} />)}
          <Button type="button" variant="ghost" size="icon" onClick={() => setItems(items.filter((_, j) => j !== i))} aria-label="Rimuovi"><X className="w-4 h-4" /></Button>
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={() => setItems([...items, {}])}><Plus className="w-3.5 h-3.5 mr-1" />{addLabel}</Button>
    </div>
  );
}

function SendDialog({ rel, onClose, onDone }) {
  const [f, setF] = useState({ mode: "now", send_at: "", oggetto_email: rel.oggetto_email || rel.titolo || "", media: [], regioni: [] });
  const [rc, setRc] = useState(null);
  const [test, setTest] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.post(`/press/releases/${rel.id}/recipients`, f).then(({ data }) => setRc(data)).catch(() => {}); }, [f.media, f.regioni]); // eslint-disable-line react-hooks/exhaustive-deps
  const go = async () => {
    setBusy(true);
    try { await api.post(`/press/releases/${rel.id}/send`, { ...f, send_at: f.mode === "scheduled" ? new Date(f.send_at).toISOString() : null }); toast.success(f.mode === "now" ? "Invio avviato" : "Invio programmato"); onDone(); } catch (e) { pErr(e); }
    setBusy(false);
  };
  const sendTest = async () => { try { await api.post(`/press/releases/${rel.id}/test`, { email: test }); toast.success("Email di prova inviata"); } catch (e) { pErr(e); } };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto" data-testid="press-send-dialog">
        <DialogTitle>Prepara invio</DialogTitle>
        <DialogDescription>Ricevono il comunicato solo i contatti attivi, con base giuridica indicata e non disiscritti dalla tua organizzazione.</DialogDescription>
        <Field label="Oggetto email"><Input value={f.oggetto_email} onChange={(e) => setF({ ...f, oggetto_email: e.target.value })} data-testid="press-send-subject" /></Field>
        <Field label="Tipologia media (vuoto = tutte)"><select multiple className={`${SEL} w-full h-24`} value={f.media} onChange={(e) => setF({ ...f, media: [...e.target.selectedOptions].map((o) => o.value) })} data-testid="press-send-media">{MEDIA.map((m) => <option key={m}>{m}</option>)}</select></Field>
        <Field label="Regioni (separate da virgola, vuoto = tutte)"><Input onChange={(e) => setF({ ...f, regioni: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} data-testid="press-send-regioni" /></Field>
        <div className="text-sm font-medium text-slate-700" data-testid="press-send-count">Destinatari idonei: {rc ? rc.count : "…"}{rc?.excluded ? <span className="text-xs text-slate-500"> · {rc.excluded} esclusi (disiscritti, sospesi o senza base giuridica)</span> : null}</div>
        <div className="flex gap-2"><Input placeholder="Email per la prova" value={test} onChange={(e) => setTest(e.target.value)} data-testid="press-test-email" /><Button variant="outline" onClick={sendTest} disabled={!test} data-testid="press-test-send">Invia prova</Button></div>
        <div className="flex gap-4 text-sm">
          <label className="flex items-center gap-2"><input type="radio" checked={f.mode === "now"} onChange={() => setF({ ...f, mode: "now" })} data-testid="press-mode-now" />Invia subito</label>
          <label className="flex items-center gap-2"><input type="radio" checked={f.mode === "scheduled"} onChange={() => setF({ ...f, mode: "scheduled" })} data-testid="press-mode-scheduled" />Programma</label>
        </div>
        {f.mode === "scheduled" && <Input type="datetime-local" value={f.send_at} onChange={(e) => setF({ ...f, send_at: e.target.value })} data-testid="press-send-at" />}
        <Button disabled={busy || !rc?.count || (f.mode === "scheduled" && !f.send_at)} onClick={go} className={`w-full h-11 ${TIFFANY_BTN}`} data-testid="press-send-confirm"><Send className="w-4 h-4 mr-2" />{f.mode === "now" ? `Conferma invio a ${rc?.count || 0} destinatari` : "Conferma programmazione"}</Button>
      </DialogContent>
    </Dialog>
  );
}

export function Editor({ id, canEdit, onClose, onChanged }) {
  const [r, setR] = useState(null);
  const [busy, setBusy] = useState("");
  const [sending, setSending] = useState(false);
  const load = () => api.get(`/press/releases/${id}`).then(({ data }) => setR(data)).catch(pErr);
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  const locked = !canEdit || ["in_invio", "inviato", "annullato"].includes(r?.status);
  const set = (k) => (e) => setR({ ...r, [k]: e.target ? e.target.value : e });
  const run = async (kind, fn, ok) => { setBusy(kind); try { await fn(); if (ok) toast.success(ok); await load(); onChanged(); } catch (e) { pErr(e); } setBusy(""); };
  const save = () => run("save", () => api.put(`/press/releases/${id}`, { titolo: r.titolo, sottotitolo: r.sottotitolo, testo: r.testo, citazioni: r.citazioni, foto: r.foto, contatto_stampa: r.contatto_stampa, oggetto_email: r.oggetto_email }), "Bozza salvata");
  const regen = () => run("regen", () => api.post(`/press/generate`, { event_id: r.event_id, tipo: r.tipo, extra: r.extra || "", tono: r.tono || "istituzionale" }, { params: { rid: id } }), "Comunicato rigenerato");
  const preview = async (print) => {
    try {
      const { data } = await api.get(`/press/releases/${id}/preview`, { responseType: "text" });
      const w = window.open("", "_blank");
      if (!w) return toast.error("Consenti le finestre popup per l'anteprima");
      w.document.write(data); w.document.close();
      if (print) setTimeout(() => w.print(), 400);
    } catch (e) { pErr(e); }
  };
  const copy = () => { navigator.clipboard.writeText(`${r.titolo}\n${r.sottotitolo || ""}\n\n${r.testo}`); toast.success("Testo copiato"); };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto p-4 sm:p-6" data-testid="press-editor">
        {!r ? <p className="text-sm text-slate-400">Caricamento...</p> : (<>
          <div className="pr-6 flex flex-wrap items-center gap-2"><DialogTitle>{TIPI[r.tipo]}</DialogTitle><StatusPill s={r.status} testid="press-editor-status" />
            {r.approved_at && <span className="text-xs text-emerald-700" data-testid="press-editor-approved"><CheckCircle2 className="inline w-3.5 h-3.5 mr-0.5" />Approvato da {r.approved_by?.name} il {dt(r.approved_at)}</span>}
            {r.send_at && r.status === "programmato" && <span className="text-xs text-sky-700">Invio: {dt(r.send_at)}</span>}
            {r.approval_expired && <span className="text-xs text-red-600 font-semibold" data-testid="press-editor-expired">Invio sospeso: non approvato in tempo. Approva e programma di nuovo.</span>}</div>
          {r.dati_mancanti?.length > 0 && <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800" data-testid="press-editor-missing"><AlertTriangle className="inline w-3.5 h-3.5 mr-1" />Dati non disponibili, da completare o verificare: {r.dati_mancanti.join(", ")}</div>}
          <Field label="Titolo"><Input disabled={locked} value={r.titolo || ""} onChange={set("titolo")} data-testid="press-editor-title" /></Field>
          <Field label="Sottotitolo"><Input disabled={locked} value={r.sottotitolo || ""} onChange={set("sottotitolo")} data-testid="press-editor-subtitle" /></Field>
          <Field label="Testo"><Textarea disabled={locked} rows={14} value={r.testo || ""} onChange={set("testo")} data-testid="press-editor-body" /></Field>
          <Field label="Citazioni (testo esatto e autore)"><ListEditor items={r.citazioni || []} setItems={set("citazioni")} fields={[["testo", "Citazione"], ["autore", "Autore e ruolo"]]} addLabel="Aggiungi citazione" testid="press-editor-quotes" /></Field>
          <Field label="Fotografie (URL https pubblico e didascalia)"><ListEditor items={r.foto || []} setItems={set("foto")} fields={[["url", "https://..."], ["didascalia", "Didascalia"]]} addLabel="Aggiungi foto" testid="press-editor-photos" /></Field>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Contatto stampa"><Input disabled={locked} value={r.contatto_stampa || ""} onChange={set("contatto_stampa")} placeholder="Nome · email · telefono" data-testid="press-editor-contact" /></Field>
            <Field label="Oggetto email"><Input disabled={locked} value={r.oggetto_email || ""} onChange={set("oggetto_email")} data-testid="press-editor-subject" /></Field>
          </div>
          <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-100">
            {!locked && <Button onClick={save} disabled={!!busy} variant="outline" data-testid="press-editor-save"><Save className="w-4 h-4 mr-1" />Salva bozza</Button>}
            {!locked && <Button onClick={regen} disabled={!!busy} variant="outline" data-testid="press-editor-regen">{busy === "regen" ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-1" />}Rigenera</Button>}
            <Button onClick={() => preview(false)} variant="outline" data-testid="press-editor-preview"><Eye className="w-4 h-4 mr-1" />Anteprima email</Button>
            <Button onClick={() => preview(true)} variant="outline" data-testid="press-editor-pdf"><FileDown className="w-4 h-4 mr-1" />Esporta PDF</Button>
            <Button onClick={copy} variant="outline" data-testid="press-editor-copy"><Copy className="w-4 h-4 mr-1" />Copia testo</Button>
            {canEdit && ["bozza", "da_approvare"].includes(r.status) && !r.approved_at && <Button onClick={() => run("approve", () => api.post(`/press/releases/${id}/approve`), "Comunicato approvato")} disabled={!!busy} className={TIFFANY_BTN} data-testid="press-editor-approve"><CheckCircle2 className="w-4 h-4 mr-1" />Approva testo</Button>}
            {canEdit && r.approved_at && ["bozza", "da_approvare", "programmato"].includes(r.status) && <Button onClick={() => setSending(true)} className={TIFFANY_BTN} data-testid="press-editor-send"><Send className="w-4 h-4 mr-1" />Prepara invio</Button>}
            {canEdit && r.status === "programmato" && <Button variant="outline" onClick={() => run("cancel", () => api.post(`/press/releases/${id}/cancel`), "Invio annullato")} data-testid="press-editor-cancel">Annulla invio</Button>}
          </div>
          {r.versions?.length > 0 && <details className="text-xs text-slate-500"><summary className="cursor-pointer">Versioni salvate ({r.versions.length})</summary>{r.versions.map((v) => <div key={v.id}>{dt(v.created_at)} · {v.origin} · {v.by?.name || "Automazione"}</div>)}</details>}
          {sending && <SendDialog rel={r} onClose={() => setSending(false)} onDone={() => { setSending(false); load(); onChanged(); }} />}
        </>)}
      </DialogContent>
    </Dialog>
  );
}
