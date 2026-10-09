import { useEffect, useRef, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StickyNote, Trash2 } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const fmt = (iso) => new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

function NoteItem({ n, onDelete }) {
  const [text, setText] = useState(n.text);
  const [state, setState] = useState("");
  const timer = useRef(null);
  const save = (v) => {
    clearTimeout(timer.current);
    if (!v.trim() || v === n.text) return;
    setState("…");
    timer.current = setTimeout(async () => {
      try { await api.put(`/my/notes/${n.id}`, { text: v }); n.text = v; setState("Salvato"); setTimeout(() => setState(""), 1500); }
      catch (e) { setState(""); toast.error(formatApiError(e.response?.data?.detail)); }
    }, 700);
  };
  return (
    <li className="group px-4 py-3 border-b border-slate-100 last:border-0" data-testid={`note-item-${n.id}`}>
      <div className="flex items-start gap-2">
        <textarea value={text} rows={Math.min(8, Math.max(1, text.split("\n").length))} onChange={(e) => { setText(e.target.value); save(e.target.value); }}
          className="flex-1 resize-none bg-transparent text-sm text-slate-800 outline-none focus:bg-[#0ABAB5]/5 rounded px-1 -mx-1" aria-label="Modifica nota" data-testid={`note-text-${n.id}`} />
        <button type="button" onClick={() => onDelete(n)} title="Elimina nota" aria-label="Elimina nota" data-testid={`note-delete-${n.id}`}
          className="w-7 h-7 shrink-0 rounded-md flex items-center justify-center text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors"><Trash2 className="w-4 h-4" /></button>
      </div>
      <div className="mt-1 text-[11px] text-slate-400">{fmt(n.created_at)}{state && <span className="ml-2 text-[#088F8A]">{state}</span>}</div>
    </li>
  );
}

export default function NotesPanel() {
  const [items, setItems] = useState(null);
  const [draft, setDraft] = useState("");
  const [del, setDel] = useState(null);
  const [err, setErr] = useState(false);
  const load = () => { setErr(false); setItems(null); api.get("/my/notes").then(({ data }) => setItems(data.items)).catch(() => { setErr(true); setItems([]); }); };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const add = async () => {
    if (!draft.trim()) return;
    try { const { data } = await api.post("/my/notes", { text: draft }); setItems((l) => [data, ...(l || [])]); setDraft(""); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const remove = async () => {
    const n = del; setDel(null);
    try { await api.delete(`/my/notes/${n.id}`); setItems((l) => l.filter((x) => x.id !== n.id)); toast.success("Nota eliminata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <section className="flex flex-col min-h-0 h-[420px] lg:h-[calc(100dvh-14rem)] lg:min-h-[420px] rounded-xl border border-slate-200 bg-white" data-testid="notes-panel">
      <header className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
        <StickyNote className="w-4 h-4 text-[#0ABAB5]" /><h2 className="font-semibold text-slate-900">Note e appunti</h2>
      </header>
      <div className="px-4 py-3 border-b border-slate-100">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder="Appunta qui..." enterKeyHint="done" data-testid="note-input"
          className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-[#0ABAB5] focus:ring-2 focus:ring-[#0ABAB5]/20 transition-[border-color,box-shadow]" />
      </div>
      <ul className="flex-1 overflow-y-auto" data-testid="notes-list">
        {items === null ? <li className="p-4 text-sm text-slate-400" data-testid="notes-loading">Caricamento...</li>
          : err ? <li className="p-4 text-sm text-red-600" data-testid="notes-error">Impossibile caricare le note. <button type="button" onClick={load} className="underline font-semibold" data-testid="notes-retry">Riprova</button></li>
          : !items.length ? <li className="p-4 text-sm text-slate-500" data-testid="notes-empty">Nessuna nota. Scrivi sopra e premi Invio.</li>
          : items.map((n) => <NoteItem key={n.id} n={n} onDelete={setDel} />)}
      </ul>
      <AlertDialog open={!!del} onOpenChange={(o) => !o && setDel(null)}>
        <AlertDialogContent data-testid="note-delete-dialog">
          <AlertDialogHeader><AlertDialogTitle>Eliminare la nota?</AlertDialogTitle><AlertDialogDescription>La nota verrà eliminata definitivamente.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="note-delete-cancel">Annulla</AlertDialogCancel>
            <AlertDialogAction onClick={remove} className="bg-red-600 hover:bg-red-700" data-testid="note-delete-confirm">Elimina</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
