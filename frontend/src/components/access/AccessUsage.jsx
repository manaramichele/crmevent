import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { inputCls, fmtDate } from "./accessShared";
import { AccessKpis } from "./AccessKpis";
import { AccessUsersTable } from "./AccessUsersTable";
import { AccessUserDetail } from "./AccessUserDetail";
import { AccessReminderSettings } from "./AccessReminderSettings";
import { AccessSimulation } from "./AccessSimulation";
import { AccessEmailLog } from "./AccessEmailLog";

const SUB = [["users", "Utenti"], ["reminders", "Promemoria automatici"], ["emails", "Registro email Brevo"]];

function UsersView() {
  const { actingOrgId } = useAuth();
  const [scope, setScope] = useState("all");
  const [period, setPeriod] = useState({ date_from: "", date_to: "" });
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(null);
  const load = useCallback(async () => {
    try {
      const params = { scope, ...Object.fromEntries(Object.entries(period).filter(([, v]) => v)) };
      const { data: d } = await api.get("/platform/access/overview", { params });
      setData(d);
    } catch (e) { setData({ kpis: null, users: [] }); toast.error(formatApiError(e.response?.data?.detail)); }
  }, [scope, period, actingOrgId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <select data-testid="access-scope" className={inputCls} value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="all">Tutte le organizzazioni</option><option value="active">Solo Org attiva (tendina gialla)</option>
        </select>
        <label className="text-xs text-slate-500">Sessioni dal<input type="date" data-testid="access-period-from" className={`${inputCls} block`} value={period.date_from} onChange={(e) => setPeriod((p) => ({ ...p, date_from: e.target.value }))} /></label>
        <label className="text-xs text-slate-500">al<input type="date" data-testid="access-period-to" className={`${inputCls} block`} value={period.date_to} onChange={(e) => setPeriod((p) => ({ ...p, date_to: e.target.value }))} /></label>
        {data?.monitoring_started_at && <span className="text-xs text-slate-400 pb-2" data-testid="access-monitor-start">Monitoraggio attivo dal {fmtDate(data.monitoring_started_at)}</span>}
      </div>
      <AccessKpis k={data?.kpis} />
      {data && <AccessUsersTable users={data.users} onOpen={setOpen} />}
      <AccessUserDetail userId={open} onClose={() => setOpen(null)} />
    </div>
  );
}

export function AccessUsage() {
  const [sub, setSub] = useState("users");
  return (
    <div className="space-y-5" data-testid="access-usage">
      <div className="flex flex-wrap gap-2">{SUB.map(([k, l]) => (
        <button key={k} type="button" onClick={() => setSub(k)} data-testid={`access-subtab-${k}`}
          className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${sub === k ? "bg-slate-900 text-white" : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"}`}>{l}</button>))}
      </div>
      {sub === "users" && <UsersView />}
      {sub === "reminders" && <div className="space-y-5"><AccessReminderSettings /><AccessSimulation /></div>}
      {sub === "emails" && <AccessEmailLog />}
    </div>
  );
}
