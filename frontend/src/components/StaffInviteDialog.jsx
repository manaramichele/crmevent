import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge, TextAction } from "@/components/crm";
import { toast } from "sonner";
import { UserPlus, Search, ArrowLeft, Crown, Users, CalendarDays, Mail, Phone } from "lucide-react";
import PhoneInput from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { PermFields, initialPerm } from "@/pages/Permissions";

const ROLE_OPTS = [{ value: "admin_org", label: "Admin" }, { value: "collaboratore", label: "Collaboratore" }, { value: "user", label: "Utente" }];
const CAT = { staff: "Staff", collaboratore: "Collaboratore" };
const fullName = (p) => `${p.cognome || ""} ${p.nome || ""}`.trim();

function PersonFacts({ p }) {
  return (
    <div className="space-y-1 text-xs text-slate-600">
      <div className="flex flex-wrap gap-1">{(p.categorie || []).map((c) => <StatusBadge key={c} color="blue">{CAT[c] || c}</StatusBadge>)}</div>
      {p.leader_of?.length > 0 && <div className="flex items-start gap-1"><Crown className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-px" /><span>Team Leader: <b>{p.leader_of.join(", ")}</b></span></div>}
      {p.teams?.length > 0 && <div className="flex items-start gap-1"><Users className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-px" /><span>Team: {p.teams.join(", ")}</span></div>}
      {p.events?.length > 0 && <div className="flex items-start gap-1"><CalendarDays className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-px" /><span>Eventi: {p.events.join(", ")}</span></div>}
    </div>
  );
}

function AddStaffForm({ events, onCancel, onCreated, orgId }) {
  const [f, setF] = useState({ evento_id: events[0]?.id || "", nome: "", cognome: "", email: "", cellulare: "" });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!f.evento_id) return toast.error("Seleziona l'evento");
    if (!f.nome.trim() || !f.cognome.trim()) return toast.error("Nome e cognome sono obbligatori");
    setBusy(true);
    try { const { data } = await api.post(`/platform/organizations/${orgId}/staff-candidates`, f); toast.success("Persona aggiunta allo Staff"); onCreated(data.id); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="invite-add-staff-form">
      <button type="button" onClick={onCancel} className="inline-flex items-center gap-1 text-sm text-slate-500 py-1"><ArrowLeft className="w-4 h-4" />Torna alla ricerca</button>
      <div className="space-y-1.5"><Label>Evento *</Label>
        <select className="h-10 w-full px-3 rounded-lg border border-slate-200 text-sm bg-white" value={f.evento_id} onChange={(e) => setF((s) => ({ ...s, evento_id: e.target.value }))} data-testid="add-staff-event">
          {events.length === 0 && <option value="">Nessun evento disponibile</option>}
          {events.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1.5"><Label>Nome *</Label><Input value={f.nome} onChange={(e) => setF((s) => ({ ...s, nome: e.target.value }))} data-testid="add-staff-nome" /></div>
        <div className="space-y-1.5"><Label>Cognome *</Label><Input value={f.cognome} onChange={(e) => setF((s) => ({ ...s, cognome: e.target.value }))} data-testid="add-staff-cognome" /></div>
      </div>
      <div className="space-y-1.5"><Label>Email</Label><Input type="email" value={f.email} onChange={(e) => setF((s) => ({ ...s, email: e.target.value }))} data-testid="add-staff-email" /></div>
      <div className="space-y-1.5"><Label>Cellulare</Label><PhoneInput international defaultCountry="IT" value={f.cellulare || undefined} onChange={(v) => setF((s) => ({ ...s, cellulare: v || "" }))} className="phone-input" numberInputProps={{ "data-testid": "add-staff-cellulare" }} /></div>
      <Button onClick={save} disabled={busy} className="w-full sm:w-auto bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="add-staff-save">{busy ? "Salvataggio..." : "Aggiungi allo Staff e continua"}</Button>
    </div>
  );
}

// Invita utente → Cerca Staff → Seleziona persona → Ruolo → Permessi → Invia invito
export default function StaffInviteDialog({ orgId, meta, open, onOpenChange, onSent, onManageExisting }) {
  const [step, setStep] = useState("search");
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);
  const [events, setEvents] = useState([]);
  const [sel, setSel] = useState(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("user");
  const [perm, setPerm] = useState(null);
  const [busy, setBusy] = useState(false);

  const search = useCallback(async (term) => {
    try { const { data } = await api.get(`/platform/organizations/${orgId}/staff-candidates`, { params: { q: term } }); setItems(data.items); setEvents(data.events || []); return data.items; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setItems([]); return []; }
  }, [orgId]);
  useEffect(() => { if (!open) return; const t = setTimeout(() => search(q), 250); return () => clearTimeout(t); }, [q, open, search]);
  useEffect(() => { if (open) { setStep("search"); setQ(""); setSel(null); } }, [open]);

  const pick = (p) => {
    setSel(p); setEmail(p.email || ""); setRole("user");
    setPerm(meta ? initialPerm(meta, meta.defaults.user) : null); setStep("invite");
  };
  const onCreated = async (pid) => { setQ(""); const list = await search(""); const p = list.find((x) => x.id === pid); if (p) pick(p); else setStep("search"); };
  const changeRole = (r) => { setRole(r); if (meta && r !== "admin_org") setPerm(initialPerm(meta, meta.defaults[r])); };

  const send = async () => {
    if (!sel.email && !email.trim()) return toast.error("Inserisci l'email della persona");
    setBusy(true);
    try {
      const { data } = await api.post(`/platform/organizations/${orgId}/invites`, { persona_id: sel.id, email: (sel.email || email).trim(), role, ...(perm && role !== "admin_org" ? { permissions: perm } : {}) });
      toast[data.email_sent ? "success" : "warning"](data.email_sent ? "Invito inviato" : "Invito creato (email non inviata)");
      onOpenChange(false); onSent && onSent();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="org-invite-dialog">
        <DialogHeader className="text-left">
          <DialogTitle className="flex items-center gap-2"><UserPlus className="w-5 h-5 text-tiffany-active" />Invita utente</DialogTitle>
          <DialogDescription>{step === "invite" ? "Assegna ruolo e permessi, poi invia l'invito (valido 7 giorni)." : "L'account parte sempre da una persona dello Staff dell'organizzazione."}</DialogDescription>
        </DialogHeader>

        {step === "search" && (
          <div className="space-y-3" data-testid="invite-staff-search-step">
            <Label>Cerca nello Staff</Label>
            <div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <Input autoFocus className="pl-9 h-11" placeholder="Nome, cognome, email o telefono" value={q} onChange={(e) => setQ(e.target.value)} data-testid="invite-staff-search" /></div>
            <div className="space-y-2" data-testid="invite-staff-results">
              {items === null ? <p className="text-sm text-slate-400 py-4 text-center">Caricamento...</p>
                : items.length === 0 ? <p className="text-sm text-slate-400 py-4 text-center" data-testid="invite-staff-empty">Nessuna persona dello Staff trovata.</p>
                : items.map((p) => (
                  <button key={p.id} type="button" onClick={() => pick(p)} className="w-full text-left rounded-xl border border-slate-200 bg-white p-3.5 hover:border-tiffany active:bg-slate-50 transition-colors" data-testid={`invite-staff-card-${p.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0"><div className="font-semibold text-slate-900 break-words">{fullName(p)}</div>
                        <div className="text-xs text-slate-500 break-all">{p.email || <span className="text-amber-700">Email mancante</span>}{p.cellulare ? ` · ${p.cellulare}` : ""}</div></div>
                      {p.account ? <StatusBadge color="tiffany">Ha un account</StatusBadge> : p.pending_invite ? <StatusBadge color="orange">Invito in attesa</StatusBadge> : null}
                    </div>
                    <div className="mt-2"><PersonFacts p={p} /></div>
                  </button>
                ))}
            </div>
            <div className="rounded-xl border border-dashed border-slate-300 p-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2" data-testid="invite-not-found">
              <span className="text-sm text-slate-600">Non trovi la persona? Aggiungila prima allo Staff.</span>
              <TextAction icon={UserPlus} onClick={() => setStep("add")} className="self-start" data-testid="invite-add-staff-btn">Aggiungi allo Staff</TextAction>
            </div>
          </div>
        )}

        {step === "add" && <AddStaffForm orgId={orgId} events={events} onCancel={() => setStep("search")} onCreated={onCreated} />}

        {step === "invite" && sel && (
          <div className="space-y-4" data-testid="invite-form-step">
            <button type="button" onClick={() => setStep("search")} className="inline-flex items-center gap-1 text-sm text-slate-500 py-1" data-testid="invite-back-search"><ArrowLeft className="w-4 h-4" />Cambia persona</button>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-2" data-testid="invite-selected-person">
              <div className="font-semibold text-slate-900 text-base">{sel.cognome} {sel.nome}</div>
              <div className="text-sm text-slate-600 space-y-0.5">
                {sel.email && <div className="flex items-center gap-1.5 break-all"><Mail className="w-3.5 h-3.5 text-slate-400" />{sel.email}</div>}
                {sel.cellulare && <div className="flex items-center gap-1.5"><Phone className="w-3.5 h-3.5 text-slate-400" />{sel.cellulare}</div>}
              </div>
              <PersonFacts p={sel} />
              <p className="text-[11px] text-slate-400">Team e ruolo di Team Leader sono informativi: non concedono permessi.</p>
            </div>

            {sel.account ? (
              <div className="rounded-xl border border-tiffany-border bg-tiffany-light/40 p-4 space-y-2" data-testid="invite-existing-account">
                <p className="text-sm font-semibold text-slate-800">Questo membro dello Staff dispone già di un account CRMEvent.</p>
                <p className="text-xs text-slate-600">Ruolo attuale: {sel.account.role_label}{sel.account.active ? "" : " · accesso disattivato"}. Non verrà creato un secondo account.</p>
                {onManageExisting && <Button variant="outline" onClick={() => { onOpenChange(false); onManageExisting(sel.account.user_id); }} data-testid="invite-manage-existing">Gestisci ruolo e permessi</Button>}
              </div>
            ) : (<>
              {!sel.email && (
                <div className="space-y-1.5" data-testid="invite-missing-email">
                  <Label>Email *</Label>
                  <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email@esempio.it" data-testid="invite-email" />
                  <p className="text-xs text-slate-500">Questa persona non ha un'email: verrà salvata nella stessa anagrafica Staff.</p>
                </div>
              )}
              {sel.pending_invite && <p className="text-xs text-amber-700" data-testid="invite-pending-note">C'è già un invito in attesa: inviandone uno nuovo il precedente verrà sostituito.</p>}
              <div className="space-y-1.5"><Label>Livello di accesso *</Label>
                <div className="grid grid-cols-3 gap-2" role="radiogroup" data-testid="invite-role">
                  {ROLE_OPTS.map((r) => (
                    <button key={r.value} type="button" role="radio" aria-checked={role === r.value} onClick={() => changeRole(r.value)} data-testid={`invite-role-${r.value}`}
                      className={`h-11 rounded-lg border text-sm font-semibold transition-colors ${role === r.value ? "border-tiffany bg-tiffany-light text-tiffany-fg" : "border-slate-200 bg-white text-slate-600"}`}>{r.label}</button>
                  ))}
                </div>
              </div>
              {meta && (
                <div className="rounded-xl border border-slate-200 p-3 space-y-2" data-testid="invite-perms">
                  <div className="text-sm font-semibold text-slate-800">Permessi</div>
                  <PermFields meta={meta} role={role} perm={perm || initialPerm(meta, meta.defaults[role === "collaboratore" ? "collaboratore" : "user"])} setPerm={(u) => setPerm((cur) => (typeof u === "function" ? u(cur || initialPerm(meta, meta.defaults.user)) : u))} />
                </div>
              )}
            </>)}
          </div>
        )}

        {step === "invite" && sel && !sel.account && (
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
            <Button disabled={busy} onClick={send} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="invite-submit">{busy ? "Invio..." : "Invia invito"}</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
