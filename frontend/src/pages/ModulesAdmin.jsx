import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ArrowLeft, ExternalLink } from "lucide-react";
import OrgModulesAdmin from "@/components/modules/OrgModulesAdmin";
import { ConfigCard } from "@/pages/AddonAdmin";

const MODS = [["planner", "Event Planner"], ["eventmap", "Event Map"], ["controlroom", "Control Room"]];
const FILTERS = [["", "Tutte"], ["planner", "Con Event Planner"], ["eventmap", "Con Event Map"], ["controlroom", "Con Control Room"], ["disabled", "Con moduli disattivati"]];

function Cell({ m, k }) {
  const l = m.limits || {};
  const detail = k === "controlroom" ? `${l.events_active || 0} eventi` : `${l.included_used ?? 0}/${l.included ?? 0} incl. · ${l.purchased || 0} acq. · ${l.granted || 0} conc.${k === "eventmap" ? ` · video ${l.videos_used || 0}/${l.videos_total || 0}` : ""}`;
  const badge = m.disabled ? "bg-red-50 text-red-700" : m.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500";
  return (
    <td className="px-3 py-2 align-top">
      <span className={`inline-block text-[11px] font-semibold rounded-full px-2 py-0.5 ${badge}`}>{m.disabled ? "Disattivato" : m.active ? "Attivo" : "Non attivo"}</span>
      <div className="text-xs text-slate-500 mt-1">{detail}</div>
      {m.expires_at && <div className="text-[11px] text-amber-700">scad. {new Date(m.expires_at).toLocaleDateString("it-IT")}</div>}
    </td>
  );
}

function OrgTable({ rows, onOpen }) {
  const [q, setQ] = useState(""); const [f, setF] = useState("");
  const list = rows.filter((r) => (!q || (r.nome || "").toLowerCase().includes(q.toLowerCase()))
    && (!f || (f === "disabled" ? Object.values(r.modules).some((m) => m.disabled) : r.modules[f]?.active)));
  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca organizzazione" className="sm:max-w-sm" data-testid="modules-admin-search" />
        <select value={f} onChange={(e) => setF(e.target.value)} className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" data-testid="modules-admin-filter">
          {FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <span className="text-xs text-slate-500 self-center" data-testid="modules-admin-count">{list.length} organizzazioni</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm min-w-[760px]" data-testid="modules-admin-table">
          <thead className="bg-slate-50 text-xs text-slate-500 text-left"><tr><th className="px-3 py-2">Organizzazione</th><th className="px-3 py-2">Piano</th>{MODS.map(([k, l]) => <th key={k} className="px-3 py-2">{l}</th>)}<th /></tr></thead>
          <tbody>{list.map((r) => (
            <tr key={r.id} className="border-t border-slate-100" data-testid={`modules-admin-row-${r.id}`}>
              <td className="px-3 py-2 font-medium align-top">{r.nome}<div className="text-[11px] text-slate-400 capitalize">{r.type}</div></td>
              <td className="px-3 py-2 align-top">{r.plan || "—"}</td>
              {MODS.map(([k]) => <Cell key={k} k={k} m={r.modules[k] || {}} />)}
              <td className="px-3 py-2 align-top"><Button size="sm" variant="outline" onClick={() => onOpen(r.id)} data-testid={`modules-admin-manage-${r.id}`}>Gestisci</Button></td>
            </tr>))}
            {!list.length && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">Nessuna organizzazione trovata.</td></tr>}</tbody>
        </table>
      </div>
    </div>
  );
}

export default function ModulesAdmin() {
  const [rows, setRows] = useState(null);
  const [params, setParams] = useSearchParams();
  const orgId = params.get("org");
  const tab = params.get("tab") === "config" ? "config" : "orgs";
  const load = useCallback(() => api.get("/platform/modules/orgs").then(({ data }) => setRows(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), []);
  useEffect(() => { load(); }, [load]);
  const go = (p) => setParams(p, { replace: false });
  const org = rows?.find((r) => r.id === orgId);
  return (
    <div className="animate-fade-up space-y-6" data-testid="modules-admin-page">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1" data-testid="modules-admin-breadcrumb">Dashboard piattaforma · Moduli e Attivazioni{org ? ` · ${org.nome}` : ""}</div>
        <PageHeader title="Moduli e Attivazioni" subtitle="Moduli attivi di tutte le organizzazioni, concessioni gratuite, limiti, scadenze e storico. Nessuna modifica crea pagamenti Stripe." />
      </div>
      {orgId ? (
        <div className="space-y-4" data-testid="modules-admin-org">
          <div className="flex items-center gap-3 flex-wrap">
            <Button variant="outline" size="sm" onClick={() => { go({}); load(); }} data-testid="modules-admin-back"><ArrowLeft className="w-4 h-4 mr-1.5" />Tutte le organizzazioni</Button>
            <h2 className="font-semibold text-slate-900 text-lg">{org?.nome || "…"}</h2>
            <Link to={`/piattaforma/org/${orgId}?tab=moduli`} className="ml-auto inline-flex items-center gap-1 text-sm font-semibold text-tiffany-active" data-testid="modules-admin-open-org"><ExternalLink className="w-4 h-4" />Apri scheda organizzazione</Link>
          </div>
          {org && <OrgModulesAdmin org={org} />}
        </div>
      ) : (
        <>
          <div className="flex gap-1 border-b border-slate-200">
            {[["orgs", "Organizzazioni"], ["config", "Configurazione globale"]].map(([k, l]) => (
              <button key={k} type="button" onClick={() => go(k === "config" ? { tab: "config" } : {})} className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === k ? "border-[#0ABAB5] text-slate-900" : "border-transparent text-slate-500"}`} data-testid={`modules-admin-tab-${k}`}>{l}</button>))}
          </div>
          {tab === "config" ? <ConfigCard onSaved={load} /> : !rows ? <p className="text-sm text-slate-400">Caricamento…</p> : <OrgTable rows={rows} onOpen={(id) => go({ org: id })} />}
        </>
      )}
    </div>
  );
}
