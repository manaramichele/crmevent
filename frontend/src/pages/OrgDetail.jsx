import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Building2, Users, CalendarDays, ScrollText, UserPlus, Mail, Trash2, RefreshCw, XCircle, Save, Database, AlertTriangle } from "lucide-react";
import StaffInviteDialog from "@/components/StaffInviteDialog";
import { usePermMeta } from "@/pages/Permissions";
import PlanBadge, { BILLING } from "@/components/PlanBadge";

const TYPE_LABEL = { cliente: "Cliente", interna: "Interna", test: "Test" };
const TYPE_COLOR = { cliente: "tiffany", interna: "green", test: "orange" };
const INV_LABEL = { pending: "In attesa", accepted: "Accettato", expired: "Scaduto", revoked: "Revocato" };
const INV_COLOR = { pending: "orange", accepted: "green", expired: "gray", revoked: "red" };
const ROLE_OPTS = [{ value: "admin_org", label: "Admin Organizzazione" }, { value: "user", label: "Utente" }, { value: "collaboratore", label: "Collaboratore" }];
const AUTH_LABEL = (p) => (p === "google" ? "Google" : p ? "Email e password" : "—");

const inputCls = "h-10 px-3 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-tiffany focus:ring-2 focus:ring-tiffany/30";

function fmt(iso) { if (!iso) return "—"; try { return new Date(iso).toLocaleDateString("it-IT"); } catch { return iso; } }

const TABS = [
  { id: "dati", label: "Dati organizzazione", icon: Building2 },
  { id: "utenti", label: "Utenti", icon: Users },
  { id: "inviti", label: "Inviti", icon: Mail },
  { id: "eventi", label: "Eventi", icon: CalendarDays },
  { id: "audit", label: "Audit Log", icon: ScrollText },
];

export default function OrgDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [tab, setTab] = useState("dati");
  const [org, setOrg] = useState(null);
  const [form, setForm] = useState({ nome: "", type: "cliente", status: "active", formula: "" });
  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [events, setEvents] = useState([]);
  const [audit, setAudit] = useState([]);
  const [inviteOpen, setInviteOpen] = useState(false);
  const { meta } = usePermMeta(id);
  const [delName, setDelName] = useState(""); const [deleting, setDeleting] = useState(false);
  const [showSeed, setShowSeed] = useState(false); const [seedWipe, setSeedWipe] = useState(false); const [seeding, setSeeding] = useState(false);
  const [delUser, setDelUser] = useState(null); const [working, setWorking] = useState(false); const [cleaning, setCleaning] = useState(false);

  const loadOrg = useCallback(() => api.get(`/platform/organizations/${id}/detail`).then(({ data }) => {
    setOrg(data); setForm({ nome: data.nome, type: data.type, status: data.status, formula: data.formula || "" });
  }).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), [id]);
  const loadMembers = useCallback(() => api.get(`/platform/organizations/${id}/members`).then(({ data }) => setMembers(data)).catch(() => {}), [id]);
  const loadInvites = useCallback(() => api.get(`/platform/organizations/${id}/invites`).then(({ data }) => setInvites(data)).catch(() => {}), [id]);

  useEffect(() => { loadOrg(); loadMembers(); loadInvites(); }, [loadOrg, loadMembers, loadInvites]);
  useEffect(() => {
    if (tab === "eventi") api.get("/events", { headers: { "X-Org-Id": id } }).then(({ data }) => setEvents(data)).catch(() => {});
    if (tab === "audit") api.get("/platform/audit", { params: { org_id: id } }).then(({ data }) => setAudit(data.items)).catch(() => {});
  }, [tab, id]);

  const saveOrg = async () => {
    const body = { ...form };
    if (form.formula === (org.formula || "")) delete body.formula;
    try { const { data } = await api.patch(`/platform/organizations/${id}`, body); setOrg(data); setForm((f) => ({ ...f, formula: data.formula || "" })); toast.success("Organizzazione aggiornata"); }
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
  const deleteUserAccount = async () => {
    if (!delUser) return; setWorking(true);
    try { await api.delete(`/platform/users/${delUser.user_id}`); toast.success("Account eliminato definitivamente"); setDelUser(null); loadMembers(); loadInvites(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setWorking(false); }
  };
  const resendInvite = async (iid) => { try { await api.post(`/platform/invites/${iid}/resend`); toast.success("Invito reinviato"); loadInvites(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const revokeInvite = async (iid) => { try { await api.delete(`/platform/invites/${iid}`); toast.success("Invito revocato"); loadInvites(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const deleteInvite = async (iid) => { if (!window.confirm("Eliminare definitivamente questo invito? L'account eventualmente già registrato NON verrà eliminato.")) return; try { await api.delete(`/platform/invites/${iid}?hard=true`); toast.success("Invito eliminato"); loadInvites(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const cleanInvites = async () => { if (!window.confirm("Rimuovere gli inviti duplicati e non più necessari? Gli account già registrati non verranno toccati.")) return; setCleaning(true); try { const { data } = await api.post(`/platform/organizations/${id}/invites/cleanup`); toast.success(`Inviti ripuliti: ${data.removed} rimossi`); loadInvites(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setCleaning(false); } };

  const runSeed = async () => {
    setSeeding(true);
    try {
      const { data } = await api.post(`/platform/organizations/${id}/seed-demo`, { wipe: seedWipe });
      const tot = Object.values(data.counts).reduce((a, b) => a + b, 0);
      toast.success(`Dataset Demo ${data.wiped ? "ripristinato" : "popolato"}: ${tot} record`);
      setShowSeed(false); setSeedWipe(false);
      if (tab === "eventi") api.get("/events", { headers: { "X-Org-Id": id } }).then(({ data }) => setEvents(data)).catch(() => {});
      loadOrg();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSeeding(false); }
  };
  const deleteOrg = async () => {
    setDeleting(true);
    try {
      await api.delete(`/platform/organizations/${id}`, { data: { confirm_name: delName } });
      toast.success("Organizzazione eliminata definitivamente");
      window.location.href = "/piattaforma";
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setDeleting(false); }
  };

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
          <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Formula abbonamento</label>
            <select className={`${inputCls} w-full`} value={form.formula} onChange={(e) => setForm((f) => ({ ...f, formula: e.target.value }))} data-testid="org-edit-formula">
              <option value="">Nessuna formula</option><option value="bronze">BRONZE</option><option value="silver">SILVER</option><option value="gold">GOLD</option>
            </select>
            <p className="text-xs text-slate-500">{form.type === "cliente" ? "Nessuna formula = automatico (prova gratuita / abbonamento Stripe). Una formula assegnata attiva il piano senza modificare Stripe." : "Accesso gratuito con le funzionalità della formula, senza prova né pagamenti. Nessuna formula = accesso completo senza piano."} Scadenze e limiti si gestiscono in Abbonamenti.</p></div>
          <div className="flex items-center gap-2 flex-wrap text-xs text-slate-500" data-testid="org-current-plan">Piano effettivo: {org.saas?.enabled ? <PlanBadge s={org.saas} size="sm" testid="org-plan-badge" /> : <span>Nessun piano (accesso completo)</span>}{org.saas?.billing && <span>· {BILLING[org.saas.billing]}</span>}</div>
          <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Stato</label>
            <select className={`${inputCls} w-full`} value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))} data-testid="org-edit-status">
              <option value="active">Attiva</option><option value="disabled">Disattivata</option>
            </select></div>
          <Button onClick={saveOrg} data-testid="org-save-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Save className="w-4 h-4 mr-1.5" />Salva modifiche</Button>
        </div>
      )}

      {tab === "dati" && (
        <div className="max-w-lg space-y-6" data-testid="org-danger-zone">
          {org.type === "test" && (
            <div className="bg-white border border-amber-200 rounded-xl p-5 space-y-3">
              <div className="flex items-center gap-2 text-amber-700 font-semibold text-sm"><Database className="w-4 h-4" />Dataset dimostrativo</div>
              <p className="text-xs text-slate-500">Popola questa organizzazione di test con il dataset demo completo (eventi, persone, team, turni, sponsor, attività, ospitalità). Operazione idempotente: rieseguendola non crea duplicati. Nessuna email, trial, Stripe o fatturazione viene attivata.</p>
              <Button onClick={() => setShowSeed(true)} data-testid="seed-demo-btn" className="bg-slate-900 hover:bg-slate-800 text-white"><Database className="w-4 h-4 mr-1.5" />Popola / Ripristina dati Demo</Button>
            </div>
          )}
          <div className="bg-white border border-red-200 rounded-xl p-5 space-y-3" data-testid="org-delete-card">
            <div className="flex items-center gap-2 text-red-600 font-semibold text-sm"><AlertTriangle className="w-4 h-4" />Zona pericolosa · Elimina organizzazione</div>
            <p className="text-xs text-slate-500">L'eliminazione è definitiva e cancella tutti i dati appartenenti esclusivamente a questa organizzazione (eventi, persone, aziende, team, turni, sponsor, attività, ospitalità, inviti, account staff/volontari). Nessun'altra organizzazione viene toccata. Per confermare, digita il nome esatto: <span className="font-semibold text-slate-700">{org.nome}</span></p>
            <Input value={delName} onChange={(e) => setDelName(e.target.value)} placeholder="Digita il nome esatto dell'organizzazione" data-testid="org-delete-confirm-input" />
            <Button disabled={delName.trim() !== org.nome || deleting} onClick={deleteOrg} data-testid="org-delete-btn" className="bg-red-600 hover:bg-red-700 text-white disabled:opacity-40"><Trash2 className="w-4 h-4 mr-1.5" />{deleting ? "Eliminazione…" : "Elimina definitivamente"}</Button>
          </div>
        </div>
      )}

      {showSeed && (
        <div className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-4" onClick={() => !seeding && setShowSeed(false)}>
          <div className="w-full max-w-md bg-white rounded-xl p-6 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="seed-demo-dialog">
            <div className="flex items-center gap-2 text-slate-900"><Database className="w-6 h-6 text-tiffany-fg" /><h2 className="text-lg font-bold">Popola / Ripristina dati Demo</h2></div>
            <p className="text-sm text-slate-600">Verrà popolata l'organizzazione di test <span className="font-semibold">{org.nome}</span> con il dataset dimostrativo. L'operazione è idempotente e non invia email né attiva pagamenti.</p>
            <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={seedWipe} onChange={(e) => setSeedWipe(e.target.checked)} data-testid="seed-wipe-check" />Rimuovi prima i record demo esistenti (ripristino pulito)</label>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowSeed(false)} disabled={seeding} data-testid="seed-cancel">Annulla</Button>
              <Button onClick={runSeed} disabled={seeding} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="seed-confirm">{seeding ? "Esecuzione…" : "Conferma ed esegui"}</Button>
            </div>
          </div>
        </div>
      )}

      {tab === "utenti" && (
        <div className="space-y-6" data-testid="org-utenti-tab">
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="text-sm font-semibold text-slate-800 mb-1 flex items-center gap-2"><UserPlus className="w-4 h-4" />Aggiungi utente</div>
            <p className="text-xs text-slate-500 mb-3">Ogni account parte da una persona dello Staff di questa organizzazione: cerca la persona, assegna ruolo e permessi e invia l'invito. Un account già registrato altrove accetterà l'invito accedendo.</p>
            <Button onClick={() => setInviteOpen(true)} data-testid="member-add-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><UserPlus className="w-4 h-4 mr-1.5" />Invita dallo Staff</Button>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Utenti registrati con accesso ({members.length})</div>
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="members-table">
              <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
                <th className="text-left px-4 py-2.5">Nome</th><th className="text-left px-4 py-2.5">Email</th><th className="text-left px-4 py-2.5">Ruolo</th><th className="text-left px-4 py-2.5">Stato account</th><th className="text-left px-4 py-2.5">Accesso org</th><th className="text-left px-4 py-2.5">Metodo</th><th className="text-left px-4 py-2.5">Registrazione</th><th className="text-left px-4 py-2.5">Ultimo accesso</th><th className="text-right px-4 py-2.5">Azioni</th>
              </tr></thead>
              <tbody>
                {members.length === 0 ? <tr><td colSpan={9} className="px-4 py-8 text-center text-slate-400">Nessun utente registrato con accesso.</td></tr> :
                  members.map((m) => (
                    <tr key={m.user_id} className="border-t border-slate-100" data-testid={`member-row-${m.user_id}`}>
                      <td className="px-4 py-2.5 font-medium text-slate-800">{m.name || "—"}{m.is_superadmin && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-tiffany/20 text-tiffany-fg align-middle">Super Admin</span>}</td>
                      <td className="px-4 py-2.5 text-slate-600">{m.email}</td>
                      <td className="px-4 py-2.5">
                        {m.is_superadmin
                          ? <StatusBadge color="tiffany">{m.role_label || "Super Admin"}</StatusBadge>
                          : <select className="h-9 px-2 rounded-lg border border-slate-200 text-sm" value={m.role} onChange={(e) => changeRole(m.user_id, e.target.value)} data-testid={`member-role-${m.user_id}`}>{ROLE_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>}
                      </td>
                      <td className="px-4 py-2.5"><StatusBadge color={m.account_active ? "green" : "red"}>{m.account_active ? "Attivo" : "Disabilitato"}</StatusBadge></td>
                      <td className="px-4 py-2.5"><StatusBadge color={m.active ? "green" : "gray"}>{m.active ? "Consentito" : "Disabilitato"}</StatusBadge></td>
                      <td className="px-4 py-2.5 text-slate-500">{AUTH_LABEL(m.auth_provider)}</td>
                      <td className="px-4 py-2.5 text-slate-500">{fmt(m.created_at)}</td>
                      <td className="px-4 py-2.5 text-slate-500">{fmt(m.last_login_at)}</td>
                      <td className="px-4 py-2.5 text-right whitespace-nowrap">
                        {m.is_superadmin ? <span className="text-xs text-slate-400">—</span> : (
                          <>
                            <Button variant="outline" size="sm" className="mr-1" onClick={() => toggleActive(m.user_id, !m.active)} data-testid={`member-toggle-${m.user_id}`}>{m.active ? "Disabilita accesso" : "Riattiva accesso"}</Button>
                            <Button variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => setDelUser(m)} data-testid={`member-delete-${m.user_id}`}><Trash2 className="w-4 h-4" /></Button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table></div>
          </div>
        </div>
      )}

      {tab === "inviti" && (
        <div className="space-y-6" data-testid="org-inviti-tab">
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><Mail className="w-4 h-4" />Invita nuovo utente</div>
            <Button onClick={() => setInviteOpen(true)} data-testid="invite-send-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><UserPlus className="w-4 h-4 mr-1.5" />Invita dallo Staff</Button>
          </div>
          <StaffInviteDialog orgId={id} meta={meta} open={inviteOpen} onOpenChange={setInviteOpen} onSent={() => { loadInvites(); loadMembers(); }} onManageExisting={() => { setTab("utenti"); toast.info("Gestisci ruolo e permessi dalla scheda Utenti"); }} />

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800 flex items-center justify-between">
              <span>Inviti ({invites.length})</span>
              <Button variant="outline" size="sm" onClick={cleanInvites} disabled={cleaning} data-testid="invites-cleanup-btn"><RefreshCw className="w-4 h-4 mr-1.5" />{cleaning ? "Pulizia…" : "Pulisci duplicati"}</Button>
            </div>
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
                        {iv.status !== "accepted" && <Button variant="outline" size="sm" className="mr-1" onClick={() => resendInvite(iv.id)} data-testid={`invite-resend-${iv.id}`} title="Reinvia"><RefreshCw className="w-4 h-4" /></Button>}
                        {iv.status === "pending" && <Button variant="outline" size="sm" className="mr-1" onClick={() => revokeInvite(iv.id)} data-testid={`invite-revoke-${iv.id}`} title="Revoca"><XCircle className="w-4 h-4" /></Button>}
                        <Button variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => deleteInvite(iv.id)} data-testid={`invite-delete-${iv.id}`} title="Elimina invito"><Trash2 className="w-4 h-4" /></Button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table></div>
          </div>
        </div>
      )}

      {delUser && (
        <div className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-4" onClick={() => !working && setDelUser(null)}>
          <div className="w-full max-w-md bg-white rounded-xl p-6 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="member-delete-dialog">
            <div className="flex items-center gap-2 text-red-600"><AlertTriangle className="w-6 h-6" /><h2 className="text-lg font-bold text-slate-900">Elimina utente definitivamente</h2></div>
            <p className="text-sm text-slate-600">Stai per eliminare definitivamente l'account <span className="font-semibold text-slate-900">{delUser.email}</span>. L'utente non potrà più accedere a CRMEvent. L'anagrafica Persona, gli eventi, le attività, i turni e gli altri dati dell'organizzazione NON verranno eliminati.</p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setDelUser(null)} disabled={working} data-testid="member-delete-cancel">Annulla</Button>
              <Button onClick={deleteUserAccount} disabled={working} className="bg-red-600 hover:bg-red-700 text-white" data-testid="member-delete-confirm">{working ? "Eliminazione…" : "Elimina definitivamente"}</Button>
            </div>
          </div>
        </div>
      )}

      {tab === "eventi" && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid="org-eventi-tab">
          <div className="overflow-x-auto"><table className="w-full text-sm">
            <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <th className="text-left px-4 py-2.5">Evento</th>
              <th className="text-left px-4 py-2.5">Data</th>
              <th className="text-left px-4 py-2.5">Piano</th>
              <th className="text-left px-4 py-2.5">Commerciale</th>
              <th className="text-left px-4 py-2.5">Attivazione</th>
            </tr></thead>
            <tbody>
              {events.length === 0 ? <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Nessun evento in questa organizzazione.</td></tr> :
                events.map((e) => {
                  const ent = e.entitlement || {};
                  const purchased = ent.source === "purchased";
                  const orgTrial = org?.subscription?.status === "trial" && (org?.subscription?.days_left ?? 0) > 0;
                  const PL = { starter: "Starter", professional: "Professional", premium: "Premium" };
                  const plan = purchased ? (PL[ent.plan] || ent.plan) : (orgTrial ? "Premium (prova)" : "—");
                  const commColor = purchased ? "green" : (orgTrial ? "tiffany" : "red");
                  const commLabel = purchased ? "Acquistato" : (orgTrial ? "Prova Premium" : "Nessun piano");
                  return (
                    <tr key={e.id} className="border-t border-slate-100" data-testid={`org-event-row-${e.id}`}>
                      <td className="px-4 py-2.5 font-medium text-slate-800">{e.nome}</td>
                      <td className="px-4 py-2.5 text-slate-600">{fmt(e.data_inizio)}</td>
                      <td className="px-4 py-2.5 text-slate-700">{plan}</td>
                      <td className="px-4 py-2.5"><StatusBadge color={commColor}>{commLabel}</StatusBadge></td>
                      <td className="px-4 py-2.5 text-slate-600">{purchased ? fmt(ent.purchased_at) : "—"}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table></div>
          <p className="text-xs text-slate-400 px-4 py-3 border-t border-slate-100">Stato commerciale per singolo evento. I dati legacy di abbonamento restano separati fino alla migrazione Stripe.</p>
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
