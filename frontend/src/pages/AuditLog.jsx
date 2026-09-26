import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { ScrollText, Filter, X } from "lucide-react";

const ACTION_COLOR = { org_access: "tiffany", org_switch: "orange", org_created: "green", org_updated: "blue", member_added: "green", member_removed: "red", member_role_changed: "orange", member_enabled: "green", member_disabled: "red", invite_sent: "tiffany", invite_resent: "tiffany", invite_revoked: "red", invite_accepted: "green", lead_linked: "blue" };

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

export default function AuditLog() {
  const [items, setItems] = useState([]);
  const [actors, setActors] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ org_id: "", actor_user_id: "", date_from: "", date_to: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const { data } = await api.get("/platform/audit", { params });
      setItems(data.items);
      setActors(data.actors);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get("/platform/organizations").then(({ data }) => setOrgs(data)).catch(() => {}); }, []);

  const setF = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const clearFilters = () => setFilters({ org_id: "", actor_user_id: "", date_from: "", date_to: "" });
  const hasFilters = Object.values(filters).some(Boolean);

  const inputCls = "h-10 px-3 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 transition-all";

  return (
    <div className="space-y-6" data-testid="audit-log-page">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center"><ScrollText className="w-5 h-5" /></div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Audit Log</h1>
          <p className="text-sm text-slate-500">Registro degli accessi e delle operazioni del Super Admin. Sola lettura, non modificabile.</p>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3 text-sm font-medium text-slate-600"><Filter className="w-4 h-4" />Filtri</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <select data-testid="audit-filter-org" className={inputCls} value={filters.org_id} onChange={(e) => setF("org_id", e.target.value)}>
            <option value="">Tutte le organizzazioni</option>
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
          </select>
          <select data-testid="audit-filter-actor" className={inputCls} value={filters.actor_user_id} onChange={(e) => setF("actor_user_id", e.target.value)}>
            <option value="">Tutti i Super Admin</option>
            {actors.map((a) => <option key={a.user_id} value={a.user_id}>{a.name || a.email}</option>)}
          </select>
          <input data-testid="audit-filter-from" type="date" className={inputCls} value={filters.date_from} onChange={(e) => setF("date_from", e.target.value)} />
          <input data-testid="audit-filter-to" type="date" className={inputCls} value={filters.date_to} onChange={(e) => setF("date_to", e.target.value)} />
          {hasFilters && (
            <Button variant="outline" onClick={clearFilters} data-testid="audit-clear-filters" className="h-10">
              <X className="w-4 h-4 mr-1" />Azzera
            </Button>
          )}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="audit-table">
            <thead>
              <tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
                <th className="text-left font-semibold px-4 py-3">Data/Ora</th>
                <th className="text-left font-semibold px-4 py-3">Super Admin</th>
                <th className="text-left font-semibold px-4 py-3">Organizzazione</th>
                <th className="text-left font-semibold px-4 py-3">Azione</th>
                <th className="text-left font-semibold px-4 py-3">Interessato</th>
                <th className="text-left font-semibold px-4 py-3">Dettaglio</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400">Caricamento…</td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-slate-400" data-testid="audit-empty">Nessuna voce nel registro.</td></tr>
              ) : items.map((it) => (
                <tr key={it.id} className="border-t border-slate-100 hover:bg-slate-50/60" data-testid={`audit-row-${it.id}`}>
                  <td className="px-4 py-3 text-slate-700 whitespace-nowrap">{fmtDate(it.created_at)}</td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{it.actor_name || "—"}</div>
                    <div className="text-xs text-slate-400">{it.actor_email}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {it.org_name || "—"}
                    {it.meta?.previous_org_name && (
                      <div className="text-xs text-slate-400">da: {it.meta.previous_org_name}</div>
                    )}
                  </td>
                  <td className="px-4 py-3"><StatusBadge color={ACTION_COLOR[it.action] || "gray"}>{it.action_label}</StatusBadge></td>
                  <td className="px-4 py-3 text-slate-600">{it.target_name || it.target_email || "—"}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs max-w-[280px]">{it.detail || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
