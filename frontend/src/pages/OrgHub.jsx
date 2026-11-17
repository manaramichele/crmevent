import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, SectionCard } from "@/components/crm";
import { Store } from "lucide-react";
import { ModuleCard } from "@/components/modules/ModuleCard";
import MyServices from "@/components/MyServices";
import OrgUsers from "@/components/OrgUsers";

function OrgModules() {
  const [mods, setMods] = useState(null); const [err, setErr] = useState("");
  useEffect(() => { api.get("/org/modules").then(({ data }) => setMods(data.modules)).catch((e) => setErr(formatApiError(e.response?.data?.detail))); }, []);
  if (err) return <p className="text-sm text-slate-500" data-testid="org-modules-error">{err}</p>;
  if (!mods) return <div className="py-10 text-center text-slate-400">Caricamento…</div>;
  const active = mods.filter((m) => m.active); const avail = mods.filter((m) => !m.active);
  return (
    <div className="space-y-8" data-testid="org-modules">
      <section className="space-y-3"><h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Moduli attivi ({active.length})</h2>
        {active.length ? active.map((m) => <ModuleCard key={m.key} m={m} showOpen />) : <p className="text-sm text-slate-400" data-testid="org-modules-active-empty">Nessun modulo attivo.</p>}</section>
      <section className="space-y-3"><div className="flex items-center justify-between gap-3 flex-wrap"><h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Moduli disponibili ({avail.length})</h2>
        <Link to="/marketplace" className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full bg-[#0ABAB5] text-slate-900 text-sm font-semibold hover:bg-[#09A8A3]" data-testid="org-modules-marketplace"><Store className="w-4 h-4" />Vai al Marketplace</Link></div>
        {avail.length ? avail.map((m) => <ModuleCard key={m.key} m={m} />) : <p className="text-sm text-slate-400">Tutti i moduli sono attivi.</p>}</section>
      <MyServices />
    </div>
  );
}

const PAGES = {
  moduli: { title: "Moduli e Attivazioni", subtitle: "Moduli attivi, inclusi nel tuo abbonamento e disponibili nel Marketplace" },
  utenti: { title: "Utenti e Permessi", subtitle: "Utenti, ruoli, permessi, inviti e accessi dell'organizzazione" },
};

export default function OrgHub({ section }) {
  const { user } = useAuth();
  const isSuper = user?.role === "superadmin";
  const orgId = isSuper ? localStorage.getItem("acting_org_id") : (user?.active_org_id || user?.org_id);
  const p = PAGES[section];
  return (
    <div className="animate-fade-up space-y-6 max-w-6xl" data-testid={`org-hub-${section}`}>
      <div><div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1" data-testid="org-hub-breadcrumb">Organizzazione · {p.title}</div><PageHeader title={p.title} subtitle={p.subtitle} /></div>
      {section === "moduli" ? <OrgModules /> : (
        <SectionCard title="Utenti e Permessi">
          {orgId ? <OrgUsers orgId={orgId} /> : <p className="text-sm text-slate-500" data-testid="org-users-no-org">Seleziona un'organizzazione per gestire utenti e accessi.</p>}
        </SectionCard>
      )}
    </div>
  );
}
