import { useCallback, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, MessageSquareWarning, CheckCircle2, RotateCcw } from "lucide-react";
import { CATEGORIES, StatusBadge, Conversation, Composer, FilePicker, dt, err, usePoll } from "@/components/tickets/TicketShared";

function NewTicket({ onClose, onCreated }) {
  const [f, setF] = useState({ category: "", subject: "", description: "" });
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const submit = async () => {
    if (!f.category || !f.subject.trim() || !f.description.trim()) return toast.error("Compila categoria, oggetto e descrizione");
    const fd = new FormData();
    Object.entries(f).forEach(([k, v]) => fd.append(k, v));
    files.forEach((x) => fd.append("files", x));
    setBusy(true);
    try { const { data } = await api.post("/tickets", fd); setDone(data); onCreated(); } catch (e) { err(e); }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl w-[calc(100vw-1.5rem)] max-h-[92dvh] overflow-y-auto" data-testid="ticket-new-dialog">
        {done ? (
          <div className="text-center py-6 space-y-3" data-testid="ticket-new-success">
            <CheckCircle2 className="w-12 h-12 mx-auto text-[#0ABAB5]" />
            <DialogTitle>Richiesta inviata</DialogTitle>
            <p className="text-sm text-slate-600">Il numero della tua richiesta è <b className="text-slate-900" data-testid="ticket-new-number">#{done.number}</b>. Troverai qui gli aggiornamenti del team CRMEvent.</p>
            <Button onClick={onClose} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="ticket-new-close">Chiudi</Button>
          </div>
        ) : (<>
          <DialogTitle>Nuova richiesta</DialogTitle>
          <DialogDescription>Descrivi il problema o la richiesta: il team CRMEvent ti risponderà qui.</DialogDescription>
          <div className="space-y-3">
            <label className="block text-sm font-medium text-slate-700">Categoria
              <Select value={f.category} onValueChange={(v) => setF({ ...f, category: v })}>
                <SelectTrigger className="mt-1" data-testid="ticket-new-category"><SelectValue placeholder="Seleziona una categoria" /></SelectTrigger>
                <SelectContent>{Object.entries(CATEGORIES).map(([k, v]) => <SelectItem key={k} value={k} data-testid={`ticket-category-${k}`}>{v}</SelectItem>)}</SelectContent>
              </Select>
            </label>
            <label className="block text-sm font-medium text-slate-700">Oggetto
              <Input className="mt-1" maxLength={200} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} data-testid="ticket-new-subject" />
            </label>
            <label className="block text-sm font-medium text-slate-700">Descrizione dettagliata
              <Textarea className="mt-1" rows={6} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} data-testid="ticket-new-description" />
            </label>
            <div><div className="text-sm font-medium text-slate-700 mb-1">Allegati <span className="font-normal text-slate-400">(immagini o PDF, max 5 · 10 MB)</span></div><FilePicker files={files} setFiles={setFiles} testid="ticket-new-files" /></div>
            <Button onClick={submit} disabled={busy} className="w-full h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="ticket-new-submit">{busy ? "Invio in corso..." : "Invia richiesta"}</Button>
          </div>
        </>)}
      </DialogContent>
    </Dialog>
  );
}

function ReopenRequest({ t, onDone }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  if (t.reopen_requested) return <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2" data-testid="ticket-reopen-pending">Hai chiesto la riapertura: il team CRMEvent la valuterà a breve.</p>;
  const send = async () => {
    const fd = new FormData();
    fd.append("text", text);
    setBusy(true);
    try { await api.post(`/tickets/${t.id}/reopen-request`, fd); toast.success("Richiesta di riapertura inviata"); onDone(); } catch (e) { err(e); }
    setBusy(false);
  };
  return (
    <div className="space-y-2" data-testid="ticket-reopen-box">
      <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Vuoi aggiungere informazioni? Spiega perché riaprire la richiesta" data-testid="ticket-reopen-text" />
      <Button variant="outline" disabled={busy} onClick={send} data-testid="ticket-reopen-request"><RotateCcw className="w-4 h-4 mr-1" />Chiedi la riapertura</Button>
    </div>
  );
}

function Detail({ id, onClose, onChanged }) {
  const [t, setT] = useState(null);
  const load = useCallback(() => api.get(`/tickets/${id}`).then(({ data }) => {
    setT(data);
    if (data.unread) {
      api.post(`/tickets/${id}/read`).then(() => { window.dispatchEvent(new Event("tickets:unread-changed")); onChanged(); }).catch(() => {});
    }
  }).catch(err), [id]); // eslint-disable-line react-hooks/exhaustive-deps
  usePoll(load, [load]);
  const refresh = () => { load(); onChanged(); };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto p-4 sm:p-6" data-testid="ticket-detail">
        {!t ? <p className="text-sm text-slate-400">Caricamento...</p> : (<>
          <div className="pr-6">
            <div className="text-xs text-slate-500">#{t.number} · {CATEGORIES[t.category]}</div>
            <DialogTitle className="mt-0.5 break-words" data-testid="ticket-detail-subject">{t.subject}</DialogTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2"><StatusBadge t={t} testid="ticket-detail-status" />
              {t.status === "chiusa" && <span className="text-xs text-slate-600" data-testid="ticket-detail-closed-at">Chiusa il {dt(t.closed_at)}</span>}</div>
          </div>
          <Conversation t={t} base="/tickets" viewer="org" />
          <div className="border-t border-slate-100 pt-3">
            {t.status === "chiusa" ? <ReopenRequest t={t} onDone={refresh} />
              : <Composer placeholder="Scrivi una risposta o aggiungi informazioni..." onSend={async (fd) => { await api.post(`/tickets/${t.id}/messages`, fd); refresh(); }} />}
          </div>
        </>)}
      </DialogContent>
    </Dialog>
  );
}

function Row({ t, onOpen }) {
  return (
    <button type="button" onClick={() => onOpen(t.id)} data-testid={`ticket-row-${t.number}`} data-unread={t.unread ? "true" : undefined}
      className={`w-full text-left grid grid-cols-1 md:grid-cols-[80px_140px_1fr_170px_170px_150px] gap-1 md:gap-3 items-center px-4 py-3 transition-colors ${t.unread ? "bg-[#0ABAB5]/10 hover:bg-[#0ABAB5]/15 border-l-4 border-[#0ABAB5]" : "hover:bg-slate-50"}`}>
      <span className="text-sm font-semibold text-slate-900 flex items-center gap-2">#{t.number}
        {t.unread && <span className="inline-flex items-center gap-1 h-5 px-2 rounded-full bg-red-500 text-white text-[10px] font-bold whitespace-nowrap" data-testid={`ticket-unread-${t.number}`}><span className="w-1.5 h-1.5 rounded-full bg-white" />Da leggere</span>}</span>
      <span className="text-xs text-slate-500 md:text-sm">{dt(t.created_at)}</span>
      <span className={`min-w-0 ${t.unread ? "font-semibold" : ""}`}><span className="block text-sm font-medium text-slate-800 truncate">{t.subject}</span><span className="block text-xs text-slate-500 truncate">{t.created_by?.name}</span></span>
      <span className="text-xs text-slate-600">{CATEGORIES[t.category]}</span>
      <StatusBadge t={t} testid={`ticket-status-${t.number}`} />
      <span className="text-xs text-slate-500">{t.status === "chiusa" ? `Chiusa ${dt(t.closed_at)}` : `Agg. ${dt(t.updated_at)}`}</span>
    </button>
  );
}

export default function Tickets() {
  const [rows, setRows] = useState(null);
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState(null);
  const load = useCallback(() => api.get("/tickets").then(({ data }) => setRows(data)).catch(err), []);
  usePoll(load, [load]);
  return (
    <div data-testid="tickets-page">
      <PageHeader title="Segnalazioni e richieste" subtitle="Segnala un problema o invia una richiesta al team CRMEvent e segui le risposte"
        action={<Button onClick={() => setCreating(true)} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="ticket-new-button"><Plus className="w-4 h-4 mr-1" />Nuova richiesta</Button>} />
      <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <div className="hidden md:grid grid-cols-[80px_140px_1fr_170px_170px_150px] gap-3 px-4 py-2.5 bg-slate-50 text-xs font-semibold text-slate-500">
          <span>Ticket</span><span>Apertura</span><span>Oggetto · Richiedente</span><span>Categoria</span><span>Stato</span><span>Ultimo aggiornamento</span>
        </div>
        {!rows ? <p className="p-6 text-sm text-slate-400">Caricamento...</p> : !rows.length ? (
          <div className="p-10 text-center" data-testid="tickets-empty">
            <MessageSquareWarning className="w-10 h-10 mx-auto text-[#0ABAB5]" />
            <p className="mt-2 text-sm text-slate-600">Nessuna richiesta inviata finora.</p>
          </div>
        ) : <div className="divide-y divide-slate-100" data-testid="tickets-list">{rows.map((t) => <Row key={t.id} t={t} onOpen={setOpen} />)}</div>}
      </div>
      {creating && <NewTicket onClose={() => setCreating(false)} onCreated={load} />}
      {open && <Detail id={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}
