import { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Paperclip, FileText, X, Send, Lock, RotateCcw, ArrowRightLeft, Loader2 } from "lucide-react";

export const STATUS_META = {
  aperta: { label: "Aperta", cls: "bg-sky-100 text-sky-800 border-sky-200" },
  in_lavorazione: { label: "In lavorazione", cls: "bg-amber-100 text-amber-800 border-amber-200" },
  in_attesa: { label: "In attesa di risposta", cls: "bg-violet-100 text-violet-800 border-violet-200" },
  chiusa: { label: "Chiusa", cls: "bg-slate-200 text-slate-700 border-slate-300" },
};
export const CATEGORIES = {
  problema_tecnico: "Problema tecnico", nuova_funzionalita: "Richiesta nuova funzionalità", miglioramento: "Miglioramento piattaforma",
  domanda_utilizzo: "Domanda sull'utilizzo", abbonamento: "Abbonamento e fatturazione", altro: "Altro",
};
export const POLL_MS = 30000;
export const ACCEPT = ".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf";
export const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
export const err = (e) => toast.error(formatApiError(e.response?.data?.detail) || "Operazione non riuscita");

export function StatusBadge({ t, testid }) {
  const m = STATUS_META[t.status] || STATUS_META.aperta;
  return (
    <span className="inline-flex flex-wrap items-center gap-1" data-testid={testid}>
      <span className={`inline-flex items-center h-6 px-2.5 rounded-full border text-xs font-semibold whitespace-nowrap ${m.cls}`}>{m.label}</span>
      {t.reopen_requested && <span className="inline-flex items-center h-6 px-2 rounded-full border border-rose-200 bg-rose-50 text-rose-700 text-[11px] font-semibold whitespace-nowrap">Riapertura richiesta</span>}
    </span>
  );
}

function Attachment({ a, base }) {
  const [url, setUrl] = useState(null);
  const isImg = a.content_type?.startsWith("image/");
  useEffect(() => {
    let u;
    if (isImg) api.get(`${base}/files/${a.id}`, { responseType: "blob" }).then(({ data }) => { u = URL.createObjectURL(data); setUrl(u); }).catch(() => {});
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [a.id, base, isImg]);
  const open = async () => {
    try {
      const { data } = await api.get(`${base}/files/${a.id}`, { responseType: "blob" });
      const u = URL.createObjectURL(data);
      window.open(u, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(u), 60000);
    } catch (e) { err(e); }
  };
  return (
    <button type="button" onClick={open} data-testid={`ticket-attachment-${a.id}`} title={a.filename}
      className="group inline-flex items-center gap-2 max-w-full rounded-lg border border-slate-200 bg-white p-1.5 pr-3 text-xs text-slate-700 hover:border-[#0ABAB5] transition-colors">
      {isImg && url ? <img src={url} alt={a.filename} className="w-12 h-12 rounded object-cover" /> : <span className="w-9 h-9 rounded bg-slate-100 flex items-center justify-center shrink-0"><FileText className="w-4 h-4 text-slate-500" /></span>}
      <span className="truncate max-w-[160px]">{a.filename}</span>
    </button>
  );
}

export function Attachments({ list, base }) {
  if (!list?.length) return null;
  return <div className="flex flex-wrap gap-2 mt-2">{list.map((a) => <Attachment key={a.id} a={a} base={base} />)}</div>;
}

function SystemLine({ m }) {
  const to = STATUS_META[m.meta?.to]?.label;
  const text = m.kind === "reopen_request" ? `${m.author?.name} ha chiesto la riapertura` : m.meta?.from ? `Stato: ${STATUS_META[m.meta.from]?.label} → ${to}` : `Richiesta aperta da ${m.author?.name}`;
  return (
    <div className="flex flex-col items-center gap-1 py-1" data-testid={`ticket-event-${m.id}`}>
      <div className="inline-flex items-center gap-1.5 text-[11px] text-slate-500 bg-slate-100 rounded-full px-3 py-1">
        {m.kind === "reopen_request" ? <RotateCcw className="w-3 h-3" /> : <ArrowRightLeft className="w-3 h-3" />}{text} · {dt(m.created_at)}
      </div>
      {m.text && <div className="text-xs text-slate-600 italic max-w-md text-center">“{m.text}”</div>}
    </div>
  );
}

export function Conversation({ t, base, viewer }) {
  const end = useRef(null);
  const msgs = t.messages || [];
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [msgs.length]);
  return (
    <div className="space-y-3" data-testid="ticket-conversation">
      <div className="rounded-xl border border-slate-200 bg-white p-3 sm:p-4">
        <div className="text-xs text-slate-500">{t.created_by?.name} · {dt(t.created_at)}</div>
        <p className="mt-1.5 text-sm text-slate-800 whitespace-pre-wrap break-words" data-testid="ticket-description">{t.description}</p>
        <Attachments list={t.attachments} base={base} />
      </div>
      {msgs.map((m) => {
        if (m.kind !== "message") return <SystemLine key={m.id} m={m} />;
        const mine = m.side === viewer;
        return (
          <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`} data-testid={`ticket-message-${m.id}`}>
            <div className={`max-w-[88%] sm:max-w-[75%] rounded-2xl px-3.5 py-2.5 ${m.internal ? "bg-amber-50 border border-amber-200" : mine ? "bg-[#0ABAB5]/10 border border-[#0ABAB5]/30" : "bg-white border border-slate-200"}`}>
              <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                {m.internal && <Lock className="w-3 h-3 text-amber-600" />}
                <span className="font-semibold text-slate-700">{m.author?.name}</span>{m.side === "admin" && <span>· CRMEvent</span>}<span>· {dt(m.created_at)}</span>
                {m.internal && <span className="text-amber-700 font-semibold">· Nota interna</span>}
              </div>
              {m.text && <p className="mt-1 text-sm text-slate-800 whitespace-pre-wrap break-words">{m.text}</p>}
              <Attachments list={m.attachments} base={base} />
            </div>
          </div>
        );
      })}
      <div ref={end} />
    </div>
  );
}

export function FilePicker({ files, setFiles, max = 5, testid = "ticket-files" }) {
  const ref = useRef(null);
  const add = (e) => {
    const picked = Array.from(e.target.files || []);
    e.target.value = "";
    const bad = picked.find((f) => !/\.(jpe?g|png|webp|pdf)$/i.test(f.name) || f.size > 10 * 1024 * 1024);
    if (bad) return toast.error(`«${bad.name}»: solo JPG, PNG, WEBP o PDF fino a 10 MB`);
    const next = [...files, ...picked];
    if (next.length > max) return toast.error(`Massimo ${max} allegati`);
    setFiles(next);
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input ref={ref} type="file" multiple accept={ACCEPT} onChange={add} className="hidden" data-testid={`${testid}-input`} />
      <Button type="button" variant="outline" size="sm" onClick={() => ref.current?.click()} data-testid={`${testid}-button`}><Paperclip className="w-4 h-4 mr-1" />Allega</Button>
      {files.map((f, i) => (
        <span key={`${f.name}-${i}`} className="inline-flex items-center gap-1 h-8 pl-2.5 pr-1 rounded-full bg-slate-100 text-xs text-slate-700 max-w-[200px]">
          <span className="truncate">{f.name}</span>
          <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))} className="w-6 h-6 rounded-full hover:bg-slate-200 flex items-center justify-center" aria-label="Rimuovi"><X className="w-3 h-3" /></button>
        </span>
      ))}
    </div>
  );
}

export function Composer({ onSend, placeholder, extra, testid = "ticket-reply" }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!text.trim() && !files.length) return;
    const fd = new FormData();
    fd.append("text", text);
    files.forEach((f) => fd.append("files", f));
    setBusy(true);
    try { await onSend(fd); setText(""); setFiles([]); } catch (e) { err(e); }
    setBusy(false);
  };
  return (
    <div className="space-y-2" data-testid={testid}>
      <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} rows={3} className="resize-y" data-testid={`${testid}-text`} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FilePicker files={files} setFiles={setFiles} testid={`${testid}-files`} />
        <div className="flex items-center gap-2 ml-auto">
          {extra}
          <Button onClick={send} disabled={busy || (!text.trim() && !files.length)} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid={`${testid}-send`}>
            {busy ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Send className="w-4 h-4 mr-1" />}Invia
          </Button>
        </div>
      </div>
    </div>
  );
}

export function usePoll(fn, deps) {
  useEffect(() => {
    fn();
    const t = setInterval(() => { if (document.visibilityState === "visible") fn(); }, POLL_MS);
    return () => clearInterval(t);
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}
