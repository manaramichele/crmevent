import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Power } from "lucide-react";
import { ModuleCard } from "@/components/modules/ModuleCard";
import { ProductPanel } from "@/pages/AddonAdmin";

function StateToggle({ orgId, m, onDone }) {
  const flip = async () => {
    if (!m.disabled && !window.confirm(`Disattivare ${m.name} per questa organizzazione? Progetti, planimetrie, video e configurazioni restano conservati.`)) return;
    try { await api.post(`/platform/orgs/${orgId}/modules/${m.key}/state`, { enabled: m.disabled }); toast.success(m.disabled ? `${m.name} riattivato` : `${m.name} disattivato · dati conservati`); onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return <Button size="sm" variant="outline" onClick={flip} data-testid={`module-toggle-${m.key}`} className={m.disabled ? "" : "text-red-600 border-red-200 hover:bg-red-50"}><Power className="w-4 h-4 mr-1.5" />{m.disabled ? "Riattiva modulo" : "Disattiva modulo"}</Button>;
}

function CrGrant({ orgId, m, events, onDone }) {
  const [sel, setSel] = useState([]); const [note, setNote] = useState("");
  const on = new Set(m.events.map((e) => e.id));
  const grant = async () => {
    try { const { data } = await api.post(`/platform/orgs/${orgId}/modules/controlroom/grant`, { event_ids: sel, note: note || null }); toast.success(`Control Room concessa su ${data.created} eventi`); setSel([]); setNote(""); onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const revoke = async (pid) => {
    if (!window.confirm("Revocare la concessione gratuita? I dati della Control Room restano conservati.")) return;
    try { await api.post(`/platform/orgs/${orgId}/modules/controlroom/${pid}/revoke`); toast.success("Concessione revocata"); onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="rounded-lg bg-slate-50 p-3 space-y-2" data-testid="cr-grant-form">
      {m.events.filter((e) => e.source === "superadmin").map((e) => (
        <div key={e.purchase_id} className="flex items-center gap-2 text-xs"><span className="flex-1">{e.nome} · concessione gratuita</span><button type="button" onClick={() => revoke(e.purchase_id)} className="text-red-600 font-semibold" data-testid={`cr-revoke-${e.purchase_id}`}>Revoca</button></div>
      ))}
      <div className="text-xs text-slate-500">Concedi gratuitamente sugli eventi (nessun pagamento, nessuna fattura):</div>
      <div className="flex flex-wrap gap-1.5">{events.filter((e) => !on.has(e.id)).map((e) => (
        <button key={e.id} type="button" onClick={() => setSel(sel.includes(e.id) ? sel.filter((x) => x !== e.id) : [...sel, e.id])} className={`px-2 py-1 rounded-full text-xs border ${sel.includes(e.id) ? "bg-[#0ABAB5] border-[#0ABAB5]" : "border-slate-200 bg-white"}`} data-testid={`cr-grant-ev-${e.id}`}>{e.nome}</button>))}
        {!events.length && <span className="text-xs text-slate-400">Nessun evento nell'organizzazione.</span>}</div>
      <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Nota interna" data-testid="cr-grant-note" />
      <Button size="sm" onClick={grant} disabled={!sel.length} className="bg-slate-900 text-white" data-testid="cr-grant-submit">Concedi gratuitamente</Button>
    </div>
  );
}

function History({ rows }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid="modules-history">
      <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Storico delle modifiche</div>
      <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider"><th className="text-left px-4 py-2">Data</th><th className="text-left px-4 py-2">Utente</th><th className="text-left px-4 py-2">Operazione</th><th className="text-left px-4 py-2">Dettaglio</th></tr></thead>
        <tbody>{!rows.length ? <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">Nessuna modifica registrata.</td></tr> : rows.map((a) => (
          <tr key={a.id} className="border-t border-slate-100"><td className="px-4 py-2 whitespace-nowrap text-slate-600">{new Date(a.created_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}</td><td className="px-4 py-2 text-slate-600">{a.actor_name || a.actor_email}</td><td className="px-4 py-2">{a.action_label}</td><td className="px-4 py-2 text-slate-500">{a.detail || "—"}</td></tr>))}</tbody>
      </table></div>
    </div>
  );
}

export default function OrgModulesAdmin({ org }) {
  const [data, setData] = useState(null); const [addon, setAddon] = useState(null); const [pk, setPk] = useState([]);
  const load = useCallback(() => {
    api.get(`/platform/orgs/${org.id}/modules`).then(({ data }) => setData(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
    api.get(`/platform/addons/orgs/${org.id}`).then(({ data }) => setAddon(data)).catch(() => {});
  }, [org.id]);
  useEffect(() => { load(); api.get("/platform/addons/config").then(({ data }) => setPk(data.eventmap.packages || [])).catch(() => {}); }, [load]);
  if (!data) return <div className="py-10 text-center text-slate-400">Caricamento…</div>;
  const active = data.modules.filter((m) => m.active); const avail = data.modules.filter((m) => !m.active);
  const events = addon?.planner?.events || [];
  return (
    <div className="space-y-8" data-testid="org-moduli-tab">
      <section className="space-y-3"><h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Moduli attivi ({active.length})</h2>
        {active.length ? active.map((m) => <ModuleCard key={m.key} m={m} />) : <p className="text-sm text-slate-400" data-testid="modules-active-empty">Nessun modulo attivo.</p>}</section>
      <section className="space-y-3"><h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Moduli disponibili ({avail.length})</h2>
        {avail.length ? avail.map((m) => <ModuleCard key={m.key} m={m} />) : <p className="text-sm text-slate-400">Tutti i moduli sono attivi.</p>}</section>
      <section className="space-y-3" data-testid="modules-manage"><h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Gestione attivazioni</h2>
        <p className="text-xs text-slate-500">Le concessioni non creano pagamenti Stripe né fatture e non modificano gli acquisti già effettuati. Disattivare un modulo blocca l'accesso ma conserva tutti i dati.</p>
        <div className="grid lg:grid-cols-3 gap-4">{data.modules.map((m) => (
          <div key={m.key} className="bg-white border border-slate-200 rounded-xl p-4 space-y-3" data-testid={`module-manage-${m.key}`}>
            <div className="flex items-center justify-between gap-2"><h3 className="font-semibold">{m.name}</h3><StateToggle orgId={org.id} m={m} onDone={load} /></div>
            {m.key === "controlroom" ? <CrGrant orgId={org.id} m={m} events={events} onDone={load} /> : addon?.[m.key] && <ProductPanel org={org} product={m.key} d={addon[m.key]} packages={pk} reload={load} />}
          </div>))}</div>
      </section>
      <History rows={data.history} />
    </div>
  );
}
