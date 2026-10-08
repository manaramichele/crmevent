import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import PaymentsCredits, { LegacySubscriptions } from "@/components/PaymentsCredits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Building2, Users, CalendarDays, Wallet, TrendingUp, Inbox, ReceiptText, Link2, Unlink, Plus, X, Trash2, Power, ShieldAlert, Mail } from "lucide-react";

const TYPE_LABEL = { cliente: "Cliente", interna: "Interna", test: "Test" };
const TYPE_COLOR = { cliente: "tiffany", interna: "green", test: "orange" };

function Stat({ icon: Icon, label, value, tone = "slate" }) {
  const tones = { slate: "bg-slate-100 text-slate-700", tiffany: "bg-tiffany-light text-tiffany-fg", green: "bg-emerald-50 text-emerald-700", red: "bg-red-50 text-red-600", blue: "bg-sky-50 text-sky-700" };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`platform-stat-${label}`}>
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center mb-2 ${tones[tone]}`}><Icon className="w-5 h-5" /></div>
      <div className="text-2xl font-bold text-slate-900">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

export default function Platform() {
  const nav = useNavigate();
  const [stats, setStats] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [subs, setSubs] = useState([]);
  const [fic, setFic] = useState(null);
  const [brevo, setBrevo] = useState(null); const [brevoBusy, setBrevoBusy] = useState(false);
  const [senders, setSenders] = useState(null); const [sendersBusy, setSendersBusy] = useState(false);
  const [testTo, setTestTo] = useState(""); const [testSender, setTestSender] = useState("");
  const [testBusy, setTestBusy] = useState(false); const [testResult, setTestResult] = useState(null);
  const [params, setParams] = useSearchParams();
  const [showCreate, setShowCreate] = useState(false);
  const [nf, setNf] = useState({ nome: "", type: "cliente", status: "active" });
  const [creating, setCreating] = useState(false);
  const [users, setUsers] = useState([]);
  const [delUser, setDelUser] = useState(null);
  const [working, setWorking] = useState(false);

  const loadFic = () => api.get("/fic/status").then(({ data }) => setFic(data)).catch(() => {});
  const loadUsers = () => api.get("/platform/users").then(({ data }) => setUsers(data)).catch(() => {});
  const loadAll = () => Promise.allSettled([api.get("/platform/stats"), api.get("/platform/organizations"), api.get("/platform/subscriptions"), api.get("/platform/users")])
    .then(([a, b, c, d]) => {
      if (a.status === "fulfilled") setStats(a.value.data);
      if (b.status === "fulfilled") setOrgs(b.value.data);
      if (c.status === "fulfilled") setSubs(c.value.data);
      if (d.status === "fulfilled") setUsers(d.value.data);
      const failed = [a, b, c, d].find((r) => r.status === "rejected");
      if (failed) toast.error(formatApiError(failed.reason?.response?.data?.detail));
    });

  useEffect(() => { loadAll(); loadFic(); }, []);
  useEffect(() => {
    const f = params.get("fic");
    if (!f) return;
    if (f === "connected") toast.success("Fatture in Cloud collegato"); else toast.error("Collegamento Fatture in Cloud non riuscito");
    params.delete("fic"); setParams(params, { replace: true }); loadFic();
  }, [params, setParams]);

  const connectFic = async () => { try { const { data } = await api.get("/fic/oauth/start"); window.location.href = data.authorize_url; } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const disconnectFic = async () => { try { await api.post("/fic/disconnect"); toast.success("Fatture in Cloud scollegato"); loadFic(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const checkBrevo = async () => { setBrevoBusy(true); try { const { data } = await api.get("/integrations/brevo/check"); setBrevo(data); toast[data.valid ? "success" : "warning"](data.message); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBrevoBusy(false); } };
  const loadSenders = async () => { setSendersBusy(true); try { const { data } = await api.get("/integrations/brevo/senders"); setSenders(data.senders || []); if (!data.configured) toast.warning(data.message); else if (data.message !== "OK") toast.warning(data.message); else { const active = (data.senders || []).find((s) => s.active); if (active && !testSender) setTestSender(active.email); } } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setSendersBusy(false); } };
  const sendTestEmail = async () => { if (!testTo.trim()) { toast.error("Inserisci l'indirizzo destinatario"); return; } if (!testSender) { toast.error("Seleziona un mittente verificato"); return; } setTestBusy(true); setTestResult(null); try { const { data } = await api.post("/integrations/brevo/send-test", { to: testTo.trim(), sender_email: testSender }); setTestResult(data); toast[data.success ? "success" : "error"](data.message); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setTestBusy(false); } };

  const createOrg = async () => {
    if (!nf.nome.trim()) { toast.error("Inserisci il nome"); return; }
    setCreating(true);
    try {
      const { data } = await api.post("/platform/organizations", nf);
      toast.success("Organizzazione creata");
      // Full navigation so the new org immediately appears in the "Org attiva" switcher.
      window.location.href = `/piattaforma/org/${data.id}`;
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setCreating(false); }
  };

  const toggleUser = async (u) => {
    try { await api.patch(`/platform/users/${u.user_id}`, { active: !u.active }); toast.success(u.active ? "Account disabilitato" : "Account riattivato"); loadUsers(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const confirmDeleteUser = async () => {
    if (!delUser) return;
    setWorking(true);
    try { await api.delete(`/platform/users/${delUser.user_id}`); toast.success("Account eliminato definitivamente"); setDelUser(null); loadAll(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setWorking(false); }
  };

  return (
    <div className="animate-fade-up" data-testid="platform-page">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-3xl font-bold text-slate-900">Piattaforma CRMEvent</h1>
          <p className="text-slate-500 mt-1 mb-6">Panoramica delle organizzazioni registrate e dello stato degli abbonamenti.</p>
        </div>
        <Button onClick={() => setShowCreate(true)} data-testid="new-org-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Plus className="w-4 h-4 mr-1.5" />Nuova organizzazione</Button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-8">
          <Stat icon={Building2} label="Organizzazioni" value={stats.organizations} tone="tiffany" />
          <Stat icon={CalendarDays} label="In trial" value={stats.trial} tone="blue" />
          <Stat icon={Users} label="Attive" value={stats.active} tone="green" />
          <Stat icon={Users} label="Scadute" value={stats.expired} tone="red" />
          <Stat icon={Wallet} label="MRR (€)" value={stats.mrr} />
          <Stat icon={TrendingUp} label="ARR (€)" value={stats.arr} />
          <Stat icon={Inbox} label="Lead" value={stats.leads} />
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl p-5 mb-8 flex items-center gap-4" data-testid="fic-card">
        <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><ReceiptText className="w-5 h-5" /></div>
        <div className="min-w-0">
          <div className="font-semibold text-slate-800">Fatturazione elettronica · Fatture in Cloud</div>
          <div className="text-xs text-slate-500 mt-0.5">
            {!fic ? "…" : !fic.configured ? "Non configurato: imposta FIC_CLIENT_ID / SECRET / REDIRECT_URI nei Secrets" : fic.connected ? <>Collegato · company_id {fic.company_id || "—"}</> : "Configurato — non ancora collegato"}
          </div>
        </div>
        <div className="ml-auto">
          {fic && fic.configured && (fic.connected
            ? <Button variant="outline" size="sm" onClick={disconnectFic} data-testid="fic-disconnect"><Unlink className="w-4 h-4 mr-1.5" />Scollega</Button>
            : <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={connectFic} data-testid="fic-connect"><Link2 className="w-4 h-4 mr-1.5" />Collega Fatture in Cloud</Button>)}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5 mb-8" data-testid="brevo-card">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><Mail className="w-5 h-5" /></div>
          <div className="min-w-0">
            <div className="font-semibold text-slate-800">Email marketing · Brevo</div>
            <div className="text-xs text-slate-500 mt-0.5">
              {!brevo ? "Verifica la connessione API a Brevo (nessuna email viene inviata)."
                : brevo.valid ? <span className="text-emerald-600 font-medium">Connesso · chiave API valida (HTTP {brevo.status})</span>
                : <span className="text-amber-600 font-medium">{brevo.message}{brevo.status ? ` (HTTP ${brevo.status})` : ""}</span>}
            </div>
          </div>
          <div className="ml-auto flex gap-2">
            <Button size="sm" variant="outline" onClick={checkBrevo} disabled={brevoBusy} data-testid="brevo-check-btn"><Link2 className="w-4 h-4 mr-1.5" />{brevoBusy ? "Verifica…" : "Verifica connessione Brevo"}</Button>
            <Button size="sm" variant="outline" onClick={loadSenders} disabled={sendersBusy} data-testid="brevo-senders-btn"><Users className="w-4 h-4 mr-1.5" />{sendersBusy ? "Carico…" : "Carica mittenti"}</Button>
          </div>
        </div>

        {senders !== null && (
          <div className="mt-4 border-t border-slate-100 pt-4" data-testid="brevo-senders-section">
            <div className="text-sm font-semibold text-slate-800 mb-2">Mittenti configurati su Brevo</div>
            {senders.length === 0 ? (
              <div className="text-xs text-slate-500">Nessun mittente trovato. Configura e verifica un mittente <span className="font-medium">CRMEvent</span> con casella <span className="font-medium">@crmevent.it</span> nel pannello Brevo (Mittenti, domini e IP dedicati).</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid="brevo-senders-table">
                  <thead><tr className="border-b border-slate-200 text-left text-slate-500">
                    <th className="py-2 px-3 font-semibold">Nome</th><th className="py-2 px-3 font-semibold">Email</th><th className="py-2 px-3 font-semibold">Dominio</th><th className="py-2 px-3 font-semibold">Stato</th>
                  </tr></thead>
                  <tbody>
                    {senders.map((s) => (
                      <tr key={s.id} className="border-b border-slate-100" data-testid={`brevo-sender-row-${s.id}`}>
                        <td className="py-2 px-3 text-slate-800">{s.name || "—"}</td>
                        <td className="py-2 px-3 text-slate-600">{s.email}</td>
                        <td className="py-2 px-3 text-slate-600">{s.domain || "—"}</td>
                        <td className="py-2 px-3">{s.active ? <span className="text-emerald-600 font-medium">Verificato</span> : <span className="text-amber-600 font-medium">Non verificato</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {senders.some((s) => s.active) && (
              <div className="mt-5 border-t border-slate-100 pt-4" data-testid="brevo-test-section">
                <div className="text-sm font-semibold text-slate-800 mb-2">Invia email di test</div>
                <div className="text-xs text-slate-500 mb-3">Oggetto: <span className="font-medium">CRMEvent · Test collegamento Brevo</span>. Nessuna CTA commerciale, nessuna automazione.</div>
                <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                  <div className="sm:w-64">
                    <label className="text-xs text-slate-500">Mittente verificato</label>
                    <select className="w-full mt-1 border border-slate-200 rounded-md px-2 py-2 text-sm bg-white" value={testSender} onChange={(e) => setTestSender(e.target.value)} data-testid="brevo-test-sender-select">
                      {senders.filter((s) => s.active).map((s) => <option key={s.id} value={s.email}>{s.name ? `${s.name} — ${s.email}` : s.email}</option>)}
                    </select>
                  </div>
                  <div className="flex-1">
                    <label className="text-xs text-slate-500">Destinatario</label>
                    <Input type="email" placeholder="destinatario@esempio.it" value={testTo} onChange={(e) => setTestTo(e.target.value)} className="mt-1" data-testid="brevo-test-to-input" />
                  </div>
                  <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={sendTestEmail} disabled={testBusy} data-testid="brevo-send-test-btn"><Mail className="w-4 h-4 mr-1.5" />{testBusy ? "Invio…" : "Invia email di test"}</Button>
                </div>

                {testResult && (
                  <div className={`mt-3 rounded-lg border p-3 text-xs ${testResult.success ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`} data-testid="brevo-test-result">
                    <div className={`font-semibold ${testResult.success ? "text-emerald-700" : "text-red-700"}`}>{testResult.success ? "Invio riuscito" : "Invio fallito"}</div>
                    <div className="text-slate-600 mt-1 space-y-0.5">
                      <div>Esito: {testResult.message}</div>
                      {testResult.status != null && <div>HTTP status: {testResult.status}</div>}
                      {testResult.messageId && <div>messageId: <span className="font-mono">{testResult.messageId}</span></div>}
                      <div>Timestamp: {testResult.timestamp}</div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Organizzazioni</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2.5 px-4 font-semibold">Nome</th><th className="py-2.5 px-4 font-semibold">Tipo</th><th className="py-2.5 px-4 font-semibold">Stato</th>
              <th className="py-2.5 px-4 font-semibold text-center">Utenti</th><th className="py-2.5 px-4 font-semibold text-center">Eventi</th><th className="py-2.5 px-4 font-semibold">Creazione</th>
            </tr></thead>
            <tbody>
              {orgs.length === 0 ? (
                <tr><td colSpan={6} className="py-8 text-center text-slate-400">Nessuna organizzazione registrata.</td></tr>
              ) : orgs.map((o) => (
                <tr key={o.id} onClick={() => nav(`/piattaforma/org/${o.id}`)} className="border-b border-slate-100 cursor-pointer hover:bg-slate-50" data-testid={`platform-org-${o.id}`}>
                  <td className="py-2.5 px-4 font-medium text-slate-800">{o.nome}</td>
                  <td className="py-2.5 px-4"><StatusBadge color={TYPE_COLOR[o.type] || "gray"}>{TYPE_LABEL[o.type] || o.type}</StatusBadge></td>
                  <td className="py-2.5 px-4"><StatusBadge color={o.status === "active" ? "green" : "red"}>{o.status === "active" ? "Attiva" : "Disattivata"}</StatusBadge></td>
                  <td className="py-2.5 px-4 text-center text-slate-600">{o.members}</td>
                  <td className="py-2.5 px-4 text-center text-slate-600">{o.events}</td>
                  <td className="py-2.5 px-4 text-slate-500">{o.created_at ? new Date(o.created_at).toLocaleDateString("it-IT") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden mt-8" data-testid="platform-accounts">
        <div className="px-5 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800 flex items-center gap-2"><Users className="w-4 h-4" />Account utenti <span className="text-slate-400 font-normal">({users.length})</span></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2.5 px-4 font-semibold">Nome</th><th className="py-2.5 px-4 font-semibold">Email</th>
              <th className="py-2.5 px-4 font-semibold">Organizzazione</th><th className="py-2.5 px-4 font-semibold">Ruolo</th>
              <th className="py-2.5 px-4 font-semibold">Stato</th><th className="py-2.5 px-4 font-semibold">Creazione</th>
              <th className="py-2.5 px-4 font-semibold">Ultimo accesso</th><th className="py-2.5 px-4 font-semibold text-right">Azioni</th>
            </tr></thead>
            <tbody>
              {users.length === 0 ? (
                <tr><td colSpan={8} className="py-8 text-center text-slate-400">Nessun account registrato.</td></tr>
              ) : users.map((u) => (
                <tr key={u.user_id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`platform-user-${u.user_id}`}>
                  <td className="py-2.5 px-4 font-medium text-slate-800">{u.name || "—"}</td>
                  <td className="py-2.5 px-4 text-slate-600">{u.email}</td>
                  <td className="py-2.5 px-4 text-slate-600">{u.primary_org?.nome || (u.org_names || []).join(", ") || "—"}</td>
                  <td className="py-2.5 px-4"><StatusBadge color={u.is_superadmin ? "tiffany" : "gray"}>{u.role_label}</StatusBadge></td>
                  <td className="py-2.5 px-4"><StatusBadge color={u.active ? "green" : "red"}>{u.active ? "Attivo" : "Disabilitato"}</StatusBadge></td>
                  <td className="py-2.5 px-4 text-slate-500">{u.created_at ? new Date(u.created_at).toLocaleDateString("it-IT") : "—"}</td>
                  <td className="py-2.5 px-4 text-slate-500">{u.last_login_at ? new Date(u.last_login_at).toLocaleDateString("it-IT") : "—"}</td>
                  <td className="py-2.5 px-4 text-right whitespace-nowrap">
                    {u.is_superadmin ? <span className="text-xs text-slate-400">—</span> : (
                      <>
                        <Button variant="outline" size="sm" className="mr-1" onClick={() => toggleUser(u)} data-testid={`user-toggle-${u.user_id}`}><Power className="w-4 h-4 mr-1" />{u.active ? "Disabilita" : "Riattiva"}</Button>
                        <Button variant="outline" size="sm" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => setDelUser(u)} data-testid={`user-delete-${u.user_id}`}><Trash2 className="w-4 h-4" /></Button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <PaymentsCredits />
      <LegacySubscriptions subs={subs} />

      {delUser && (
        <div className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-4" onClick={() => !working && setDelUser(null)}>
          <div className="w-full max-w-md bg-white rounded-xl p-6 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="user-delete-dialog">
            <div className="flex items-center gap-2 text-red-600"><ShieldAlert className="w-6 h-6" /><h2 className="text-lg font-bold text-slate-900">Elimina account definitivamente</h2></div>
            <p className="text-sm text-slate-600">Stai per eliminare definitivamente l'account <span className="font-semibold text-slate-900">{delUser.email}</span>. L'utente non potrà più accedere a CRMEvent. I dati appartenenti all'organizzazione non verranno eliminati.</p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setDelUser(null)} disabled={working} data-testid="user-delete-cancel">Annulla</Button>
              <Button onClick={confirmDeleteUser} disabled={working} className="bg-red-600 hover:bg-red-700 text-white" data-testid="user-delete-confirm">{working ? "Eliminazione…" : "Elimina definitivamente"}</Button>
            </div>
          </div>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-[120] bg-black/40 flex items-center justify-center p-4" onClick={() => !creating && setShowCreate(false)}>
          <div className="w-full max-w-md bg-white rounded-xl p-6 space-y-4" onClick={(e) => e.stopPropagation()} data-testid="new-org-dialog">
            <div className="flex items-center justify-between"><h2 className="text-lg font-bold text-slate-900">Nuova organizzazione</h2><button onClick={() => setShowCreate(false)}><X className="w-5 h-5 text-slate-400" /></button></div>
            <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Nome organizzazione</label><Input value={nf.nome} onChange={(e) => setNf((f) => ({ ...f, nome: e.target.value }))} placeholder="Es. Nova Events" data-testid="new-org-nome" /></div>
            <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Tipo</label>
              <select className="h-10 px-3 w-full rounded-lg border border-slate-200 text-sm" value={nf.type} onChange={(e) => setNf((f) => ({ ...f, type: e.target.value }))} data-testid="new-org-type">
                <option value="cliente">Cliente (trial + abbonamento)</option><option value="interna">Interna (nessun abbonamento)</option><option value="test">Test</option>
              </select></div>
            <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Stato</label>
              <select className="h-10 px-3 w-full rounded-lg border border-slate-200 text-sm" value={nf.status} onChange={(e) => setNf((f) => ({ ...f, status: e.target.value }))} data-testid="new-org-status">
                <option value="active">Attiva</option><option value="disabled">Disattivata</option>
              </select></div>
            <Button onClick={createOrg} disabled={creating} data-testid="new-org-create" className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">{creating ? "Creazione…" : "Crea organizzazione"}</Button>
          </div>
        </div>
      )}
    </div>
  );
}
