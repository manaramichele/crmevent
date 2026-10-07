import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, StatusBadge, TextAction, DeleteConfirm } from "@/components/crm";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Check, Pencil, Trash2, Undo2, FlaskConical, Rocket } from "lucide-react";

const fmt = (iso) => { try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return "—"; } };
const STATUS = { bozza: ["orange", "Bozza da approvare"], pubblicata: ["green", "Pubblicata"], ritirata: ["gray", "Ritirata"] };

function EditDialog({ item, onClose, onSaved }) {
  const [t, setT] = useState(item.titolo);
  const [d, setD] = useState(item.descrizione);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await api.put(`/platform/news/${item.id}`, { titolo: t, descrizione: d }); toast.success("Bozza aggiornata"); onSaved(); onClose(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="w-[95vw] max-w-lg" data-testid="news-edit-dialog">
        <DialogHeader><DialogTitle className="font-display">Modifica Novità</DialogTitle><DialogDescription>Correggi titolo e testo prima della pubblicazione.</DialogDescription></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Titolo</Label><Input value={t} onChange={(e) => setT(e.target.value)} data-testid="news-edit-title" /></div>
          <div className="space-y-1.5"><Label>Descrizione</Label><Textarea rows={5} value={d} onChange={(e) => setD(e.target.value)} data-testid="news-edit-text" /></div>
          {item.edited !== false && item.generated_descrizione !== d && <p className="text-xs text-slate-400">Testo generato originale: {item.generated_descrizione}</p>}
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="news-edit-save">{busy ? "Salvataggio..." : "Salva"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NewsCard({ n, act, onEdit }) {
  const [c, l] = STATUS[n.status] || STATUS.bozza;
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4 sm:p-5" data-testid={`admin-news-${n.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge color={c} data-testid={`admin-news-status-${n.id}`}>{l}</StatusBadge>
        {n.area && <StatusBadge color="tiffany">{n.area}</StatusBadge>}
        {n.simulated && <StatusBadge color="red">TEST · simulazione</StatusBadge>}
        <span className="text-xs text-slate-400">{n.status === "bozza" ? `Bozza del ${fmt(n.created_at)}` : `Pubblicata il ${fmt(n.published_at)}`}</span>
      </div>
      <h3 className="mt-2 text-base font-bold text-slate-900 font-display">{n.titolo}</h3>
      <p className="mt-1 text-sm text-slate-700 whitespace-pre-wrap">{n.descrizione}</p>
      <details className="mt-2 text-xs text-slate-500">
        <summary className="cursor-pointer py-1">Tracciabilità</summary>
        <div className="mt-1 space-y-0.5">
          <div>Rilascio: <b>{n.release_id}</b> ({n.release_date || "—"}) · generata da: {n.generator === "ai" ? "AI" : "testo di riserva"}</div>
          {n.edited && <div>Testo generato: {n.generated_titolo} — {n.generated_descrizione}</div>}
          {n.approved_by && <div>Approvata da {n.approved_by.name || n.approved_by.email} il {fmt(n.published_at)}</div>}
          {n.withdrawn_at && <div>Ritirata da {n.withdrawn_by?.name || n.withdrawn_by?.email} il {fmt(n.withdrawn_at)}</div>}
          {(n.source_notes || []).length > 0 && <div>Note interne: {n.source_notes.join(" · ")}</div>}
        </div>
      </details>
      <div className="mt-3 flex flex-wrap gap-2">
        {n.status === "bozza" && <>
          <Button size="sm" onClick={() => act(n, "publish")} className="h-8 text-xs bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid={`news-publish-${n.id}`}><Check />Approva e pubblica</Button>
          <TextAction icon={Pencil} onClick={() => onEdit(n)} data-testid={`news-edit-${n.id}`}>Modifica</TextAction>
        </>}
        {n.status === "ritirata" && <TextAction icon={Check} onClick={() => act(n, "publish")} data-testid={`news-republish-${n.id}`}>Ripubblica</TextAction>}
        {n.status === "pubblicata" && <TextAction icon={Undo2} danger onClick={() => act(n, "withdraw")} data-testid={`news-withdraw-${n.id}`}>Ritira</TextAction>}
        {n.status !== "pubblicata" && <DeleteConfirm onConfirm={() => act(n, "delete")} testid={`news-confirm-delete-${n.id}`}><TextAction icon={Trash2} danger data-testid={`news-delete-${n.id}`}>Elimina</TextAction></DeleteConfirm>}
      </div>
    </div>
  );
}

function SimulatePanel({ env, onDone }) {
  const [busy, setBusy] = useState(null);
  if (!env || env.production) return null;
  const sim = async (id) => {
    setBusy(id);
    try { const { data } = await api.post("/platform/news/simulate-release", { release_id: id }); toast.success(`${data.created} bozze create (TEST)`); onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(null); }
  };
  return (
    <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4" data-testid="news-simulate-panel">
      <div className="flex items-center gap-2 text-sm font-semibold text-amber-800"><FlaskConical className="w-4 h-4" />Ambiente di anteprima — nessuna bozza automatica</div>
      <p className="mt-1 text-xs text-amber-800">Le bozze vengono create automaticamente solo dal server di produzione (CRMEVENT_ENV=production) all'avvio di un nuovo rilascio. Qui puoi simulare un rilascio per provare il flusso.</p>
      <div className="mt-3 space-y-2">
        {env.releases.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-slate-800">{r.id}</span><span className="text-slate-500">{r.areas.join(", ")}</span>
            <TextAction icon={Rocket} disabled={busy === r.id} onClick={() => sim(r.id)} data-testid={`news-simulate-${r.id}`}>Simula rilascio in produzione</TextAction>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function PlatformNews() {
  const [items, setItems] = useState([]);
  const [env, setEnv] = useState(null);
  const [editing, setEditing] = useState(null);
  const load = useCallback(async () => {
    try { const [a, b] = await Promise.all([api.get("/platform/news"), api.get("/platform/news/env")]); setItems(a.data); setEnv(b.data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const act = async (n, action) => {
    try {
      if (action === "delete") await api.delete(`/platform/news/${n.id}`); else await api.post(`/platform/news/${n.id}/${action}`);
      toast.success({ publish: "Novità pubblicata", withdraw: "Novità ritirata", delete: "Bozza eliminata" }[action]); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const drafts = items.filter((n) => n.status === "bozza");
  const published = items.filter((n) => n.status !== "bozza").sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  const list = (arr, empty, tid) => arr.length === 0
    ? <p className="text-sm text-slate-400 py-8 text-center" data-testid={tid}>{empty}</p>
    : <div className="space-y-3">{arr.map((n) => <NewsCard key={n.id} n={n} act={act} onEdit={setEditing} />)}</div>;
  return (
    <div className="animate-fade-up max-w-3xl" data-testid="platform-news-page">
      <PageHeader title="Novità" subtitle="Comunicazioni preparate automaticamente da CRMEvent per ogni rilascio in produzione" />
      {env?.production && <p className="mb-4 text-xs text-emerald-700" data-testid="news-env-prod">Produzione: le bozze nascono automaticamente all'avvio di ogni nuovo rilascio.</p>}
      <SimulatePanel env={env} onDone={load} />
      <Tabs defaultValue="draft">
        <TabsList className="mb-4">
          <TabsTrigger value="draft" data-testid="news-tab-draft">Da approvare{drafts.length ? ` · ${drafts.length}` : ""}</TabsTrigger>
          <TabsTrigger value="published" data-testid="news-tab-published">Pubblicate</TabsTrigger>
        </TabsList>
        <TabsContent value="draft">{list(drafts, "Nessuna bozza da approvare.", "news-drafts-empty")}</TabsContent>
        <TabsContent value="published">{list(published, "Nessuna Novità pubblicata.", "news-published-empty")}</TabsContent>
      </Tabs>
      {editing && <EditDialog item={editing} onClose={() => setEditing(null)} onSaved={load} />}
    </div>
  );
}
