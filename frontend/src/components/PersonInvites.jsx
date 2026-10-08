import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { StatusBadge } from "@/components/crm";
import { toast } from "sonner";
import { Send, AlertTriangle, X } from "lucide-react";

export const INV = { non_invitato: "gray", invito_inviato: "orange", account_attivato: "green", accesso_disabilitato: "red" };
export const INV_LABEL = { non_invitato: "Non invitato", invito_inviato: "Invito inviato", account_attivato: "Registrato", accesso_disabilitato: "Disabilitato" };
const DUP_MS = 24 * 3600 * 1000;
export const fmtInvite = (iso) => { try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return iso; } };
export const isRecentInvite = (p) => !!p?.last_invite_at && Date.now() - new Date(p.last_invite_at).getTime() < DUP_MS;

export function LastInvite({ person, className = "" }) {
  if (!person?.last_invite_at) return null;
  return <div className={`text-xs text-slate-500 ${className}`} data-testid={`last-invite-${person.id}`}>Ultimo invito: {fmtInvite(person.last_invite_at)}</div>;
}

export function PersonInviteDialog({ person, open, onOpenChange, onDone }) {
  const [role, setRole] = useState(person?.user_role || (person?.is_volontario && !person?.is_staff ? "volunteer" : "staff"));
  const [confirm, setConfirm] = useState(false);
  const [recent, setRecent] = useState(isRecentInvite(person) ? person.last_invite_at : null);
  const [busy, setBusy] = useState(false);
  const status = person?.invite_status || "non_invitato";
  const resend = !!person?.last_invite_at || status === "invito_inviato";
  const send = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/persons/${person.id}/invite`, { role, force: !!recent });
      toast[data.email_sent ? "success" : "warning"](data.email_sent ? "Invito inviato via email" : "Invito creato (email non inviata)");
      onDone(); onOpenChange(false);
    } catch (e) {
      const d = e.response?.data?.detail;
      if (d?.code === "recent_invite") { setRecent(d.last_invite_at); toast.warning(d.message); }
      else toast.error(formatApiError(d));
    } finally { setBusy(false); }
  };
  const toggle = async (enabled) => {
    try { await api.put(`/persons/${person.id}/access`, { enabled }); toast.success(enabled ? "Accesso riattivato" : "Accesso disabilitato"); onDone(); onOpenChange(false); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="invite-dialog" className="max-w-md">
        <DialogHeader><DialogTitle className="font-display">Invita su <strong className="font-semibold">CRMEvent</strong></DialogTitle>
          <DialogDescription>{person?.cognome} {person?.nome} — {person?.email || "nessuna email"}</DialogDescription></DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-2"><span className="text-sm text-slate-500">Stato attuale:</span><StatusBadge color={INV[status]}>{INV_LABEL[status]}</StatusBadge></div>
          {person?.last_invite_at && <div className="text-sm text-slate-600" data-testid="invite-last-date">Ultimo invito: <b className="font-semibold">{fmtInvite(person.last_invite_at)}</b>{person.last_invite_by ? ` · da ${person.last_invite_by}` : ""}{person.invite_count > 1 ? ` · ${person.invite_count} invii` : ""}</div>}
          {!confirm ? (
            <div className="space-y-1.5"><Label className="text-xs">Ruolo accesso</Label>
              <Select value={role} onValueChange={setRole}><SelectTrigger data-testid="invite-role"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="volunteer">Volontario</SelectItem><SelectItem value="staff">Staff</SelectItem></SelectContent></Select>
            </div>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 space-y-2" data-testid="invite-confirm-box">
              <p>Confermi l'invio dell'invito a <b className="font-semibold break-all">{person?.email}</b> come {role === "staff" ? "Staff" : "Volontario"}?</p>
              {recent && <p className="flex gap-2 text-amber-700" data-testid="invite-recent-warning"><AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />Un invito è già stato inviato il {fmtInvite(recent)}. Confermando ne verrà inviato un altro e il link precedente non sarà più valido.</p>}
            </div>
          )}
        </div>
        <DialogFooter className="flex-col sm:flex-row gap-2">
          {!confirm && status === "account_attivato" && <Button variant="outline" onClick={() => toggle(false)} data-testid="disable-access">Disabilita accesso</Button>}
          {!confirm && status === "accesso_disabilitato" && <Button variant="outline" onClick={() => toggle(true)} data-testid="enable-access">Riattiva accesso</Button>}
          {confirm && <Button variant="outline" onClick={() => setConfirm(false)} data-testid="invite-confirm-back">Indietro</Button>}
          {!confirm
            ? <Button onClick={() => setConfirm(true)} disabled={!person?.email} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="send-invite">{resend ? "Reinvia invito" : "Invia invito"}</Button>
            : <Button onClick={send} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="invite-confirm-send">{busy ? "Invio..." : "Conferma invio"}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function BulkInviteBar({ selected, onClear, onDone }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  if (!selected.length && !result) return null;
  const noEmail = selected.filter((p) => !p.email).length;
  const recent = selected.filter((p) => p.email && isRecentInvite(p)).length;
  const send = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/person-invites/bulk", { person_ids: selected.map((p) => p.id) });
      setOpen(false); setResult(data); onClear(); onDone();
      toast[data.sent.length ? "success" : "warning"](`${data.sent.length} inviti inviati${data.skipped.length ? ` · ${data.skipped.length} saltati` : ""}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <>
      {selected.length > 0 && (
        <div className="sticky bottom-3 z-20 mt-3 flex items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white/95 backdrop-blur px-3 py-2 shadow-lg" data-testid="bulk-invite-bar">
          <span className="text-sm text-slate-700"><b className="font-semibold" data-testid="bulk-invite-count">{selected.length}</b> selezionati</span>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClear} data-testid="bulk-invite-clear"><X className="w-4 h-4 sm:mr-1" /><span className="hidden sm:inline">Annulla</span></Button>
            <Button size="sm" onClick={() => setOpen(true)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="bulk-invite-open"><Send className="w-4 h-4 mr-1" />Invia inviti</Button>
          </div>
        </div>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid="bulk-invite-confirm">
          <DialogHeader><DialogTitle>Inviare {selected.length} inviti?</DialogTitle>
            <DialogDescription>Verrà inviata l'email di accesso all'area personale CRMEvent con il ruolo già associato a ciascuna persona.</DialogDescription></DialogHeader>
          <ul className="text-sm text-slate-600 space-y-1">
            {recent > 0 && <li className="text-amber-700" data-testid="bulk-recent-note">{recent} già invitati nelle ultime 24 ore: verranno saltati</li>}
            {noEmail > 0 && <li className="text-amber-700" data-testid="bulk-noemail-note">{noEmail} senza email: verranno saltati</li>}
          </ul>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
            <Button onClick={send} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="bulk-invite-confirm-send">{busy ? "Invio..." : "Conferma invio"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={!!result} onOpenChange={(o) => !o && setResult(null)}>
        <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto" data-testid="bulk-invite-result">
          <DialogHeader><DialogTitle>Esito invio inviti</DialogTitle>
            <DialogDescription>{result?.sent.length || 0} inviati · {result?.skipped.length || 0} saltati</DialogDescription></DialogHeader>
          {result?.skipped.length > 0 && (
            <div className="space-y-1.5">{result.skipped.map((s) => (
              <div key={s.id} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm" data-testid={`bulk-skipped-${s.id}`}><b className="font-semibold">{s.name}</b><div className="text-xs text-amber-800">{s.reason}</div></div>
            ))}</div>
          )}
          <DialogFooter><Button onClick={() => setResult(null)} data-testid="bulk-invite-result-close">Chiudi</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
