import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Building2, Users, CalendarDays, ScrollText, UserPlus, Mail, Trash2, RefreshCw, XCircle, Save } from "lucide-react";

const TYPE_LABEL = { cliente: "Cliente", interna: "Interna", test: "Test" };
const TYPE_COLOR = { cliente: "tiffany", interna: "green", test: "orange" };
const INV_LABEL = { pending: "In attesa", accepted: "Accettato", expired: "Scaduto", revoked: "Revocato" };
const INV_COLOR = { pending: "orange", accepted: "green", expired: "gray", revoked: "red" };
const ROLE_OPTS = [{ value: "admin_org", label: "Admin Organizzazione" }, { value: "user", label: "Utente" }];

const inputCls = "h-10 px-3 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-tiffany focus:ring-2 focus:ring-tiffany/30";

function fmt(iso) { if (!iso) return "—"; try { return new Date(iso).toLocaleDateString("it-IT"); } catch { return iso; } }

const TABS = [
  { id: "dati", label: "Dati organizzazione", icon: Building2 },
  { id: "utenti", label: "Utenti e accessi", icon: Users },
  { id: "eventi", label: "Eventi", icon: CalendarDays },
  { id: "audit", label: "Audit Log", icon: ScrollText },
];

export default function OrgDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [tab, setTab] = useState("dati");
  const [org, setOrg] = useState(null);
  const [form, setForm] = useState({ nome: "", type: "cliente", status: "active" });
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [events, setEvents] = useState([]);
  const [audit, setAudit] = useState([]);
  const [addEmail, setAddEmail] = useState(""); const [addRole, setAddRole] = useState("user");
  const [invEmail, setInvEmail] = useState(""); const [invRole, setInvRole] = useState("user");

  const loadOrg = useCallback(() => api.get(`/platform/organizations/${id}/detail`).then(({ data }) => {
    setOrg(data); setForm({ nome: data.nome, type: data.type, status: data.status });
  }).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), [id]);
  const loadMembers = useCallback(() => api.get(`/platform/organizations/${id}/members`).then(({ data }) => setMembers(data)).catch(() => {}), [id]);
  const loadInvites = useCallback(() => api.get(`/platform/organizations/${id}/invites`).then(({ data }) => setInvites(data)).catch(() => {}), [id]);

  useEffect(() => { loadOrg(); loadMembers(); loadInvites(); }, [loadOrg, loadMembers, loadInvites]);
  useEffect(() => {
    if (tab === "eventi") api.get("/events", { headers: { "X-Org-Id": id } }).then(({ data }) => setEvents(data)).catch(() => {});
    if (tab === "audit") api.get("/platform/audit", { params: { org_id: id } }).then(({ data }) => setAudit(data.items)).catch(() => {});
  }, [tab, id]);

  const saveOrg = async () => {
    try { const { data } = await api.patch(`/platform/organizations/${id}`, form); setOrg(data); toast.success("Organizzazione aggiornata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const addMember = async () => {
    if (!addEmail) return;
    try { await api.post(`/platform/organizations/${id}/members`, { email: addEmail, role: addRole }); toast.success("Utente associato"); setAddEmail(""); loadMembers(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const changeRole = async (uid, role) => {
    try { await api.patch(`/platform/organizations/${id}/members/${uid}`, { role }); loadMembers(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const toggleActive = async (uid, active) => {
    try { await api.patch(`/platform/organizations/${id}/members/${uid}`, { active }); toast.success(active ? "Accesso riattivato" : "Accesso disabilitato"); loadMembers(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const removeMember = async (uid) => {
    if (!window.confirm("Rimuovere l'utente da questa organizzazione? I dati dell'organizzazione restano intatti.")) return;
    try { await api.delete(`/platform/organizations/${id}/members/${uid}`); toast.success("Utente rimosso"); loadMembers(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const sendInvite = async () => {
    if (!invEmail) return;
    try { const { data } = await api.post(`/platform/organizations/${id}/invites`, { email: invEmail, role: invRole }); toast[data.email_sent ? "success" : "warning"](data.email_sent ? "Invito inviato" : "Invito creato (email non inviata)"); setInvEmail(""); loadInvites(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const resendInvite = async (iid) => { try { await api.post(`/platform/invites/${iid}/resend`); toast.success("Invito reinviato"); loadInvites(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const revokeInvite = async (iid) => { try { await api.delete(`/platform/invites/${iid}`); toast.success("Invito revocato"); loadInvites(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

  if (!org) return <div className="py-20 text-center text-slate-400">Caricamento…</div>;

  return (
    <div className="space-y-6" data-testid="org-detail-page">
      <button onClick={() => nav("/piattaforma")} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800" data-testid="org-detail-back"><ArrowLeft className="w-4 h-4" />Organizzazioni</button>
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-2xl font-bold text-slate-900">{org.nome}</h1>
        <StatusBadge color={TYPE_COLOR[org.type]}>{TYPE_LABEL[org.type]}</StatusBadge>
        <StatusBadge color={org.status === "active" ? "green" : "red"}>{org.status === "active" ? "Attiva" : "Disattivata"}</StatusBadge>
      </div>

      <div className="flex gap-1 border-b border-slate-200 overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)} data-testid={`org-tab-${t.id}`}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap ${tab === t.id ? "border-tiffany text-slate-900" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            <t.icon className="w-4 h-4" />{t.label}
          </button>
        ))}
      </div>

      {tab === "dati" && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 max-w-lg space-y-4" data-testid="org-dati-tab">
          <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Nome organizzazione</label>
            <Input value={form.nome} onChange={(e) => setForm((f) => ({ ...f, nome: e.target.value }))} data-testid="org-edit-nome" /></div>
          <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Tipo</label>
            <select className={`${inputCls} w-full`} value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))} data-testid="org-edit-type">
              <option value="cliente">Cliente (trial + abbonamento)</option>
              <option value="interna">Interna (nessun abbonamento)</option>
              <option value="test">Test</option>
            </select></div>
          <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Stato</label>
            <select className={`${inputCls} w-full`} value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))} data-testid="org-edit-status">
              <option value="active">Attiva</option><option value="disabled">Disattivata</option>
            </select></div>
          <div className="text-xs text-slate-500">Abbonamento: {org.subscription.status === "cliente" || org.type === "cliente" ? `${org.subscription.status}${org.subscription.days_left != null ? ` · ${org.subscription.days_left} gg` : ""}` : "Non applicabile (organizzazione " + TYPE_LABEL[org.type] + ")"}</div>
          <Button onClick={saveOrg} data-testid="org-save-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Save className="w-4 h-4 mr-1.5" />Salva modifiche</Button>
        </div>
      )}

      {tab === "utenti" && (
        <div className="space-y-6" data-testid="org-utenti-tab">
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><UserPlus className="w-4 h-4" />Aggiungi utente esistente</div>
            <div className="flex flex-wrap gap-2">
              <input className={`${inputCls} flex-1 min-w-[200px]`} placeholder="email@utente.it" value={addEmail} onChange={(e) => setAddEmail(e.target.value)} data-testid="member-add-email" />
              <select className={inputCls} value={addRole} onChange={(e) => setAddRole(e.target.value)} data-testid="member-add-role">{ROLE_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
              <Button onClick={addMember} data-testid="member-add-btn" className="bg-slate-900 hover:bg-slate-800 text-white">Associa</Button>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Utenti associati</div>
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="members-table">
              <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
                <th className="text-left px-4 py-2.5">Nome</th><th className="text-left px-4 py-2.5">Email</th><th className="text-left px-4 py-2.5">Ruolo</th><th className="text-left px-4 py-2.5">Stato</th><th className="text-left px-4 py-2.5">Ultimo accesso</th><th className="text-right px-4 py-2.5">Azioni</th>
              </tr></thead>
              <tbody>
                {members.length === 0 ? <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Nessun utente associato.</td></tr> :
                  members.map((m) => (
                    <tr key={m.user_id} className="border-t border-slate-100" data-testid={`member-row-${m.user_id}`}>
                      <td className="px-4 py-2.5 font-medium text-slate-800">{m.name || "—"}</td>
                      <td className="px-4 py-2.5 text-slate-600">{m.email}</td>
                      <td className="px-4 py-2.5">
                        <select className="h-9 px-2 rounded-lg border border-slate-200 text-sm" value={m.role} onChange={(e) => changeRole(m.user_id, e.target.value)} data-testid={`member-role-${m.user_id}`}>{ROLE_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
                      </td>
                      <td className="px-4 py-2.5"><StatusBadge color={m.active ? "green" : "gray"}>{m.active ? "Attivo" : "Disabilitato"}</StatusBadge></td>
                      <td className="px-4 py-2.5 text-slate-500">{fmt(m.last_login_at)}</td>
                      <td className="px-4 py-2.5 text-right whitespace-nowrap">
                        <Button variant="outline" size="sm" className="mr-1" onClick={() => toggleActive(m.user_id, !m.active)} data-testid={`member-toggle-${m.user_id}`}>{m.active ? "Disabilita" : "Riattiva"}</Button>
                        <Button variant="outline" size="sm" className="text-red-600" onClick={() => removeMember(m.user_id)} data-testid={`member-remove-${m.user_id}`}><Trash2 className="w-4 h-4" /></Button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table></div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Mail className="w-4 h-4" />Invita nuovo utente</div>
            <div className="flex flex-wrap gap-2">
              <input className={`${inputCls} flex-1 min-w-[200px]`} placeholder="email@nuovo.it" value={invEmail} onChange={(e) => setInvEmail(e.target.value)} data-testid="invite-email" />
              <select className={inputCls} value={invRole} onChange={(e) => setInvRole(e.target.value)} data-testid="invite-role">{ROLE_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
              <Button onClick={sendInvite} data-testid="invite-send-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">Invia invito</Button>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Inviti</div>
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="invites-table">
              <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
                <th className="text-left px-4 py-2.5">Email</th><th className="text-left px-4 py-2.5">Ruolo</th><th className="text-left px-4 py-2.5">Data invito</th><th className="text-left px-4 py-2.5">Scadenza</th><th className="text-left px-4 py-2.5">Stato</th><th className="text-right px-4 py-2.5">Azioni</th>
              </tr></thead>
              <tbody>
                {invites.length === 0 ? <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Nessun invito.</td></tr> :
                  invites.map((iv) => (
                    <tr key={iv.id} className="border-t border-slate-100" data-testid={`invite-row-${iv.id}`}>
                      <td className="px-4 py-2.5 text-slate-700">{iv.email}</td>
                      <td className="px-4 py-2.5 text-slate-600">{iv.role_label}</td>
                      <td className="px-4 py-2.5 text-slate-500">{fmt(iv.created_at)}</td>
                      <td className="px-4 py-2.5 text-slate-500">{fmt(iv.expires_at)}</td>
                      <td className="px-4 py-2.5"><StatusBadge color={INV_COLOR[iv.status]}>{INV_LABEL[iv.status]}</StatusBadge></td>
                      <td className="px-4 py-2.5 text-right whitespace-nowrap">
                        {iv.status !== "accepted" && <Button variant="outline" size="sm" className="mr-1" onClick={() => resendInvite(iv.id)} data-testid={`invite-resend-${iv.id}`}><RefreshCw className="w-4 h-4" /></Button>}
                        {iv.status === "pending" && <Button variant="outline" size="sm" className="text-red-600" onClick={() => revokeInvite(iv.id)} data-testid={`invite-revoke-${iv.id}`}><XCircle className="w-4 h-4" /></Button>}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table></div>
          </div>
        </div>
      )}

      {tab === "eventi" && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid="org-eventi-tab">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider"><th className="text-left px-4 py-2.5">Evento</th><th className="text-left px-4 py-2.5">Città</th><th className="text-left px-4 py-2.5">Stato</th></tr></thead>
            <tbody>
              {events.length === 0 ? <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-400">Nessun evento in questa organizzazione.</td></tr> :
                events.map((e) => <tr key={e.id} className="border-t border-slate-100"><td className="px-4 py-2.5 font-medium text-slate-800">{e.nome}</td><td className="px-4 py-2.5 text-slate-600">{e.citta || "—"}</td><td className="px-4 py-2.5 text-slate-600">{e.stato || "—"}</td></tr>)}
            </tbody>
          </table></div>
        </div>
      )}

      {tab === "audit" && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid="org-audit-tab">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider"><th className="text-left px-4 py-2.5">Data/Ora</th><th className="text-left px-4 py-2.5">Autore</th><th className="text-left px-4 py-2.5">Azione</th><th className="text-left px-4 py-2.5">Dettaglio</th></tr></thead>
            <tbody>
              {audit.length === 0 ? <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-400">Nessuna voce.</td></tr> :
                audit.map((a) => <tr key={a.id} className="border-t border-slate-100">
                  <td className="px-4 py-2.5 text-slate-600 whitespace-nowrap">{a.created_at ? new Date(a.created_at).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}</td>
                  <td className="px-4 py-2.5 text-slate-600">{a.actor_name || a.actor_email}</td>
                  <td className="px-4 py-2.5"><StatusBadge color="tiffany">{a.action_label}</StatusBadge></td>
                  <td className="px-4 py-2.5 text-slate-500">{[a.target_email, a.detail].filter(Boolean).join(" · ") || "—"}</td>
                </tr>)}
            </tbody>
          </table></div>
        </div>
      )}
    </div>
  );
}
