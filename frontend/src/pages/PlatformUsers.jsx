import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, StatusBadge } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Search, LogIn, MoreHorizontal } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { formatApiError } from "@/lib/api";
import AccountStateDialog from "@/components/platform/AccountStateDialog";
import UserAccessDialog from "@/components/platform/UserAccessDialog";

const ORG_ROLE = { admin_org: "Organizzatore", user: "Amministratore", collaboratore: "Collaboratore" };
const fullName = (u) => `${u.cognome || ""} ${u.nome || ""}`.trim() || u.name || "—";
const roleLabels = (u) => (u.memberships?.length ? [...new Set(u.memberships.map((m) => ORG_ROLE[m.role] || m.role))] : [u.role_label]);
const orgLabel = (u) => (u.org_names || []).join(", ") || u.primary_org?.nome || "—";
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const stateKey = (u) => (u.is_invite ? (u.invite_status === "expired" ? "expired" : "pending") : u.active ? "active" : "disabled");
const STATE = { active: ["Attivo", "green"], disabled: ["Disattivato", "red"], pending: ["Invito in attesa", "blue"], expired: ["Invito scaduto", "amber"] };
const accessNote = (u) => {
  if (u.is_invite) return "";
  const m = u.memberships || [];
  const off = m.filter((x) => x.active === false).length;
  const ev = Object.values(Object.assign({}, ...m.map((x) => x.event_states || {})));
  const n = (k, one, many) => { const c = ev.filter((s) => s === k).length; return c && `${c} ${c === 1 ? one : many}`; };
  const parts = [off && `${off} ${off === 1 ? "org. disattivata" : "org. disattivate"}`, n("disabled", "evento disattivato", "eventi disattivati"), n("revoked", "evento revocato", "eventi revocati")].filter(Boolean);
  return parts.join(" · ");
};
const eventsLabel = (u) => {
  const c = (u.memberships || []).filter((m) => m.role === "collaboratore");
  if (!c.length || u.is_invite) return "—";
  return c.some((m) => m.events === "all") ? "Tutti" : `${c.reduce((n, m) => n + (m.events || []).length, 0)} eventi`;
};

function Filter({ value, onChange, all, options, testid }) {
  return (
    <div className="w-full sm:w-52" data-testid={testid}>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent><SelectItem value="all">{all}</SelectItem>{options.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
      </Select>
    </div>
  );
}

function ChooseOrg({ data, onPick, onClose }) {
  return (
    <Dialog open={!!data} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="support-choose-org">
        <DialogHeader><DialogTitle>Scegli l'organizzazione</DialogTitle>
          <DialogDescription>{data?.name} appartiene a più organizzazioni: verranno applicati ruolo e permessi di quella selezionata.</DialogDescription></DialogHeader>
        <div className="space-y-2">{(data?.orgs || []).map((o) => (
          <Button key={o.org_id} variant="outline" className="w-full justify-start" onClick={() => onPick(o.org_id)} data-testid={`support-org-${o.org_id}`}>{o.nome}</Button>
        ))}</div>
      </DialogContent>
    </Dialog>
  );
}

export default function PlatformUsers({ embedded = false, onChanged }) {
  const { startSupport } = useAuth();
  const [users, setUsers] = useState([]);
  const [q, setQ] = useState("");
  const [fOrg, setFOrg] = useState("all");
  const [fRole, setFRole] = useState("all");
  const [fState, setFState] = useState("all");
  const [choose, setChoose] = useState(null);
  const [stateFor, setStateFor] = useState(null);
  const [accessFor, setAccessFor] = useState(null);
  const load = () => { onChanged?.(); return api.get("/platform/users").then(({ data }) => setUsers(data.filter((u) => !u.is_superadmin))).catch(() => setUsers([])); };
  useEffect(() => { api.get("/platform/users").then(({ data }) => setUsers(data.filter((u) => !u.is_superadmin))).catch(() => setUsers([])); }, []);

  const orgOpts = useMemo(() => [...new Set(users.flatMap((u) => u.org_names || []))].sort((a, b) => a.localeCompare(b)).map((n) => [n, n]), [users]);
  const roleOpts = useMemo(() => [...new Set(users.flatMap(roleLabels))].sort().map((r) => [r, r]), [users]);
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    return users.filter((u) => (!s || `${u.cognome || ""} ${u.nome || ""}`.toLowerCase().includes(s) || `${u.nome || ""} ${u.cognome || ""}`.toLowerCase().includes(s) || (u.email || "").toLowerCase().includes(s))
      && (fOrg === "all" || (u.org_names || []).includes(fOrg))
      && (fRole === "all" || roleLabels(u).includes(fRole))
      && (fState === "all" || fState === stateKey(u)))
      .sort((a, b) => (a.cognome || "").localeCompare(b.cognome || "", "it", { sensitivity: "base" }) || (a.nome || "").localeCompare(b.nome || "", "it", { sensitivity: "base" }));
  }, [users, q, fOrg, fRole, fState]);

  const access = async (u, orgId) => {
    const r = await startSupport(u.user_id, orgId);
    if (r?.choose) setChoose({ user: u, name: fullName(u), orgs: r.choose });
  };
  const resend = async (u) => {
    try { const { data } = await api.post(`/platform/invites/${u.invite_id}/resend`); toast.success(data.email_sent ? "Invito reinviato" : "Invito rinnovato (email non inviata)"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const action = (u, p = "") => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button variant="outline" size="sm" className="h-8 gap-1" data-testid={`${p}user-actions-${u.user_id}`}><MoreHorizontal className="w-4 h-4" />Azioni</Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        {u.is_invite ? <DropdownMenuItem onClick={() => resend(u)} data-testid={`${p}user-resend-${u.user_id}`}>Reinvia invito</DropdownMenuItem> : (<>
          <DropdownMenuItem onClick={() => access(u)} data-testid={`${p}impersonate-${u.user_id}`}><LogIn className="w-3.5 h-3.5 mr-2" />Accedi come</DropdownMenuItem>
          {u.active ? <DropdownMenuItem className="text-red-600" onClick={() => setStateFor(u)} data-testid={`${p}user-deactivate-${u.user_id}`}>Disattiva account</DropdownMenuItem>
            : <DropdownMenuItem onClick={() => setStateFor(u)} data-testid={`${p}user-activate-${u.user_id}`}>Attiva account</DropdownMenuItem>}
          <DropdownMenuItem onClick={() => setAccessFor(u)} data-testid={`${p}user-access-${u.user_id}`}>Gestisci accessi</DropdownMenuItem>
          {(u.memberships || []).some((m) => m.role !== "admin_org") && <DropdownMenuItem onClick={() => setAccessFor(u)} data-testid={`${p}user-perms-${u.user_id}`}>Modifica permessi</DropdownMenuItem>}
        </>)}
      </DropdownMenuContent>
    </DropdownMenu>
  );
  const state = (u) => { const [l, c] = STATE[stateKey(u)]; const n = accessNote(u); return <div><StatusBadge color={c}>{l}</StatusBadge>{n && <div className="text-[11px] text-amber-700 mt-0.5">{n}</div>}{!u.active && u.deactivated_at && <div className="text-[11px] text-slate-400">dal {fmt(u.deactivated_at)}</div>}</div>; };
  const kind = (u) => ({ collaboratore: "Collaboratore", utente: "Utente (link evento)", staff_vol: "Staff / Volontari" }[u.kind] || "Gestionale");

  return (
    <div className="animate-fade-up" data-testid="platform-users-page">
      {embedded ? <h2 className="font-semibold text-slate-800 mb-1">Gestione utenti</h2> : <PageHeader title="Gestione Utenti" subtitle="Accedi come utente per verificare cosa vede e può usare (sessione di assistenza di 30 minuti, registrata in Audit)" />}
      {embedded && <p className="text-sm text-slate-500 mb-4">Accedi come utente per verificare cosa vede e può usare (sessione di assistenza di 30 minuti, registrata in Audit).</p>}
      <div className="mb-4 flex flex-col sm:flex-row sm:flex-wrap gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9" placeholder="Cerca per cognome, nome o email..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="users-search" />
        </div>
        <Filter value={fOrg} onChange={setFOrg} all="Tutte le organizzazioni" options={orgOpts} testid="users-filter-org" />
        <Filter value={fRole} onChange={setFRole} all="Tutti i ruoli" options={roleOpts} testid="users-filter-role" />
        <Filter value={fState} onChange={setFState} all="Tutti gli stati" options={[["active", "Attivo"], ["disabled", "Disattivato"], ["pending", "Invito in attesa"], ["expired", "Invito scaduto"]]} testid="users-filter-state" />
      </div>
      <div className="md:hidden space-y-2.5" data-testid="users-mobile-list">
        {rows.map((u) => (
          <div key={u.user_id} className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={`user-card-${u.user_id}`}>
            <div className="flex items-start justify-between gap-2"><div className="font-semibold text-slate-900 break-words">{fullName(u)}</div>{state(u)}</div>
            <div className="text-sm text-slate-600 break-all">{u.email}</div>
            <div className="text-xs text-slate-500 mt-1">{roleLabels(u).includes(kind(u)) ? "" : `${kind(u)} · `}{orgLabel(u)} · {roleLabels(u).join(", ")} · Eventi: {eventsLabel(u)}</div>
            <div className="text-xs text-slate-400 mt-0.5">Ultimo accesso: {fmt(u.last_login_at)}</div>
            <div className="mt-2">{action(u, "m-")}</div>
          </div>
        ))}
        {rows.length === 0 && <div className="py-10 text-center text-slate-400 text-sm">Nessun utente trovato.</div>}
      </div>
      <div className="hidden md:block bg-white border border-slate-200 rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm" data-testid="users-table">
          <thead><tr className="border-b border-slate-200 bg-slate-50/70 text-left text-slate-600">
            {["Cognome e Nome", "Email", "Tipologia", "Organizzazione", "Ruolo", "Eventi autorizzati", "Stato accesso", "Ultimo accesso"].map((h) => <th key={h} className="px-4 py-3 font-semibold whitespace-nowrap">{h}</th>)}
            <th className="px-4 py-3 font-semibold text-right">Azioni</th>
          </tr></thead>
          <tbody>
            {rows.length === 0 ? <tr><td colSpan={9} className="px-4 py-10 text-center text-slate-400">Nessun utente trovato.</td></tr> : rows.map((u) => (
              <tr key={u.user_id} className="border-b border-slate-100 hover:bg-slate-50/80" data-testid={`user-row-${u.user_id}`}>
                <td className="px-4 py-3 font-medium text-slate-800">{fullName(u)}</td>
                <td className="px-4 py-3 text-slate-600">{u.email}</td>
                <td className="px-4 py-3 text-slate-600" data-testid={`user-kind-${u.user_id}`}>{kind(u)}</td>
                <td className="px-4 py-3 text-slate-600">{orgLabel(u)}</td>
                <td className="px-4 py-3 text-slate-600">{roleLabels(u).join(", ")}</td>
                <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{eventsLabel(u)}</td>
                <td className="px-4 py-3" data-testid={`user-state-${u.user_id}`}>{state(u)}</td>
                <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{fmt(u.last_login_at)}</td>
                <td className="px-4 py-3 text-right whitespace-nowrap">{action(u)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ChooseOrg data={choose} onClose={() => setChoose(null)} onPick={(oid) => { const u = choose.user; setChoose(null); access(u, oid); }} />
      {stateFor && <AccountStateDialog user={stateFor} onClose={() => setStateFor(null)} onDone={() => { setStateFor(null); load(); }} />}
      {accessFor && <UserAccessDialog user={accessFor} onClose={() => setAccessFor(null)} onChanged={load} />}
    </div>
  );
}
