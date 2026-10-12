import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, SectionCard, PrimaryButton, StatusBadge } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { GoogleCalendarCard } from "@/components/GoogleCalendarCard";
import OrgUsers from "@/components/OrgUsers";
import Account from "@/pages/Account";
import { isOrgAdmin } from "@/lib/perms";
import MySubscription from "@/components/MySubscription";
import MyServices from "@/components/MyServices";
import { useSearchParams } from "react-router-dom";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export default function Profile() {
  const { user } = useAuth();
  const isPw = user?.auth_provider === "password";
  const isSuper = user?.role === "superadmin";
  const actingOrgId = typeof window !== "undefined" ? localStorage.getItem("acting_org_id") : null;
  const canManageUsers = user?.org_role === "admin_org" || isSuper;
  const manageOrgId = isSuper ? actingOrgId : (user?.active_org_id || user?.org_id);
  const [cur, setCur] = useState(""); const [np, setNp] = useState(""); const [np2, setNp2] = useState("");

  const changePw = async (e) => {
    e.preventDefault();
    if (np !== np2) return toast.error("Le password non coincidono");
    try { await api.post("/auth/change-password", { current_password: cur, new_password: np }); toast.success("Password aggiornata"); setCur(""); setNp(""); setNp2(""); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const saas = !!user?.saas?.enabled;
  const showSub = (isOrgAdmin(user) || !!user?.permissions?.subscription_manage) && !isSuper && saas;
  const [params, setParams] = useSearchParams();
  const showServices = !isSuper && !!user?.org_id && (isOrgAdmin(user) || !!user?.permissions?.marketplace_purchase);
  const tabs = ["account", ...(showSub ? ["abbonamento"] : []), ...(showServices ? ["servizi"] : []), ...(canManageUsers ? ["utenti"] : [])];
  const req = params.get("tab") === "crediti" ? "abbonamento" : params.get("tab");
  const tab = tabs.includes(req) ? req : "account";

  return (
    <div className="animate-fade-up space-y-6 max-w-6xl">
      <PageHeader title="Profilo & Account" subtitle="Il tuo account, abbonamento e fatturazione, utenti e permessi" />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabsList className="mb-4 w-full sm:w-auto overflow-x-auto justify-start h-auto flex-nowrap" data-testid="profile-tabs">
          <TabsTrigger value="account" className="h-9" data-testid="profile-tab-account">Account</TabsTrigger>
          {showSub && <TabsTrigger value="abbonamento" className="h-9" data-testid="profile-tab-abbonamento">Il mio abbonamento</TabsTrigger>}
          {showServices && <TabsTrigger value="servizi" className="h-9" data-testid="profile-tab-servizi">Servizi aggiuntivi</TabsTrigger>}
          {canManageUsers && <TabsTrigger value="utenti" className="h-9" data-testid="profile-tab-utenti">Utenti e Permessi</TabsTrigger>}
        </TabsList>
        {showSub && <TabsContent value="abbonamento" className="space-y-4"><MySubscription />{isOrgAdmin(user) && <div className="max-w-3xl"><Account embedded hideCredits /></div>}</TabsContent>}
        {showServices && <TabsContent value="servizi"><MyServices /></TabsContent>}
        {canManageUsers && <TabsContent value="utenti">
          <SectionCard title="Utenti e Permessi">
            {manageOrgId ? <OrgUsers orgId={manageOrgId} /> : <p className="text-sm text-slate-500" data-testid="org-users-no-org">Seleziona un'organizzazione per gestire utenti e accessi.</p>}
          </SectionCard>
        </TabsContent>}
        <TabsContent value="account" className="space-y-6">
      <SectionCard title="Dati account">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div><div className="text-xs uppercase text-slate-400 font-medium">Nome</div><div className="text-slate-800 font-medium">{user?.name}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Email</div><div className="text-slate-800 font-medium">{user?.email}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Ruolo</div><div className="text-slate-800 font-medium capitalize">{user?.role}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Accesso</div><div className="text-slate-800 font-medium">{isPw ? "Email / Password" : "Google"}</div></div>
        </div>
      </SectionCard>

      <SectionCard title="Cambia password">
        {isPw ? (
          <form onSubmit={changePw} className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
            <div className="space-y-1.5"><Label>Password attuale</Label><Input type="password" value={cur} onChange={(e) => setCur(e.target.value)} data-testid="cur-pw" required /></div>
            <div className="space-y-1.5"><Label>Nuova password</Label><Input type="password" value={np} onChange={(e) => setNp(e.target.value)} data-testid="new-pw" required /></div>
            <div className="space-y-1.5"><Label>Conferma</Label><Input type="password" value={np2} onChange={(e) => setNp2(e.target.value)} data-testid="new-pw2" required /></div>
            <div className="sm:col-span-3"><PrimaryButton type="submit" data-testid="change-pw-submit">Aggiorna password</PrimaryButton></div>
          </form>
        ) : (
          <div className="flex items-center gap-2 text-sm text-slate-600"><StatusBadge color="blue">Google</StatusBadge> Account collegato a Google — nessuna password locale.</div>
        )}
      </SectionCard>

      <SectionCard title="Integrazioni · Google Calendar">
        <GoogleCalendarCard />
      </SectionCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}
