import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/crm";
import { toast } from "sonner";
import { CollabPermEditor, fromPerm, permBody } from "@/components/collab/CollabPermEditor";

const ST = { active: ["Attivo", "green"], disabled: ["Disattivato", "amber"], revoked: ["Revocato", "red"] };
const INV = { pending: "Invito in attesa", expired: "Invito scaduto", revoked: "Invito revocato" };
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

function Confirm({ c, onClose }) {
  const [reason, setReason] = useState("");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="access-confirm-dialog">
        <DialogHeader><DialogTitle>{c.title}</DialogTitle><DialogDescription>{c.text}</DialogDescription></DialogHeader>
        {c.reason && <Input placeholder="Motivo (facoltativo)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="access-confirm-reason" />}
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button><Button onClick={() => c.run(reason)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="access-confirm-ok">Conferma</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EventLine({ m, e, ask, onAssign }) {
  const [l, c] = ST[e.status] || [e.status, "gray"];
  const act = (action, title, text, reason) => ask({ title, text, reason, url: `/memberships/${m.org_id}/events/${e.id}`, body: { action } });
  return (
    <div className="flex flex-wrap items-center gap-2 py-1.5 border-t border-slate-100 first:border-t-0" data-testid={`access-event-${e.id}`}>
      <span className="flex-1 min-w-[10rem] text-sm text-slate-700">{e.nome}</span>
      <StatusBadge color={c}>{l}</StatusBadge>
      {e.at && e.status !== "active" && <span className="text-[11px] text-slate-400">{fmt(e.at)}{e.reason ? ` · ${e.reason}` : ""}</span>}
      {e.status === "active" && <Button size="sm" variant="outline" onClick={() => act("disable", "Disattivare l'accesso all'evento?", `Sospeso temporaneamente: i permessi restano salvati e si potrà ripristinare.`, true)} data-testid={`access-ev-disable-${e.id}`}>Disattiva</Button>}
      {e.status === "disabled" && <Button size="sm" variant="outline" onClick={() => act("restore", "Ripristinare l'accesso?", `«${e.nome}» torna accessibile con i permessi precedenti.`)} data-testid={`access-ev-restore-${e.id}`}>Ripristina</Button>}
      {e.status !== "revoked" && <Button size="sm" variant="outline" className="text-red-600" onClick={() => act("revoke", "Revocare l'accesso all'evento?", "Gli altri eventi restano accessibili. Per ridarlo servirà riassegnarlo scegliendo i permessi.", true)} data-testid={`access-ev-revoke-${e.id}`}>Revoca</Button>}
      {e.status === "revoked" && <Button size="sm" variant="outline" onClick={() => onAssign(m, e)} data-testid={`access-ev-assign-${e.id}`}>Riassegna</Button>}
    </div>
  );
}

function OrgCard({ m, acc, ask, onPerms, onAssign }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3" data-testid={`access-org-${m.org_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-800 flex-1">{m.org_nome}</span>
        <span className="text-xs text-slate-500">{m.role_label}</span>
        <StatusBadge color={m.active ? "green" : "amber"}>{m.org_disabled ? "Organizzazione disattivata" : m.active ? "Accesso attivo" : "Accesso disattivato"}</StatusBadge>
        <Button size="sm" variant="outline" onClick={() => ask({ title: m.active ? "Disattivare l'accesso all'organizzazione?" : "Riattivare l'accesso all'organizzazione?", text: m.active ? `${acc.email} non potrà più lavorare in ${m.org_nome}. Le altre organizzazioni restano invariate.` : `${m.org_nome} torna accessibile con ruolo e permessi conservati.`, reason: m.active, url: `/memberships/${m.org_id}/state`, body: { active: !m.active } })} data-testid={`access-org-toggle-${m.org_id}`}>{m.active ? "Disattiva accesso" : "Riattiva accesso"}</Button>
        {m.role !== "admin_org" && <Button size="sm" variant="outline" onClick={() => onPerms(m)} data-testid={`access-org-perms-${m.org_id}`}>Modifica permessi</Button>}
      </div>
      {!m.active && m.deactivated_at && <div className="text-[11px] text-slate-400 mt-1">Disattivato il {fmt(m.deactivated_at)}{m.deactivation_reason ? ` · ${m.deactivation_reason}` : ""}</div>}
      {m.role === "collaboratore" && <div className="mt-2">
        <div className="text-xs font-semibold uppercase text-slate-500 mb-1">Eventi autorizzati {m.all_events && "· tutti gli eventi"}</div>
        {m.events.length === 0 && !m.all_events && <div className="text-xs text-slate-400">Nessun evento.</div>}
        {m.events.map((e) => <EventLine key={e.id} m={m} e={e} ask={ask} onAssign={onAssign} />)}
      </div>}
    </div>
  );
}

export default function UserAccessDialog({ user, onClose, onChanged }) {
  const [acc, setAcc] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [perms, setPerms] = useState(null);
  const load = useCallback(() => api.get(`/platform/users/${user.user_id}/access`).then(({ data }) => setAcc(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), [user.user_id]);
  useEffect(() => { load(); }, [load]);
  const call = async (method, url, body, ok) => {
    try { await api[method](`/platform/users/${user.user_id}${url}`, body); toast.success(ok); setConfirm(null); setPerms(null); load(); onChanged(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const ask = (c) => setConfirm({ ...c, run: (reason) => call("post", c.url, { ...c.body, reason }, "Accesso aggiornato") });
  const resend = (i) => call("post", `/invites/${i.id}/resend`, {}, "Invito reinviato");
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="user-access-dialog">
        <DialogHeader><DialogTitle>Gestisci accessi · {user.name || user.email}</DialogTitle>
          <DialogDescription>Stato dell'account separato dagli accessi alle singole organizzazioni ed eventi. Ogni modifica è registrata nell'Audit Log.</DialogDescription></DialogHeader>
        {!acc ? <p className="text-sm text-slate-400">Caricamento...</p> : <div className="space-y-3">
          <div className="flex flex-wrap gap-2 items-center text-sm"><span className="text-slate-600">Account:</span><StatusBadge color={acc.active ? "green" : "red"}>{acc.active ? "Attivo" : "Disattivato"}</StatusBadge>
            {!acc.active && acc.deactivated_at && <span className="text-xs text-slate-500">dal {fmt(acc.deactivated_at)}{acc.deactivation_reason ? ` · ${acc.deactivation_reason}` : ""}</span>}
            <span className="text-xs text-slate-400">Ultimo accesso: {fmt(acc.last_login_at)}</span></div>
          {acc.memberships.map((m) => <OrgCard key={m.org_id} m={m} acc={acc} ask={ask} onPerms={(mm) => setPerms({ m: mm, value: fromPerm(mm, acc.flags) })} onAssign={(mm, e) => setPerms({ m: mm, e, value: fromPerm(mm, acc.flags) })} />)}
          {acc.invites.map((i) => <div key={i.id} className="flex items-center gap-2 text-sm rounded-lg border border-dashed border-slate-300 px-3 py-2" data-testid={`access-invite-${i.id}`}>
            <span className="flex-1">{INV[i.status] || i.status} · scade {fmt(i.expires_at)}</span>
            {i.status !== "revoked" && <Button size="sm" variant="outline" onClick={() => resend(i)} data-testid={`access-invite-resend-${i.id}`}>Reinvia invito</Button>}</div>)}
        </div>}
        {confirm && <Confirm c={confirm} onClose={() => setConfirm(null)} />}
        {perms && <Dialog open onOpenChange={(o) => !o && setPerms(null)}>
          <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="access-perms-dialog">
            <DialogHeader><DialogTitle>{perms.e ? `Riassegna «${perms.e.nome}»` : `Permessi in ${perms.m.org_nome}`}</DialogTitle>
              <DialogDescription>{perms.e ? "L'accesso era stato revocato: scegli esplicitamente i permessi da assegnare." : "Valgono per tutti gli eventi autorizzati in questa organizzazione."}</DialogDescription></DialogHeader>
            <CollabPermEditor sections={acc.sections} flags={acc.flags} value={perms.value} onChange={(value) => setPerms({ ...perms, value })} testid="access-perm" />
            <DialogFooter><Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="access-perms-save"
              onClick={() => (perms.e ? call("post", `/memberships/${perms.m.org_id}/events/${perms.e.id}`, { action: "assign", ...permBody(perms.value) }, "Accesso riassegnato") : call("put", `/memberships/${perms.m.org_id}/permissions`, permBody(perms.value), "Permessi aggiornati"))}>
              {perms.e ? "Riassegna accesso" : "Salva permessi"}</Button></DialogFooter>
          </DialogContent>
        </Dialog>}
      </DialogContent>
    </Dialog>
  );
}
