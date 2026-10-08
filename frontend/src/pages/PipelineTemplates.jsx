import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { LayoutTemplate, Plus, Pencil, Trash2, ArrowLeft, ListChecks, Clock, Flag } from "lucide-react";

const PRIO = { normale: "Normale", importante: "Importante", critica: "Critica" };
const PRIO_CLS = { normale: "bg-slate-100 text-slate-500", importante: "bg-indigo-50 text-indigo-700", critica: "bg-red-50 text-red-700" };
const CRM_SECTIONS = ["", "staff", "volunteers", "sponsors", "hospitality", "routes", "briefing", "companies"];
const offsetLabel = (d) => { const n = Number(d) || 0; if (n === 0) return "Giorno evento"; return n < 0 ? `${Math.abs(n)} giorni prima` : `${n} giorni dopo`; };

const emptyTpl = { key: "", name: "", description: "", active: true, order: 0 };
const emptyTask = { titolo: "", descrizione: "", categoria: "", giorni_offset: 0, priorita: "normale", order: 0, active: true, crm_section: "" };

export default function PipelineTemplates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null); // template key opened for task editing
  const [detail, setDetail] = useState(null); // { template, tasks, categories }
  const [tplDlg, setTplDlg] = useState(null);
  const [taskDlg, setTaskDlg] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get("/platform/pipeline-templates"); setTemplates(data.templates); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setLoading(false);
  }, []);

  const loadDetail = useCallback(async (key) => {
    try { const { data } = await api.get(`/platform/pipeline-templates/${key}/tasks`); setDetail(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (selected) loadDetail(selected); }, [selected, loadDetail]);

  const saveTpl = async () => {
    const t = tplDlg;
    if (!t.name?.trim()) { toast.error("Nome obbligatorio"); return; }
    setBusy(true);
    try {
      if (t.key && !t._new) await api.put(`/platform/pipeline-templates/${t.key}`, { name: t.name, description: t.description, active: t.active, order: Number(t.order) || 0 });
      else await api.post("/platform/pipeline-templates", { key: t.key || undefined, name: t.name, description: t.description, active: t.active, order: Number(t.order) || 0 });
      toast.success("Modello salvato"); setTplDlg(null); await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };

  const toggleTpl = async (t) => {
    try { await api.put(`/platform/pipeline-templates/${t.key}`, { active: !t.active }); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const delTpl = async (t) => {
    if (!window.confirm(`Eliminare il modello "${t.name}" e tutte le sue attività?`)) return;
    try { await api.delete(`/platform/pipeline-templates/${t.key}`); toast.success("Modello eliminato"); if (selected === t.key) setSelected(null); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const saveTask = async () => {
    const t = taskDlg;
    if (!t.titolo?.trim()) { toast.error("Titolo obbligatorio"); return; }
    if (!t.categoria) { toast.error("Categoria obbligatoria"); return; }
    const payload = { titolo: t.titolo, descrizione: t.descrizione, categoria: t.categoria, giorni_offset: Number(t.giorni_offset) || 0, priorita: t.priorita, order: Number(t.order) || 0, active: t.active, crm_section: t.crm_section || null };
    setBusy(true);
    try {
      if (t.id) await api.put(`/platform/pipeline-template-tasks/${t.id}`, payload);
      else await api.post(`/platform/pipeline-templates/${selected}/tasks`, payload);
      toast.success("Attività salvata"); setTaskDlg(null); await loadDetail(selected); await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };

  const delTask = async (t) => {
    if (!window.confirm(`Eliminare l'attività "${t.titolo}"?`)) return;
    try { await api.delete(`/platform/pipeline-template-tasks/${t.id}`); await loadDetail(selected); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  // ---- Detail (task editing) view ----
  if (selected && detail) {
    const byCat = {};
    (detail.categories || []).forEach((c) => (byCat[c] = []));
    detail.tasks.forEach((t) => { (byCat[t.categoria] = byCat[t.categoria] || []).push(t); });
    return (
      <div className="max-w-5xl space-y-6" data-testid="pipeline-template-detail">
        <button onClick={() => { setSelected(null); setDetail(null); }} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800" data-testid="tpl-back"><ArrowLeft className="w-4 h-4" />Torna ai modelli</button>
        <div className="bg-white border border-slate-200 rounded-2xl p-6">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <div className="text-xs font-bold tracking-wider text-slate-400 uppercase">Modello · {detail.template.key}</div>
              <h1 className="text-2xl font-bold text-slate-900">{detail.template.name}</h1>
              <p className="text-slate-500 mt-1 max-w-2xl">{detail.template.description}</p>
            </div>
            <Button onClick={() => setTaskDlg({ ...emptyTask, order: detail.tasks.length })} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="tpl-add-task"><Plus className="w-4 h-4 mr-1.5" />Nuova attività</Button>
          </div>
          <div className="mt-3 inline-flex items-center gap-1.5 text-sm text-slate-600"><ListChecks className="w-4 h-4 text-tiffany-active" />{detail.tasks.length} attività configurate</div>
        </div>

        {Object.entries(byCat).map(([cat, items]) => (
          <div key={cat} className="bg-white border border-slate-200 rounded-2xl p-5" data-testid={`tpl-cat-${cat}`}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-slate-800">{cat}</h2>
              <span className="text-xs text-slate-400">{items.length} attività</span>
            </div>
            {items.length === 0 ? <div className="text-sm text-slate-400">Nessuna attività in questa categoria.</div> : (
              <div className="divide-y divide-slate-50">
                {items.sort((a, b) => a.order - b.order).map((t) => (
                  <div key={t.id} className="flex items-center gap-3 py-2.5" data-testid={`tpl-task-${t.id}`}>
                    <div className="flex-1 min-w-0">
                      <div className={`font-medium ${t.active ? "text-slate-800" : "text-slate-400 line-through"}`}>{t.titolo}</div>
                      {t.descrizione && <div className="text-xs text-slate-400 truncate">{t.descrizione}</div>}
                    </div>
                    <span className="inline-flex items-center gap-1 text-xs text-slate-500"><Clock className="w-3.5 h-3.5" />{offsetLabel(t.giorni_offset)}</span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${PRIO_CLS[t.priorita]}`}><Flag className="w-3 h-3 inline mr-0.5" />{PRIO[t.priorita]}</span>
                    {t.crm_section && <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-sky-50 text-sky-700">{t.crm_section}</span>}
                    <button onClick={() => setTaskDlg({ ...t })} className="p-1 text-slate-500 hover:bg-slate-100 rounded" data-testid={`tpl-task-edit-${t.id}`}><Pencil className="w-4 h-4" /></button>
                    <button onClick={() => delTask(t)} className="p-1 text-red-600 hover:bg-red-50 rounded"><Trash2 className="w-4 h-4" /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        <Dialog open={!!taskDlg} onOpenChange={(o) => !o && setTaskDlg(null)}>
          <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="tpl-task-dialog">
            <DialogHeader><DialogTitle>{taskDlg?.id ? "Modifica attività modello" : "Nuova attività modello"}</DialogTitle></DialogHeader>
            {taskDlg && (
              <div className="space-y-3">
                <div className="space-y-1.5"><Label>Titolo *</Label><Input value={taskDlg.titolo} onChange={(e) => setTaskDlg((t) => ({ ...t, titolo: e.target.value }))} data-testid="tpl-task-titolo" /></div>
                <div className="space-y-1.5"><Label>Descrizione</Label><Textarea rows={2} value={taskDlg.descrizione || ""} onChange={(e) => setTaskDlg((t) => ({ ...t, descrizione: e.target.value }))} /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5"><Label>Categoria *</Label><Select value={taskDlg.categoria || ""} onValueChange={(v) => setTaskDlg((t) => ({ ...t, categoria: v }))}><SelectTrigger data-testid="tpl-task-categoria"><SelectValue placeholder="Scegli…" /></SelectTrigger><SelectContent>{(detail.categories || []).map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></div>
                  <div className="space-y-1.5"><Label>Giorni rispetto all'evento</Label><Input type="number" value={taskDlg.giorni_offset} onChange={(e) => setTaskDlg((t) => ({ ...t, giorni_offset: e.target.value }))} data-testid="tpl-task-offset" /><div className="text-[11px] text-slate-400">{offsetLabel(taskDlg.giorni_offset)} (-180 = prima, 0 = evento, +1 = dopo)</div></div>
                  <div className="space-y-1.5"><Label>Priorità</Label><Select value={taskDlg.priorita} onValueChange={(v) => setTaskDlg((t) => ({ ...t, priorita: v }))}><SelectTrigger data-testid="tpl-task-priorita"><SelectValue /></SelectTrigger><SelectContent>{Object.entries(PRIO).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select></div>
                  <div className="space-y-1.5"><Label>Ordine</Label><Input type="number" value={taskDlg.order} onChange={(e) => setTaskDlg((t) => ({ ...t, order: e.target.value }))} /></div>
                  <div className="space-y-1.5"><Label>Sezione CRM (FASE 4)</Label><Select value={taskDlg.crm_section || "none"} onValueChange={(v) => setTaskDlg((t) => ({ ...t, crm_section: v === "none" ? "" : v }))}><SelectTrigger><SelectValue placeholder="—" /></SelectTrigger><SelectContent>{CRM_SECTIONS.map((s) => <SelectItem key={s || "none"} value={s || "none"}>{s || "—"}</SelectItem>)}</SelectContent></Select></div>
                  <div className="flex items-center gap-2 pt-6"><Switch checked={taskDlg.active} onCheckedChange={(v) => setTaskDlg((t) => ({ ...t, active: v }))} data-testid="tpl-task-active" /><Label>Attiva</Label></div>
                </div>
              </div>
            )}
            <DialogFooter><Button variant="outline" onClick={() => setTaskDlg(null)}>Annulla</Button><Button onClick={saveTask} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="tpl-task-save">Salva</Button></DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ---- List view ----
  return (
    <div className="max-w-5xl space-y-6" data-testid="pipeline-templates-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 text-tiffany-active"><LayoutTemplate className="w-5 h-5" /><span className="text-xs font-bold tracking-wider uppercase">Super Admin</span></div>
          <h1 className="text-2xl font-bold text-slate-900">Modelli Pipeline</h1>
          <p className="text-slate-500 mt-1 max-w-2xl">Gestisci i modelli di Pipeline proposti agli organizzatori. Ogni modello contiene attività con categoria, scadenza relativa alla data evento, priorità e ordinamento.</p>
        </div>
        <Button onClick={() => setTplDlg({ ...emptyTpl, _new: true })} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="tpl-add"><Plus className="w-4 h-4 mr-1.5" />Nuovo modello</Button>
      </div>

      {loading ? <div className="text-slate-400">Caricamento…</div> : (
        <div className="grid gap-4 sm:grid-cols-2">
          {templates.map((t) => (
            <div key={t.key} className="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col" data-testid={`tpl-card-${t.key}`}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="font-bold text-slate-900 text-lg">{t.name}</h2>
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${t.active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-400"}`}>{t.active ? "Attivo" : "Disattivo"}</span>
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">codice: {t.key}{t.in_use ? " · in uso" : ""}</div>
                </div>
                <Switch checked={t.active} onCheckedChange={() => toggleTpl(t)} data-testid={`tpl-toggle-${t.key}`} />
              </div>
              <p className="text-sm text-slate-500 mt-2 flex-1">{t.description || "—"}</p>
              <div className="flex items-center gap-1.5 text-sm text-slate-600 mt-3"><ListChecks className="w-4 h-4 text-tiffany-active" />{t.task_count} attività</div>
              <div className="flex gap-2 mt-4">
                <Button variant="outline" size="sm" onClick={() => setSelected(t.key)} data-testid={`tpl-manage-${t.key}`}><ListChecks className="w-4 h-4 mr-1" />Gestisci attività</Button>
                <Button variant="outline" size="sm" onClick={() => setTplDlg({ ...t })} data-testid={`tpl-edit-${t.key}`}><Pencil className="w-4 h-4" /></Button>
                <Button variant="outline" size="sm" disabled={t.in_use} title={t.in_use ? "Modello utilizzato da eventi: puoi solo disattivarlo" : "Elimina"} onClick={() => delTpl(t)} className="text-red-600 hover:bg-red-50" data-testid={`tpl-delete-${t.key}`}><Trash2 className="w-4 h-4" /></Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={!!tplDlg} onOpenChange={(o) => !o && setTplDlg(null)}>
        <DialogContent className="max-w-md" data-testid="tpl-dialog">
          <DialogHeader><DialogTitle>{tplDlg?._new ? "Nuovo modello" : "Modifica modello"}</DialogTitle><DialogDescription>Il codice identifica il modello e non è modificabile dopo la creazione.</DialogDescription></DialogHeader>
          {tplDlg && (
            <div className="space-y-3">
              <div className="space-y-1.5"><Label>Nome *</Label><Input value={tplDlg.name} onChange={(e) => setTplDlg((t) => ({ ...t, name: e.target.value }))} data-testid="tpl-name" /></div>
              {tplDlg._new && <div className="space-y-1.5"><Label>Codice</Label><Input value={tplDlg.key} onChange={(e) => setTplDlg((t) => ({ ...t, key: e.target.value }))} placeholder="es. trail, triathlon (auto dal nome se vuoto)" data-testid="tpl-key" /></div>}
              <div className="space-y-1.5"><Label>Descrizione</Label><Textarea rows={3} value={tplDlg.description || ""} onChange={(e) => setTplDlg((t) => ({ ...t, description: e.target.value }))} /></div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5"><Label>Ordine</Label><Input type="number" value={tplDlg.order} onChange={(e) => setTplDlg((t) => ({ ...t, order: e.target.value }))} /></div>
                <div className="flex items-center gap-2 pt-6"><Switch checked={tplDlg.active} onCheckedChange={(v) => setTplDlg((t) => ({ ...t, active: v }))} data-testid="tpl-active" /><Label>Attivo</Label></div>
              </div>
            </div>
          )}
          <DialogFooter><Button variant="outline" onClick={() => setTplDlg(null)}>Annulla</Button><Button onClick={saveTpl} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="tpl-save">Salva</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
