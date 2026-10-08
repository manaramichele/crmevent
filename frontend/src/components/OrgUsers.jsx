import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/crm";
import { toast } from "sonner";
import { UserPlus, RefreshCw, XCircle, Pencil } from "lucide-react";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { usePermMeta, PermissionsDialog, PermAudit, teamAccessLabel, permSummary } from "@/pages/Permissions";
import StaffInviteDialog from "@/components/StaffInviteDialog";

const fmt = (iso) => { if (!iso) return "—"; try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return iso; } };
const STATUS = {
  member_active: ["green", "Attivo"], member_inactive: ["gray", "Accesso disattivato"],
  pending: ["orange", "Invito inviato"], expired: ["red", "Invito scaduto"],
};

export default function OrgUsers({ orgId, allowProfileEdit = false }) {
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [ef, setEf] = useState({ nome: "", cognome: "", email: "", telefono: "" });
  const [ebusy, setEbusy] = useState(false);
  const { meta, reload: reloadMeta } = usePermMeta(orgId);
  const [permFor, setPermFor] = useState(null);
  const [auditKey, setAuditKey] = useState(0);
  const pm = (uid) => meta?.members?.find((x) => x.user_id === uid);
  const manageExisting = (uid) => { const m = pm(uid); if (m && !m.is_self) setPermFor(m); else toast.info(m?.is_self ? "È il tuo account: non puoi modificare il tuo ruolo" : "Account non gestibile da qui"); };

  const load = useCallback(async () => {
    try {
      const [m, i] = await Promise.all([
        api.get(`/platform/organizations/${orgId}/members`),
        api.get(`/platform/organizations/${orgId}/invites`),
      ]);
      setMembers(m.data); setInvites(i.data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [orgId]);
  useEffect(() => { if (orgId) load(); }, [orgId, load]);

  const pendingInvites = invites.filter((iv) => iv.status === "pending" || iv.status === "expired");

  const toggleActive = async (uid, active) => { try { await api.patch(`/platform/organizations/${orgId}/members/${uid}`, { active }); toast.success(active ? "Accesso riattivato" : "Accesso disattivato"); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const resend = async (id) => { try { const { data } = await api.post(`/platform/invites/${id}/resend`); toast[data.email_sent ? "success" : "warning"](data.email_sent ? "Invito reinviato" : "Invito aggiornato (email non inviata)"); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const revoke = async (id) => { if (!window.confirm("Revocare questo invito?")) return; try { await api.delete(`/platform/invites/${id}`); toast.success("Invito revocato"); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

  const openEdit = (m) => { setEf({ nome: m.nome || "", cognome: m.cognome || "", email: m.email || "", telefono: m.telefono || "" }); setEdit(m); };
  const submitEdit = async () => {
    if (!ef.nome.trim()) return toast.error("Il nome è obbligatorio");
    if (!ef.email.trim()) return toast.error("Email obbligatoria");
    if (!ef.telefono || !isValidPhoneNumber(ef.telefono)) return toast.error("Inserisci un cellulare valido");
    setEbusy(true);
    try {
      await api.patch(`/platform/users/${edit.user_id}/profile`, { nome: ef.nome.trim(), cognome: ef.cognome.trim(), email: ef.email.trim(), telefono: ef.telefono });
      toast.success("Anagrafica aggiornata");
      setEdit(null); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setEbusy(false); }
  };

  return (
    <div data-testid="org-users-section">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <p className="text-sm text-slate-500">Gestisci chi può accedere e operare nella tua organizzazione.</p>
        <Button onClick={() => setOpen(true)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="org-invite-btn"><UserPlus className="w-4 h-4 mr-1.5" />Invita utente</Button>
      </div>
      <div className="md:hidden space-y-2.5" data-testid="org-users-mobile-list">
        {members.length === 0 && pendingInvites.length === 0 && <p className="py-8 text-center text-slate-400 text-sm">Nessun utente.</p>}
        {members.map((m) => {
          const st = m.active ? STATUS.member_active : STATUS.member_inactive;
          return (
            <div key={m.user_id} className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`m-user-card-${m.user_id}`}>
              <div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="font-semibold text-slate-900 break-words">{m.name || "—"}</div><div className="text-xs text-slate-500 break-all">{m.email}</div></div><StatusBadge color={st[0]}>{st[1]}</StatusBadge></div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5"><StatusBadge color={m.is_superadmin || m.role === "admin_org" ? "tiffany" : m.role === "collaboratore" ? "orange" : "blue"}>{m.is_superadmin ? "Super Admin" : m.role_label}</StatusBadge></div>
              {!m.is_superadmin && <div className="mt-2 space-y-1 text-xs text-slate-600"><div><span className="text-slate-400">Team: </span>{teamAccessLabel(pm(m.user_id)?.permissions, meta)}</div><div><span className="text-slate-400">Permessi: </span>{permSummary(pm(m.user_id)?.permissions, meta)}</div></div>}
              {!m.is_superadmin && <div className="mt-3 flex flex-wrap gap-2">
                {allowProfileEdit && <Button variant="outline" size="sm" onClick={() => openEdit(m)} data-testid={`m-user-edit-${m.user_id}`}><Pencil className="w-3.5 h-3.5 mr-1" />Modifica</Button>}
                {pm(m.user_id) && !pm(m.user_id).is_self && <Button variant="outline" size="sm" onClick={() => setPermFor(pm(m.user_id))} data-testid={`m-user-perms-btn-${m.user_id}`}>Permessi</Button>}
                <Button variant="outline" size="sm" onClick={() => toggleActive(m.user_id, !m.active)} data-testid={`m-user-toggle-${m.user_id}`}>{m.active ? "Disattiva" : "Riattiva"}</Button>
              </div>}
            </div>
          );
        })}
        {pendingInvites.map((iv) => {
          const st = STATUS[iv.status] || STATUS.pending;
          return (
            <div key={iv.id} className="rounded-xl border border-amber-200 bg-amber-50/40 p-4" data-testid={`m-invite-card-${iv.id}`}>
              <div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="font-semibold text-slate-800 break-words">{`${iv.nome || ""} ${iv.cognome || ""}`.trim() || "—"}</div><div className="text-xs text-slate-500 break-all">{iv.email} · {iv.role_label}</div></div><StatusBadge color={st[0]}>{st[1]}</StatusBadge></div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => resend(iv.id)} data-testid={`m-invite-resend-${iv.id}`}><RefreshCw className="w-3.5 h-3.5 mr-1" />Reinvia</Button>
                <Button variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => revoke(iv.id)} data-testid={`m-invite-revoke-${iv.id}`}><XCircle className="w-3.5 h-3.5 mr-1" />Revoca</Button>
              </div>
            </div>
          );
        })}
      </div>
      <div className="hidden md:block overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full min-w-[920px] text-sm" data-testid="org-users-table">
          <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
            <th className="text-left px-3 py-2.5">Utente</th><th className="text-left px-3 py-2.5">Email</th><th className="text-left px-3 py-2.5">Ruolo</th><th className="text-left px-3 py-2.5">Accesso Team</th><th className="text-left px-3 py-2.5">Permessi</th><th className="text-left px-3 py-2.5">Stato</th><th className="text-right px-3 py-2.5">Azioni</th>
          </tr></thead>
          <tbody>
            {members.length === 0 && pendingInvites.length === 0 && <tr><td colSpan={7} className="px-3 py-8 text-center text-slate-400">Nessun utente.</td></tr>}
            {members.map((m) => {
              const st = m.active ? STATUS.member_active : STATUS.member_inactive;
              return (
                <tr key={m.user_id} className="border-t border-slate-100" data-testid={`user-row-${m.user_id}`}>
                  <td className="px-3 py-2.5 font-medium text-slate-800">{m.name || "—"}{m.is_superadmin && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-tiffany/20 text-tiffany-fg">Super Admin</span>}</td>
                  <td className="px-3 py-2.5 text-slate-600 whitespace-nowrap">{m.email}</td>
                  <td className="px-3 py-2.5"><StatusBadge color={m.is_superadmin ? "tiffany" : m.role === "admin_org" ? "tiffany" : m.role === "collaboratore" ? "orange" : "blue"}>{m.role_label}</StatusBadge></td>
                  <td className="px-3 py-2.5 text-slate-600 text-xs max-w-[200px]" data-testid={`user-teams-${m.user_id}`}>{m.is_superadmin ? "—" : teamAccessLabel(pm(m.user_id)?.permissions, meta)}</td>
                  <td className="px-3 py-2.5 text-slate-600 text-xs max-w-[220px]" data-testid={`user-perms-${m.user_id}`}>{m.is_superadmin ? "Super Admin" : permSummary(pm(m.user_id)?.permissions, meta)}{pm(m.user_id)?.custom && <span className="ml-1 text-[10px] text-tiffany-fg">personalizzati</span>}</td>
                  <td className="px-3 py-2.5"><StatusBadge color={st[0]}>{st[1]}</StatusBadge></td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">{m.is_superadmin ? <span className="text-xs text-slate-400">—</span> : <>{allowProfileEdit && <Button variant="outline" size="sm" className="mr-1" onClick={() => openEdit(m)} data-testid={`user-edit-${m.user_id}`} title="Modifica anagrafica"><Pencil className="w-3.5 h-3.5 mr-1" />Modifica</Button>}{pm(m.user_id) && !pm(m.user_id).is_self && <Button variant="outline" size="sm" className="mr-1" onClick={() => setPermFor(pm(m.user_id))} data-testid={`user-perms-btn-${m.user_id}`}>Permessi</Button>}<Button variant="outline" size="sm" onClick={() => toggleActive(m.user_id, !m.active)} data-testid={`user-toggle-${m.user_id}`}>{m.active ? "Disattiva" : "Riattiva"}</Button></>}</td>
                </tr>
              );
            })}
            {pendingInvites.map((iv) => {
              const st = STATUS[iv.status] || STATUS.pending;
              const nm = `${iv.nome || ""} ${iv.cognome || ""}`.trim();
              return (
                <tr key={iv.id} className="border-t border-slate-100 bg-amber-50/30" data-testid={`invite-row-${iv.id}`}>
                  <td className="px-3 py-2.5 font-medium text-slate-700">{nm || "—"}</td>
                  <td className="px-3 py-2.5 text-slate-600 whitespace-nowrap">{iv.email}</td>
                  <td className="px-3 py-2.5 text-slate-500">{iv.role_label}</td>
                  <td className="px-3 py-2.5 text-slate-400 text-xs">—</td>
                  <td className="px-3 py-2.5 text-slate-400 text-xs">Applicati all'accettazione</td>
                  <td className="px-3 py-2.5"><StatusBadge color={st[0]}>{st[1]}</StatusBadge></td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    <Button variant="outline" size="sm" className="mr-1" onClick={() => resend(iv.id)} data-testid={`invite-resend-${iv.id}`} title="Reinvia invito"><RefreshCw className="w-4 h-4" /></Button>
                    <Button variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => revoke(iv.id)} data-testid={`invite-revoke-${iv.id}`} title="Revoca invito"><XCircle className="w-4 h-4" /></Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <StaffInviteDialog orgId={orgId} meta={meta} open={open} onOpenChange={setOpen} onSent={() => { load(); reloadMeta(); }} onManageExisting={manageExisting} />

      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent className="max-w-md" data-testid="user-edit-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Pencil className="w-5 h-5 text-tiffany-active" />Modifica anagrafica</DialogTitle><DialogDescription>Correggi i dati dell'account collegato. Il cellulare è salvato in formato internazionale (E.164).</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label>Nome *</Label><Input value={ef.nome} onChange={(e) => setEf((s) => ({ ...s, nome: e.target.value }))} data-testid="edit-nome" /></div>
              <div className="space-y-1.5"><Label>Cognome</Label><Input value={ef.cognome} onChange={(e) => setEf((s) => ({ ...s, cognome: e.target.value }))} data-testid="edit-cognome" /></div>
            </div>
            <div className="space-y-1.5"><Label>Email *</Label><Input type="email" value={ef.email} onChange={(e) => setEf((s) => ({ ...s, email: e.target.value }))} data-testid="edit-email" /></div>
            <div className="space-y-1.5"><Label>Cellulare *</Label><PhoneInput international defaultCountry="IT" value={ef.telefono} onChange={(v) => setEf((s) => ({ ...s, telefono: v || "" }))} className="phone-input" numberInputProps={{ "data-testid": "edit-telefono-input" }} data-testid="edit-telefono" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEdit(null)}>Annulla</Button>
            <Button disabled={ebusy} onClick={submitEdit} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="edit-submit">Salva modifiche</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {permFor && meta && <PermissionsDialog orgId={orgId} meta={meta} member={permFor} onClose={() => setPermFor(null)}
        onSaved={() => { setPermFor(null); reloadMeta(); load(); setAuditKey((k) => k + 1); }} />}
      {meta && <div className="mt-6"><PermAudit orgId={orgId} refreshKey={auditKey} /></div>}
    </div>
  );
}
