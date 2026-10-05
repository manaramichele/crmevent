import { useEffect, useState, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Pencil, Trash2, Power, BarChart3, Search, X } from "lucide-react";
import { toast } from "sonner";

const TIP = { informazione: "Informazione", novita: "Novità", importante: "Importante", manutenzione: "Manutenzione" };
const STATUS = { bozza: "Bozza", programmato: "Programmato", pubblicato: "Pubblicato", scaduto: "Scaduto", disattivato: "Disattivato" };
const STATUS_CLS = { bozza: "bg-slate-100 text-slate-600", programmato: "bg-sky-100 text-sky-700", pubblicato: "bg-emerald-100 text-emerald-700", scaduto: "bg-amber-100 text-amber-700", disattivato: "bg-red-100 text-red-600" };

const toLocalInput = (iso) => { if (!iso) return ""; const d = new Date(iso); const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
const fmt = (iso) => iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";

const EMPTY = { titolo: "", messaggio: "", tipologia: "informazione", recipients_mode: "all", org_ids: [], publish_mode: "now", publish_at: "", end_at: "", require_ack: false, status: "attivo" };

export default function PlatformMessages() {
  const [rows, setRows] = useState([]);
  const [orgs, setOrgs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(null);
  const [editId, setEditId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [orgSearch, setOrgSearch] = useState("");
  const [stats, setStats] = useState(null);
  const [statsId, setStatsId] = useState(null);
  const [del, setDel] = useState(null);

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [m, o] = await Promise.all([api.get("/platform/messages"), api.get("/platform/organizations")]);
      setRows(m.data); setOrgs(o.data);
    } catch (e) { if (!silent) toast.error(formatApiError(e.response?.data?.detail)); }
    if (!silent) setLoading(false);
  };
  const refreshStats = async (id) => {
    try { const { data } = await api.get(`/platform/messages/${id}/stats`); setStats(data); } catch { /* silent */ }
  };
  // Refetch al mount, quando la finestra torna in focus e con polling leggero (letture sempre reali, no WebSocket)
  useEffect(() => {
    load();
    const onFocus = () => load(true);
    window.addEventListener("focus", onFocus);
    const iv = setInterval(() => { if (document.visibilityState === "visible") load(true); }, 45000);
    return () => { window.removeEventListener("focus", onFocus); clearInterval(iv); };
  }, []);
  // Aggiornamento automatico del dettaglio letture mentre la modale è aperta
  useEffect(() => {
    if (!statsId) return;
    const refresh = () => refreshStats(statsId);
    const iv = setInterval(refresh, 20000);
    window.addEventListener("focus", refresh);
    return () => { clearInterval(iv); window.removeEventListener("focus", refresh); };
  }, [statsId]);

  const openNew = () => { setEditId(null); setForm({ ...EMPTY }); setOrgSearch(""); };
  const openEdit = (r) => {
    setEditId(r.id);
    setForm({ titolo: r.titolo, messaggio: r.messaggio, tipologia: r.tipologia, recipients_mode: r.recipients_mode,
      org_ids: r.org_ids || [], publish_mode: r.publish_at ? "scheduled" : "now", publish_at: toLocalInput(r.publish_at),
      end_at: toLocalInput(r.end_at), require_ack: !!r.require_ack, status: r.status === "disattivato" ? "disattivato" : "attivo" });
    setOrgSearch("");
  };

  const payload = (status) => ({
    titolo: form.titolo, messaggio: form.messaggio, tipologia: form.tipologia,
    recipients_mode: form.recipients_mode, org_ids: form.recipients_mode === "selected" ? form.org_ids : [],
    publish_at: form.publish_mode === "scheduled" && form.publish_at ? new Date(form.publish_at).toISOString() : "",
    end_at: form.end_at ? new Date(form.end_at).toISOString() : "",
    require_ack: form.tipologia === "importante" ? form.require_ack : false,
    status,
  });
  const submit = async (status) => {
    if (!form.titolo.trim() || !form.messaggio.trim()) { toast.error("Titolo e messaggio obbligatori"); return; }
    if (form.recipients_mode === "selected" && !form.org_ids.length) { toast.error("Seleziona almeno un'organizzazione"); return; }
    setSaving(true);
    try {
      if (editId) await api.put(`/platform/messages/${editId}`, payload(status));
      else await api.post("/platform/messages", payload(status));
      toast.success(status === "bozza" ? "Bozza salvata" : "Messaggio pubblicato");
      setForm(null); setEditId(null); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setSaving(false);
  };
  const toggleStatus = async (r) => {
    const action = (r.status === "disattivato") ? "ripubblica" : "disattiva";
    try { await api.post(`/platform/messages/${r.id}/status`, { action }); toast.success(action === "disattiva" ? "Messaggio disattivato" : "Messaggio ripubblicato"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const doDelete = async () => {
    try { await api.delete(`/platform/messages/${del.id}`); toast.success("Messaggio eliminato"); setDel(null); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const openStats = async (r) => {
    setStatsId(r.id);
    try { const { data } = await api.get(`/platform/messages/${r.id}/stats`); setStats(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const filteredOrgs = useMemo(() => orgs.filter((o) => !orgSearch || (o.nome || "").toLowerCase().includes(orgSearch.toLowerCase())), [orgs, orgSearch]);
  const toggleOrg = (id) => setForm((f) => ({ ...f, org_ids: f.org_ids.includes(id) ? f.org_ids.filter((x) => x !== id) : [...f.org_ids, id] }));

  return (
    <div className="animate-fade-up space-y-5" data-testid="platform-messages-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 font-display">Messaggi</h1>
          <p className="text-sm text-slate-500 mt-1">Comunicazioni pubblicate nelle Dashboard delle Organizzazioni CRMEvent.</p>
        </div>
        <Button onClick={openNew} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="msg-new-btn"><Plus className="w-4 h-4 mr-1" />Nuovo messaggio</Button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr>
            <th className="p-3 text-left">Titolo</th><th className="p-3">Tipologia</th><th className="p-3">Destinatari</th>
            <th className="p-3">Pubblicazione</th><th className="p-3">Scadenza</th><th className="p-3">Stato</th><th className="p-3">Letture</th><th className="p-3">Azioni</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100 hover:bg-slate-50" data-testid={`msg-row-${r.id}`}>
                <td className="p-3 font-medium text-slate-800 max-w-xs truncate">{r.titolo}</td>
                <td className="p-3 text-center">{TIP[r.tipologia]}{r.require_ack ? " ·✔" : ""}</td>
                <td className="p-3 text-center">{r.recipients_mode === "all" ? "Tutte" : `${(r.org_ids || []).length} org`}</td>
                <td className="p-3 text-center text-xs text-slate-500">{fmt(r.publish_at)}</td>
                <td className="p-3 text-center text-xs text-slate-500">{r.end_at ? fmt(r.end_at) : "—"}</td>
                <td className="p-3 text-center"><span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_CLS[r.effective_status]}`} data-testid={`msg-status-${r.id}`}>{STATUS[r.effective_status]}</span></td>
                <td className="p-3 text-center"><button onClick={() => openStats(r)} className="text-tiffany-fg hover:underline" data-testid={`msg-stats-${r.id}`}>{r.read}/{r.recipients}</button></td>
                <td className="p-3">
                  <div className="flex items-center justify-center gap-1">
                    <button onClick={() => openEdit(r)} title="Modifica" className="p-1 text-slate-400 hover:text-tiffany-fg" data-testid={`msg-edit-${r.id}`}><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => toggleStatus(r)} title={r.status === "disattivato" ? "Ripubblica" : "Disattiva"} className="p-1 text-slate-400 hover:text-amber-600" data-testid={`msg-toggle-${r.id}`}><Power className="w-4 h-4" /></button>
                    <button onClick={() => openStats(r)} title="Letture" className="p-1 text-slate-400 hover:text-sky-600" data-testid={`msg-statsbtn-${r.id}`}><BarChart3 className="w-4 h-4" /></button>
                    <button onClick={() => setDel(r)} title="Elimina" className="p-1 text-slate-400 hover:text-red-500" data-testid={`msg-delete-${r.id}`}><Trash2 className="w-4 h-4" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && rows.length === 0 && <div className="p-8 text-center text-slate-400 text-sm">Nessun messaggio. Crea la prima comunicazione.</div>}
        {loading && <div className="p-8 text-center text-slate-400 text-sm">Caricamento…</div>}
      </div>

      {/* ---- Create / Edit ---- */}
      <Dialog open={!!form} onOpenChange={(o) => !o && setForm(null)}>
        <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="msg-form-dialog">
          <DialogHeader><DialogTitle>{editId ? "Modifica messaggio" : "Nuovo messaggio"}</DialogTitle><DialogDescription>Pubblica una comunicazione nelle Dashboard delle Organizzazioni.</DialogDescription></DialogHeader>
          {form && (
            <div className="space-y-4">
              <div className="space-y-1.5"><Label className="text-xs">Titolo *</Label><Input value={form.titolo} onChange={(e) => setForm((f) => ({ ...f, titolo: e.target.value }))} data-testid="msg-f-titolo" /></div>
              <div className="space-y-1.5"><Label className="text-xs">Messaggio *</Label><Textarea rows={4} value={form.messaggio} onChange={(e) => setForm((f) => ({ ...f, messaggio: e.target.value }))} data-testid="msg-f-messaggio" /></div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5"><Label className="text-xs">Tipologia</Label>
                  <Select value={form.tipologia} onValueChange={(v) => setForm((f) => ({ ...f, tipologia: v, require_ack: v === "importante" ? f.require_ack : false }))}>
                    <SelectTrigger data-testid="msg-f-tipologia"><SelectValue /></SelectTrigger>
                    <SelectContent>{Object.entries(TIP).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label className="text-xs">Destinatari</Label>
                  <Select value={form.recipients_mode} onValueChange={(v) => setForm((f) => ({ ...f, recipients_mode: v }))}>
                    <SelectTrigger data-testid="msg-f-recipients"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="all">Tutte le Organizzazioni</SelectItem><SelectItem value="selected">Organizzazioni selezionate</SelectItem></SelectContent></Select></div>
              </div>
              {form.recipients_mode === "selected" && (
                <div className="space-y-2 border border-slate-200 rounded-lg p-3">
                  <div className="relative"><Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" /><Input value={orgSearch} onChange={(e) => setOrgSearch(e.target.value)} placeholder="Cerca organizzazione…" className="pl-8 h-9" data-testid="msg-f-orgsearch" /></div>
                  <div className="max-h-44 overflow-y-auto space-y-1" data-testid="msg-f-orglist">
                    {filteredOrgs.map((o) => (
                      <label key={o.id} className="flex items-center gap-2 text-sm px-2 py-1 rounded hover:bg-slate-50 cursor-pointer">
                        <input type="checkbox" checked={form.org_ids.includes(o.id)} onChange={() => toggleOrg(o.id)} data-testid={`msg-f-org-${o.id}`} />
                        <span className="truncate">{o.nome}</span>
                      </label>
                    ))}
                    {filteredOrgs.length === 0 && <div className="text-xs text-slate-400 py-2 text-center">Nessuna organizzazione</div>}
                  </div>
                  <div className="text-xs text-slate-500">{form.org_ids.length} selezionate</div>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5"><Label className="text-xs">Pubblicazione</Label>
                  <Select value={form.publish_mode} onValueChange={(v) => setForm((f) => ({ ...f, publish_mode: v }))}>
                    <SelectTrigger data-testid="msg-f-pubmode"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="now">Subito</SelectItem><SelectItem value="scheduled">Programmata</SelectItem></SelectContent></Select>
                  {form.publish_mode === "scheduled" && <Input type="datetime-local" value={form.publish_at} onChange={(e) => setForm((f) => ({ ...f, publish_at: e.target.value }))} className="mt-1.5" data-testid="msg-f-publishat" />}</div>
                <div className="space-y-1.5"><Label className="text-xs">Fine visualizzazione (facoltativa)</Label>
                  <Input type="datetime-local" value={form.end_at} onChange={(e) => setForm((f) => ({ ...f, end_at: e.target.value }))} data-testid="msg-f-endat" /></div>
              </div>
              {form.tipologia === "importante" && (
                <label className="flex items-center gap-2 text-sm text-slate-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                  <input type="checkbox" checked={form.require_ack} onChange={(e) => setForm((f) => ({ ...f, require_ack: e.target.checked }))} data-testid="msg-f-ack" />
                  Richiedi conferma di lettura (l'utente deve premere «Ho letto», non può solo nascondere)
                </label>
              )}
            </div>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => submit("bozza")} disabled={saving} data-testid="msg-f-draft">Salva bozza</Button>
            <Button onClick={() => submit("attivo")} disabled={saving} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="msg-f-publish">{saving ? "Salvataggio…" : "Pubblica"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ---- Stats ---- */}
      <Dialog open={!!stats} onOpenChange={(o) => { if (!o) { setStats(null); setStatsId(null); } }}>
        <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="msg-stats-dialog">
          <DialogHeader><DialogTitle>Dettaglio letture</DialogTitle><DialogDescription>{stats?.message?.titolo}</DialogDescription></DialogHeader>
          {stats && (
            <div className="space-y-3">
              <div className="text-sm font-semibold text-slate-700" data-testid="msg-stats-summary">
                {stats.recipients} destinatari · <span className="text-emerald-600">{stats.read} letti</span> · <span className="text-amber-600">{stats.unread} non letto</span>
              </div>
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr>
                    <th className="p-2 text-left">Utente</th><th className="p-2 text-left">Organizzazione</th>
                    <th className="p-2 text-left">Email</th><th className="p-2 text-center">Stato</th><th className="p-2 text-left">Letto il</th>
                  </tr></thead>
                  <tbody>
                    {(stats.users || []).map((u) => (
                      <tr key={`${u.org_id}-${u.user_id}`} className="border-t border-slate-100" data-testid={`msg-stats-user-${u.user_id}`}>
                        <td className="p-2 text-slate-800 font-medium">{u.name}</td>
                        <td className="p-2 text-slate-700">{u.org_name || "—"}</td>
                        <td className="p-2 text-slate-500">{u.email}</td>
                        <td className="p-2 text-center">{u.read
                          ? <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700" data-state="letto" data-testid={`msg-stats-state-letto-${u.user_id}`}>Letto</span>
                          : <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500" data-state="nonletto" data-testid={`msg-stats-state-nonletto-${u.user_id}`}>Non letto</span>}</td>
                        <td className="p-2 text-slate-500">{u.read_at ? fmt(u.read_at) : "—"}</td>
                      </tr>
                    ))}
                    {(stats.users || []).length === 0 && <tr><td colSpan={5} className="p-4 text-center text-slate-400 text-sm">Nessun destinatario</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* ---- Delete confirm ---- */}
      <Dialog open={!!del} onOpenChange={(o) => !o && setDel(null)}>
        <DialogContent className="w-[95vw] max-w-sm" data-testid="msg-delete-dialog">
          <DialogHeader><DialogTitle>Eliminare il messaggio?</DialogTitle><DialogDescription>«{del?.titolo}» verrà rimosso definitivamente, insieme agli stati di lettura.</DialogDescription></DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDel(null)}><X className="w-4 h-4 mr-1" />Annulla</Button>
            <Button onClick={doDelete} className="bg-red-500 hover:bg-red-600 text-white" data-testid="msg-delete-confirm"><Trash2 className="w-4 h-4 mr-1" />Elimina</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
