import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/crm";
import { toast } from "sonner";
import { Link2, Pencil, Send, Ban } from "lucide-react";

const fmt = (iso) => (iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

function Form({ event, info, row, onClose, onSaved }) {
  const [f, setF] = useState({ nome: "", cognome: "", email: "", incarico: row?.incarico || "", note: row?.note || "", info: row?.info || ["orari", "luogo"] });
  const [busy, setBusy] = useState(false);
  const tog = (k) => setF({ ...f, info: f.info.includes(k) ? f.info.filter((x) => x !== k) : [...f.info, k] });
  const save = async () => {
    setBusy(true);
    try {
      if (row) { await api.put(`/event-users/assignments/${row.id}`, { incarico: f.incarico, note: f.note, info: f.info }); toast.success("Aggiornato"); }
      else { const { data } = await api.post("/event-users", { ...f, event_id: event.id }); toast.success(data.email_sent ? "Link inviato" : "Utente assegnato (email non inviata)"); }
      onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="event-user-form">
        <DialogHeader><DialogTitle>{row ? `Modifica ${row.name}` : "Assegna Utente all'evento"}</DialogTitle>
          <DialogDescription>L'Utente riceve un link personale: vede solo questo evento, il suo incarico e le informazioni che scegli. Nessun accesso al back-end.</DialogDescription></DialogHeader>
        {!row && <div className="grid sm:grid-cols-3 gap-2">{[["nome", "Nome"], ["cognome", "Cognome"], ["email", "Email"]].map(([k, l]) => (
          <Input key={k} placeholder={l} type={k === "email" ? "email" : "text"} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`event-user-${k}`} />))}</div>}
        <Input placeholder="Ruolo o incarico nell'evento" value={f.incarico} onChange={(e) => setF({ ...f, incarico: e.target.value })} data-testid="event-user-incarico" />
        <Textarea placeholder="Nota per l'Utente (facoltativa)" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} data-testid="event-user-note" />
        <div><div className="text-xs font-semibold uppercase text-slate-500 mb-1.5">Informazioni visibili</div>
          <div className="grid grid-cols-2 gap-2">{Object.entries(info).map(([k, l]) => (
            <label key={k} className="flex items-center gap-2 text-sm rounded-lg border border-slate-200 px-3 py-2"><input type="checkbox" className="accent-tiffany w-4 h-4" checked={f.info.includes(k)} onChange={() => tog(k)} data-testid={`event-user-info-${k}`} />{l}</label>))}</div></div>
        <DialogFooter><Button disabled={busy || (!row && !(f.nome && f.cognome && f.email))} onClick={save} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-user-save">{row ? "Salva" : "Assegna e invia link"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Row({ r, onEdit, onResend, onRevoke }) {
  const on = r.status === "active";
  return (
    <div className="flex flex-col lg:flex-row lg:items-center gap-2 border border-slate-200 rounded-lg px-3 py-2.5" data-testid={`event-user-row-${r.id}`}>
      <div className="flex-1 min-w-0"><div className="font-medium text-slate-800">{r.name}</div><div className="text-xs text-slate-500 break-all">{r.email} · incarico: {r.incarico || "—"}</div></div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <StatusBadge color={!r.account_active ? "amber" : on ? "green" : "red"}>{!r.account_active ? "Account disattivato" : on ? "Attivo" : "Revocato"}</StatusBadge>
        <span className="text-slate-400">Link: {fmt(r.link_sent_at)} · Ultimo accesso: {fmt(r.last_login_at)}</span></div>
      {on && <div className="flex gap-1">
        <Button size="sm" variant="outline" onClick={() => onEdit(r)} data-testid={`event-user-edit-${r.id}`}><Pencil className="w-3.5 h-3.5 mr-1" />Modifica</Button>
        <Button size="sm" variant="outline" onClick={() => onResend(r)} data-testid={`event-user-resend-${r.id}`}><Send className="w-3.5 h-3.5 mr-1" />Reinvia link</Button>
        <Button size="sm" variant="outline" className="text-red-600" onClick={() => onRevoke(r)} data-testid={`event-user-revoke-${r.id}`}><Ban className="w-3.5 h-3.5 mr-1" />Revoca</Button></div>}
    </div>
  );
}

export default function EventUsers({ event, onClose }) {
  const [data, setData] = useState(null);
  const [form, setForm] = useState(undefined);
  const load = useCallback(() => api.get("/event-users", { params: { event_id: event.id } }).then(({ data: x }) => setData(x))
    .catch((e) => { toast.error(formatApiError(e.response?.data?.detail)); onClose(); }), [event.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  const act = async (url, ok, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    try { const { data: x } = await api.post(url); toast.success(x.email_sent === false ? "Operazione eseguita (email non inviata)" : ok); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="event-users-dialog">
        <DialogHeader><DialogTitle>Utenti con link · {event.nome}</DialogTitle>
          <DialogDescription>Persone che vedono solo l'evento e il proprio incarico tramite link personale con codice di verifica. Per lavorare nel back-end usa invece «Collaboratori».</DialogDescription></DialogHeader>
        <div className="flex justify-end"><Button onClick={() => setForm(null)} disabled={!data} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-user-add"><Link2 className="w-4 h-4 mr-1.5" />Assegna Utente</Button></div>
        <div className="space-y-2" data-testid="event-users-list">
          {data?.rows.length === 0 && <div className="text-sm text-slate-400 py-6 text-center">Nessun Utente assegnato a questo evento.</div>}
          {data?.rows.map((r) => <Row key={r.id} r={r} onEdit={setForm}
            onResend={(x) => act(`/event-users/assignments/${x.id}/send-link`, "Link reinviato")}
            onRevoke={(x) => act(`/event-users/assignments/${x.id}/revoke`, "Accesso revocato", `Revocare l'accesso di ${x.name} a «${event.nome}»?`)} />)}
        </div>
        {form !== undefined && data && <Form event={event} info={data.info} row={form} onClose={() => setForm(undefined)} onSaved={() => { setForm(undefined); load(); }} />}
      </DialogContent>
    </Dialog>
  );
}
