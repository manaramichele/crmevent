import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, SectionCard, PrimaryButton, StatusBadge } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { CalendarCheck2, Link2, Unplug } from "lucide-react";
import OrgUsers from "@/components/OrgUsers";

export default function Profile() {
  const { user } = useAuth();
  const isPw = user?.auth_provider === "password";
  const isSuper = user?.role === "superadmin";
  const actingOrgId = typeof window !== "undefined" ? localStorage.getItem("acting_org_id") : null;
  const canManageUsers = user?.org_role === "admin_org" || isSuper;
  const manageOrgId = isSuper ? actingOrgId : (user?.active_org_id || user?.org_id);
  const [cur, setCur] = useState(""); const [np, setNp] = useState(""); const [np2, setNp2] = useState("");
  const [cal, setCal] = useState(null);
  const [cals, setCals] = useState([]);

  const loadCal = async () => { try { const { data } = await api.get("/calendar/status"); setCal(data); if (data.connected) { try { const r = await api.get("/calendar/calendars"); setCals(r.data.calendars); } catch {} } } catch {} };
  useEffect(() => { loadCal(); }, []);

  const changePw = async (e) => {
    e.preventDefault();
    if (np !== np2) return toast.error("Le password non coincidono");
    try { await api.post("/auth/change-password", { current_password: cur, new_password: np }); toast.success("Password aggiornata"); setCur(""); setNp(""); setNp2(""); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const connect = async () => {
    try { const { data } = await api.get("/calendar/connect"); window.location.href = data.authorization_url; }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };
  const disconnect = async () => { await api.post("/calendar/disconnect"); toast.success("Google Calendar scollegato"); loadCal(); };
  const selectCal = async (id) => { await api.post("/calendar/select", { calendar_id: id }); setCal((c) => ({ ...c, calendar_id: id })); toast.success("Calendario aggiornato"); };

  return (
    <div className="animate-fade-up space-y-6 max-w-6xl">
      <PageHeader title="Profilo & Account" subtitle="Gestisci password e integrazioni" />

      <SectionCard title="Dati account">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div><div className="text-xs uppercase text-slate-400 font-medium">Nome</div><div className="text-slate-800 font-medium">{user?.name}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Email</div><div className="text-slate-800 font-medium">{user?.email}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Ruolo</div><div className="text-slate-800 font-medium capitalize">{user?.role}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Accesso</div><div className="text-slate-800 font-medium">{isPw ? "Email / Password" : "Google"}</div></div>
        </div>
      </SectionCard>

      {canManageUsers && (
        <SectionCard title="Utenti e Permessi">
          {manageOrgId ? (
            <OrgUsers orgId={manageOrgId} />
          ) : (
            <p className="text-sm text-slate-500" data-testid="org-users-no-org">Seleziona un'organizzazione per gestire utenti e accessi.</p>
          )}
        </SectionCard>
      )}

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
        {!cal ? <div className="text-sm text-slate-400">Caricamento...</div> : !cal.configured ? (
          <div className="text-sm text-amber-700 bg-amber-50 ring-1 ring-amber-200 rounded-lg p-3">
            Google Calendar non è ancora configurato dall'amministratore (mancano GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET nei Secrets).
          </div>
        ) : cal.connected ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-sm"><CalendarCheck2 className="w-5 h-5 text-emerald-600" /><span className="text-slate-700">Collegato come <b>{cal.google_email}</b></span></div>
            {cals.length > 0 && (
              <div className="max-w-xs space-y-1.5"><Label className="text-xs">Calendario selezionato</Label>
                <Select value={cal.calendar_id} onValueChange={selectCal}>
                  <SelectTrigger data-testid="calendar-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{cals.map((c) => <SelectItem key={c.id} value={c.id}>{c.summary}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <Button variant="outline" onClick={disconnect} data-testid="calendar-disconnect"><Unplug className="w-4 h-4 mr-1.5" />Disconnetti</Button>
          </div>
        ) : (
          <PrimaryButton onClick={connect} data-testid="calendar-connect"><Link2 className="w-4 h-4 mr-1.5" />Collega Google Calendar</PrimaryButton>
        )}
      </SectionCard>
    </div>
  );
}
