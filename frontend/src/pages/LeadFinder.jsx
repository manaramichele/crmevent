import { useEffect, useState } from "react";
import api from "@/lib/platformApi";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Building2, Users, CalendarRange, Search, ShieldCheck, ExternalLink, GitMerge, Send, Instagram, Linkedin, Mail, Globe, Plus, Upload, Sparkles, Pencil, Trash2 } from "lucide-react";

const FIELD = "w-full h-10 px-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm";
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: ShieldCheck },
  { id: "organizers", label: "Organizzatori", icon: Building2 },
  { id: "events", label: "Eventi trovati", icon: CalendarRange },
  { id: "finder", label: "Lead Finder", icon: Search },
  { id: "review", label: "Da verificare", icon: Users },
  { id: "brevo", label: "Brevo", icon: Send },
];
const BREVO_LABEL = { non_approvato: "Non approvato", approvato: "Approvato per Brevo", in_corso: "Sincronizzazione in corso", sincronizzato: "Sincronizzato Prospect", gia_presente: "Già presente in Brevo", disiscritto_bloccato: "Disiscritto / bloccato", errore: "Errore sincronizzazione" };
const BREVO_BADGE = { sincronizzato: "bg-emerald-100 text-emerald-700", gia_presente: "bg-sky-100 text-sky-700", approvato: "bg-amber-100 text-amber-700", disiscritto_bloccato: "bg-red-100 text-red-700", errore: "bg-red-100 text-red-700", in_corso: "bg-slate-100 text-slate-600", non_approvato: "bg-slate-100 text-slate-500" };
const STATE_LABEL = { da_completare: "Da completare", da_verificare: "Da verificare", verificato: "Verificato", interessante: "Interessante", contattato: "Contattato", demo_richiesta: "Demo richiesta", trial: "Trial", cliente: "Cliente", non_interessato: "Non interessato", non_contattare: "Non contattare" };
const SCAN_STAT = [
  ["events_analyzed", "Eventi analizzati"], ["endu_reachable", "ENDU raggiungibili"],
  ["endu_with_site", "Siti ufficiali su ENDU"],
  ["endu_with_social", "Social su ENDU"], ["sites_visited", "Siti visitati"],
  ["organizers_identified", "Organizzatori identificati"], ["emails_found", "Email trovate"],
  ["instagram_found", "Instagram"], ["facebook_found", "Facebook"], ["linkedin_found", "LinkedIn"],
  ["duplicates_found", "Duplicati rilevati"], ["complete", "Record completi"],
  ["partial", "Record parziali"], ["to_verify", "Da verificare"],
];
const SCAN_BADGE = { Completo: "bg-emerald-100 text-emerald-700", Parziale: "bg-amber-100 text-amber-700", "Da verificare": "bg-slate-100 text-slate-600", Errore: "bg-red-100 text-red-700" };
const yesNo = (v) => (v ? "Sì" : "—");

function Stat({ label, value }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`lf-stat-${label}`}><div className="text-2xl font-bold text-slate-800">{value}</div><div className="text-xs text-slate-500 mt-1">{label}</div></div>;
}
function Dist({ title, data }) {
  const entries = Object.entries(data || {}).slice(0, 10);
  return <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-sm font-semibold text-slate-700 mb-2">{title}</div>{entries.length === 0 ? <div className="text-xs text-slate-400">Nessun dato</div> : entries.map(([k, v]) => <div key={k} className="flex justify-between text-sm py-0.5"><span className="text-slate-600 truncate">{k}</span><span className="font-semibold text-slate-800">{v}</span></div>)}</div>;
}

export default function LeadFinder() {
  const [tab, setTab] = useState("dashboard");
  const [dash, setDash] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [events, setEvents] = useState([]);
  const [q, setQ] = useState("");
  const [fRegion, setFRegion] = useState(""); const [fSport, setFSport] = useState(""); const [fStatus, setFStatus] = useState("");
  const [fEmail, setFEmail] = useState(false); const [fIg, setFIg] = useState(false); const [fLi, setFLi] = useState(false);
  const [detail, setDetail] = useState(null);
  const [mergeSel, setMergeSel] = useState([]);
  const [scan, setScan] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [diag, setDiag] = useState(null);
  const [diagUrl, setDiagUrl] = useState("");
  const [diagBusy, setDiagBusy] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ email: "", name: "", website: "", notes: "" });
  const [showImport, setShowImport] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importPrev, setImportPrev] = useState(null);
  const [importBusy, setImportBusy] = useState(false);
  const [brevoCfg, setBrevoCfg] = useState(null);
  const [brevoTest, setBrevoTest] = useState(null);
  const [brevoBusy, setBrevoBusy] = useState(false);
  const [syncConfirm, setSyncConfirm] = useState(null);
  const [editOrg, setEditOrg] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [delOrg, setDelOrg] = useState(null);
  const [delRel, setDelRel] = useState(null);
  const [bulkDel, setBulkDel] = useState(false);

  const openEdit = (o) => {
    setEditForm({ name: o.name || "", email: (o.emails || [])[0] || o.email || "", website: o.website || "",
      instagram_url: o.instagram_url || "", linkedin_url: o.linkedin_url || "", region: o.region || "",
      sport: (o.sports || [])[0] || "", status: o.status || "da_verificare" });
    setEditOrg(o);
  };
  const submitEdit = async () => {
    try {
      const payload = { ...editForm, _manual: true, _verified: editForm.status === "verificato" };
      await api.put(`/leadfinder/organizers/${editOrg.id}`, payload);
      toast.success("Organizzatore aggiornato"); setEditOrg(null); load();
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const askDelete = async (o) => {
    setDelOrg(o); setDelRel(null);
    try { const { data } = await api.get(`/leadfinder/organizers/${o.id}/relations`); setDelRel(data); } catch { /* ignore */ }
  };
  const doDelete = async () => {
    try { await api.delete(`/leadfinder/organizers/${delOrg.id}`); toast.success("Organizzatore eliminato"); setMergeSel((s) => s.filter((x) => x !== delOrg.id)); setDelOrg(null); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const doBulkDelete = async () => {
    try { const { data } = await api.post("/leadfinder/organizers/delete-bulk", { ids: mergeSel }); toast.success(`Eliminati ${data.deleted} organizzatori`); setBulkDel(false); setMergeSel([]); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const load = async () => {
    try {
      const [d, o, e] = await Promise.all([api.get("/leadfinder/dashboard"), api.get("/leadfinder/organizers"), api.get("/leadfinder/events")]);
      setDash(d.data); setOrgs(o.data); setEvents(e.data);
    } catch (err) { toast.error(formatApiError(err?.response?.data?.detail)); }
  };
  const loadLastScan = async () => {
    try {
      const { data } = await api.get("/leadfinder/scans");
      const last = (data || [])[0];
      if (last && last.status === "done") { const { data: full } = await api.get(`/leadfinder/scan/${last.id}`); setScan(full); }
    } catch { /* no scans yet */ }
  };
  const loadBrevo = async () => { try { const { data } = await api.get("/brevo/status"); setBrevoCfg(data); } catch { /* ignore */ } };
  useEffect(() => { load(); loadLastScan(); loadBrevo(); }, []);

  const regions = [...new Set(orgs.map((o) => o.region).filter(Boolean))].sort();
  const sports = [...new Set(events.map((e) => e.sport).filter(Boolean))].sort();

  const filtered = orgs.filter((o) => {
    if (fRegion && o.region !== fRegion) return false;
    if (fStatus && o.status !== fStatus) return false;
    if (fSport && !(o.sports || []).includes(fSport)) return false;
    if (fEmail && !(o.emails || []).length) return false;
    if (fIg && !o.instagram_url) return false;
    if (fLi && !o.linkedin_url) return false;
    if (q) { const s = q.toLowerCase(); if (!(`${o.name} ${o.city} ${o.region} ${(o.emails || []).join(" ")} ${(o.events || []).map((e) => e.name).join(" ")}`.toLowerCase().includes(s))) return false; }
    return true;
  });
  const toReview = orgs.filter((o) => o.status === "da_verificare" || o.socials_status === "da_verificare");

  const doMerge = async () => {
    if (mergeSel.length < 2) { toast.error("Seleziona almeno 2 organizzatori"); return; }
    try { await api.post("/leadfinder/organizers/merge", { primary_id: mergeSel[0], duplicate_ids: mergeSel.slice(1) }); toast.success("Duplicati uniti nel primo selezionato"); setMergeSel([]); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const setStatus = async (o, status) => {
    try { const { data } = await api.put(`/leadfinder/organizers/${o.id}`, { status, _manual: true, _verified: status === "verificato" }); setDetail(data); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const brevo = async () => { try { await api.post("/leadfinder/brevo-export", {}); } catch (e) { toast.info(formatApiError(e?.response?.data?.detail)); } };

  const startScan = async () => {
    setScanning(true); setScan(null);
    try {
      const { data } = await api.post("/leadfinder/scan-endu", {});
      const sid = data.scan_id;
      const poll = async () => {
        try {
          const { data: s } = await api.get(`/leadfinder/scan/${sid}`);
          setScan(s);
          if (s.status === "done" || s.status === "empty") {
            setScanning(false); load();
            if (s.status === "empty") toast.error(s.message || "Nessun evento acquisito"); else toast.success("Scansione ENDU completata");
            return;
          }
        } catch { /* keep polling */ }
        setTimeout(poll, 2500);
      };
      poll();
    } catch (e) { setScanning(false); toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const runDiagnose = async () => {
    setDiagBusy(true); setDiag(null);
    try { const { data } = await api.get("/leadfinder/diagnose", { params: diagUrl.trim() ? { url: diagUrl.trim() } : {} }); setDiag(data); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    finally { setDiagBusy(false); }
  };

  const submitAdd = async () => {
    if (!addForm.email.trim()) { toast.error("Email obbligatoria"); return; }
    try {
      const { data } = await api.post("/leadfinder/organizers/manual", addForm);
      if (data.status === "exists") { toast.info(`Email già presente: ${data.organizer.name || data.organizer.email}`); setDetail(data.organizer); }
      else { toast.success("Organizzatore creato in stato 'Da completare'"); }
      setShowAdd(false); setAddForm({ email: "", name: "", website: "", notes: "" }); load();
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const doPreview = async () => {
    if (!importFile) { toast.error("Seleziona un file"); return; }
    setImportBusy(true); setImportPrev(null);
    try {
      const fd = new FormData(); fd.append("file", importFile);
      const { data } = await api.post("/leadfinder/organizers/import/preview", fd);
      setImportPrev(data);
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    finally { setImportBusy(false); }
  };
  const doImport = async () => {
    if (!importPrev?.new?.length) return;
    setImportBusy(true);
    try {
      const { data } = await api.post("/leadfinder/organizers/import/confirm", { emails: importPrev.new });
      toast.success(`Importate ${data.created} nuove email${data.skipped ? ` · ${data.skipped} saltate` : ""}`);
      setShowImport(false); setImportFile(null); setImportPrev(null); load();
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    finally { setImportBusy(false); }
  };
  const enrichSelected = () => {
    toast.info("Arricchimento automatico dei selezionati in arrivo. I record 'Da completare' sono già predisposti: dominio email → sito ufficiale → organizzatore → eventi → città/regione → social → fonti.");
  };
  const approveBrevo = async () => {
    if (!mergeSel.length) return;
    try { const { data } = await api.post("/leadfinder/organizers/approve-brevo", { ids: mergeSel }); toast.success(`Approvati per Brevo: ${data.approved}${data.skipped ? ` · ${data.skipped} saltati (bloccati)` : ""}`); setMergeSel([]); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const askSync = () => {
    const approved = orgs.filter((o) => mergeSel.includes(o.id) && o.brevo_status === "approvato");
    if (!approved.length) { toast.error('Seleziona contatti in stato "Approvato per Brevo"'); return; }
    setSyncConfirm(approved.map((o) => o.id));
  };
  const doSync = async () => {
    const ids = syncConfirm; setSyncConfirm(null);
    try { const { data } = await api.post("/leadfinder/organizers/sync-brevo", { ids }); toast.success(`Sincronizzati ${data.synced} · bloccati ${data.blocked} · errori ${data.errors}${data.skipped_not_approved ? ` · ${data.skipped_not_approved} non approvati` : ""}`); setMergeSel([]); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const syncOne = async (o) => {
    if (o.brevo_status !== "approvato") { toast.error('Prima "Approva per Brevo"'); return; }
    try { const { data } = await api.post("/leadfinder/organizers/sync-brevo", { ids: [o.id] }); const r = (data.results || [])[0]; toast.success(`Brevo: ${BREVO_LABEL[r?.status] || r?.status}`); load(); const { data: fresh } = await api.get(`/leadfinder/organizers/${o.id}`); setDetail(fresh); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const testBrevo = async () => {
    setBrevoBusy(true);
    try { const { data } = await api.post("/brevo/test", {}); setBrevoTest(data); loadBrevo(); toast.success("Connessione Brevo OK"); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    finally { setBrevoBusy(false); }
  };
  const createProspectList = async () => {
    if (!window.confirm(`Creare/collegare la lista Brevo "${brevoCfg?.prospect_list_name}"?`)) return;
    try { const { data } = await api.post("/brevo/create-list", {}); toast.success(data.created ? `Lista creata (ID ${data.list_id})` : `Lista esistente collegata (ID ${data.list_id})`); loadBrevo(); testBrevo(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const createTemplate = async () => {
    if (!window.confirm('Creare il template "CRMEvent · Funnel Prospect · Email 1" in Brevo (bozza, nessun invio)?')) return;
    try { const { data } = await api.post("/brevo/create-email-template", {}); toast.success(data.created ? `Template creato in Brevo (ID ${data.template_id})` : `Template già presente (ID ${data.template_id})`); testBrevo(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const Link = ({ url, icon: Icon, label }) => url ? <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-tiffany-fg hover:underline text-sm" data-testid={`lf-link-${label}`}><Icon className="w-4 h-4" />{label}<ExternalLink className="w-3 h-3" /></a> : <span className="inline-flex items-center gap-1 text-slate-400 text-sm"><Icon className="w-4 h-4" />Da verificare</span>;

  return (
    <div className="space-y-6" data-testid="leadfinder-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Organizzatori — Lead Finder</h1>
        <p className="text-sm text-slate-500">Database proprietario degli organizzatori di eventi sportivi italiani. Fonte iniziale: ENDU. Nessun invio a Brevo in questa fase.</p>
      </div>
      <div className="flex gap-1 border-b border-slate-200 overflow-x-auto">
        {TABS.map((t) => <button key={t.id} onClick={() => setTab(t.id)} data-testid={`lf-tab-${t.id}`} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${tab === t.id ? "border-tiffany text-tiffany-fg" : "border-transparent text-slate-500 hover:text-slate-800"}`}><t.icon className="w-4 h-4" />{t.label}{t.id === "review" && toReview.length > 0 ? ` (${toReview.length})` : ""}</button>)}
      </div>

      {tab === "dashboard" && dash && (
        <div className="space-y-4" data-testid="lf-dashboard">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Organizzatori" value={dash.organizers_total} />
            <Stat label="Verificati" value={dash.organizers_verified} />
            <Stat label="Eventi censiti" value={dash.events_total} />
            <Stat label="Da verificare" value={dash.organizers_to_verify} />
            <Stat label="Con email" value={dash.with_email} />
            <Stat label="Con Instagram" value={dash.with_instagram} />
            <Stat label="Con LinkedIn" value={dash.with_linkedin} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Dist title="Per sport" data={dash.by_sport} />
            <Dist title="Per regione" data={dash.by_region} />
            <Dist title="Per fonte" data={dash.by_source} />
          </div>
        </div>
      )}

      {(tab === "organizers" || tab === "review") && (
        <div className="space-y-3" data-testid="lf-organizers">
          {tab === "organizers" && (
            <div className="flex flex-wrap gap-2 items-center">
              <div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ricerca libera…" className={`${FIELD} pl-9 w-64`} data-testid="lf-search" /></div>
              <select value={fRegion} onChange={(e) => setFRegion(e.target.value)} className={`${FIELD} w-auto`} data-testid="lf-filter-region"><option value="">Regione</option>{regions.map((r) => <option key={r}>{r}</option>)}</select>
              <select value={fSport} onChange={(e) => setFSport(e.target.value)} className={`${FIELD} w-auto`} data-testid="lf-filter-sport"><option value="">Sport</option>{sports.map((s) => <option key={s}>{s}</option>)}</select>
              <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} className={`${FIELD} w-auto`} data-testid="lf-filter-status"><option value="">Stato</option>{Object.entries(STATE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <label className="text-sm flex items-center gap-1"><input type="checkbox" checked={fEmail} onChange={(e) => setFEmail(e.target.checked)} data-testid="lf-filter-email" />Email</label>
              <label className="text-sm flex items-center gap-1"><input type="checkbox" checked={fIg} onChange={(e) => setFIg(e.target.checked)} />Instagram</label>
              <label className="text-sm flex items-center gap-1"><input type="checkbox" checked={fLi} onChange={(e) => setFLi(e.target.checked)} />LinkedIn</label>
              {mergeSel.length >= 2 && <Button size="sm" onClick={doMerge} data-testid="lf-merge-btn" className="bg-amber-500 hover:bg-amber-600 text-white"><GitMerge className="w-4 h-4 mr-1" />Unisci {mergeSel.length}</Button>}
              {mergeSel.length >= 1 && <Button size="sm" variant="outline" onClick={enrichSelected} data-testid="lf-enrich-btn"><Sparkles className="w-4 h-4 mr-1" />Arricchisci selezionati</Button>}
              {mergeSel.length >= 1 && <Button size="sm" variant="outline" onClick={approveBrevo} data-testid="lf-approve-brevo-btn"><ShieldCheck className="w-4 h-4 mr-1" />Approva per Brevo</Button>}
              {mergeSel.length >= 1 && <Button size="sm" onClick={askSync} data-testid="lf-sync-brevo-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900"><Send className="w-4 h-4 mr-1" />Sincronizza con Brevo</Button>}
              {mergeSel.length >= 1 && <Button size="sm" variant="outline" onClick={() => setBulkDel(true)} data-testid="lf-bulk-delete-btn" className="text-red-600 border-red-200 hover:bg-red-50"><Trash2 className="w-4 h-4 mr-1" />Elimina {mergeSel.length}</Button>}
              <div className="flex-1" />
              <Button size="sm" onClick={() => setShowAdd(true)} data-testid="lf-add-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900"><Plus className="w-4 h-4 mr-1" />Aggiungi organizzatore</Button>
              <Button size="sm" variant="outline" onClick={() => { setShowImport(true); setImportPrev(null); setImportFile(null); }} data-testid="lf-import-btn"><Upload className="w-4 h-4 mr-1" />Importa email</Button>
            </div>
          )}
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr>
                {tab === "organizers" && <th className="p-2"></th>}
                <th className="p-2 text-left">Organizzazione</th><th className="p-2">Eventi</th><th className="p-2">Email</th><th className="p-2">Instagram</th><th className="p-2">LinkedIn</th><th className="p-2">Regione</th><th className="p-2">Fonte</th><th className="p-2">Stato</th><th className="p-2">Brevo</th><th className="p-2">Ultima verifica</th>{tab === "organizers" && <th className="p-2">Azioni</th>}
              </tr></thead>
              <tbody>
                {(tab === "organizers" ? filtered : toReview).map((o) => (
                  <tr key={o.id} className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" data-testid={`lf-org-row-${o.id}`}>
                    {tab === "organizers" && <td className="p-2 text-center"><input type="checkbox" checked={mergeSel.includes(o.id)} onChange={(e) => setMergeSel((s) => e.target.checked ? [...s, o.id] : s.filter((x) => x !== o.id))} onClick={(ev) => ev.stopPropagation()} data-testid={`lf-merge-check-${o.id}`} /></td>}
                    <td className="p-2 font-medium text-slate-800" onClick={() => setDetail(o)}>{o.name || <span className="text-slate-500 font-normal">{o.email || "—"}</span>}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{o.events_count}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{yesNo((o.emails || []).length)}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{yesNo(o.instagram_url)}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{yesNo(o.linkedin_url)}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{o.region || "—"}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{o.source_main}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}><span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">{STATE_LABEL[o.status] || o.status}</span></td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}><span className={`text-xs px-2 py-0.5 rounded-full ${BREVO_BADGE[o.brevo_status || "non_approvato"]}`}>{BREVO_LABEL[o.brevo_status || "non_approvato"]}</span></td>
                    <td className="p-2 text-center text-xs text-slate-400" onClick={() => setDetail(o)}>{o.last_verified_at ? o.last_verified_at.slice(0, 10) : "—"}</td>
                    {tab === "organizers" && (
                      <td className="p-2 text-center" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-center gap-1">
                          <button onClick={() => openEdit(o)} data-testid={`lf-edit-${o.id}`} title="Modifica" className="p-1 text-slate-400 hover:text-tiffany-fg"><Pencil className="w-4 h-4" /></button>
                          <button onClick={() => askDelete(o)} data-testid={`lf-delete-${o.id}`} title="Elimina" className="p-1 text-slate-400 hover:text-red-500"><Trash2 className="w-4 h-4" /></button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {(tab === "organizers" ? filtered : toReview).length === 0 && <div className="p-6 text-center text-slate-400 text-sm">Nessun organizzatore</div>}
          </div>
        </div>
      )}

      {tab === "events" && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white" data-testid="lf-events">
          <table className="w-full text-sm"><thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr><th className="p-2 text-left">Evento</th><th className="p-2">Sport</th><th className="p-2">Data</th><th className="p-2">Città</th><th className="p-2">Regione</th><th className="p-2">Organizzatore</th><th className="p-2">Fonte ENDU</th></tr></thead>
            <tbody>{events.map((e) => (<tr key={e.id} className="border-t border-slate-100"><td className="p-2 font-medium text-slate-800">{e.name}</td><td className="p-2 text-center">{e.sport}</td><td className="p-2 text-center">{e.date}</td><td className="p-2 text-center">{e.city} {e.province ? `(${e.province})` : ""}</td><td className="p-2 text-center">{e.region}</td><td className="p-2 text-center">{e.organizer_name || "—"}</td><td className="p-2 text-center">{e.endu_url ? <a href={e.endu_url} target="_blank" rel="noreferrer" className="text-tiffany-fg hover:underline"><ExternalLink className="w-4 h-4 inline" /></a> : "—"}</td></tr>))}</tbody>
          </table>
          {events.length === 0 && <div className="p-6 text-center text-slate-400 text-sm">Nessun evento</div>}
        </div>
      )}

      {tab === "finder" && (
        <div className="space-y-4" data-testid="lf-finder">
          <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
            <div className="text-sm text-slate-700">Il Lead Finder ricerca organizzatori ed eventi da fonti pubbliche. <strong>Fonte attiva: ENDU.</strong></div>
            <div className="text-sm text-slate-600">Catena di scansione: <strong>ENDU → sito ufficiale → pagine rilevanti → organizzatore → contatti → social → deduplicazione → CRMEvent.</strong> I risultati vengono salvati in stato <em>Da verificare</em>: nessun dato è inventato, ogni informazione conserva la propria fonte. LinkedIn è associato solo se presente esplicitamente su ENDU o sui siti ufficiali.</div>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button onClick={startScan} disabled={scanning} data-testid="lf-scan-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900">
                <Search className="w-4 h-4 mr-1" />{scanning ? "Scansione in corso…" : "Scansiona ENDU + Arricchisci"}
              </Button>
              <Button disabled variant="outline" className="opacity-60 cursor-not-allowed" data-testid="lf-brevo-btn-disabled" onClick={brevo}><Send className="w-4 h-4 mr-1" />Esporta/Sincronizza con Brevo (non attivo)</Button>
            </div>
            {scan && (
              scan.status === "empty" ? (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2" data-testid="lf-scan-empty">
                  <strong>Nessun evento acquisito — scansione da verificare.</strong>{scan.reason ? <div className="text-xs mt-1">{scan.reason}</div> : null}
                </div>
              ) : (
                <div className="text-xs text-slate-500" data-testid="lf-scan-progress">
                  Stato: <strong>{scan.status === "done" ? "Completata" : "In corso"}</strong> — {scan.done || 0}/{scan.total || 0} eventi analizzati{scan.seeded ? ` · ${scan.seeded} eventi ENDU importati` : ""}
                </div>
              )
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3" data-testid="lf-diagnose">
            <div className="text-sm font-semibold text-slate-700">Diagnostica su 1 evento ENDU</div>
            <div className="text-xs text-slate-500">Verifica end-to-end del primo passaggio della pipeline su un singolo evento (nessun dato salvato). Lascia vuoto per usare un evento ENDU noto.</div>
            <div className="flex flex-wrap gap-2">
              <input value={diagUrl} onChange={(e) => setDiagUrl(e.target.value)} placeholder="https://www.endu.net/events/…" className={`${FIELD} flex-1 min-w-[260px]`} data-testid="lf-diagnose-url" />
              <Button variant="outline" onClick={runDiagnose} disabled={diagBusy} data-testid="lf-diagnose-btn"><ShieldCheck className="w-4 h-4 mr-1" />{diagBusy ? "Verifica…" : "Diagnostica"}</Button>
            </div>
            {diag && (
              <div className="text-xs bg-slate-50 rounded-lg border border-slate-200 p-3 space-y-1" data-testid="lf-diagnose-result">
                <div><span className="text-slate-400">URL ENDU:</span> <a href={diag.endu_url} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.endu_url}</a></div>
                <div><span className="text-slate-400">HTTP:</span> <strong className={diag.http_status === 200 ? "text-emerald-600" : "text-red-600"}>{diag.http_status ?? "—"}</strong> · {diag.bytes || 0} byte {diag.final_url && diag.final_url !== diag.endu_url ? `→ ${diag.final_url}` : ""}</div>
                <div><span className="text-slate-400">Evento:</span> {diag.name || "—"} · <span className="text-slate-400">data</span> {diag.date || "—"} · <span className="text-slate-400">città</span> {diag.city || "—"} {diag.province ? `(${diag.province})` : ""}</div>
                <div><span className="text-slate-400">Sito ufficiale:</span> {diag.official_site ? <a href={diag.official_site} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.official_site}</a> : "—"} {diag.official_reachable === false ? <span className="text-red-600">(non raggiungibile)</span> : diag.official_reachable ? <span className="text-emerald-600">(raggiungibile)</span> : null}</div>
                <hr className="my-1 border-slate-200" />
                <div><span className="text-slate-400">Organizzatore:</span> {diag.organizer || "—"} {diag.org_site ? <a href={diag.org_site} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">· sito org.</a> : ""}</div>
                <div><span className="text-slate-400">Email:</span> {diag.email_main ? <strong>{diag.email_main}</strong> : "—"}{(diag.emails || []).length > 1 ? ` (+${diag.emails.length - 1})` : ""}</div>
                <div><span className="text-slate-400">Telefono:</span> {diag.phone || "—"}</div>
                <div><span className="text-slate-400">Instagram evento (ENDU):</span> {diag.instagram_event ? <a href={diag.instagram_event} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.instagram_event}</a> : "—"}</div>
                <div><span className="text-slate-400">Instagram organizzatore (sito):</span> {diag.instagram_org ? <a href={diag.instagram_org} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.instagram_org}</a> : "—"}</div>
                <div><span className="text-slate-400">Facebook:</span> {diag.facebook ? <a href={diag.facebook} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.facebook}</a> : "—"}</div>
                <div><span className="text-slate-400">LinkedIn:</span> {diag.linkedin ? <a href={diag.linkedin} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.linkedin}</a> : "—"}</div>
                <div><span className="text-slate-400">Pagine sito analizzate ({(diag.pages_analyzed || []).length}):</span>
                  <ul className="list-disc pl-5 mt-0.5">{(diag.pages_analyzed || []).map((u, i) => <li key={i}><a href={u} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{u}</a></li>)}{(diag.pages_analyzed || []).length === 0 ? <li className="text-slate-400 list-none">—</li> : null}</ul>
                </div>
                {(diag.not_found || []).length > 0 && (
                  <div><span className="text-amber-600 font-medium">Dati non trovati:</span>
                    <ul className="list-disc pl-5 mt-0.5 text-amber-700">{diag.not_found.map((n, i) => <li key={i}>{n}</li>)}</ul>
                  </div>
                )}
                {diag.error ? <div className="text-red-600"><span className="text-slate-400">Errore:</span> {diag.error}</div> : <div className="text-emerald-600 font-medium">Pipeline ENDU → sito ufficiale → contatti OK</div>}
              </div>
            )}
          </div>

          {scan && scan.stats && Object.keys(scan.stats).length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3" data-testid="lf-scan-stats">
              {SCAN_STAT.map(([k, label]) => <Stat key={k} label={label} value={scan.stats[k] ?? 0} />)}
            </div>
          )}

          {scan && (scan.rows || []).length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white" data-testid="lf-scan-table">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-slate-500 uppercase"><tr>
                  <th className="p-2 text-left">Evento</th><th className="p-2 text-left">Organizzatore</th><th className="p-2">Sito evento</th><th className="p-2">Sito org.</th><th className="p-2">Email</th><th className="p-2">IG</th><th className="p-2">FB</th><th className="p-2">LinkedIn</th><th className="p-2">Stato</th><th className="p-2 text-left">Note</th>
                </tr></thead>
                <tbody>
                  {scan.rows.map((r, i) => (
                    <tr key={i} className="border-t border-slate-100 align-top" data-testid={`lf-scan-row-${i}`}>
                      <td className="p-2 font-medium text-slate-800">{r.endu_url ? <a href={r.endu_url} target="_blank" rel="noreferrer" className="hover:underline">{r.event}</a> : r.event}</td>
                      <td className="p-2 text-slate-700">{r.organizer_legal || r.organizer || "—"}</td>
                      <td className="p-2 text-center">{r.event_site ? <a href={r.event_site} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Globe className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center">{r.org_site ? <a href={r.org_site} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Globe className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-slate-600">{(r.emails || []).length ? (r.emails || []).join(", ") : "—"}</td>
                      <td className="p-2 text-center">{r.instagram ? <a href={r.instagram} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Instagram className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center">{r.facebook ? <a href={r.facebook} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Globe className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center">{r.linkedin ? <a href={r.linkedin} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Linkedin className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center whitespace-nowrap"><span className={`px-2 py-0.5 rounded-full ${SCAN_BADGE[r.status] || "bg-slate-100 text-slate-600"}`}>{r.status}</span>{r.duplicate_of && <div className="text-[10px] text-amber-600 mt-0.5">dup? {r.duplicate_of.name}</div>}</td>
                      <td className="p-2 text-slate-400">{r.reason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <ul className="text-xs text-slate-500 list-disc pl-5 space-y-1">
            <li>Dati a livello evento (nome, sport, città/provincia, data, URL) recuperati da ENDU.</li>
            <li>Email e social ufficiali provengono dai siti ufficiali; ogni dato conserva l'URL della pagina sorgente.</li>
            <li>La scansione massiva e i provider esterni a pagamento non sono attivi.</li>
          </ul>
        </div>
      )}

      {tab === "brevo" && (
        <div className="space-y-4" data-testid="lf-brevo">
          <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <div className="text-sm font-semibold text-slate-700">Marketing → Impostazioni → Brevo</div>
                <div className="text-xs text-slate-500">Sincronizzazione controllata dei Prospect. Il Funnel Demo esistente non viene toccato.</div>
              </div>
              <Button size="sm" onClick={testBrevo} disabled={brevoBusy} data-testid="brevo-test-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900"><ShieldCheck className="w-4 h-4 mr-1" />{brevoBusy ? "Test…" : "Test connessione"}</Button>
            </div>
            {brevoCfg && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div className="rounded-lg border border-slate-200 p-2">API key backend: <strong className={brevoCfg.configured ? "text-emerald-600" : "text-red-600"}>{brevoCfg.configured ? "Configurata" : "Non configurata"}</strong></div>
                <div className="rounded-lg border border-slate-200 p-2">Connessione: <strong>{brevoCfg.connection}</strong></div>
                <div className="rounded-lg border border-slate-200 p-2">Lista: <strong>{brevoCfg.list_name || "—"}</strong></div>
                <div className="rounded-lg border border-slate-200 p-2">listId: <strong>{brevoCfg.list_id || "—"}</strong></div>
                <div className="rounded-lg border border-slate-200 p-2 col-span-2">Ultimo test: {brevoCfg.last_test ? `${brevoCfg.last_test.at?.slice(0, 19).replace("T", " ")} · ${brevoCfg.last_test.ok ? "OK" : "errore"}` : "—"}</div>
              </div>
            )}
            {!brevoCfg?.configured && <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2">La chiave <code>BREVO_API_KEY</code> è vuota in preview (impostata nei Secrets di produzione). Il test funziona in produzione o aggiungendo una chiave in preview.</div>}
          </div>

          {brevoTest && (
            <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3 text-sm" data-testid="brevo-test-result">
              <div className="text-emerald-600 font-medium">Connessione OK{brevoTest.account_email ? ` · account ${brevoTest.account_email}` : ""}</div>
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400 mb-1">Lista Prospect "{brevoCfg?.prospect_list_name}"</div>
                {brevoTest.prospect_list_exists
                  ? <div className="text-slate-700">Trovata · listId <strong>{brevoTest.prospect_list.id}</strong></div>
                  : <div className="flex items-center gap-2 flex-wrap"><span className="text-amber-700">Non esiste ancora.</span><Button size="sm" variant="outline" onClick={createProspectList} data-testid="brevo-create-list-btn">Crea lista "{brevoCfg?.prospect_list_name}"</Button></div>}
                <div className="text-xs text-slate-400 mt-1">{brevoTest.note_demo}</div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400 mb-1">Template Email 1 "{`CRMEvent · Funnel Prospect · Email 1`}"</div>
                {brevoTest.prospect_template_exists
                  ? <div className="text-slate-700">Presente in Brevo · template ID <strong>{brevoTest.prospect_template.id}</strong></div>
                  : <div className="flex items-center gap-2 flex-wrap"><span className="text-amber-700">Non presente in Brevo.</span><Button size="sm" variant="outline" onClick={createTemplate} data-testid="brevo-create-template-btn">Crea template in Brevo (bozza)</Button></div>}
                <div className="text-xs text-slate-400 mt-1">Bozza, nessun invio. Automazione/Funnel Prospect da configurare manualmente in Brevo (le API non creano automazioni).</div>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400 mb-1">Attributi Brevo</div>
                <div className="text-slate-700">Disponibili: {(brevoTest.attributes_available || []).join(", ") || "—"}</div>
                {(brevoTest.attributes_missing || []).length > 0 && <div className="text-amber-700">Mancanti (NON creati automaticamente): {brevoTest.attributes_missing.join(", ")}</div>}
              </div>
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400 mb-1">Mittenti configurati</div>
                <ul className="text-slate-700">{(brevoTest.senders || []).map((s, i) => <li key={i}>{s.name} · {s.email} · {s.active ? "verificato" : "non verificato"}</li>)}{(brevoTest.senders || []).length === 0 ? <li className="text-slate-400">Nessun mittente</li> : null}</ul>
              </div>
              <div>
                <div className="text-xs font-semibold uppercase text-slate-400 mb-1">Tutte le liste</div>
                <ul className="text-xs text-slate-600 max-h-40 overflow-y-auto">{(brevoTest.lists || []).map((l) => <li key={l.id}>#{l.id} · {l.name}{l.name?.includes("·") ? " (Demo — non toccata)" : ""}</li>)}</ul>
              </div>
            </div>
          )}
          <ul className="text-xs text-slate-500 list-disc pl-5 space-y-1">
            <li>Nessun invio email da CRMEvent · nessuna sincronizzazione massiva · nessuna modifica al Funnel Demo.</li>
            <li>Contatti disiscritti/bloccati NON vengono reinseriti (priorità assoluta).</li>
          </ul>
        </div>
      )}

      <Dialog open={!!syncConfirm} onOpenChange={(o) => !o && setSyncConfirm(null)}>
        <DialogContent className="max-w-sm" data-testid="brevo-sync-confirm">
          <DialogHeader><DialogTitle>Conferma sincronizzazione</DialogTitle></DialogHeader>
          <div className="text-sm text-slate-700">Stai per sincronizzare <strong>{(syncConfirm || []).length}</strong> prospect con la lista <strong>"{brevoCfg?.list_name || brevoCfg?.prospect_list_name}"</strong> di Brevo. Il funnel Brevo gestirà le email.</div>
          <div className="flex justify-end gap-2 pt-2"><Button variant="outline" size="sm" onClick={() => setSyncConfirm(null)}>Annulla</Button><Button size="sm" onClick={doSync} data-testid="brevo-sync-confirm-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900">Sincronizza {(syncConfirm || []).length} prospect</Button></div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="lf-org-detail">
          {detail && (<>
            <DialogHeader><DialogTitle>{detail.name || detail.email || "Organizzatore"}</DialogTitle></DialogHeader>
            <div className="space-y-4 text-sm">
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Anagrafica</div>
                <div className="grid grid-cols-2 gap-1 text-slate-700"><div>Ragione sociale: {detail.legal_name || "—"}</div><div>Tipologia: {detail.org_type || "—"}</div><div>Città: {detail.city || "—"} {detail.province ? `(${detail.province})` : ""}</div><div>Regione: {detail.region || "—"}</div><div className="col-span-2"><Link url={detail.website} icon={Globe} label="Sito web" /></div></div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Contatti</div>
                <div className="text-slate-700">{(detail.emails || []).length ? detail.emails.map((e) => <span key={e} className="inline-flex items-center gap-1 mr-3"><Mail className="w-4 h-4" />{e}</span>) : <span className="text-slate-400 inline-flex items-center gap-1"><Mail className="w-4 h-4" />Da verificare</span>}{detail.phone ? <div>Tel: {detail.phone}</div> : null}</div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Social</div>
                <div className="flex gap-4 flex-wrap"><Link url={detail.instagram_url} icon={Instagram} label="Instagram" /><Link url={detail.linkedin_url} icon={Linkedin} label="LinkedIn" /><Link url={detail.facebook_url} icon={Globe} label="Facebook" /></div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Eventi organizzati ({(detail.events || []).length})</div>
                <ul className="space-y-1">{(detail.events || []).map((e) => <li key={e.id} className="flex items-center justify-between"><span>{e.name} · <span className="text-slate-500">{e.sport} · {e.city} · {e.date}</span></span>{e.endu_url && <a href={e.endu_url} target="_blank" rel="noreferrer" className="text-tiffany-fg"><ExternalLink className="w-3.5 h-3.5" /></a>}</li>)}</ul>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Fonti</div>
                <div className="text-slate-600">Principale: {detail.source_main} {detail.source_url && <a href={detail.source_url} target="_blank" rel="noreferrer" className="text-tiffany-fg ml-1"><ExternalLink className="w-3.5 h-3.5 inline" /></a>}</div>
                <div className="text-xs text-slate-400">Acquisito: {(detail.acquired_at || "").slice(0, 10) || "—"} · Ultima verifica: {(detail.last_verified_at || "").slice(0, 10) || "—"}</div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Stato</div>
                {detail.possibile_duplicato && <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 mb-2" data-testid="lf-detail-dup">Possibile duplicato di: <strong>{detail.possibile_duplicato.name}</strong> — verifica e usa "Unisci duplicati" se confermato.</div>}
                <select value={detail.status} onChange={(e) => setStatus(detail, e.target.value)} className={FIELD} data-testid="lf-detail-status">{Object.entries(STATE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                {detail.status === "non_contattare" && <div className="text-xs text-red-600 mt-1">"Non contattare" ha priorità e non viene sovrascritto dalle ricerche automatiche.</div>}
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Brevo</div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${BREVO_BADGE[detail.brevo_status || "non_approvato"]}`} data-testid="lf-detail-brevo-status">{BREVO_LABEL[detail.brevo_status || "non_approvato"]}</span>
                  {detail.brevo_status === "approvato" && <Button size="sm" onClick={() => syncOne(detail)} data-testid="lf-detail-sync-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900 h-7 px-2 text-xs"><Send className="w-3.5 h-3.5 mr-1" />Sincronizza con Brevo</Button>}
                </div>
                <div className="grid grid-cols-2 gap-1 text-xs text-slate-600 mt-2">
                  <div>Lista: {detail.brevo_list_id ? (brevoCfg?.list_name || detail.brevo_list_id) : "—"}</div>
                  <div>Contact ID: {detail.brevo_contact_id || "—"}</div>
                  <div className="col-span-2">Data sincronizzazione: {(detail.brevo_synced_at || "").slice(0, 19).replace("T", " ") || "—"}</div>
                  {detail.brevo_error && <div className="col-span-2 text-red-600">Errore: {detail.brevo_error}</div>}
                </div>
              </section>
            </div>
          </>)}
        </DialogContent>
      </Dialog>

      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-md" data-testid="lf-add-modal">
          <DialogHeader><DialogTitle>Aggiungi organizzatore</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div><label className="text-xs text-slate-500">Email <span className="text-red-500">*</span></label><input type="email" value={addForm.email} onChange={(e) => setAddForm((f) => ({ ...f, email: e.target.value }))} placeholder="info@organizzatore.it" className={FIELD} data-testid="lf-add-email" /></div>
            <div><label className="text-xs text-slate-500">Nome organizzatore (facoltativo)</label><input value={addForm.name} onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))} className={FIELD} data-testid="lf-add-name" /></div>
            <div><label className="text-xs text-slate-500">Sito (facoltativo)</label><input value={addForm.website} onChange={(e) => setAddForm((f) => ({ ...f, website: e.target.value }))} placeholder="https://…" className={FIELD} data-testid="lf-add-website" /></div>
            <div><label className="text-xs text-slate-500">Note (facoltativo)</label><textarea value={addForm.notes} onChange={(e) => setAddForm((f) => ({ ...f, notes: e.target.value }))} rows={2} className={`${FIELD} h-auto py-2`} data-testid="lf-add-notes" /></div>
            <p className="text-xs text-slate-400">Con la sola email il record viene creato in stato <strong>Da completare</strong>. Nessun dato viene inventato. I duplicati (email già presente) non vengono creati.</p>
            <div className="flex justify-end gap-2 pt-1"><Button variant="outline" size="sm" onClick={() => setShowAdd(false)}>Annulla</Button><Button size="sm" onClick={submitAdd} data-testid="lf-add-submit" className="bg-tiffany hover:bg-tiffany/90 text-slate-900">Salva</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showImport} onOpenChange={setShowImport}>        <DialogContent className="max-w-lg" data-testid="lf-import-modal">
          <DialogHeader><DialogTitle>Importa email</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-xs text-slate-500">Carica un file <strong>.xlsx</strong>, <strong>.xls</strong> o <strong>.csv</strong> con una colonna <code>email</code>. Non servono altre colonne.</p>
            <input type="file" accept=".xlsx,.xls,.csv" onChange={(e) => { setImportFile(e.target.files?.[0] || null); setImportPrev(null); }} className="block w-full text-sm text-slate-600 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:bg-slate-100 file:text-slate-700 file:text-sm" data-testid="lf-import-file" />
            {!importPrev && <div className="flex justify-end"><Button size="sm" onClick={doPreview} disabled={importBusy || !importFile} data-testid="lf-import-preview-btn">{importBusy ? "Analisi…" : "Analizza file"}</Button></div>}
            {importPrev && (
              <div className="space-y-2" data-testid="lf-import-preview">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded-lg bg-slate-50 border border-slate-200 p-2">Email nel file: <strong>{importPrev.total}</strong></div>
                  <div className="rounded-lg bg-slate-50 border border-slate-200 p-2">Valide: <strong>{importPrev.valid}</strong></div>
                  <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-2 text-emerald-700">Nuove: <strong>{importPrev.new_count}</strong></div>
                  <div className="rounded-lg bg-amber-50 border border-amber-200 p-2 text-amber-700">Già presenti: <strong>{importPrev.existing_count}</strong></div>
                  <div className="rounded-lg bg-slate-50 border border-slate-200 p-2">Duplicate nel file: <strong>{importPrev.dup_in_file}</strong></div>
                  <div className="rounded-lg bg-red-50 border border-red-200 p-2 text-red-700">Non valide: <strong>{importPrev.invalid_count}</strong></div>
                </div>
                {importPrev.invalid_count > 0 && (
                  <details className="text-xs" data-testid="lf-import-invalid"><summary className="cursor-pointer text-red-600">Mostra email non valide ({importPrev.invalid_count})</summary>
                    <ul className="list-disc pl-5 mt-1 max-h-32 overflow-y-auto text-slate-600">{importPrev.invalid.map((e, i) => <li key={i} className="break-all">{e || "(vuota)"}</li>)}</ul>
                  </details>
                )}
                <p className="text-xs text-slate-400">I nuovi record vengono creati in stato <strong>Da completare</strong> · origine <strong>Importazione manuale</strong> · verifica <strong>Non verificato</strong>. Nessun invio a Brevo.</p>
                <div className="flex justify-end gap-2"><Button variant="outline" size="sm" onClick={() => { setImportPrev(null); setImportFile(null); }}>Cambia file</Button><Button size="sm" onClick={doImport} disabled={importBusy || !importPrev.new_count} data-testid="lf-import-confirm-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900">{importBusy ? "Importazione…" : `Importa ${importPrev.new_count} nuove email`}</Button></div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!editOrg} onOpenChange={(o) => !o && setEditOrg(null)}>
        <DialogContent className="max-w-md" data-testid="lf-edit-modal">
          <DialogHeader><DialogTitle>Modifica organizzatore</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div><label className="text-xs text-slate-500">Nome organizzazione</label><input value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} className={FIELD} data-testid="lf-edit-name" placeholder="Nome ufficiale (non usare l'email)" /></div>
            <div><label className="text-xs text-slate-500">Email</label><input type="email" value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} className={FIELD} data-testid="lf-edit-email" /></div>
            <div><label className="text-xs text-slate-500">Sito web</label><input value={editForm.website} onChange={(e) => setEditForm((f) => ({ ...f, website: e.target.value }))} className={FIELD} data-testid="lf-edit-website" placeholder="https://…" /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className="text-xs text-slate-500">Instagram</label><input value={editForm.instagram_url} onChange={(e) => setEditForm((f) => ({ ...f, instagram_url: e.target.value }))} className={FIELD} data-testid="lf-edit-instagram" /></div>
              <div><label className="text-xs text-slate-500">LinkedIn</label><input value={editForm.linkedin_url} onChange={(e) => setEditForm((f) => ({ ...f, linkedin_url: e.target.value }))} className={FIELD} data-testid="lf-edit-linkedin" /></div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className="text-xs text-slate-500">Regione</label><input value={editForm.region} onChange={(e) => setEditForm((f) => ({ ...f, region: e.target.value }))} className={FIELD} data-testid="lf-edit-region" /></div>
              <div><label className="text-xs text-slate-500">Sport</label><input value={editForm.sport} onChange={(e) => setEditForm((f) => ({ ...f, sport: e.target.value }))} className={FIELD} data-testid="lf-edit-sport" /></div>
            </div>
            <div><label className="text-xs text-slate-500">Stato / verifica</label><select value={editForm.status} onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))} className={FIELD} data-testid="lf-edit-status">{Object.entries(STATE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
            <p className="text-xs text-slate-400">La fonte e la tracciabilità dei dati vengono mantenute. Se il nome non è disponibile lascia il campo vuoto: il record resta “Da completare”.</p>
            <div className="flex justify-end gap-2 pt-1"><Button variant="outline" size="sm" onClick={() => setEditOrg(null)}>Annulla</Button><Button size="sm" onClick={submitEdit} data-testid="lf-edit-submit" className="bg-tiffany hover:bg-tiffany/90 text-slate-900">Salva modifiche</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!delOrg} onOpenChange={(o) => !o && setDelOrg(null)}>
        <DialogContent className="max-w-md" data-testid="lf-delete-modal">
          <DialogHeader><DialogTitle>Elimina organizzatore</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm text-slate-700">
            <p>Vuoi eliminare l'organizzatore <strong>{delOrg?.name || delOrg?.email}</strong>? Questa operazione non può essere annullata.</p>
            {delRel && (delRel.events_count > 0 || delRel.brevo_synced) && (
              <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1" data-testid="lf-delete-warning">
                <div className="font-semibold">Attenzione: relazioni collegate</div>
                {delRel.events_count > 0 && <div>• {delRel.events_count} evento/i trovato/i collegato/i (verranno scollegati, non eliminati).</div>}
                {delRel.brevo_synced && <div>• Contatto sincronizzato con Brevo: <strong>NON verrà eliminato da Brevo</strong> (sono due operazioni distinte).</div>}
              </div>
            )}
            <div className="flex justify-end gap-2 pt-1"><Button variant="outline" size="sm" onClick={() => setDelOrg(null)} data-testid="lf-delete-cancel">Annulla</Button><Button size="sm" onClick={doDelete} data-testid="lf-delete-confirm" className="bg-red-500 hover:bg-red-600 text-white">Elimina</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={bulkDel} onOpenChange={setBulkDel}>
        <DialogContent className="max-w-md" data-testid="lf-bulk-delete-modal">
          <DialogHeader><DialogTitle>Elimina selezionati</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm text-slate-700">
            <p>Stai per eliminare <strong>{mergeSel.length}</strong> anagrafic{mergeSel.length === 1 ? "a" : "he"} organizzatore. Questa operazione non può essere annullata.</p>
            <p className="text-xs text-slate-500">Gli eventi collegati verranno scollegati (non eliminati). I contatti su Brevo NON vengono eliminati.</p>
            <div className="flex justify-end gap-2 pt-1"><Button variant="outline" size="sm" onClick={() => setBulkDel(false)}>Annulla</Button><Button size="sm" onClick={doBulkDelete} data-testid="lf-bulk-delete-confirm" className="bg-red-500 hover:bg-red-600 text-white">Elimina {mergeSel.length}</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
