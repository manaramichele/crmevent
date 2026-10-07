import { useState } from "react";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StickyNote } from "lucide-react";

export const hasNote = (team) => !!(team?.descrizione || "").trim();

// Nota operativa del Team = campo "descrizione" esistente (nessun campo nuovo).
export function TeamNoteDialog({ team, open, onOpenChange, canEdit, onSave }) {
  const [editing, setEditing] = useState(!hasNote(team) && canEdit);
  const [text, setText] = useState(team?.descrizione || "");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await onSave(text.trim()); toast.success("Nota salvata"); onOpenChange(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-md" data-testid="team-note-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><StickyNote className="w-5 h-5 text-tiffany-active" />Nota · {team?.nome}</DialogTitle>
          <DialogDescription>Nota operativa del Team (campo Descrizione).</DialogDescription>
        </DialogHeader>
        {editing ? (
          <Textarea autoFocus rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="Scrivi una nota operativa per il Team..." data-testid="team-note-textarea" />
        ) : hasNote(team) ? (
          <p className="text-sm text-slate-800 whitespace-pre-wrap break-words max-h-[50dvh] overflow-y-auto" data-testid="team-note-text">{team.descrizione}</p>
        ) : (
          <p className="text-sm text-slate-400" data-testid="team-note-empty">Nessuna nota per questo Team.</p>
        )}
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="team-note-close">{editing ? "Annulla" : "Chiudi"}</Button>
          {canEdit && !editing && <Button variant="outline" onClick={() => setEditing(true)} data-testid="team-note-edit">{hasNote(team) ? "Modifica nota" : "Aggiungi nota"}</Button>}
          {editing && <Button onClick={save} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="team-note-save">{busy ? "Salvataggio..." : "Salva nota"}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TeamNoteButton({ team, canEdit, onSave, className = "" }) {
  const [open, setOpen] = useState(false);
  const on = hasNote(team);
  return (
    <>
      <Button type="button" variant="outline" size="sm" onClick={(e) => { e.stopPropagation(); setOpen(true); }}
        title={on ? "Nota presente" : canEdit ? "Aggiungi nota" : "Nessuna nota"} aria-label={on ? "Nota presente" : "Nessuna nota"}
        data-testid={`team-note-btn-${team.id}`} data-has-note={on ? "true" : "false"}
        className={`h-8 px-2.5 text-xs gap-1 ${on ? "bg-tiffany border-tiffany text-slate-900 hover:bg-tiffany-hover hover:text-slate-900" : "bg-white border-slate-200 text-slate-500"} ${className}`}>
        <StickyNote />Nota
      </Button>
      {open && <TeamNoteDialog team={team} open={open} onOpenChange={setOpen} canEdit={canEdit} onSave={onSave} />}
    </>
  );
}
