import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { X, UserCheck, Link2, Mail, Building2, Workflow } from "lucide-react";

const STATO = { nuovo: "blue", da_contattare: "orange", contattato: "tiffany", demo_fissata: "tiffany", interessato: "green", cliente: "green", non_interessato: "red" };
const STATO_LABEL = { nuovo: "Nuovo", da_contattare: "Da contattare", contattato: "Contattato", demo_fissata: "Demo fissata", interessato: "Interessato", cliente: "Cliente", non_interessato: "Non interessato" };
const ROLE_OPTS = [{ value: "admin_org", label: "Admin Organizzazione" }, { value: "user", label: "Utente" }];
const FUNNEL_ST = { active: { label: "attivo", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" }, stopped: { label: "interrotto", cls: "text-amber-700 bg-amber-50 border-amber-200" }, completed: { label: "completato", cls: "text-slate-600 bg-slate-50 border-slate-200" } };
const STEP_ST = { scheduled: "Programmata", sent: "Inviata", failed: "Fallita", canceled: "Annullata", skipped: "Saltata" };
const STOP_LABEL = { trial_started: "prova gratuita avviata", cliente: "diventato cliente", unsubscribed: "disiscritto", hard_bounce: "hard bounce", spam: "spam", lead_deleted: "lead eliminato" };
const inputCls = "h-10 px-3 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-tiffany focus:ring-2 focus:ring-tiffany/30";
const ORIGINE = { demo_sito: { label: "Demo sito", color: "tiffany" }, manuale: { label: "Inserimento manuale", color: "gray" }, lead_finder: { label: "Lead Finder", color: "blue" }, area_personale: { label: "Area personale", color: "gray" } };

export default function Leads({ embedded = false }) {
  const [leads, setLeads] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [sel, setSel] = useState(null); // lead detail {lead, account, linked}
  const [assign, setAssign] = useState({ org_id: "", role: "user" });

  const load = useCallback(() => api.get("/leads").then(({ data }) => setLeads(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), []);
  useEffect(() => { load(); api.get("/platform/organizations").then(({ data }) => setOrgs(data)).catch(() => {}); }, [load]);

  const openLead = async (id) => {
    try { const { data } = await api.get(`/leads/${id}`); setSel(data); setAssign({ org_id: orgs[0]?.id || "", role: "user" }); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const refresh = async () => { if (sel) await openLead(sel.lead.id); load(); };

  const setStato = async (stato) => { try { await api.put(`/leads/${sel.lead.id}`, { stato }); toast.success("Stato aggiornato"); refresh(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const linkAccount = async () => { try { await api.post(`/leads/${sel.lead.id}/link-account`); toast.success("Account collegato"); refresh(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const assignOrg = async () => { if (!assign.org_id) return toast.error("Seleziona un'organizzazione"); try { await api.post(`/leads/${sel.lead.id}/assign-org`, assign); toast.success("Utente assegnato all'organizzazione"); refresh(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const inviteToOrg = async () => { if (!assign.org_id) return toast.error("Seleziona un'organizzazione"); try { const { data } = await api.post(`/leads/${sel.lead.id}/invite`, assign); toast[data.email_sent ? "success" : "warning"](data.email_sent ? "Invito inviato" : "Invito creato (email non inviata)"); refresh(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

  return (
    <div className="animate-fade-up" data-testid="leads-page">
      {!embedded && <>
        <h1 className="font-display text-3xl font-bold text-slate-900">Lead</h1>
        <p className="text-slate-500 mt-1 mb-6">Richieste demo e pipeline commerciale. Un Lead è un contatto commerciale, distinto da Utente e Organizzazione.</p>
      </>}

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
            <th className="text-left px-4 py-2.5">Nome</th><th className="text-left px-4 py-2.5">Organizzazione</th><th className="text-left px-4 py-2.5">Email</th><th className="text-left px-4 py-2.5">Origine</th><th className="text-left px-4 py-2.5">Data</th><th className="text-left px-4 py-2.5">Stato</th>
          </tr></thead>
          <tbody>
            {leads.length === 0 ? <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Nessun lead.</td></tr> :
              leads.map((l) => (
                <tr key={l.id} onClick={() => openLead(l.id)} className="border-t border-slate-100 cursor-pointer hover:bg-slate-50" data-testid={`lead-row-${l.id}`}>
                  <td className="px-4 py-2.5 font-medium text-slate-800">{l.nome} {l.cognome || ""}</td>
                  <td className="px-4 py-2.5 text-slate-600">{l.organizzazione || "—"}</td>
                  <td className="px-4 py-2.5 text-slate-600">{l.email}</td>
                  <td className="px-4 py-2.5"><StatusBadge color={(ORIGINE[l.origine] || ORIGINE.manuale).color}>{(ORIGINE[l.origine] || ORIGINE.manuale).label}</StatusBadge></td>
                  <td className="px-4 py-2.5 text-slate-500">{(l.created_at || "").slice(0, 10)}</td>
                  <td className="px-4 py-2.5"><StatusBadge color={STATO[l.stato] || "gray"}>{STATO_LABEL[l.stato] || l.stato}</StatusBadge></td>
                </tr>
              ))}
          </tbody>
        </table></div>
      </div>

      {sel && (
        <div className="fixed inset-0 z-[120] bg-black/40 flex justify-end" onClick={() => setSel(null)}>
          <div className="w-full max-w-md h-full bg-white overflow-y-auto p-6 space-y-5" onClick={(e) => e.stopPropagation()} data-testid="lead-detail">
            <div className="flex items-center justify-between"><h2 className="text-lg font-bold text-slate-900">{sel.lead.nome} {sel.lead.cognome || ""}</h2><button onClick={() => setSel(null)}><X className="w-5 h-5 text-slate-400" /></button></div>
            <div className="text-sm text-slate-600 space-y-1">
              <div><span className="text-slate-400">Email:</span> {sel.lead.email}</div>
              {sel.lead.organizzazione && <div><span className="text-slate-400">Organizzazione (lead):</span> {sel.lead.organizzazione}</div>}
              <div><span className="text-slate-400">Origine:</span> {(ORIGINE[sel.lead.origine] || ORIGINE.manuale).label}</div>
              {sel.lead.telefono && <div><span className="text-slate-400">Telefono:</span> {sel.lead.telefono}</div>}
            </div>
            <div className="space-y-1.5"><label className="text-sm font-medium text-slate-600">Stato commerciale</label>
              <select className={`${inputCls} w-full`} value={sel.lead.stato} onChange={(e) => setStato(e.target.value)} data-testid="lead-stato">{Object.keys(STATO_LABEL).map((v) => <option key={v} value={v}>{STATO_LABEL[v]}</option>)}</select>
            </div>

            {sel.account ? (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 space-y-2" data-testid="lead-account-found">
                <div className="flex items-center gap-2 text-emerald-800 font-semibold text-sm"><UserCheck className="w-4 h-4" />Account CRMEvent trovato</div>
                <div className="text-sm text-slate-700">{sel.account.name} · {sel.account.email} · <span className="text-slate-500">{sel.account.active ? "attivo" : "disabilitato"}</span></div>
                {sel.account.organizations?.length > 0 && (
                  <div className="text-xs text-slate-600">Organizzazioni: {sel.account.organizations.map((o) => `${o.nome} (${o.role_label})`).join(", ")}</div>
                )}
                {!sel.linked && <Button size="sm" variant="outline" onClick={linkAccount} data-testid="lead-link-account"><Link2 className="w-4 h-4 mr-1.5" />Collega account al lead</Button>}
                {sel.linked && <div className="text-xs text-emerald-700">✓ Account collegato al lead</div>}
              </div>
            ) : (
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500" data-testid="lead-no-account">Nessun account CRMEvent con questa email. Puoi invitare questa persona in un'organizzazione.</div>
            )}

            <div className="rounded-lg border border-slate-200 p-4 space-y-2" data-testid="lead-funnel">
              <div className="flex items-center gap-2 text-slate-800 font-semibold text-sm"><Workflow className="w-4 h-4" />Funnel Demo email</div>
              {!sel.funnel ? (
                <div className="text-xs text-slate-500">Nessun invio automatico per questo lead.</div>
              ) : (
                <>
                  <div className="text-xs">
                    <span className={`inline-block px-2 py-0.5 rounded-full border font-medium ${(FUNNEL_ST[sel.funnel.status] || FUNNEL_ST.completed).cls}`}>Funnel {(FUNNEL_ST[sel.funnel.status] || {}).label || sel.funnel.status}</span>
                    {sel.funnel.stop_reason && <span className="text-slate-500 ml-2">— {STOP_LABEL[sel.funnel.stop_reason] || sel.funnel.stop_reason}</span>}
                  </div>
                  <div className="space-y-1">
                    {sel.funnel.steps.map((s) => (
                      <div key={s.step} className="flex items-center justify-between text-xs" data-testid={`lead-funnel-step-${s.step}`}>
                        <span className="text-slate-600">Email {s.step}</span>
                        <span className={s.status === "sent" ? "text-emerald-600" : s.status === "failed" ? "text-red-600" : "text-slate-500"}>
                          {STEP_ST[s.status] || s.status}
                          {s.status === "scheduled" && s.scheduled_at ? ` · ${s.scheduled_at.slice(0, 10)}` : ""}
                          {s.status === "sent" && s.sent_at ? ` · ${s.sent_at.slice(0, 10)}` : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div className="rounded-lg border border-slate-200 p-4 space-y-3">
              <div className="flex items-center gap-2 text-slate-800 font-semibold text-sm"><Building2 className="w-4 h-4" />Assegna a organizzazione</div>
              <select className={`${inputCls} w-full`} value={assign.org_id} onChange={(e) => setAssign((a) => ({ ...a, org_id: e.target.value }))} data-testid="lead-assign-org">
                <option value="">Seleziona organizzazione…</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
              </select>
              <select className={`${inputCls} w-full`} value={assign.role} onChange={(e) => setAssign((a) => ({ ...a, role: e.target.value }))} data-testid="lead-assign-role">{ROLE_OPTS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}</select>
              {sel.account ? (
                <Button onClick={assignOrg} data-testid="lead-assign-btn" className="w-full bg-slate-900 hover:bg-slate-800 text-white">Assegna a organizzazione</Button>
              ) : (
                <Button onClick={inviteToOrg} data-testid="lead-invite-btn" className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Mail className="w-4 h-4 mr-1.5" />Invita in CRMEvent</Button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
