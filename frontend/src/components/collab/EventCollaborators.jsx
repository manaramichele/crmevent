import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/crm";
import { toast } from "sonner";
import { UserPlus, Pencil, Send, Ban } from "lucide-react";
import { CollabPermEditor, fromPerm, levelOf, permBody } from "@/components/collab/CollabPermEditor";

const INV = { accepted: ["Accettato", "green"], pending: ["Inviato", "blue"], expired: ["Scaduto", "amber"], revoked: ["Revocato", "red"] };
const ACC = { active: "green", disabled: "amber", revoked: "red", pending: "blue", expired: "amber" };
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

function PermSummary({ row, sections }) {
  const vis = sections.filter((s) => levelOf(row.sections?.[s.key]) !== "none");
  const ed = vis.filter((s) => levelOf(row.sections?.[s.key]) === "edit");
  const fl = Object.values(row.flags || {}).filter(Boolean).length;
  return <span className="text-xs text-slate-500">{vis.length} sezioni ({ed.length} con modifica){fl ? ` · ${fl} permessi delicati` : ""}</span>;
}

function EditDialog({ eventId, meta, row, onClose, onSaved }) {
  const isNew = !row;
  const [f, setF] = useState({ nome: "", cognome: "", email: "" });
  const [perm, setPerm] = useState(fromPerm(row || meta.defaults, meta.flags));
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      if (isNew) {
        const { data } = await api.post(`/events/${eventId}/collaborators`, { ...f, ...permBody(perm) });
        toast.success(data.mode === "added" ? "Evento aggiunto al collaboratore esistente" : data.email_sent ? "Invito inviato" : "Invito creato (email non inviata)");
      } else {
        const id = row.kind === "invite" ? row.invite_id : row.user_id;
        await api.put(`/events/${eventId}/collaborators/${id}${row.kind === "invite" ? "?kind=invite" : ""}`, permBody(perm));
        toast.success("Permessi aggiornati");
      }
      onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="collab-edit-dialog">
        <DialogHeader><DialogTitle>{isNew ? "Invita collaboratore" : `Permessi di ${row.name || row.email}`}</DialogTitle>
          <DialogDescription>Il collaboratore accede solo agli eventi autorizzati e alle sezioni scelte. I permessi valgono per tutti i suoi eventi in questa organizzazione.</DialogDescription></DialogHeader>
        {isNew && <div className="grid sm:grid-cols-3 gap-2">
          {[["nome", "Nome"], ["cognome", "Cognome"], ["email", "Email"]].map(([k, l]) => (
            <Input key={k} placeholder={l} type={k === "email" ? "email" : "text"} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`collab-invite-${k}`} />
          ))}
        </div>}
        <CollabPermEditor sections={meta.sections} flags={meta.flags} value={perm} onChange={setPerm} cap={meta.cap} />
        <DialogFooter><Button disabled={busy || (isNew && !(f.nome && f.cognome && f.email))} onClick={save} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="collab-save">{isNew ? "Invia invito" : "Salva"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Row({ r, meta, onEdit, onResend, onRevoke }) {
  const [il, ic] = INV[r.invite_status] || [r.invite_status, "gray"];
  return (
    <div className="flex flex-col lg:flex-row lg:items-center gap-2 border border-slate-200 rounded-lg px-3 py-2.5" data-testid={`collab-row-${r.user_id || r.invite_id}`}>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-slate-800 truncate">{r.name || "—"}</div>
        <div className="text-xs text-slate-500 break-all">{r.email}</div>
        <PermSummary row={r} sections={meta.sections} />
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <StatusBadge color={ic}>Invito: {il}</StatusBadge>
        <StatusBadge color={ACC[r.access_status] || "gray"}>Accesso: {r.access_label}</StatusBadge>
        <span className="text-slate-400">Ultimo accesso: {fmt(r.last_login_at)}</span>
      </div>
      <div className="flex gap-1">
        {r.access_status !== "revoked" && <Button size="sm" variant="outline" onClick={() => onEdit(r)} data-testid={`collab-edit-${r.user_id || r.invite_id}`}><Pencil className="w-3.5 h-3.5 mr-1" />Permessi</Button>}
        {r.kind === "invite" && r.invite_status !== "accepted" && <Button size="sm" variant="outline" onClick={() => onResend(r)} data-testid={`collab-resend-${r.invite_id}`}><Send className="w-3.5 h-3.5 mr-1" />Reinvia</Button>}
        {!["revoked"].includes(r.access_status) && r.invite_status !== "revoked" && <Button size="sm" variant="outline" className="text-red-600" onClick={() => onRevoke(r)} data-testid={`collab-revoke-${r.user_id || r.invite_id}`}><Ban className="w-3.5 h-3.5 mr-1" />Revoca</Button>}
      </div>
    </div>
  );
}

export default function EventCollaborators({ event, onClose }) {
  const [meta, setMeta] = useState(null);
  const [edit, setEdit] = useState(undefined);
  const [revoke, setRevoke] = useState(null);
  const load = useCallback(() => api.get(`/events/${event.id}/collaborators`).then(({ data }) => setMeta(data))
    .catch((e) => { toast.error(formatApiError(e.response?.data?.detail)); onClose(); }), [event.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  const resend = async (r) => {
    try { const { data } = await api.post(`/events/${event.id}/collaborators/${r.invite_id}/resend`); toast.success(data.email_sent ? "Invito reinviato" : "Invito rinnovato (email non inviata)"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const doRevoke = async () => {
    const r = revoke; setRevoke(null);
    try { await api.post(`/events/${event.id}/collaborators/${r.kind === "invite" ? r.invite_id : r.user_id}/revoke${r.kind === "invite" ? "?kind=invite" : ""}`); toast.success("Accesso revocato"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="event-collaborators-dialog">
        <DialogHeader><DialogTitle>Collaboratori · {event.nome}</DialogTitle>
          <DialogDescription>Persone invitate a lavorare solo su questo evento, con le sezioni del back-end che scegli tu.</DialogDescription></DialogHeader>
        <div className="flex justify-end"><Button onClick={() => setEdit(null)} disabled={!meta} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="collab-invite-btn"><UserPlus className="w-4 h-4 mr-1.5" />Invita collaboratore</Button></div>
        <div className="space-y-2" data-testid="collab-list">
          {!meta && <div className="text-sm text-slate-400">Caricamento...</div>}
          {meta?.rows.length === 0 && <div className="text-sm text-slate-400 py-6 text-center">Nessun collaboratore per questo evento.</div>}
          {meta?.rows.map((r) => <Row key={r.user_id || r.invite_id} r={r} meta={meta} onEdit={setEdit} onResend={resend} onRevoke={setRevoke} />)}
        </div>
        {edit !== undefined && meta && <EditDialog eventId={event.id} meta={meta} row={edit} onClose={() => setEdit(undefined)} onSaved={() => { setEdit(undefined); load(); }} />}
        {revoke && <Dialog open onOpenChange={(o) => !o && setRevoke(null)}>
          <DialogContent className="max-w-md" data-testid="collab-revoke-dialog">
            <DialogHeader><DialogTitle>Revocare l'accesso?</DialogTitle>
              <DialogDescription>{revoke.name || revoke.email} non potrà più accedere a «{event.nome}». Gli altri eventi e l'account restano invariati. Per ridare l'accesso andranno scelti di nuovo i permessi.</DialogDescription></DialogHeader>
            <DialogFooter><Button variant="outline" onClick={() => setRevoke(null)}>Annulla</Button><Button className="bg-red-500 hover:bg-red-600" onClick={doRevoke} data-testid="collab-revoke-confirm">Revoca accesso</Button></DialogFooter>
          </DialogContent>
        </Dialog>}
      </DialogContent>
    </Dialog>
  );
}
