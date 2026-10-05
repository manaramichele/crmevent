import { useEffect, useState, useCallback, useRef } from "react";
import api from "@/lib/platformApi";
import { formatApiError } from "@/lib/api";
import { utcIsoToRomeParts, romePartsToUtcIso, formatRome, nowRomeParts } from "@/lib/datetime";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Sparkles, CalendarPlus, Bot, Loader2, Pencil, CheckCircle2, Clock, Trash2,
  RefreshCw, ImagePlus, FileText, Images, Upload, Instagram, Star, Coins, Wallet,
} from "lucide-react";
import { RechargeDialog } from "@/components/CreditsSection";

const FIELD = "w-full h-10 px-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm";
const AREA = "w-full px-3 py-2 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm";

const STATUS_COLORS = {
  draft: "bg-slate-100 text-slate-600", pending_approval: "bg-amber-100 text-amber-700",
  approved: "bg-blue-100 text-blue-700", scheduled: "bg-tiffany-light text-tiffany-fg",
  published: "bg-green-100 text-green-700", error: "bg-red-100 text-red-700",
};

const STAT_CARDS = [
  { key: "draft", label: "Bozze" }, { key: "pending_approval", label: "Da approvare" },
  { key: "approved", label: "Approvati" }, { key: "scheduled", label: "Programmati" },
  { key: "published", label: "Pubblicati" },
];

const csv = (v) => (Array.isArray(v) ? v.join(" ") : v || "");
const toTags = (s) => (s || "").split(/[\s,]+/).map((x) => x.trim()).filter(Boolean).map((h) => (h.startsWith("#") ? h : `#${h}`));

function Stat({ label, value, active, onClick }) {
  return (
    <button onClick={onClick} data-testid={`stat-${label}`}
      className={`rounded-xl border p-4 text-left transition-all ${active ? "border-tiffany bg-tiffany-light/40" : "border-slate-200 bg-white hover:border-slate-300"}`}>
      <div className="text-2xl font-bold text-slate-900">{value}</div>
      <div className="text-xs text-slate-500 mt-1">{label}</div>
    </button>
  );
}

export default function Social() {
  const [tab, setTab] = useState("contenuti");
  const [meta, setMeta] = useState({ statuses: [], status_labels: {}, categories: [], formats: [], events: [] });
  const [dash, setDash] = useState({ counts: {}, upcoming: [], total: 0 });
  const [posts, setPosts] = useState([]);
  const [filter, setFilter] = useState(null);
  const [loading, setLoading] = useState(true);

  const [aiOpen, setAiOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [genBusy, setGenBusy] = useState(false);

  // FASE E.1 — trasparenza consumi crediti (servizio ai_content, costo dal backend)
  const [svcCost, setSvcCost] = useState(null); // {cost, will_charge, balance}
  const [rechargeOpen, setRechargeOpen] = useState(false);
  const [insuff, setInsuff] = useState(null); // {cost, balance}
  const loadCost = useCallback(async () => {
    try {
      const { data } = await api.post("/credits/estimate", { service_key: "ai_content", quantity: 1 });
      setSvcCost(data);
    } catch { /* non bloccare la UI se l'estimate fallisce */ }
  }, []);
  useEffect(() => { loadCost(); }, [loadCost]);
  const afterGen = (label) => {
    const used = svcCost?.will_charge ? ` · ${svcCost.cost} ${svcCost.cost === 1 ? "credito utilizzato" : "crediti utilizzati"}` : "";
    toast.success(`${label}${used}`);
    loadCost();
  };
  const handleCreditError = (e) => {
    if (e?.response?.status === 402) {
      setInsuff({ cost: svcCost?.cost ?? null, balance: svcCost?.balance ?? null });
      loadCost();
      return true;
    }
    return false;
  };

  const [media, setMedia] = useState([]);
  const [creative, setCreative] = useState(null);
  const [creativeBusy, setCreativeBusy] = useState(false);
  const [igOpen, setIgOpen] = useState(false);
  const creativeInputRef = useRef(null);
  const [schedDate, setSchedDate] = useState("");
  const [schedTime, setSchedTime] = useState("");

  const igAccounts = (dash.accounts || []).filter((a) => a.platform === "instagram" && a.connected && a.ig_user_id);
  const saveAccount = async (accId) => {
    setEditing((p) => ({ ...p, account_id: accId }));
    try { await api.put(`/social/posts/${editing.id}`, { account_id: accId }); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  // Keep the Rome date/time fields in sync with the post being edited.
  useEffect(() => {
    if (editing?.id) {
      const { date, time } = utcIsoToRomeParts(editing.scheduled_at);
      setSchedDate(date); setSchedTime(time);
    } else { setSchedDate(""); setSchedTime(""); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing?.id]);

  const applySchedule = (dateStr, timeStr) => {
    setSchedDate(dateStr || ""); setSchedTime(timeStr || "");
    if (dateStr && timeStr) {
      let iso = romePartsToUtcIso(dateStr, timeStr);
      if (new Date(iso).getTime() < Date.now()) {
        const n = nowRomeParts();
        setSchedDate(n.date); setSchedTime(n.time);
        iso = romePartsToUtcIso(n.date, n.time);
        toast.info("Data/ora nel passato non consentita: impostato l'orario attuale");
      }
      setEditing((prev) => ({ ...prev, scheduled_at: iso }));
    } else {
      setEditing((prev) => ({ ...prev, scheduled_at: "" }));
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, d, p] = await Promise.all([
        api.get("/social/meta"), api.get("/social/dashboard"),
        api.get("/social/posts", { params: filter ? { status: filter } : {} }),
      ]);
      setMeta(m.data); setDash(d.data); setPosts(p.data);
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    setLoading(false);
  }, [filter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === "media") api.get("/social/media").then(({ data }) => setMedia(data)).catch(() => {}); }, [tab]);

  useEffect(() => {
    if (!editing) { setCreative(null); return; }
    if (editing.creative_media_id) {
      api.get("/social/media", { params: { category: "creative" } }).then(({ data }) => {
        const m = data.find((x) => x.id === editing.creative_media_id);
        setCreative(m ? { url: m.url } : null);
      }).catch(() => setCreative(null));
    } else setCreative(null);
  }, [editing?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const uploadCreative = async (fileObj) => {
    if (!fileObj) return;
    setCreativeBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", fileObj);
      const { data } = await api.post(`/social/posts/${editing.id}/creative/upload`, fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      setCreative({ url: data.url + "?t=" + Date.now() });
      setEditing(data.post);
      toast.success("Creatività caricata");
      load();
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    setCreativeBusy(false);
  };
  const removeCreative = async () => {
    if (!window.confirm("Eliminare la creatività di questo post?")) return;
    try {
      const { data } = await api.delete(`/social/posts/${editing.id}/creative`);
      setCreative(null); setEditing(data);
      toast.success("Creatività eliminata");
      load();
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const catLabel = (c) => (c || "").replace(/_/g, " ");

  // ---- AI single post ----
  const [aiForm, setAiForm] = useState({ topic: "", category: "", event_id: "", extra_instructions: "" });
  const generate = async () => {
    setGenBusy(true);
    try {
      const { data } = await api.post("/social/generate", {
        topic: aiForm.topic || undefined, category: aiForm.category || undefined,
        event_id: aiForm.event_id || undefined, extra_instructions: aiForm.extra_instructions || undefined,
      });
      toast.success("Contenuto generato");
      setAiOpen(false); setAiForm({ topic: "", category: "", event_id: "", extra_instructions: "" });
      setEditing(data); load(); afterGen("Contenuto generato");
    } catch (e) { if (!handleCreditError(e)) toast.error(formatApiError(e?.response?.data?.detail)); }
    setGenBusy(false);
  };

  // ---- Editorial plan ----
  const [planForm, setPlanForm] = useState({ date_from: "", date_to: "", posts_per_week: 3, goal: "", event_id: "" });
  const genPlan = async () => {
    if (!planForm.date_from || !planForm.date_to) { toast.error("Indica periodo di inizio e fine"); return; }
    setGenBusy(true);
    try {
      const { data } = await api.post("/social/plan/generate", {
        date_from: planForm.date_from, date_to: planForm.date_to,
        posts_per_week: Number(planForm.posts_per_week) || 3,
        goal: planForm.goal || undefined, event_id: planForm.event_id || undefined,
      });
      toast.success(`Piano editoriale generato · ${data.count} contenuti`);
      setPlanOpen(false); load(); afterGen("Piano editoriale generato");
    } catch (e) { if (!handleCreditError(e)) toast.error(formatApiError(e?.response?.data?.detail)); }
    setGenBusy(false);
  };

  // ---- Post actions ----
  const savePost = async () => {
    try {
      const body = {
        title: editing.title, body: editing.body, caption: editing.caption, cta: editing.cta,
        hashtags: Array.isArray(editing.hashtags) ? editing.hashtags : toTags(editing.hashtags),
        image_suggestion: editing.image_suggestion, category: editing.category, format: editing.format,
        scheduled_at: editing.scheduled_at || undefined, media_id: editing.media_id || undefined,
      };
      const { data } = await api.put(`/social/posts/${editing.id}`, body);
      toast.success("Contenuto salvato"); setEditing(data); load();
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const regenerate = async () => {
    setGenBusy(true);
    try {
      const { data } = await api.post(`/social/posts/${editing.id}/regenerate`, {});
      setEditing(data); load(); afterGen("Contenuto rigenerato");
    } catch (e) { if (!handleCreditError(e)) toast.error(formatApiError(e?.response?.data?.detail)); }
    setGenBusy(false);
  };
  const approve = async (p) => {
    try { await api.post(`/social/posts/${p.id}/approve`); toast.success("Contenuto approvato"); if (editing) setEditing({ ...editing, status: "approved" }); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const schedule = async (p) => {
    const when = editing?.scheduled_at || p.scheduled_at;
    if (!when) { toast.error("Imposta prima data e ora nel contenuto"); return; }
    try { await api.post(`/social/posts/${p.id}/schedule`, { scheduled_at: when }); toast.success("Contenuto programmato"); if (editing) setEditing({ ...editing, status: "scheduled" }); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const del = async (p) => {
    if (!window.confirm("Eliminare questo contenuto?")) return;
    try { await api.delete(`/social/posts/${p.id}`); toast.success("Contenuto eliminato"); setEditing(null); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const publishNow = async (p) => {
    if (!window.confirm("Pubblicare ORA questo contenuto su Instagram? L'azione è irreversibile.")) return;
    try {
      const { data } = await api.post(`/social/posts/${p.id}/publish`, { confirm: true });
      toast.success("Pubblicato su Instagram 🎉");
      if (editing) setEditing(data);
      load();
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  // ---- Media ----
  const [upForm, setUpForm] = useState({ name: "", category: "photo", event_id: "", description: "", tags: "" });
  const [upBusy, setUpBusy] = useState(false);
  const uploadMedia = async (file) => {
    if (!file) return;
    setUpBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", upForm.name || file.name);
      fd.append("category", upForm.category);
      if (upForm.event_id) fd.append("event_id", upForm.event_id);
      if (upForm.description) fd.append("description", upForm.description);
      if (upForm.tags) fd.append("tags", upForm.tags);
      await api.post("/social/media", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Media caricato");
      setUpForm({ name: "", category: "photo", event_id: "", description: "", tags: "" });
      api.get("/social/media").then(({ data }) => setMedia(data));
    } catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    setUpBusy(false);
  };
  const delMedia = async (m) => {
    if (!window.confirm("Eliminare questo media?")) return;
    try { await api.delete(`/social/media/${m.id}`); api.get("/social/media").then(({ data }) => setMedia(data)); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const backendUrl = "https://api.crmevent.it";

  return (
    <div className="max-w-6xl space-y-6" data-testid="social-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-900 bg-tiffany rounded-full px-2.5 py-1 mb-1" data-testid="platform-scope-badge">Marketing CRMEvent — Piattaforma</span>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><Sparkles className="w-6 h-6 text-tiffany-active" />Social</h1>
          <p className="text-slate-500 text-sm mt-1">Comunicazione ufficiale CRMEvent · indipendente dall'organizzazione attiva.{dash.brand_name ? ` · ${dash.brand_name}` : ""}</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => setPlanOpen(true)} variant="outline" data-testid="plan-open-btn"><CalendarPlus className="w-4 h-4 mr-2" />Genera piano editoriale</Button>
          <Button onClick={() => setAiOpen(true)} data-testid="create-ai-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Bot className="w-4 h-4 mr-2" />Crea con AI</Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-200">
        <button onClick={() => setTab("contenuti")} data-testid="tab-contenuti" className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 ${tab === "contenuti" ? "border-tiffany text-tiffany-fg" : "border-transparent text-slate-500"}`}><FileText className="w-4 h-4 inline mr-1" />Contenuti</button>
        <button onClick={() => setTab("media")} data-testid="tab-media" className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 ${tab === "media" ? "border-tiffany text-tiffany-fg" : "border-transparent text-slate-500"}`}><Images className="w-4 h-4 inline mr-1" />Libreria Media</button>
      </div>

      {tab === "contenuti" && (
        <>
          {/* Dashboard */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {STAT_CARDS.map((c) => (
              <Stat key={c.key} label={c.label} value={dash.counts?.[c.key] || 0}
                active={filter === c.key} onClick={() => setFilter(filter === c.key ? null : c.key)} />
            ))}
          </div>

          {/* Upcoming */}
          {dash.upcoming?.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-4" data-testid="upcoming-card">
              <div className="text-sm font-semibold text-slate-800 mb-2 flex items-center gap-2"><Clock className="w-4 h-4 text-tiffany-active" />Prossime pubblicazioni</div>
              <div className="space-y-1">
                {dash.upcoming.map((p) => (
                  <div key={p.id} className="flex items-center gap-3 text-sm py-1">
                    <span className="text-xs text-slate-400 w-32 shrink-0">{formatRome(p.scheduled_at)}</span>
                    <span className="truncate text-slate-700">{p.title || p.topic}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Posts */}
          {loading ? (
            <div className="text-center text-slate-400 py-12"><Loader2 className="w-6 h-6 animate-spin inline" /></div>
          ) : posts.length === 0 ? (
            <div className="bg-white border border-slate-200 rounded-xl p-12 text-center text-slate-400" data-testid="posts-empty">
              Nessun contenuto{filter ? " in questo stato" : ""}. Clicca "Crea con AI" per iniziare.
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="posts-grid">
              {posts.map((p) => (
                <div key={p.id} className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col gap-2" data-testid={`post-card-${p.id}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-[11px] px-2 py-0.5 rounded-full ${STATUS_COLORS[p.status]}`}>{meta.status_labels?.[p.status] || p.status}</span>
                    <span className="text-[11px] text-slate-400 capitalize">{catLabel(p.category)}</span>
                  </div>
                  {p.is_sample && <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-700 bg-amber-100 rounded-full px-2 py-0.5 w-fit" data-testid={`sample-badge-${p.id}`}><Star className="w-3 h-3" />CAMPIONE · {p.sample_label}</span>}
                  <div className="font-semibold text-slate-800 text-sm line-clamp-2">{p.title || p.topic || "Senza titolo"}</div>
                  <div className="text-xs text-slate-500 line-clamp-3 flex-1">{p.caption}</div>
                  {p.scheduled_at && <div className="text-[11px] text-slate-400">📅 {formatRome(p.scheduled_at)}</div>}
                  <div className="flex gap-1 pt-1 flex-wrap">
                    <Button size="sm" variant="outline" onClick={() => setEditing(p)} data-testid={`post-edit-${p.id}`}><Pencil className="w-3.5 h-3.5" /></Button>
                    {p.status !== "approved" && p.status !== "scheduled" && <Button size="sm" variant="outline" disabled={!p.creative_media_id} onClick={() => approve(p)} data-testid={`post-approve-${p.id}`}><CheckCircle2 className="w-3.5 h-3.5" /></Button>}
                    <Button size="sm" variant="outline" onClick={() => del(p)} data-testid={`post-delete-${p.id}`}><Trash2 className="w-3.5 h-3.5" /></Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === "media" && (
        <div className="space-y-4" data-testid="media-tab">
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
            <div className="text-sm font-semibold text-slate-800">Carica media</div>
            <div className="grid sm:grid-cols-2 gap-3">
              <input className={FIELD} placeholder="Nome" value={upForm.name} onChange={(e) => setUpForm({ ...upForm, name: e.target.value })} data-testid="media-name" />
              <select className={FIELD} value={upForm.category} onChange={(e) => setUpForm({ ...upForm, category: e.target.value })} data-testid="media-category">
                <option value="photo">Fotografia</option><option value="logo">Logo</option>
                <option value="sponsor">Immagine sponsor</option><option value="event">Immagine evento</option>
                <option value="graphic">Grafica</option>
              </select>
              <select className={FIELD} value={upForm.event_id} onChange={(e) => setUpForm({ ...upForm, event_id: e.target.value })} data-testid="media-event">
                <option value="">Nessun evento associato</option>
                {meta.events?.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
              </select>
              <input className={FIELD} placeholder="Tag (separati da virgola)" value={upForm.tags} onChange={(e) => setUpForm({ ...upForm, tags: e.target.value })} data-testid="media-tags" />
            </div>
            <input className={AREA} placeholder="Descrizione" value={upForm.description} onChange={(e) => setUpForm({ ...upForm, description: e.target.value })} data-testid="media-description" />
            <label className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold text-sm cursor-pointer w-fit" data-testid="media-upload-label">
              {upBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}Carica file
              <input type="file" className="hidden" accept="image/*" onChange={(e) => uploadMedia(e.target.files?.[0])} data-testid="media-file-input" />
            </label>
          </div>
          {media.length === 0 ? (
            <div className="text-center text-slate-400 py-8">Nessun media caricato.</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="media-grid">
              {media.map((m) => (
                <div key={m.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden" data-testid={`media-item-${m.id}`}>
                  <div className="aspect-square bg-slate-50 overflow-hidden"><img src={`${backendUrl}${m.url}`} alt={m.name} className="w-full h-full object-cover" /></div>
                  <div className="p-2">
                    <div className="text-xs font-medium text-slate-700 truncate">{m.name}</div>
                    <div className="text-[11px] text-slate-400 capitalize">{m.category}</div>
                    <button onClick={() => delMedia(m)} className="text-[11px] text-red-500 mt-1" data-testid={`media-delete-${m.id}`}>Elimina</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Crea con AI */}
      <Dialog open={aiOpen} onOpenChange={setAiOpen}>
        <DialogContent className="max-w-lg" data-testid="ai-dialog">
          <DialogHeader><DialogTitle>Crea contenuto con AI</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><label className="text-sm text-slate-600">Argomento (opzionale)</label><input className={FIELD} value={aiForm.topic} onChange={(e) => setAiForm({ ...aiForm, topic: e.target.value })} data-testid="ai-topic" placeholder="Lascia vuoto per far scegliere all'AI" /></div>
            <div><label className="text-sm text-slate-600">Categoria (opzionale)</label>
              <select className={FIELD} value={aiForm.category} onChange={(e) => setAiForm({ ...aiForm, category: e.target.value })} data-testid="ai-category">
                <option value="">Automatica</option>
                {meta.categories?.map((c) => <option key={c} value={c}>{catLabel(c)}</option>)}
              </select>
            </div>
            <div><label className="text-sm text-slate-600">Evento (opzionale — crea contenuti per l'evento)</label>
              <select className={FIELD} value={aiForm.event_id} onChange={(e) => setAiForm({ ...aiForm, event_id: e.target.value })} data-testid="ai-event">
                <option value="">Nessuno</option>
                {meta.events?.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
              </select>
            </div>
            <div><label className="text-sm text-slate-600">Istruzioni aggiuntive (opzionale)</label><textarea rows={2} className={AREA} value={aiForm.extra_instructions} onChange={(e) => setAiForm({ ...aiForm, extra_instructions: e.target.value })} data-testid="ai-extra" /></div>
          </div>
          <DialogFooter className="items-center sm:justify-between gap-2">
            <CostHint svcCost={svcCost} onRecharge={() => { setAiOpen(false); setRechargeOpen(true); }} />
            <Button onClick={generate} disabled={genBusy} data-testid="ai-generate-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">
              {genBusy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}Genera
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Piano editoriale */}
      <Dialog open={planOpen} onOpenChange={setPlanOpen}>
        <DialogContent className="max-w-lg" data-testid="plan-dialog">
          <DialogHeader><DialogTitle>Genera piano editoriale</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><label className="text-sm text-slate-600">Dal</label><input type="date" className={FIELD} value={planForm.date_from} onChange={(e) => setPlanForm({ ...planForm, date_from: e.target.value })} data-testid="plan-from" /></div>
              <div><label className="text-sm text-slate-600">Al</label><input type="date" className={FIELD} value={planForm.date_to} onChange={(e) => setPlanForm({ ...planForm, date_to: e.target.value })} data-testid="plan-to" /></div>
            </div>
            <div><label className="text-sm text-slate-600">Post a settimana</label><input type="number" min="1" max="14" className={FIELD} value={planForm.posts_per_week} onChange={(e) => setPlanForm({ ...planForm, posts_per_week: e.target.value })} data-testid="plan-ppw" /></div>
            <div><label className="text-sm text-slate-600">Obiettivo</label><input className={FIELD} value={planForm.goal} onChange={(e) => setPlanForm({ ...planForm, goal: e.target.value })} data-testid="plan-goal" placeholder="es. far conoscere CRMEvent" /></div>
            <div><label className="text-sm text-slate-600">Evento da promuovere (opzionale)</label>
              <select className={FIELD} value={planForm.event_id} onChange={(e) => setPlanForm({ ...planForm, event_id: e.target.value })} data-testid="plan-event">
                <option value="">Nessuno</option>
                {meta.events?.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
              </select>
            </div>
          </div>
          <DialogFooter className="items-center sm:justify-between gap-2">
            <CostHint svcCost={svcCost} onRecharge={() => { setPlanOpen(false); setRechargeOpen(true); }} />
            <Button onClick={genPlan} disabled={genBusy} data-testid="plan-generate-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">
              {genBusy ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CalendarPlus className="w-4 h-4 mr-2" />}Genera piano
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Editor contenuto */}
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="post-editor">
          <DialogHeader><DialogTitle>Modifica contenuto</DialogTitle></DialogHeader>
          {editing && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className={`text-[11px] px-2 py-0.5 rounded-full ${STATUS_COLORS[editing.status]}`}>{meta.status_labels?.[editing.status] || editing.status}</span>
                <span className="text-xs text-slate-400 capitalize">{catLabel(editing.category)}</span>
              </div>
              <div><label className="text-sm text-slate-600">Titolo</label><input className={FIELD} value={editing.title || ""} onChange={(e) => setEditing({ ...editing, title: e.target.value })} data-testid="edit-title" /></div>
              <div><label className="text-sm text-slate-600">Testo per la creatività</label><textarea rows={2} className={AREA} value={editing.body || ""} onChange={(e) => setEditing({ ...editing, body: e.target.value })} data-testid="edit-body" /></div>
              <div><label className="text-sm text-slate-600">Caption Instagram</label><textarea rows={4} className={AREA} value={editing.caption || ""} onChange={(e) => setEditing({ ...editing, caption: e.target.value })} data-testid="edit-caption" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="text-sm text-slate-600">CTA</label><input className={FIELD} value={editing.cta || ""} onChange={(e) => setEditing({ ...editing, cta: e.target.value })} data-testid="edit-cta" /></div>
                <div><label className="text-sm text-slate-600">Formato</label>
                  <select className={FIELD} value={editing.format || "1:1"} onChange={(e) => setEditing({ ...editing, format: e.target.value })} data-testid="edit-format">
                    {meta.formats?.map((f) => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>
              </div>
              <div><label className="text-sm text-slate-600">Hashtag</label><input className={FIELD} value={csv(editing.hashtags)} onChange={(e) => setEditing({ ...editing, hashtags: e.target.value })} data-testid="edit-hashtags" /></div>
              <div>
                <label className="text-sm text-slate-600">Data e ora pubblicazione</label>
                <div className="grid grid-cols-2 gap-3">
                  <input type="date" className={FIELD} value={schedDate} min={nowRomeParts().date}
                    onChange={(e) => applySchedule(e.target.value, schedTime)} data-testid="edit-sched-date" />
                  <input type="time" className={FIELD} value={schedTime} step="60"
                    min={schedDate && schedDate === nowRomeParts().date ? nowRomeParts().time : undefined}
                    onChange={(e) => applySchedule(schedDate, e.target.value)} data-testid="edit-sched-time" />
                </div>
                <div className="text-xs text-slate-400 mt-1" data-testid="edit-sched-display">
                  {editing.scheduled_at ? `Pubblicazione: ${formatRome(editing.scheduled_at)} (ora italiana)` : "Nessuna data impostata"}
                </div>
              </div>

              {/* Account di pubblicazione */}
              <div data-testid="account-section">
                <label className="text-sm text-slate-600">Account di pubblicazione</label>
                {igAccounts.length === 0
                  ? <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-1" data-testid="account-none">Nessun account Instagram collegato. Collega @crmevent nelle Impostazioni Social.</div>
                  : igAccounts.length === 1
                    ? <div className="flex items-center gap-2 text-sm text-slate-800 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mt-1" data-testid="account-single"><Instagram className="w-4 h-4 text-pink-600" />Account di pubblicazione: <span className="font-semibold">@{igAccounts[0].username || igAccounts[0].handle}</span></div>
                    : <select className={FIELD} value={editing.account_id || ""} onChange={(e) => saveAccount(e.target.value)} data-testid="account-select">
                        <option value="">Seleziona account…</option>
                        {igAccounts.map((a) => <option key={a.id} value={a.id}>@{a.username || a.handle}</option>)}
                      </select>}
              </div>

              {/* Creatività — upload manuale (nessuna generazione automatica) */}
              <div className="border-t border-slate-200 pt-3 space-y-3" data-testid="creative-panel">
                <div className="text-sm font-semibold text-slate-800 flex items-center gap-2"><ImagePlus className="w-4 h-4 text-tiffany-active" />Creatività</div>
                <div className="rounded-lg bg-slate-50 border border-slate-200 p-3" data-testid="creative-brief">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Brief grafico</div>
                  <div className="text-sm text-slate-700 whitespace-pre-wrap">{editing.image_brief || editing.image_suggestion || "—"}</div>
                  <div className="text-[11px] text-slate-400 mt-1">Crea la grafica esternamente (es. ChatGPT) nello stile ufficiale CRMEvent, poi caricala qui.</div>
                </div>
                {creative
                  ? <div className="space-y-1">
                      <img src={`${backendUrl}${creative.url}`} alt="creatività" className="w-full max-w-[280px] rounded-lg border border-slate-200" data-testid="creative-preview" />
                      <div className="text-[11px] text-green-700">✓ Immagine caricata{editing.creative_meta?.format ? ` · ${editing.creative_meta.format}` : ""}</div>
                    </div>
                  : <div className="text-sm text-slate-400 flex items-center gap-2" data-testid="creative-empty"><ImagePlus className="w-4 h-4" />Nessuna immagine caricata</div>}
                <input ref={creativeInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                  onChange={(e) => { uploadCreative(e.target.files?.[0]); e.target.value = ""; }} data-testid="creative-file-input" />
                <div className="flex gap-2 flex-wrap">
                  <Button onClick={() => creativeInputRef.current?.click()} disabled={creativeBusy} data-testid="creative-upload-btn" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">
                    {creativeBusy ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Upload className="w-4 h-4 mr-1" />}{creative ? "Sostituisci immagine" : "Carica immagine"}
                  </Button>
                  {creative && <a href={`${backendUrl}${creative.url}`} download target="_blank" rel="noreferrer" data-testid="creative-download" className="inline-flex items-center px-3 h-10 rounded-lg border border-slate-200 text-sm hover:bg-slate-50">Anteprima</a>}
                  {creative && <Button variant="outline" className="text-red-600" onClick={removeCreative} data-testid="creative-remove-btn"><Trash2 className="w-4 h-4 mr-1" />Elimina immagine</Button>}
                </div>
                <div className="text-[11px] text-slate-400">Formato richiesto: 1:1 (quadrato) o 4:5 (verticale) · JPG, PNG o WEBP.</div>
              </div>
            </div>
          )}
          <DialogFooter className="flex-wrap gap-2">
            {editing && (() => {
              const miss = [];
              if (!editing.creative_media_id) miss.push("creatività");
              if (!(editing.caption || "").trim()) miss.push("caption");
              if (!["1:1", "4:5"].includes(editing.format)) miss.push("formato feed (1:1 o 4:5)");
              if (igAccounts.length === 0) miss.push("account collegato");
              else if (igAccounts.length > 1 && !editing.account_id) miss.push("account selezionato");
              return miss.length
                ? <div data-testid="approve-readiness" className="w-full text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">⚠️ Prima di approvare completa: {miss.join(", ")}</div>
                : <div data-testid="approve-ready" className="w-full text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-1.5">✓ Pronto per l'approvazione</div>;
            })()}
            <Button variant="outline" onClick={() => setIgOpen(true)} data-testid="edit-igpreview"><Instagram className="w-4 h-4 mr-1" />Anteprima Instagram</Button>
            <Button variant="outline" onClick={regenerate} disabled={genBusy} data-testid="edit-regenerate"><RefreshCw className={`w-4 h-4 mr-1 ${genBusy ? "animate-spin" : ""}`} />Rigenera{svcCost?.will_charge ? ` · ${svcCost.cost} cr` : ""}</Button>
            <Button variant="outline" onClick={savePost} data-testid="edit-save"><Pencil className="w-4 h-4 mr-1" />Salva</Button>
            <Button variant="outline" onClick={() => approve(editing)} disabled={!editing?.creative_media_id || igAccounts.length === 0 || (igAccounts.length > 1 && !editing?.account_id)} data-testid="edit-approve"><CheckCircle2 className="w-4 h-4 mr-1" />Approva</Button>
            <Button variant="outline" onClick={() => schedule(editing)} data-testid="edit-schedule"><Clock className="w-4 h-4 mr-1" />Programma</Button>
            {editing && (editing.status === "approved" || editing.status === "scheduled" || editing.status === "error") && (
              <Button onClick={() => publishNow(editing)} disabled={!editing?.creative_media_id || igAccounts.length === 0 || (igAccounts.length > 1 && !editing?.account_id)} data-testid="edit-publish" className="bg-pink-600 hover:bg-pink-700 text-white"><Instagram className="w-4 h-4 mr-1" />{editing.status === "error" ? "Riprova pubblicazione" : "Pubblica ora"}</Button>
            )}
            <Button variant="outline" className="text-red-600" onClick={() => del(editing)} data-testid="edit-delete"><Trash2 className="w-4 h-4 mr-1" />Elimina</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Anteprima Instagram */}
      <Dialog open={igOpen} onOpenChange={setIgOpen}>
        <DialogContent className="max-w-sm p-0 overflow-hidden" data-testid="ig-preview-dialog">
          <DialogHeader className="px-4 pt-4"><DialogTitle>Anteprima Instagram</DialogTitle></DialogHeader>
          {editing && (
            <div className="bg-white">
              <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-100">
                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-tiffany to-tiffany-hover flex items-center justify-center text-slate-900 text-xs font-bold">{(dash.brand_name || "CR").slice(0, 2).toUpperCase()}</div>
                <div className="text-sm font-semibold text-slate-800" data-testid="ig-brand">{dash.brand_name || "CRMEvent"}</div>
              </div>
              {creative
                ? <img src={`${backendUrl}${creative.url}`} alt="post" className="w-full" data-testid="ig-image" />
                : <div className="aspect-square bg-slate-100 flex items-center justify-center text-slate-400 text-sm" data-testid="ig-no-image">Carica prima la creatività</div>}
              <div className="px-3 py-3 space-y-2 text-sm">
                <div className="text-slate-800 whitespace-pre-wrap" data-testid="ig-caption"><span className="font-semibold">{dash.brand_name || "CRMEvent"}</span> {editing.caption}</div>
                {editing.cta && <div className="text-tiffany-active font-semibold" data-testid="ig-cta">👉 {editing.cta}</div>}
                <div className="text-sky-700 text-xs" data-testid="ig-hashtags">{(Array.isArray(editing.hashtags) ? editing.hashtags : (editing.hashtags || "").split(/\s+/)).join(" ")}</div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <RechargeDialog open={rechargeOpen} onClose={() => { setRechargeOpen(false); loadCost(); }} />
      <Dialog open={!!insuff} onOpenChange={(v) => !v && setInsuff(null)}>
        <DialogContent className="max-w-sm" data-testid="insufficient-credits-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Coins className="w-5 h-5 text-amber-500" />Crediti insufficienti</DialogTitle></DialogHeader>
          <div className="text-sm text-slate-600 space-y-1">
            <p>Servono <b data-testid="insuff-cost">{insuff?.cost ?? svcCost?.cost}</b> crediti per questa operazione.</p>
            <p>Saldo disponibile: <b data-testid="insuff-balance">{insuff?.balance ?? svcCost?.balance ?? 0}</b> {(insuff?.balance ?? svcCost?.balance) === 1 ? "credito" : "crediti"}.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInsuff(null)}>Annulla</Button>
            <Button data-testid="insuff-recharge-btn" onClick={() => { setInsuff(null); setRechargeOpen(true); }} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><Wallet className="w-4 h-4 mr-1.5" />Ricarica crediti</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CostHint({ svcCost, onRecharge }) {
  if (!svcCost || !svcCost.will_charge) return null;
  const insufficient = svcCost.cost != null && svcCost.balance < svcCost.cost;
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500 mr-auto" data-testid="cost-hint">
      <span className="inline-flex items-center gap-1"><Coins className="w-3.5 h-3.5 text-tiffany-active" />Costo: <b className="text-slate-700">{svcCost.cost} {svcCost.cost === 1 ? "credito" : "crediti"}</b></span>
      <span className={insufficient ? "text-amber-600 font-semibold" : "text-slate-400"} data-testid="cost-hint-balance">· Saldo: {svcCost.balance}</span>
      {insufficient && onRecharge && <button type="button" onClick={onRecharge} className="text-tiffany-active underline font-semibold" data-testid="cost-hint-recharge">Ricarica</button>}
    </div>
  );
}
