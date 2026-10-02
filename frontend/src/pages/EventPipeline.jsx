import { useEffect, useState, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RechargeDialog } from "@/components/CreditsSection";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { StaffAssignSelect } from "@/components/StaffAssignSelect";
import {
  ArrowLeft, Rocket, Coins, Wallet, CheckCircle2, Clock, AlertTriangle, Flame, Plus, Pencil,
  Copy, Trash2, RotateCcw, Check, FolderPlus, ListChecks, LayoutTemplate, CalendarClock, RefreshCw,
  ExternalLink, Layers, MoreHorizontal, ArrowUp, ArrowDown, ArrowUpDown,
} from "lucide-react";

const STATI = { da_fare: "Da fare", in_corso: "In corso", in_attesa: "In attesa", completata: "Completata" };
const STATO_CLS = { da_fare: "bg-slate-100 text-slate-600", in_corso: "bg-sky-50 text-sky-700", in_attesa: "bg-amber-50 text-amber-700", completata: "bg-emerald-50 text-emerald-700" };
const PRIO = { normale: "Normale", importante: "Importante", critica: "Critica" };
const PRIO_CLS = { normale: "bg-slate-100 text-slate-500", importante: "bg-indigo-50 text-indigo-700", critica: "bg-red-50 text-red-700" };
const dmy = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");
const CRM_NAV = {
  staff: { label: "Staff e volontari", to: () => `/persone` },
  volunteers: { label: "Staff e volontari", to: () => `/persone` },
  persons: { label: "Persone", to: () => `/persone` },
  companies: { label: "Aziende", to: () => `/aziende` },
  sponsors: { label: "Sponsor & Partner", to: (id) => `/sponsor?evento=${id}` },
  hospitality: { label: "Ospitalità & Pasti", to: (id) => `/ospitalita?evento=${id}` },
  routes: { label: "Percorsi", to: (id) => `/eventi?maps=${id}` },
  briefing: { label: "Briefing", to: (id) => `/eventi/${id}/briefing` },
};
const CRM_SECTION_KEYS = ["", "staff", "volunteers", "persons", "companies", "sponsors", "hospitality", "routes", "briefing"];
const CRM_SECTION_LABELS = { "": "— Nessuna —", staff: "Staff e volontari", volunteers: "Volontari", persons: "Persone", companies: "Aziende / fornitori", sponsors: "Sponsor & Partner", hospitality: "Ospitalità & Pasti", routes: "Percorsi / GPX", briefing: "Briefing" };
const emptyTask = { titolo: "", descrizione: "", categoria_id: "", stato: "da_fare", priorita: "normale", scadenza: "", responsabile_id: "", azienda_id: "", persona_id: "", costo_previsto: "", costo_effettivo: "", note: "", crm_section: "" };

export default function EventPipeline() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [cats, setCats] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState({ percent: 0, completate: 0, da_fare: 0, in_ritardo: 0, critiche: 0 });
  const [persons, setPersons] = useState([]);
  const [staffLinks, setStaffLinks] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [recharge, setRecharge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [taskDlg, setTaskDlg] = useState(null);
  const [catName, setCatName] = useState("");
  const [filters, setFilters] = useState({ categoria: "all", stato: "all", priorita: "all" });
  const [sort, setSort] = useState({ key: null, dir: "asc" });
  // FASE 3
  const [templates, setTemplates] = useState([]);
  const [selectedTpl, setSelectedTpl] = useState(null);
  const [changeMode, setChangeMode] = useState(false); // chooser aperto per cambio modello
  const [genBusy, setGenBusy] = useState(false);
  const [dateDlg, setDateDlg] = useState(false);
  const [crmCounts, setCrmCounts] = useState({});
  const [dupOpen, setDupOpen] = useState(false);
  const [dupSources, setDupSources] = useState([]);
  const [dupSource, setDupSource] = useState(null);
  const [dupBusy, setDupBusy] = useState(false);

  const loadStatus = useCallback(async () => {
    try { const { data } = await api.get(`/events/${id}/pipeline/status`); setStatus(data); return data; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [id]);

  const loadTemplates = useCallback(async () => {
    try { const { data } = await api.get(`/events/${id}/pipeline/templates`); setTemplates(data.templates); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [id]);

  const loadPipeline = useCallback(async () => {
    const [c, t] = await Promise.all([
      api.get(`/events/${id}/pipeline/categories`),
      api.get(`/events/${id}/pipeline/tasks`),
    ]);
    setCats(c.data); setTasks(t.data.tasks); setStats(t.data.stats);
  }, [id]);

  const loadCrmCounts = useCallback(async () => {
    try { const { data } = await api.get(`/events/${id}/pipeline/crm-counts`); setCrmCounts(data.counts || {}); }
    catch { /* informativo: non bloccante */ }
  }, [id]);

  const refreshActive = useCallback(async (s) => {
    if (s?.active && s?.template_key && s?.task_count) {
      await loadPipeline();
      loadCrmCounts();
      api.get("/persons").then(({ data }) => setPersons(data)).catch(() => {});
      api.get("/staff").then(({ data }) => setStaffLinks(data)).catch(() => {});
      api.get("/companies").then(({ data }) => setCompanies(data)).catch(() => {});
      if (s.date_changed) setDateDlg(true);
    } else if (s?.active && s?.needs_template) {
      await loadTemplates();
    }
  }, [loadPipeline, loadTemplates, loadCrmCounts]);

  useEffect(() => { (async () => { const s = await loadStatus(); await refreshActive(s); })(); }, [loadStatus, refreshActive]);

  const activate = async () => {
    setBusy(true);
    try {
      await api.post(`/events/${id}/pipeline/activate`, {});
      toast.success("Pipeline attivata");
      setConfirmOpen(false);
      const s = await loadStatus();
      await refreshActive(s);
    } catch (e) {
      if (e.response?.status === 402) { toast.error("Crediti insufficienti"); setConfirmOpen(false); setRecharge(true); }
      else toast.error(formatApiError(e.response?.data?.detail));
    }
    setBusy(false);
  };

  const generate = async (confirm = false) => {
    if (!selectedTpl) { toast.error("Scegli un modello"); return; }
    setGenBusy(true);
    try {
      const { data } = await api.post(`/events/${id}/pipeline/generate`, { template_key: selectedTpl, confirm });
      toast.success(`Pipeline creata: ${data.generated} attività`);
      setChangeMode(false); setSelectedTpl(null);
      const s = await loadStatus();
      await refreshActive(s);
    } catch (e) {
      if (e.response?.status === 409) {
        if (window.confirm(e.response.data.detail + "\n\nProcedere?")) { await generate(true); setGenBusy(false); return; }
      } else toast.error(formatApiError(e.response?.data?.detail));
    }
    setGenBusy(false);
  };

  const recalc = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/events/${id}/pipeline/recalculate-deadlines`); toast.success(`Scadenze ricalcolate: ${data.recalculated} attività`); setDateDlg(false); const s = await loadStatus(); await refreshActive(s); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  const keepDeadlines = async () => {
    setBusy(true);
    try { await api.post(`/events/${id}/pipeline/keep-deadlines`); setDateDlg(false); const s = await loadStatus(); await refreshActive(s); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };

  const openChangeModel = async () => { await loadTemplates(); setSelectedTpl(status?.template_key || null); setChangeMode(true); };

  const openDup = async () => {
    try { const { data } = await api.get(`/events/${id}/pipeline/duplicatable-sources`); setDupSources(data.sources); setDupSource(null); setDupOpen(true); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const doDuplicate = async (confirm = false) => {
    if (!dupSource) { toast.error("Scegli un evento origine"); return; }
    setDupBusy(true);
    try {
      const { data } = await api.post(`/events/${id}/pipeline/duplicate-from`, { source_event_id: dupSource, confirm });
      toast.success(`Pipeline creata da edizione precedente: ${data.duplicated} attività${data.charged ? ` · −${status.cost} crediti` : ""}`);
      setDupOpen(false); setDupSource(null);
      const s = await loadStatus(); await refreshActive(s);
    } catch (e) {
      if (e.response?.status === 402) { toast.error("Crediti insufficienti"); setDupOpen(false); setRecharge(true); }
      else if (e.response?.status === 409) { if (window.confirm(e.response.data.detail + "\n\nProcedere?")) { await doDuplicate(true); setDupBusy(false); return; } }
      else toast.error(formatApiError(e.response?.data?.detail));
    }
    setDupBusy(false);
  };

  const saveTask = async () => {
    const t = taskDlg;
    if (!t.titolo?.trim()) { toast.error("Titolo obbligatorio"); return; }
    const payload = { ...t };
    ["costo_previsto", "costo_effettivo"].forEach((k) => { payload[k] = payload[k] === "" || payload[k] == null ? null : Number(payload[k]); });
    ["categoria_id", "responsabile_id", "azienda_id", "persona_id", "scadenza", "descrizione", "note", "crm_section"].forEach((k) => { if (payload[k] === "") payload[k] = null; });
    try {
      if (t.id) await api.put(`/pipeline/tasks/${t.id}`, payload);
      else await api.post(`/events/${id}/pipeline/tasks`, payload);
      setTaskDlg(null); setRespQuery(""); await loadPipeline();
      toast.success("Attività salvata");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const setTaskStato = async (t, stato) => {
    try { await api.put(`/pipeline/tasks/${t.id}`, { stato }); await loadPipeline(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const dupTask = async (t) => { try { await api.post(`/pipeline/tasks/${t.id}/duplicate`); await loadPipeline(); toast.success("Attività duplicata"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const delTask = async (t) => { if (!window.confirm("Eliminare questa attività?")) return; try { await api.delete(`/pipeline/tasks/${t.id}`); await loadPipeline(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };

  const addCat = async () => {
    const n = catName.trim(); if (!n) return;
    try { await api.post(`/events/${id}/pipeline/categories`, { name: n }); setCatName(""); await loadPipeline(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const renameCat = async (c) => {
    const n = window.prompt("Nuovo nome categoria", c.name); if (!n || !n.trim()) return;
    try { await api.put(`/pipeline/categories/${c.id}`, { name: n.trim() }); await loadPipeline(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const delCat = async (c) => {
    try { await api.delete(`/pipeline/categories/${c.id}`); await loadPipeline(); }
    catch (e) {
      if (e.response?.status === 409) {
        if (window.confirm(e.response.data.detail + " Procedere?")) {
          try { await api.delete(`/pipeline/categories/${c.id}?confirm=true`); await loadPipeline(); toast.success("Categoria e attività eliminate"); }
          catch (e2) { toast.error(formatApiError(e2.response?.data?.detail)); }
        }
      } else toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const catName_ = useMemo(() => Object.fromEntries(cats.map((c) => [c.id, c.name])), [cats]);
  const nameOf = (arr, pid) => { const p = arr.find((x) => x.id === pid); return p ? (p.nome ? `${p.nome} ${p.cognome || ""}`.trim() : p.ragione_sociale || p.name) : "—"; };
  const eventStaffIds = useMemo(() => {
    const s = new Set();
    (staffLinks || []).forEach((l) => { if (l.evento_id === id && ["staff", "collaboratore"].includes(l.categoria)) s.add(l.persona_id); });
    return s;
  }, [staffLinks, id]);
  const staffPersons = useMemo(() => (
    (persons || []).filter((p) => eventStaffIds.has(p.id))
      .sort((a, b) => `${a.cognome || ""} ${a.nome || ""}`.trim().localeCompare(`${b.cognome || ""} ${b.nome || ""}`.trim(), "it", { sensitivity: "base" }))
  ), [persons, eventStaffIds]);

  const reloadStaffData = async () => {
    const [p, s] = await Promise.all([api.get("/persons"), api.get("/staff")]);
    setPersons(p.data); setStaffLinks(s.data);
  };
  const filtered = tasks.filter((t) =>
    (filters.categoria === "all" || t.categoria_id === filters.categoria) &&
    (filters.stato === "all" || t.stato === filters.stato) &&
    (filters.priorita === "all" || t.priorita === filters.priorita));

  const PRIO_RANK = { critica: 0, importante: 1, normale: 2 };
  const toggleSort = (key) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  const sorted = useMemo(() => {
    if (!sort.key) return filtered;
    const dir = sort.dir === "asc" ? 1 : -1;
    const cmpStr = (a, b) => (a || "").localeCompare(b || "", "it", { sensitivity: "base" });
    const val = {
      titolo: (t) => t.titolo || "",
      categoria: (t) => catName_[t.categoria_id] || "",
      stato: (t) => STATI[t.stato] || "",
    };
    const arr = [...filtered];
    arr.sort((a, b) => {
      if (sort.key === "scadenza") {
        const sa = a.scadenza || "", sb = b.scadenza || "";
        if (!sa && !sb) return 0;
        if (!sa) return 1;   // vuote sempre in fondo
        if (!sb) return -1;
        return sa < sb ? -1 * dir : sa > sb ? 1 * dir : 0;
      }
      if (sort.key === "responsabile") {
        const pa = persons.find((p) => p.id === a.responsabile_id);
        const pb = persons.find((p) => p.id === b.responsabile_id);
        const ka = pa ? `${pa.cognome || ""} ${pa.nome || ""}`.trim() : "";
        const kb = pb ? `${pb.cognome || ""} ${pb.nome || ""}`.trim() : "";
        if (!ka && !kb) return 0;
        if (!ka) return 1;
        if (!kb) return -1;
        return cmpStr(ka, kb) * dir;
      }
      if (sort.key === "priorita") {
        const ra = PRIO_RANK[a.priorita] ?? 99, rb = PRIO_RANK[b.priorita] ?? 99;
        return (ra - rb) * dir;
      }
      return cmpStr(val[sort.key](a), val[sort.key](b)) * dir;
    });
    return arr;
  }, [filtered, sort, catName_, persons]);

  if (!status) return <div className="text-slate-400 p-6">Caricamento…</div>;

  const showChooser = status.active && (status.needs_template || changeMode);
  const chosen = templates.find((t) => t.key === selectedTpl);
  const dupSel = dupSources.find((s) => s.event_id === dupSource);

  return (
    <div className="max-w-6xl space-y-6" data-testid="event-pipeline-page">
      <button onClick={() => navigate("/eventi")} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800" data-testid="pipeline-back"><ArrowLeft className="w-4 h-4" />Torna agli eventi</button>

      {!status.active ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center max-w-2xl mx-auto" data-testid="pipeline-intro">
          <div className="w-14 h-14 rounded-2xl bg-tiffany-light/40 flex items-center justify-center mx-auto mb-4"><Rocket className="w-7 h-7 text-tiffany-active" /></div>
          <h1 className="text-2xl font-bold text-slate-900">Porta il tuo evento dalla pianificazione al giorno della gara</h1>
          <p className="text-slate-500 mt-3">Tieni sotto controllo tutto quello che serve: autorizzazioni, fornitori, materiali, staff, sicurezza, iscrizioni, sponsor e attività operative.</p>
          <div className="mt-6 inline-flex items-center gap-2 rounded-full bg-slate-900 text-white px-4 py-2 text-sm font-semibold"><Coins className="w-4 h-4 text-tiffany" />Attivazione Pipeline Evento Pro: {status.cost} crediti</div>
          <div className="mt-6">
            <Button onClick={() => setConfirmOpen(true)} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-activate-cta"><Rocket className="w-4 h-4 mr-1.5" />Attiva Pipeline Evento</Button>
          </div>
          <button onClick={openDup} className="mt-4 text-sm text-slate-500 hover:text-tiffany-active inline-flex items-center gap-1.5" data-testid="pipeline-dup-intro"><Layers className="w-4 h-4" />oppure crea da un'edizione precedente</button>
        </div>
      ) : showChooser ? (
        <div className="bg-white border border-slate-200 rounded-2xl p-8 max-w-3xl mx-auto" data-testid="pipeline-template-chooser">
          <div className="text-center">
            <div className="w-14 h-14 rounded-2xl bg-tiffany-light/40 flex items-center justify-center mx-auto mb-4"><LayoutTemplate className="w-7 h-7 text-tiffany-active" /></div>
            <h1 className="text-2xl font-bold text-slate-900">Che tipo di evento stai organizzando?</h1>
            <p className="text-slate-500 mt-2">{changeMode ? "Scegli un nuovo modello per rigenerare la Pipeline." : "La tua Pipeline è attiva. Scegli un modello per iniziare: genereremo automaticamente le attività con le scadenze calcolate sulla data del tuo evento."}</p>
          </div>
          {changeMode && status.task_count > 0 && (
            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" data-testid="pipeline-change-warning">
              Cambiando modello verranno <strong>eliminate le attività attuali</strong>, gli stati e le personalizzazioni. Verrà generata una nuova Pipeline dal modello selezionato.
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2 mt-6">
            {templates.map((t) => (
              <button key={t.key} onClick={() => setSelectedTpl(t.key)} className={`text-left rounded-2xl border p-5 transition-all ${selectedTpl === t.key ? "border-tiffany-active ring-2 ring-tiffany-active/30 bg-tiffany-light/10" : "border-slate-200 hover:border-slate-300"}`} data-testid={`pipeline-tpl-${t.key}`}>
                <div className="flex items-center justify-between">
                  <h3 className="font-bold text-slate-900 text-lg">{t.name}</h3>
                  {selectedTpl === t.key && <CheckCircle2 className="w-5 h-5 text-tiffany-active" />}
                </div>
                <p className="text-sm text-slate-500 mt-1">{t.description}</p>
                <div className="mt-3 inline-flex items-center gap-1.5 text-sm text-slate-600"><ListChecks className="w-4 h-4 text-tiffany-active" />{t.task_count} attività</div>
              </button>
            ))}
          </div>
          {chosen && (
            <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700" data-testid="pipeline-gen-preview">
              Verranno create <strong>{chosen.task_count} attività</strong> organizzative con scadenze calcolate sulla data del tuo evento. Potrai modificarle o eliminarle liberamente.
            </div>
          )}
          <div className="flex items-center justify-end gap-2 mt-6">
            {changeMode && <Button variant="outline" onClick={() => { setChangeMode(false); setSelectedTpl(null); }}>Annulla</Button>}
            <Button onClick={() => generate(changeMode)} disabled={!selectedTpl || genBusy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-create-cta"><Rocket className="w-4 h-4 mr-1.5" />Crea Pipeline</Button>
          </div>
        </div>
      ) : (
        <>
          {status.date_changed && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-start gap-3" data-testid="pipeline-date-banner">
              <CalendarClock className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold text-amber-900">Hai modificato la data dell'evento</div>
                <div className="text-sm text-amber-800">La Pipeline contiene attività con scadenze calcolate sulla data precedente.</div>
              </div>
              <Button size="sm" variant="outline" onClick={() => setDateDlg(true)} data-testid="pipeline-date-review">Rivedi scadenze</Button>
            </div>
          )}
          <div className="bg-white border border-slate-200 rounded-2xl p-6" data-testid="pipeline-dashboard">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <div className="text-xs font-bold tracking-wider text-slate-400 uppercase">Preparazione evento{status.template_key ? ` · modello ${status.template_key}` : ""}</div>
                <div className="text-3xl font-bold text-slate-900" data-testid="pipeline-percent">{stats.percent}% completato</div>
              </div>
              <div className="flex items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" data-testid="pipeline-actions-menu"><MoreHorizontal className="w-4 h-4 mr-1.5" />Azioni Pipeline</Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={openChangeModel} data-testid="pipeline-change-model"><RefreshCw className="w-4 h-4 mr-2" />Cambia modello</DropdownMenuItem>
                    <DropdownMenuItem onClick={openDup} data-testid="pipeline-duplicate-action"><Layers className="w-4 h-4 mr-2" />Crea da edizione precedente</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button onClick={() => setTaskDlg({ ...emptyTask })} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-add-task"><Plus className="w-4 h-4 mr-1.5" />Nuova attività</Button>
              </div>
            </div>
            <div className="mt-3 h-2.5 rounded-full bg-slate-100 overflow-hidden"><div className="h-full bg-emerald-500 transition-all" style={{ width: `${stats.percent}%` }} /></div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5">
              {[["Completate", stats.completate, CheckCircle2, "text-emerald-600"], ["Da fare", stats.da_fare, Clock, "text-slate-500"], ["In ritardo", stats.in_ritardo, AlertTriangle, "text-amber-600"], ["Critiche", stats.critiche, Flame, "text-red-600"]].map(([lbl, val, Icon, cls]) => (
                <div key={lbl} className="rounded-xl border border-slate-200 p-3" data-testid={`pipeline-stat-${lbl}`}>
                  <div className={`flex items-center gap-1.5 text-xs font-semibold ${cls}`}><Icon className="w-4 h-4" />{lbl}</div>
                  <div className="text-2xl font-bold text-slate-900 mt-1">{val}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl p-6">
            <div className="flex items-center gap-2 mb-3"><ListChecks className="w-5 h-5 text-tiffany-active" /><h2 className="font-semibold text-slate-800">Categorie</h2></div>
            <div className="flex flex-wrap gap-2 mb-3">
              {cats.map((c) => (
                <span key={c.id} className="group inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700" data-testid={`pipeline-cat-${c.id}`}>
                  {c.name}
                  <button onClick={() => renameCat(c)} className="opacity-50 hover:opacity-100"><Pencil className="w-3 h-3" /></button>
                  <button onClick={() => delCat(c)} className="opacity-50 hover:opacity-100 text-red-600"><Trash2 className="w-3 h-3" /></button>
                </span>
              ))}
            </div>
            <div className="flex gap-2 max-w-sm">
              <Input value={catName} onChange={(e) => setCatName(e.target.value)} placeholder="Nuova categoria" data-testid="pipeline-cat-input" />
              <Button variant="outline" onClick={addCat} data-testid="pipeline-cat-add"><FolderPlus className="w-4 h-4" /></Button>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl p-6">
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <h2 className="font-semibold text-slate-800 mr-auto">Attività</h2>
              <Select value={filters.categoria} onValueChange={(v) => setFilters((f) => ({ ...f, categoria: v }))}><SelectTrigger className="w-44" data-testid="filter-categoria"><SelectValue placeholder="Categoria" /></SelectTrigger><SelectContent><SelectItem value="all">Tutte le categorie</SelectItem>{cats.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>
              <Select value={filters.stato} onValueChange={(v) => setFilters((f) => ({ ...f, stato: v }))}><SelectTrigger className="w-36" data-testid="filter-stato"><SelectValue placeholder="Stato" /></SelectTrigger><SelectContent><SelectItem value="all">Tutti gli stati</SelectItem>{Object.entries(STATI).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select>
              <Select value={filters.priorita} onValueChange={(v) => setFilters((f) => ({ ...f, priorita: v }))}><SelectTrigger className="w-36" data-testid="filter-priorita"><SelectValue placeholder="Priorità" /></SelectTrigger><SelectContent><SelectItem value="all">Tutte le priorità</SelectItem>{Object.entries(PRIO).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="pipeline-tasks-table">
                <thead><tr className="text-left text-xs text-slate-400 uppercase tracking-wide border-b border-slate-100">
                  {[["titolo", "Attività"], ["categoria", "Categoria"], ["responsabile", "Responsabile"], ["scadenza", "Scadenza"], ["stato", "Stato"], ["priorita", "Priorità"]].map(([key, label], i) => (
                    <th key={key} className={`${i === 0 ? "py-2 pr-3" : "px-3"} select-none cursor-pointer group`} onClick={() => toggleSort(key)} data-testid={`sort-${key}`}>
                      <span className={`inline-flex items-center gap-1 ${sort.key === key ? "text-slate-700" : "group-hover:text-slate-600"}`}>{label}
                        {sort.key === key ? (sort.dir === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />) : <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-40" />}
                      </span>
                    </th>
                  ))}
                  <th className="px-3"></th>
                </tr></thead>
                <tbody>
                  {sorted.length === 0 && <tr><td colSpan={7} className="py-8 text-center text-slate-400">Nessuna attività. Creane una con "Nuova attività".</td></tr>}
                  {sorted.map((t) => (
                    <tr key={t.id} className="border-b border-slate-50 hover:bg-slate-50/50" data-testid={`pipeline-task-${t.id}`}>
                      <td className="py-2.5 pr-3 font-medium text-slate-800">
                        {t.titolo}
                        {t.crm_section && CRM_NAV[t.crm_section] && (
                          <button onClick={() => navigate(CRM_NAV[t.crm_section].to(id))} className="mt-0.5 flex items-center gap-1 text-xs text-tiffany-active hover:underline font-normal" data-testid={`task-crmlink-${t.id}`}>
                            Vai a {CRM_NAV[t.crm_section].label}<ExternalLink className="w-3 h-3" />
                            {crmCounts[t.crm_section] && <span className="text-slate-400">· {crmCounts[t.crm_section].count} {crmCounts[t.crm_section].label}</span>}
                          </button>
                        )}
                      </td>
                      <td className="px-3 text-slate-500">{catName_[t.categoria_id] || "—"}</td>
                      <td className="px-3 text-slate-500">{t.responsabile_id ? nameOf(persons, t.responsabile_id) : "—"}</td>
                      <td className="px-3"><span className={t.late ? "text-red-600 font-semibold" : "text-slate-500"}>{dmy(t.scadenza)}{t.late && " · In ritardo"}{t.due_date_overridden && <span title="Scadenza modificata manualmente" className="ml-1 text-[10px] text-indigo-600">✎</span>}</span></td>
                      <td className="px-3"><span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${STATO_CLS[t.stato]}`}>{STATI[t.stato]}</span></td>
                      <td className="px-3"><span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PRIO_CLS[t.priorita]}`}>{PRIO[t.priorita]}</span></td>
                      <td className="px-3">
                        <div className="flex items-center gap-1 justify-end">
                          {t.stato !== "completata"
                            ? <button title="Completa" onClick={() => setTaskStato(t, "completata")} className="p-1 text-emerald-600 hover:bg-emerald-50 rounded" data-testid={`task-complete-${t.id}`}><Check className="w-4 h-4" /></button>
                            : <button title="Riapri" onClick={() => setTaskStato(t, "da_fare")} className="p-1 text-slate-500 hover:bg-slate-100 rounded" data-testid={`task-reopen-${t.id}`}><RotateCcw className="w-4 h-4" /></button>}
                          <button title="Modifica" onClick={() => setTaskDlg({ ...emptyTask, ...t })} className="p-1 text-slate-500 hover:bg-slate-100 rounded" data-testid={`task-edit-${t.id}`}><Pencil className="w-4 h-4" /></button>
                          <button title="Duplica" onClick={() => dupTask(t)} className="p-1 text-slate-500 hover:bg-slate-100 rounded"><Copy className="w-4 h-4" /></button>
                          <button title="Elimina" onClick={() => delTask(t)} className="p-1 text-red-600 hover:bg-red-50 rounded"><Trash2 className="w-4 h-4" /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Conferma attivazione */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="max-w-sm" data-testid="pipeline-confirm-dialog">
          <DialogHeader><DialogTitle>Attiva Pipeline Evento Pro</DialogTitle><DialogDescription>Il costo viene addebitato una sola volta per questo evento. Dopo l'attivazione sceglierai il modello.</DialogDescription></DialogHeader>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">Crediti disponibili</span><span className="font-semibold">{status.balance}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Costo attivazione</span><span className="font-semibold">{status.cost}</span></div>
            <div className="flex justify-between border-t pt-2"><span className="text-slate-500">Saldo dopo attivazione</span><span className="font-semibold">{status.balance_after}</span></div>
          </div>
          {!status.sufficient && <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800 mt-2">Non hai crediti sufficienti per attivare la Pipeline Evento.</div>}
          <DialogFooter className="mt-3">
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>Annulla</Button>
            {status.sufficient
              ? <Button onClick={activate} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-confirm-activate"><Coins className="w-4 h-4 mr-1.5" />Attiva per {status.cost} crediti</Button>
              : <Button onClick={() => { setConfirmOpen(false); setRecharge(true); }} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-confirm-recharge"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog cambio data evento */}
      <Dialog open={dateDlg} onOpenChange={setDateDlg}>
        <DialogContent className="max-w-md" data-testid="pipeline-date-dialog">
          <DialogHeader><DialogTitle>Hai modificato la data dell'evento</DialogTitle><DialogDescription>Vuoi ricalcolare le scadenze della Pipeline sulla nuova data? Verrà mantenuto lo stesso numero di giorni relativo a ciascuna attività.</DialogDescription></DialogHeader>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">Le scadenze modificate manualmente verranno mantenute.</div>
          <DialogFooter className="mt-2">
            <Button variant="outline" onClick={keepDeadlines} disabled={busy} data-testid="pipeline-keep-deadlines">Mantieni le scadenze attuali</Button>
            <Button onClick={recalc} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-recalc-deadlines"><RefreshCw className="w-4 h-4 mr-1.5" />Ricalcola le scadenze</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog attività */}
      <Dialog open={!!taskDlg} onOpenChange={(o) => { if (!o) { setTaskDlg(null); setRespQuery(""); } }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="pipeline-task-dialog">
          <DialogHeader><DialogTitle>{taskDlg?.id ? "Modifica attività" : "Nuova attività"}</DialogTitle></DialogHeader>
          {taskDlg && (
            <div className="space-y-3">
              <div className="space-y-1.5"><Label>Titolo *</Label><Input value={taskDlg.titolo} onChange={(e) => setTaskDlg((t) => ({ ...t, titolo: e.target.value }))} data-testid="task-titolo" /></div>
              <div className="space-y-1.5"><Label>Descrizione</Label><Textarea rows={2} value={taskDlg.descrizione || ""} onChange={(e) => setTaskDlg((t) => ({ ...t, descrizione: e.target.value }))} /></div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Categoria</Label><Select value={taskDlg.categoria_id || "none"} onValueChange={(v) => setTaskDlg((t) => ({ ...t, categoria_id: v === "none" ? "" : v }))}><SelectTrigger data-testid="task-categoria"><SelectValue placeholder="—" /></SelectTrigger><SelectContent><SelectItem value="none">—</SelectItem>{cats.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label>Scadenza</Label><Input type="date" value={taskDlg.scadenza || ""} onChange={(e) => setTaskDlg((t) => ({ ...t, scadenza: e.target.value }))} data-testid="task-scadenza" /></div>
                <div className="space-y-1.5"><Label>Stato</Label><Select value={taskDlg.stato} onValueChange={(v) => setTaskDlg((t) => ({ ...t, stato: v }))}><SelectTrigger data-testid="task-stato"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(STATI).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label>Priorità</Label><Select value={taskDlg.priorita} onValueChange={(v) => setTaskDlg((t) => ({ ...t, priorita: v }))}><SelectTrigger data-testid="task-priorita"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(PRIO).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label>Responsabile <span className="text-xs font-normal text-slate-400">(solo Staff dell'evento)</span></Label>
                  <StaffAssignSelect eventoId={id} staffPersons={staffPersons} allPersons={persons} value={taskDlg.responsabile_id || null}
                    onChange={(pid) => setTaskDlg((t) => ({ ...t, responsabile_id: pid || "" }))} onStaffAdded={reloadStaffData} align="start" triggerTestid="task-responsabile" />
                </div>
                <div className="space-y-1.5"><Label>Azienda/fornitore</Label><Select value={taskDlg.azienda_id || "none"} onValueChange={(v) => setTaskDlg((t) => ({ ...t, azienda_id: v === "none" ? "" : v }))}><SelectTrigger><SelectValue placeholder="—" /></SelectTrigger><SelectContent><SelectItem value="none">—</SelectItem>{companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale || c.nome || c.id}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label>Costo previsto (€)</Label><Input type="number" value={taskDlg.costo_previsto ?? ""} onChange={(e) => setTaskDlg((t) => ({ ...t, costo_previsto: e.target.value }))} /></div>
                <div className="space-y-1.5"><Label>Costo effettivo (€)</Label><Input type="number" value={taskDlg.costo_effettivo ?? ""} onChange={(e) => setTaskDlg((t) => ({ ...t, costo_effettivo: e.target.value }))} /></div>
                <div className="space-y-1.5 col-span-2"><Label>Sezione CRMEvent collegata</Label><Select value={taskDlg.crm_section || "none"} onValueChange={(v) => setTaskDlg((t) => ({ ...t, crm_section: v === "none" ? "" : v }))}><SelectTrigger data-testid="task-crm-section"><SelectValue placeholder="— Nessuna —" /></SelectTrigger><SelectContent>{CRM_SECTION_KEYS.map((k) => <SelectItem key={k || "none"} value={k || "none"}>{CRM_SECTION_LABELS[k]}</SelectItem>)}</SelectContent></Select></div>
              </div>
              <div className="space-y-1.5"><Label>Note</Label><Textarea rows={2} value={taskDlg.note || ""} onChange={(e) => setTaskDlg((t) => ({ ...t, note: e.target.value }))} /></div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setTaskDlg(null)}>Annulla</Button>
            <Button onClick={saveTask} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="task-save">Salva</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={dupOpen} onOpenChange={setDupOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="pipeline-dup-dialog">
          <DialogHeader><DialogTitle>Crea da edizione precedente</DialogTitle><DialogDescription>Copia categorie e attività da una Pipeline di un altro evento della tua organizzazione. Le scadenze verranno ricalcolate sulla data di questo evento.</DialogDescription></DialogHeader>
          {dupSources.length === 0 ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500" data-testid="pipeline-dup-empty">Nessuna Pipeline disponibile da copiare. Attiva e configura prima la Pipeline di un altro evento.</div>
          ) : (
            <div className="space-y-2">
              {dupSources.map((s) => (
                <button key={s.event_id} onClick={() => setDupSource(s.event_id)} className={`w-full text-left rounded-xl border p-3 transition-all ${dupSource === s.event_id ? "border-tiffany-active ring-2 ring-tiffany-active/30 bg-tiffany-light/10" : "border-slate-200 hover:border-slate-300"}`} data-testid={`pipeline-dup-src-${s.event_id}`}>
                  <div className="flex items-center justify-between"><span className="font-semibold text-slate-800">{s.event_name}</span>{dupSource === s.event_id && <CheckCircle2 className="w-4 h-4 text-tiffany-active" />}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{s.data_inizio ? dmy(s.data_inizio) : "senza data"} · {s.task_count} attività{s.template_key ? ` · modello ${s.template_key}` : ""}</div>
                </button>
              ))}
            </div>
          )}
          {dupSel && (
            <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm space-y-1" data-testid="pipeline-dup-summary">
              <div className="flex justify-between"><span className="text-slate-500">Pipeline origine</span><span className="font-semibold">{dupSel.event_name}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Nuovo evento</span><span className="font-semibold">{status.event_name}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Attività da copiare</span><span className="font-semibold">{dupSel.task_count}</span></div>
              {!status.active && (<>
                <div className="border-t border-slate-200 my-2" />
                <div className="flex items-center gap-1.5 text-slate-700 font-semibold"><Coins className="w-4 h-4 text-tiffany-active" />Attivazione Pipeline Evento Pro: {status.cost} crediti</div>
                <div className="flex justify-between"><span className="text-slate-500">Saldo disponibile</span><span className="font-semibold">{status.balance}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Saldo dopo attivazione</span><span className="font-semibold">{status.balance_after}</span></div>
                {!status.sufficient && <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-amber-800">Crediti insufficienti per attivare la Pipeline su questo evento.</div>}
              </>)}
              {status.active && <div className="text-xs text-emerald-700">La Pipeline di questo evento è già attiva: la copia non consuma crediti.</div>}
            </div>
          )}
          <DialogFooter className="mt-3">
            <Button variant="outline" onClick={() => setDupOpen(false)}>Annulla</Button>
            {(!status.active && !status.sufficient)
              ? <Button onClick={() => { setDupOpen(false); setRecharge(true); }} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-dup-recharge"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>
              : <Button onClick={() => doDuplicate(false)} disabled={!dupSource || dupBusy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-dup-confirm"><Layers className="w-4 h-4 mr-1.5" />Crea Pipeline</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RechargeDialog open={recharge} onClose={() => { setRecharge(false); loadStatus(); }} />
    </div>
  );
}
