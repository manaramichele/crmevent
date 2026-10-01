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
import {
  ArrowLeft, Rocket, Coins, Wallet, CheckCircle2, Clock, AlertTriangle, Flame, Plus, Pencil,
  Copy, Trash2, RotateCcw, Check, FolderPlus, ListChecks,
} from "lucide-react";

const STATI = { da_fare: "Da fare", in_corso: "In corso", in_attesa: "In attesa", completata: "Completata" };
const STATO_CLS = { da_fare: "bg-slate-100 text-slate-600", in_corso: "bg-sky-50 text-sky-700", in_attesa: "bg-amber-50 text-amber-700", completata: "bg-emerald-50 text-emerald-700" };
const PRIO = { normale: "Normale", importante: "Importante", critica: "Critica" };
const PRIO_CLS = { normale: "bg-slate-100 text-slate-500", importante: "bg-indigo-50 text-indigo-700", critica: "bg-red-50 text-red-700" };
const dmy = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");
const emptyTask = { titolo: "", descrizione: "", categoria_id: "", stato: "da_fare", priorita: "normale", scadenza: "", responsabile_id: "", azienda_id: "", persona_id: "", costo_previsto: "", costo_effettivo: "", note: "" };

export default function EventPipeline() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [cats, setCats] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState({ percent: 0, completate: 0, da_fare: 0, in_ritardo: 0, critiche: 0 });
  const [persons, setPersons] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [recharge, setRecharge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [taskDlg, setTaskDlg] = useState(null); // task object or null
  const [catName, setCatName] = useState("");
  const [filters, setFilters] = useState({ categoria: "all", stato: "all", priorita: "all" });

  const loadStatus = useCallback(async () => {
    try { const { data } = await api.get(`/events/${id}/pipeline/status`); setStatus(data); return data; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [id]);

  const loadPipeline = useCallback(async () => {
    const [c, t] = await Promise.all([
      api.get(`/events/${id}/pipeline/categories`),
      api.get(`/events/${id}/pipeline/tasks`),
    ]);
    setCats(c.data); setTasks(t.data.tasks); setStats(t.data.stats);
  }, [id]);

  useEffect(() => {
    (async () => {
      const s = await loadStatus();
      if (s?.active) {
        await loadPipeline();
        api.get("/persons").then(({ data }) => setPersons(data)).catch(() => {});
        api.get("/companies").then(({ data }) => setCompanies(data)).catch(() => {});
      }
    })();
  }, [loadStatus, loadPipeline]);

  const activate = async () => {
    setBusy(true);
    try {
      await api.post(`/events/${id}/pipeline/activate`, {});
      toast.success("Pipeline attivata");
      setConfirmOpen(false);
      const s = await loadStatus();
      if (s?.active) { await loadPipeline(); }
    } catch (e) {
      if (e.response?.status === 402) { toast.error("Crediti insufficienti"); setConfirmOpen(false); setRecharge(true); }
      else toast.error(formatApiError(e.response?.data?.detail));
    }
    setBusy(false);
  };

  const saveTask = async () => {
    const t = taskDlg;
    if (!t.titolo?.trim()) { toast.error("Titolo obbligatorio"); return; }
    const payload = { ...t };
    ["costo_previsto", "costo_effettivo"].forEach((k) => { payload[k] = payload[k] === "" || payload[k] == null ? null : Number(payload[k]); });
    ["categoria_id", "responsabile_id", "azienda_id", "persona_id", "scadenza", "descrizione", "note"].forEach((k) => { if (payload[k] === "") payload[k] = null; });
    try {
      if (t.id) await api.put(`/pipeline/tasks/${t.id}`, payload);
      else await api.post(`/events/${id}/pipeline/tasks`, payload);
      setTaskDlg(null); await loadPipeline();
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
  const filtered = tasks.filter((t) =>
    (filters.categoria === "all" || t.categoria_id === filters.categoria) &&
    (filters.stato === "all" || t.stato === filters.stato) &&
    (filters.priorita === "all" || t.priorita === filters.priorita));

  if (!status) return <div className="text-slate-400 p-6">Caricamento…</div>;

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
        </div>
      ) : (
        <>
          <div className="bg-white border border-slate-200 rounded-2xl p-6" data-testid="pipeline-dashboard">
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <div className="text-xs font-bold tracking-wider text-slate-400 uppercase">Preparazione evento</div>
                <div className="text-3xl font-bold text-slate-900" data-testid="pipeline-percent">{stats.percent}% completato</div>
              </div>
              <Button onClick={() => setTaskDlg({ ...emptyTask })} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pipeline-add-task"><Plus className="w-4 h-4 mr-1.5" />Nuova attività</Button>
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
                <thead><tr className="text-left text-xs text-slate-400 uppercase tracking-wide border-b border-slate-100"><th className="py-2 pr-3">Attività</th><th className="px-3">Categoria</th><th className="px-3">Responsabile</th><th className="px-3">Scadenza</th><th className="px-3">Stato</th><th className="px-3">Priorità</th><th className="px-3"></th></tr></thead>
                <tbody>
                  {filtered.length === 0 && <tr><td colSpan={7} className="py-8 text-center text-slate-400">Nessuna attività. Creane una con "Nuova attività".</td></tr>}
                  {filtered.map((t) => (
                    <tr key={t.id} className="border-b border-slate-50 hover:bg-slate-50/50" data-testid={`pipeline-task-${t.id}`}>
                      <td className="py-2.5 pr-3 font-medium text-slate-800">{t.titolo}</td>
                      <td className="px-3 text-slate-500">{catName_[t.categoria_id] || "—"}</td>
                      <td className="px-3 text-slate-500">{t.responsabile_id ? nameOf(persons, t.responsabile_id) : "—"}</td>
                      <td className="px-3"><span className={t.late ? "text-red-600 font-semibold" : "text-slate-500"}>{dmy(t.scadenza)}{t.late && " · In ritardo"}</span></td>
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
          <DialogHeader><DialogTitle>Attiva Pipeline Evento Pro</DialogTitle><DialogDescription>Il costo viene addebitato una sola volta per questo evento.</DialogDescription></DialogHeader>
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

      {/* Dialog attività */}
      <Dialog open={!!taskDlg} onOpenChange={(o) => !o && setTaskDlg(null)}>
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
                <div className="space-y-1.5"><Label>Responsabile</Label><Select value={taskDlg.responsabile_id || "none"} onValueChange={(v) => setTaskDlg((t) => ({ ...t, responsabile_id: v === "none" ? "" : v }))}><SelectTrigger><SelectValue placeholder="—" /></SelectTrigger><SelectContent><SelectItem value="none">—</SelectItem>{persons.map((p) => <SelectItem key={p.id} value={p.id}>{`${p.nome || ""} ${p.cognome || ""}`.trim() || p.id}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label>Azienda/fornitore</Label><Select value={taskDlg.azienda_id || "none"} onValueChange={(v) => setTaskDlg((t) => ({ ...t, azienda_id: v === "none" ? "" : v }))}><SelectTrigger><SelectValue placeholder="—" /></SelectTrigger><SelectContent><SelectItem value="none">—</SelectItem>{companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale || c.nome || c.id}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-1.5"><Label>Costo previsto (€)</Label><Input type="number" value={taskDlg.costo_previsto ?? ""} onChange={(e) => setTaskDlg((t) => ({ ...t, costo_previsto: e.target.value }))} /></div>
                <div className="space-y-1.5"><Label>Costo effettivo (€)</Label><Input type="number" value={taskDlg.costo_effettivo ?? ""} onChange={(e) => setTaskDlg((t) => ({ ...t, costo_effettivo: e.target.value }))} /></div>
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

      <RechargeDialog open={recharge} onClose={() => { setRecharge(false); loadStatus(); }} />
    </div>
  );
}
