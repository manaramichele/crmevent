import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { RotateCcw, History } from "lucide-react";

// Componenti permessi riutilizzati in Profilo & Account → Utenti e Permessi (Admin Org e Super Admin, stesse API).
const fmt = (iso) => { try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return iso; } };
export const orgHeaders = (orgId) => (orgId ? { headers: { "X-Org-Id": orgId } } : undefined);
const SECTION_LBL = "text-xs font-semibold uppercase text-slate-500";

export function usePermMeta(orgId) {
  const [meta, setMeta] = useState(null);
  const load = useCallback(async () => {
    try { const { data } = await api.get("/org/permissions", orgHeaders(orgId)); setMeta(data); } catch { setMeta(null); }
  }, [orgId]);
  useEffect(() => { load(); }, [load]);
  return { meta, reload: load };
}

export function teamAccessLabel(p, meta) {
  if (!p || p.admin) return "Tutti i Team";
  const t = p.teams || {};
  if (t.scope === "all") return "Tutti i Team";
  if (t.scope === "leader") return "Solo Team di cui è Team Leader";
  const names = (meta?.teams || []).filter((x) => (t.ids || []).includes(x.id)).map((x) => x.nome);
  return names.length ? `${names.join(", ")} + Team di cui è leader` : "Solo Team di cui è Team Leader";
}

export function permSummary(p, meta) {
  if (!p || p.admin) return "Accesso completo";
  const secs = meta?.sections || [];
  const vis = secs.filter((s) => (p.sections?.[s.key] || []).length);
  const edit = vis.filter((s) => (p.sections[s.key] || []).some((a) => a !== "view"));
  return `${vis.length}/${secs.length} sezioni (${edit.length} con modifica) · ${p.events === "all" ? "tutti gli eventi" : `${(p.events || []).length} eventi`}${p.send_invites ? " · inviti email" : ""}`;
}

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
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="radio" checked={all} onChange={() => onChange("all")} data-testid="perm-events-all" />Tutti gli eventi</label>
        <label className="flex items-center gap-2"><input type="radio" checked={!all} onChange={() => onChange([])} data-testid="perm-events-selected" />Solo eventi selezionati</label>
      </div>
      {!all && (
        <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1" data-testid="perm-events-list">
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
  const v = { scope: "all", ids: [], manage_staff: true, manage_volunteers: true, ...(value || {}) };
  const sel = new Set(v.ids || []);
  const set = (patch) => onChange({ ...v, ...patch });
  const flip = (id) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); set({ scope: "selected", ids: [...n] }); };
  const evName = (id) => events.find((e) => e.id === id)?.nome || "";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-4 text-sm">
        {[["leader", "Solo Team di cui è Team Leader"], ["selected", "Team selezionati"], ["all", "Tutti i Team"]].map(([k, l]) => (
          <label key={k} className="flex items-center gap-2"><input type="radio" checked={v.scope === k} onChange={() => set({ scope: k, ids: k === "selected" ? [...sel] : [] })} data-testid={`perm-teams-${k}`} />{l}</label>
        ))}
      </div>
      {v.scope === "selected" && (
        <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 p-2 space-y-1" data-testid="perm-teams-list">
          {teams.length === 0 && <div className="text-xs text-slate-400">Nessun Team nell'organizzazione.</div>}
          {teams.map((t) => (
            <label key={t.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="accent-tiffany" checked={sel.has(t.id)} onChange={() => flip(t.id)} data-testid={`perm-team-${t.id}`} />{t.nome}<span className="text-xs text-slate-400">{evName(t.evento_id)}</span>
            </label>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-tiffany" checked={v.manage_staff} onChange={(e) => set({ manage_staff: e.target.checked })} data-testid="perm-teams-manage-staff" />Gestione Staff nei Team</label>
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-tiffany" checked={v.manage_volunteers} onChange={(e) => set({ manage_volunteers: e.target.checked })} data-testid="perm-teams-manage-volunteers" />Gestione Volontari nei Team</label>
      </div>
      <p className="text-xs text-slate-400">Team Leader = persona Staff collegata all'account (o con la stessa email) indicata come Team Leader. Gestione Staff/Volontari richiede anche Modifica su Staff / Volontari.</p>
    </div>
  );
}

function InviteToggle({ value, onChange }) {
  return (
    <div className="space-y-1.5">
      <div className={SECTION_LBL}>Invio inviti email</div>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="radio" checked={value} onChange={() => onChange(true)} data-testid="perm-send-invites-on" />Attivo</label>
        <label className="flex items-center gap-2"><input type="radio" checked={!value} onChange={() => onChange(false)} data-testid="perm-send-invites-off" />Disattivo</label>
      </div>
      <p className="text-xs text-slate-400">Consente di inviare via email l'invito all'area personale a Staff, Volontari e Collaboratori dei soli Team ed eventi accessibili. Non permette di creare utenti CRM, cambiare ruoli o assegnare permessi.</p>
    </div>
  );
}

export const initialPerm = (meta, p) => {
  const base = !p || p.admin ? meta.defaults.user : p;
  return { sections: base.sections, events: base.events, teams: base.teams || { scope: "all", ids: [] }, send_invites: !!base.send_invites };
};

export function PermFields({ meta, role, perm, setPerm, personaId, setPersonaId }) {
  return (
    <div className="space-y-4">
      {setPersonaId && <div className="space-y-1.5">
        <div className={SECTION_LBL}>Persona Staff collegata</div>
        <select className="h-10 w-full px-3 rounded-lg border border-slate-200 text-sm bg-white" value={personaId || ""} onChange={(e) => setPersonaId(e.target.value)} data-testid="perm-persona-select">
          <option value="">Nessuna (riconoscimento per email)</option>
          {(meta.persons || []).map((p) => <option key={p.id} value={p.id}>{`${p.cognome || ""} ${p.nome || ""}`.trim() || p.email}{p.email ? ` · ${p.email}` : ""}</option>)}
        </select>
        <p className="text-xs text-slate-400">Collega l'account all'anagrafica esistente senza duplicarla. Essere Team Leader non concede permessi amministrativi.</p>
      </div>}
      {role === "admin_org" ? (
        <p className="text-sm text-slate-600">L'Admin Organizzatore vede e gestisce tutto, compresi account, crediti, impostazioni e utenti.</p>
      ) : (<>
        <div className="space-y-1.5"><div className={SECTION_LBL}>Sezioni</div><MatrixEditor meta={meta} value={perm} onChange={setPerm} /></div>
        <div className="space-y-1.5"><div className={SECTION_LBL}>Eventi</div><EventScope events={meta.events} value={perm.events} onChange={(events) => setPerm((p) => ({ ...p, events }))} /></div>
        <div className="space-y-1.5"><div className={SECTION_LBL}>Accesso ai Team</div><TeamScope teams={meta.teams || []} events={meta.events} value={perm.teams} onChange={(teams) => setPerm((p) => ({ ...p, teams }))} /></div>
        <InviteToggle value={!!perm.send_invites} onChange={(send_invites) => setPerm((p) => ({ ...p, send_invites }))} />
        <p className="text-xs text-slate-400">Account, abbonamento, crediti, fatture, impostazioni e gestione utenti restano riservati all'Admin Organizzatore.</p>
      </>)}
    </div>
  );
}

export function PermissionsDialog({ orgId, meta, member, onClose, onSaved }) {
  const [role, setRole] = useState(member.role);
  const [perm, setPerm] = useState(initialPerm(meta, member.permissions));
  const [personaId, setPersonaId] = useState(member.persona_id || "");
  const [busy, setBusy] = useState(false);
  const changeRole = (r) => { setRole(r); if (r !== "admin_org" && r !== member.role) setPerm(initialPerm(meta, meta.defaults[r])); };
  const save = async (reset = false) => {
    setBusy(true);
    try {
      const body = reset ? { role, reset: true, persona_id: personaId } : role === "admin_org" ? { role, persona_id: personaId } : { role, persona_id: personaId, ...perm };
      await api.put(`/org/permissions/${member.user_id}`, body, orgHeaders(orgId));
      toast.success("Permessi aggiornati"); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="perm-dialog">
        <DialogHeader>
          <DialogTitle>Permessi di {member.name || member.email}</DialogTitle>
          <DialogDescription>Valgono solo per questa organizzazione e sono verificati dal server.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5 mb-3">
          <div className={SECTION_LBL}>Ruolo</div>
          <select className="h-10 w-full px-3 rounded-lg border border-slate-200 text-sm bg-white" value={role} onChange={(e) => changeRole(e.target.value)} data-testid="perm-role-select">
            {Object.entries(meta.roles).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <PermFields meta={meta} role={role} perm={perm} setPerm={setPerm} personaId={personaId} setPersonaId={setPersonaId} />
        <DialogFooter className="gap-2">
          {role !== "admin_org" && <Button variant="outline" size="sm" disabled={busy} onClick={() => save(true)} data-testid="perm-reset"><RotateCcw className="w-4 h-4 mr-1" />Predefiniti del ruolo</Button>}
          <Button size="sm" disabled={busy} onClick={() => save(false)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="perm-save">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PermAudit({ orgId, refreshKey }) {
  const [items, setItems] = useState([]);
  useEffect(() => { api.get("/org/permissions/audit", orgHeaders(orgId)).then(({ data }) => setItems(data.items || [])).catch(() => setItems([])); }, [orgId, refreshKey]);
  return (
    <div>
      <div className="flex items-center gap-2 mb-2 text-slate-800 font-semibold text-sm"><History className="w-4 h-4" />Storico modifiche ruoli e permessi</div>
      <div className="space-y-2 max-h-72 overflow-y-auto" data-testid="perm-audit">
        {items.length === 0 && <div className="text-sm text-slate-400">Nessuna modifica registrata.</div>}
        {items.map((a) => (
          <div key={a.id} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
            <div className="flex flex-wrap gap-x-2 text-slate-800"><span className="font-medium">{a.action_label}</span><span className="text-slate-400">·</span><span>{a.target_name || a.target_email}</span><span className="text-slate-400">· da {a.actor_name || a.actor_email} · {fmt(a.created_at)}</span></div>
            {a.detail && <div className="text-xs text-slate-500 mt-0.5 break-words">{a.detail}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
