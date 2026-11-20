import { useMemo, useState } from "react";
import { StatusBadge } from "@/components/crm";
import { ArrowUpDown } from "lucide-react";
import { fmtDate, fmtDur, STATUS, inputCls, ROLE_OPTIONS } from "./accessShared";

const COLS = [
  ["name", "Utente"], ["org", "Organizzazione"], ["role", "Ruolo"], ["first_login_at", "Primo accesso"],
  ["last_login_at", "Ultimo login"], ["last_activity_at", "Ultima attività"], ["login_count", "Accessi"],
  ["total_seconds", "Tempo totale"], ["days_inactive", "Giorni inattività"], ["status", "Stato"],
];

const val = (u, k) => (k === "org" ? u.org_names.join(", ") : k === "role" ? u.role_labels.join(", ") : u[k]);

function Filters({ f, setF, orgs }) {
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e.target.value }));
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
      <input data-testid="access-search" placeholder="Cerca nome o email…" className={inputCls} value={f.q} onChange={set("q")} />
      <select data-testid="access-filter-org" className={inputCls} value={f.org} onChange={set("org")}>
        <option value="">Tutte le organizzazioni</option>
        {orgs.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <select data-testid="access-filter-role" className={inputCls} value={f.role} onChange={set("role")}>
        <option value="">Tutti i ruoli</option>
        {ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
      </select>
      <select data-testid="access-filter-status" className={inputCls} value={f.status} onChange={set("status")}>
        <option value="">Tutti gli stati</option>
        <option value="online">Online</option><option value="offline">Offline</option><option value="never">Mai effettuato accesso</option>
      </select>
      <select data-testid="access-filter-inactive" className={inputCls} value={f.inactive} onChange={set("inactive")}>
        <option value="">Qualsiasi inattività</option>
        <option value="7">Inattivi da 7+ giorni</option><option value="14">Inattivi da 14+ giorni</option><option value="30">Inattivi da 30+ giorni</option>
      </select>
    </div>
  );
}

export function AccessUsersTable({ users, onOpen }) {
  const [f, setF] = useState({ q: "", org: "", role: "", status: "", inactive: "" });
  const [sort, setSort] = useState({ k: "last_activity_at", dir: -1 });
  const orgs = useMemo(() => [...new Set(users.flatMap((u) => u.org_names))].sort(), [users]);
  const rows = useMemo(() => {
    const q = f.q.trim().toLowerCase();
    const out = users.filter((u) => (!q || `${u.name} ${u.email}`.toLowerCase().includes(q))
      && (!f.org || u.org_names.includes(f.org)) && (!f.role || u.roles.includes(f.role) || u.user_role === f.role)
      && (!f.status || u.status === f.status) && (!f.inactive || (u.days_inactive ?? -1) >= Number(f.inactive)));
    return out.sort((a, b) => {
      const x = val(a, sort.k) ?? ""; const y = val(b, sort.k) ?? "";
      return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
    });
  }, [users, f, sort]);
  const toggle = (k) => setSort((s) => ({ k, dir: s.k === k ? -s.dir : -1 }));
  return (
    <div className="space-y-3">
      <Filters f={f} setF={setF} orgs={orgs} />
      <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
        <table className="w-full text-sm" data-testid="access-users-table">
          <thead><tr className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
            {COLS.map(([k, l]) => (
              <th key={k} className="text-left font-semibold px-3 py-3 whitespace-nowrap">
                <button type="button" onClick={() => toggle(k)} className="inline-flex items-center gap-1 hover:text-slate-800" data-testid={`access-sort-${k}`}>{l}<ArrowUpDown className="w-3 h-3" /></button>
              </th>))}
          </tr></thead>
          <tbody>
            {rows.length === 0 ? <tr><td colSpan={COLS.length} className="px-4 py-10 text-center text-slate-400" data-testid="access-users-empty">Nessun utente</td></tr>
              : rows.map((u) => (
                <tr key={u.user_id} className="border-t border-slate-100 hover:bg-slate-50/60 cursor-pointer" onClick={() => onOpen(u.user_id)} data-testid={`access-user-row-${u.user_id}`}>
                  <td className="px-3 py-3"><div className="font-medium text-slate-800">{u.name || "—"}</div><div className="text-xs text-slate-400">{u.email}</div></td>
                  <td className="px-3 py-3 text-slate-600">{u.org_names.join(", ") || "—"}</td>
                  <td className="px-3 py-3 text-slate-600">{u.role_labels.join(", ")}</td>
                  <td className="px-3 py-3 text-slate-600 whitespace-nowrap">{fmtDate(u.first_login_at)}</td>
                  <td className="px-3 py-3 text-slate-600 whitespace-nowrap">{fmtDate(u.last_login_at)}{u.last_login_legacy && <div className="text-[11px] text-slate-400">prima del monitoraggio</div>}</td>
                  <td className="px-3 py-3 text-slate-600 whitespace-nowrap">{fmtDate(u.last_activity_at)}</td>
                  <td className="px-3 py-3 text-slate-700">{u.login_count}</td>
                  <td className="px-3 py-3 text-slate-700 whitespace-nowrap">{fmtDur(u.total_seconds)}</td>
                  <td className="px-3 py-3 text-slate-700">{u.days_inactive ?? "—"}</td>
                  <td className="px-3 py-3"><StatusBadge color={STATUS[u.status].color}>{STATUS[u.status].label}</StatusBadge>{!u.active && <div className="text-[11px] text-red-500 mt-1">Disabilitato</div>}</td>
                </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
