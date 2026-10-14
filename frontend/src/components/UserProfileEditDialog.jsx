import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { Pencil } from "lucide-react";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";

export function UserProfileEditDialog({ member, onClose, onSaved }) {
  const [ef, setEf] = useState({ nome: "", cognome: "", email: "", telefono: "" });
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    if (member) setEf({ nome: member.nome || "", cognome: member.cognome || "", email: member.email || "", telefono: member.telefono || "" });
  }, [member]);
  const emailChanged = !!member && ef.email.trim().toLowerCase() !== (member.email || "").toLowerCase();
  const save = async () => {
    setBusy(true);
    try {
      const { data } = await api.patch(`/platform/users/${member.user_id}/profile`, { nome: ef.nome.trim(), cognome: ef.cognome.trim(), email: ef.email.trim(), telefono: ef.telefono, confirm_email_change: emailChanged });
      toast.success(data.changes?.length ? `Anagrafica aggiornata${data.brevo === "errore" ? " (Brevo non aggiornato)" : ""}` : "Nessuna modifica");
      setConfirm(false); onSaved();
    } catch (e) { setConfirm(false); toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const submit = () => {
    if (!ef.nome.trim()) return toast.error("Il nome è obbligatorio");
    if (!ef.email.trim()) return toast.error("Email obbligatoria");
    if (!ef.telefono || !isValidPhoneNumber(ef.telefono)) return toast.error("Inserisci un cellulare valido");
    if (emailChanged) return setConfirm(true);
    save();
  };
  const set = (k) => (e) => setEf((s) => ({ ...s, [k]: e.target.value }));
  return (
    <>
      <Dialog open={!!member} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-md w-[calc(100vw-1.5rem)]" data-testid="user-edit-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Pencil className="w-5 h-5 text-tiffany-active" />Modifica anagrafica</DialogTitle>
            <DialogDescription>Ruoli, permessi, organizzazioni, accesso Google e storico non vengono modificati; le password non sono visibili. Ogni modifica è registrata nell'Audit Log.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Nome *</Label><Input value={ef.nome} onChange={set("nome")} data-testid="edit-nome" /></div>
              <div className="space-y-1.5"><Label>Cognome</Label><Input value={ef.cognome} onChange={set("cognome")} data-testid="edit-cognome" /></div>
            </div>
            <div className="space-y-1.5"><Label>Email *</Label><Input type="email" value={ef.email} onChange={set("email")} data-testid="edit-email" /></div>
            <div className="space-y-1.5"><Label>Cellulare *</Label><PhoneInput international defaultCountry="IT" value={ef.telefono} onChange={(v) => setEf((s) => ({ ...s, telefono: v || "" }))} className="phone-input" data-testid="edit-telefono-input" /></div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={onClose} data-testid="edit-cancel">Annulla</Button>
            <Button disabled={busy} onClick={submit} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="edit-submit">Salva modifiche</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent data-testid="edit-email-confirm-dialog">
          <AlertDialogHeader><AlertDialogTitle>Confermi la modifica dell'email?</AlertDialogTitle>
            <AlertDialogDescription>Da «{member?.email}» a «{ef.email.trim()}». Il nuovo indirizzo sarà usato subito per l'accesso con password; il contatto Brevo viene aggiornato mantenendo liste e attributi.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel data-testid="edit-email-confirm-cancel">Annulla</AlertDialogCancel><AlertDialogAction disabled={busy} onClick={(e) => { e.preventDefault(); save(); }} data-testid="edit-email-confirm-ok">Conferma modifica</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
