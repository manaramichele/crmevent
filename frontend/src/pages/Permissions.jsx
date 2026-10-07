import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { KeyRound, Pencil, RotateCcw, History } from "lucide-react";

const ROLE_COLORS = { admin_org: "tiffany", user: "blue", collaboratore: "orange" };
const fmt = (iso) => { try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return iso; } };

function MatrixEditor({ meta, value, onChange }) {
  const toggle = (sec, act) => {
    const cur = new Set(value.sections[sec] || []);
    if (cur.has(act)) { cur.delete(act); if (act === "view") cur.clear(); } else { cur.add(act); cur.add("view"); }
    onChange({ ...value, sections: { ...value.sections, [sec]: [...cur] } });
  };
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm" data-testid="perm-matrix">
        <thead><tr className="bg-slate-50 text-xs uppercase text-slate-500">
          <th className="text-left px-3 py-2">Sezione</th>
          {Object.entries(meta.actions).map(([k, l]) => <th key={k} className="px-2 py-2 text-center">{l}</th>)}
        </tr></thead>
        <tbody>
          {meta.sections.map((s) => (
            <tr key={s.key} className="border-t border-slate-100">
              <td className="px-3 py-2 text-slate-700">{s.label}</td>
              {Object.keys(meta.actions).map((a) => (
                <td key={a} className="px-2 py-2 text-center">
                  <input type="checkbox" className="accent-tiffany w-4 h-4" checked={(value.sections[s.key] || []).includes(a)}
                    onChange={() => toggle(s.key, a)} data-testid={`perm-${s.key}-${a}`} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventScope({ events, value, onChange }) {
  const all = value === "all";
  const sel = new Set(all ? [] : value);
  const flip = (id) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); onChange([...n]); };
  return (
    <div className="space-y-2">
      <div className="flex gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="radio" checked={all} onChange={() => onChange("all")} data-testid="perm-events-all" />Tutti gli eventi</label>
        <label className="flex items-center gap-2"><input type="radio" checked={!all} onChange={() => onChange([])} data-testid="perm-events-selected" />Solo eventi selezionati</label>
      </div>
      {!all && (
        <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1" data-testid="perm-events-list">
          {events.length === 0 && <div className="text-xs text-slate-400">Nessun evento nell'organizzazione.</div>}
          {events.map((e) => (
            <label key={e.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="accent-tiffany" checked={sel.has(e.id)} onChange={() => flip(e.id)} data-testid={`perm-event-${e.id}`} />{e.nome}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function TeamScope({ teams, events, value, onChange }) {
  const scope = value?.scope || "all";
  const sel = new Set(value?.ids || []);
  const flip = (id) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); onChange({ scope: "selected", ids: [...n] }); };
  const evName = (id) => events.find((e) => e.id === id)?.nome || "";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-4 text-sm">
        {[["leader", "Solo Team di cui è Team Leader"], ["selected", "Team selezionati"], ["all", "Tutti i Team"]].map(([k, l]) => (
          <label key={k} className="flex items-center gap-2"><input type="radio" checked={scope === k} onChange={() => onChange({ scope: k, ids: k === "selected" ? [...sel] : [] })} data-testid={`perm-teams-${k}`} />{l}</label>
        ))}
      </div>
      {scope !== "all" && <p className="text-xs text-slate-400">Team Leader = persona dell'anagrafica con la stessa email dell'utente, indicata come Team Leader del Team.</p>}
      {scope === "selected" && (
        <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1" data-testid="perm-teams-list">
          {teams.length === 0 && <div className="text-xs text-slate-400">Nessun Team nell'organizzazione.</div>}
          {teams.map((t) => (
            <label key={t.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="accent-tiffany" checked={sel.has(t.id)} onChange={() => flip(t.id)} data-testid={`perm-team-${t.id}`} />{t.nome}<span className="text-xs text-slate-400">{evName(t.evento_id)}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function EditDialog({ meta, member, onClose, onSaved }) {
  const [role, setRole] = useState(member.role);
  const base = member.permissions.admin ? meta.defaults.user : member.permissions;
  const [perm, setPerm] = useState({ sections: base.sections, events: base.events, teams: base.teams || { scope: "all", ids: [] } });
  const [busy, setBusy] = useState(false);
  const changeRole = (r) => { setRole(r); if (r !== "admin_org" && r !== member.role) setPerm({ ...meta.defaults[r] }); };
  const save = async (reset = false) => {
    setBusy(true);
    try {
      const body = reset ? { role, reset: true } : role === "admin_org" ? { role } : { role, sections: perm.sections, events: perm.events, teams: perm.teams };
      await api.put(`/org/permissions/${member.user_id}`, body);
      toast.success("Permessi aggiornati"); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="perm-dialog">
        <DialogHeader>
          <DialogTitle>Permessi di {member.name || member.email}</DialogTitle>
          <DialogDescription>I permessi valgono solo per questa organizzazione e sono verificati dal server.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <div className="text-xs font-semibold uppercase text-slate-500">Ruolo</div>
            <select className="h-10 w-full px-3 rounded-lg border border-slate-200 text-sm bg-white" value={role} onChange={(e) => changeRole(e.target.value)} data-testid="perm-role-select">
              {Object.entries(meta.roles).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          {role === "admin_org" ? (
            <p className="text-sm text-slate-600">L'Admin Organizzatore vede e gestisce tutto, compresi account, crediti, impostazioni e permessi.</p>
          ) : (<>
            <div className="space-y-1.5"><div className="text-xs font-semibold uppercase text-slate-500">Sezioni</div><MatrixEditor meta={meta} value={perm} onChange={setPerm} /></div>
            <div className="space-y-1.5"><div className="text-xs font-semibold uppercase text-slate-500">Eventi</div><EventScope events={meta.events} value={perm.events} onChange={(events) => setPerm((p) => ({ ...p, events }))} /></div>
            <div className="space-y-1.5"><div className="text-xs font-semibold uppercase text-slate-500">Accesso ai Team</div><TeamScope teams={meta.teams || []} events={meta.events} value={perm.teams} onChange={(teams) => setPerm((p) => ({ ...p, teams }))} /></div>
            <p className="text-xs text-slate-400">Account, abbonamento, crediti, fatture, impostazioni e gestione utenti restano riservati all'Admin Organizzatore.</p>
          </>)}
        </div>
        <DialogFooter className="gap-2">
          {role !== "admin_org" && <Button variant="outline" disabled={busy} onClick={() => save(true)} data-testid="perm-reset"><RotateCcw className="w-4 h-4 mr-1" />Predefiniti del ruolo</Button>}
          <Button disabled={busy} onClick={() => save(false)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="perm-save">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Permissions() {
  const [meta, setMeta] = useState(null);
  const [audit, setAudit] = useState([]);
  const [edit, setEdit] = useState(null);
  const load = useCallback(async () => {
    try {
      const [m, a] = await Promise.all([api.get("/org/permissions"), api.get("/org/permissions/audit")]);
      setMeta(m.data); setAudit(a.data.items || []);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const summary = (p) => {
    if (p.admin) return "Accesso completo";
    const n = meta.sections.filter((s) => (p.sections[s.key] || []).length).length;
    const tp = p.teams?.scope === "leader" ? " · Team: solo come leader" : p.teams?.scope === "selected" ? ` · ${p.teams.ids.length} Team` : "";
    return `${n}/${meta.sections.length} sezioni · ${p.events === "all" ? "tutti gli eventi" : `${p.events.length} eventi`}${tp}`;
  };
  return (
    <div className="animate-fade-up space-y-8" data-testid="permissions-page">
      <PageHeader title="Permessi" subtitle="Ruoli e permessi dei membri della tua organizzazione, per sezione ed evento." />
      {!meta ? <div className="text-slate-400">Caricamento...</div> : (
        <div className="overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full min-w-[720px] text-sm" data-testid="perm-members-table">
            <thead><tr className="bg-slate-50 text-xs uppercase text-slate-500">
              <th className="text-left px-3 py-2.5">Utente</th><th className="text-left px-3 py-2.5">Ruolo</th><th className="text-left px-3 py-2.5">Permessi</th><th className="text-left px-3 py-2.5">Stato</th><th className="px-3 py-2.5"></th>
            </tr></thead>
            <tbody>
              {meta.members.map((m) => (
                <tr key={m.user_id} className="border-t border-slate-100" data-testid={`perm-row-${m.user_id}`}>
                  <td className="px-3 py-2.5"><div className="font-medium text-slate-800">{m.name || "—"}</div><div className="text-xs text-slate-500">{m.email}</div></td>
                  <td className="px-3 py-2.5"><StatusBadge color={ROLE_COLORS[m.role] || "gray"}>{m.role_label}</StatusBadge></td>
                  <td className="px-3 py-2.5 text-slate-600" data-testid={`perm-summary-${m.user_id}`}>{summary(m.permissions)}{m.custom && <span className="ml-2 text-[10px] text-tiffany-fg">personalizzati</span>}</td>
                  <td className="px-3 py-2.5"><StatusBadge color={m.active ? "green" : "gray"}>{m.active ? "Attivo" : "Disattivato"}</StatusBadge></td>
                  <td className="px-3 py-2.5 text-right">{m.is_self ? <span className="text-xs text-slate-400">Tu</span> :
                    <Button variant="outline" size="sm" onClick={() => setEdit(m)} data-testid={`perm-edit-${m.user_id}`}><Pencil className="w-3.5 h-3.5 mr-1" />Modifica</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div>
        <div className="flex items-center gap-2 mb-3 text-slate-800 font-semibold"><History className="w-4 h-4" />Storico modifiche</div>
        <div className="space-y-2" data-testid="perm-audit">
          {audit.length === 0 && <div className="text-sm text-slate-400">Nessuna modifica registrata.</div>}
          {audit.map((a) => (
            <div key={a.id} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
              <div className="flex flex-wrap gap-x-2 text-slate-800"><span className="font-medium">{a.action_label}</span><span className="text-slate-400">·</span><span>{a.target_name || a.target_email}</span><span className="text-slate-400">· da {a.actor_name || a.actor_email} · {fmt(a.created_at)}</span></div>
              {a.detail && <div className="text-xs text-slate-500 mt-0.5 break-words">{a.detail}</div>}
            </div>
          ))}
        </div>
      </div>
      {edit && meta && <EditDialog meta={meta} member={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      <KeyRound className="hidden" />
    </div>
  );
}
