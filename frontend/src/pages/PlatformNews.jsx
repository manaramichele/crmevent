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
import { Check, Pencil, Trash2, Undo2, FlaskConical, Rocket, Plus, RefreshCw, ChevronsUpDown, Store, X } from "lucide-react";
import { NEWS_READ_EVENT } from "@/pages/News";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { NewsProductButton } from "@/components/news/NewsProductButton";

const fmt = (iso) => { try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); } catch { return "—"; } };
const STATUS = { bozza: ["orange", "Bozza da approvare"], pubblicata: ["green", "Pubblicata"], ritirata: ["gray", "Ritirata"] };
const SEL = "w-full h-10 rounded-md border border-slate-200 px-2 text-sm bg-white";
const audLabel = (a, svcs = []) => { const nm = (svcs.find((s) => s.key === a?.service) || {}).name || a?.service; return (!a || a.type === "all" ? "Tutte le organizzazioni" : a.type === "superadmin" ? "Solo Super Admin" : a.type === "plans" ? `Piani: ${(a.plans || []).join(", ").toUpperCase()}` : a.type === "service_missing" ? `Senza modulo: ${nm}` : `Modulo: ${nm}`); };
const MKT_STATUS = { available: "Disponibile", coming_soon: "Prossimamente", suspended: "Sospeso" };

function ProductPicker({ value, onChange, services }) {
  const [open, setOpen] = useState(false);
  const cur = services.find((s) => s.id === value);
  const list = services.filter((s) => !s.retired);
  return (
    <div className="space-y-1.5">
      <Label>Collega prodotto Marketplace <span className="font-normal text-slate-400">(facoltativo)</span></Label>
      <div className="flex gap-2">
        <Popover open={open} onOpenChange={setOpen} modal>
          <PopoverTrigger asChild>
            <button type="button" className={`${SEL} flex items-center justify-between text-left`} data-testid="news-product-select">
              <span className={`truncate ${cur ? "text-slate-900" : "text-slate-400"}`}>{cur ? cur.name : "Nessun prodotto collegato"}</span><ChevronsUpDown className="h-4 w-4 shrink-0 text-slate-400" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[260px] p-0 z-[200]" align="start">
            <Command><CommandInput placeholder="Cerca nel catalogo Marketplace…" data-testid="news-product-search" />
              <CommandList><CommandEmpty>Nessun prodotto trovato</CommandEmpty><CommandGroup>
                {list.map((s) => <CommandItem key={s.id} value={`${s.name} ${s.key}`} onSelect={() => { onChange(s.id); setOpen(false); }} data-testid={`news-product-opt-${s.key}`}>
                  {value === s.id && <Check className="w-4 h-4 mr-1" />}<span className="flex-1">{s.name}</span><span className="text-[11px] text-slate-400">{MKT_STATUS[s.status] || s.status}</span></CommandItem>)}
              </CommandGroup></CommandList></Command>
          </PopoverContent>
        </Popover>
        {cur && <Button type="button" variant="outline" size="icon" onClick={() => onChange(null)} title="Rimuovi collegamento" data-testid="news-product-clear"><X className="w-4 h-4" /></Button>}
      </div>
      {cur && <p className="text-xs text-slate-500">La notizia mostrerà «Scopri il modulo» o «Scopri e acquista» verso la scheda {cur.name}; chi ha già il modulo vedrà «Apri modulo».</p>}
    </div>
  );
}

function AudienceFields({ a, setA, services }) {
  const togglePlan = (p) => setA({ ...a, plans: a.plans.includes(p) ? a.plans.filter((x) => x !== p) : [...a.plans, p] });
  return (
    <div className="space-y-2">
      <Label>Destinatari</Label>
      <select className={SEL} value={a.type} onChange={(e) => setA({ ...a, type: e.target.value })} data-testid="news-audience-type">
        <option value="all">Tutte le organizzazioni</option><option value="superadmin">Solo Super Admin</option><option value="plans">Solo alcuni piani</option><option value="service">Organizzazioni con un modulo Marketplace attivo</option><option value="service_missing">Organizzazioni che non hanno ancora un modulo (promozione)</option>
      </select>
      {a.type === "plans" && <div className="flex gap-3 text-sm">{["bronze", "silver", "gold"].map((p) => <label key={p} className="flex items-center gap-1.5"><input type="checkbox" checked={a.plans.includes(p)} onChange={() => togglePlan(p)} data-testid={`news-audience-plan-${p}`} />{p.toUpperCase()}</label>)}</div>}
      {(a.type === "service" || a.type === "service_missing") && <select className={SEL} value={a.service || ""} onChange={(e) => setA({ ...a, service: e.target.value })} data-testid="news-audience-service"><option value="">Scegli il modulo…</option>{services.map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</select>}
    </div>
  );
}

function EditDialog({ item, onClose, onSaved, services }) {
  const isNew = !item.id;
  const [t, setT] = useState(item.titolo || "");
  const [d, setD] = useState(item.descrizione || "");
  const [area, setArea] = useState(item.area || "Generale");
  const [a, setA] = useState({ type: "all", plans: [], service: null, ...(item.audience || {}) });
  const [productId, setProductId] = useState(item.product_id || null);
  const [kind, setKind] = useState(item.kind || "funzionale");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    const body = { titolo: t, descrizione: d, area, audience: a, product_id: productId, kind };
    try { if (isNew) await api.post("/platform/news", body); else await api.put(`/platform/news/${item.id}`, body); toast.success(isNew ? "Bozza creata" : "Bozza aggiornata"); onSaved(); onClose(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="w-[95vw] max-w-lg max-h-[92vh] overflow-y-auto" data-testid="news-edit-dialog">
        <DialogHeader><DialogTitle className="font-display">{isNew ? "Nuova Novità" : "Modifica Novità"}</DialogTitle><DialogDescription>{isNew ? "Crea una comunicazione manuale: resta in bozza finché non la approvi." : "Correggi titolo, testo, categoria e destinatari prima della pubblicazione."}</DialogDescription></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5"><Label>Titolo</Label><Input value={t} onChange={(e) => setT(e.target.value)} data-testid="news-edit-title" /></div>
          <div className="space-y-1.5"><Label>Descrizione</Label><Textarea rows={5} value={d} onChange={(e) => setD(e.target.value)} data-testid="news-edit-text" /></div>
          <div className="space-y-1.5"><Label>Categoria</Label><Input value={area} onChange={(e) => setArea(e.target.value)} placeholder="es. Eventi, Staff e Volontari" data-testid="news-edit-area" /></div>
          <div className="space-y-1.5"><Label>Tipo di novità</Label>
            <select className={SEL} value={kind} onChange={(e) => { setKind(e.target.value); if (e.target.value === "commerciale" && a.type === "service") setA({ ...a, type: "service_missing" }); }} data-testid="news-kind">
              <option value="funzionale">Funzionale – per chi usa già il modulo</option><option value="commerciale">Commerciale – per chi potrebbe acquistarlo</option>
            </select></div>
          <ProductPicker value={productId} onChange={setProductId} services={services} />
          <AudienceFields a={a} setA={setA} services={services} />
          {kind === "commerciale" && a.type === "service" && <p className="text-xs text-amber-700" data-testid="news-kind-warning">Attenzione: con questi destinatari la promozione arriva solo a chi ha già il modulo.</p>}
          {!isNew && item.generated_descrizione && item.generated_descrizione !== d && <p className="text-xs text-slate-400">Testo generato originale: {item.generated_descrizione}</p>}
        </div>
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={busy} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="news-edit-save">{busy ? "Salvataggio..." : "Salva"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NewsCard({ n, act, onEdit, services }) {
  const [c, l] = STATUS[n.status] || STATUS.bozza;
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-4 sm:p-5" data-testid={`admin-news-${n.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge color={c} data-testid={`admin-news-status-${n.id}`}>{l}</StatusBadge>
        {n.area && <StatusBadge color="tiffany">{n.area}</StatusBadge>}
        {n.simulated && <StatusBadge color="red">TEST · simulazione</StatusBadge>}
        {n.needs_completion && <StatusBadge color="orange" data-testid={`admin-news-incomplete-${n.id}`}>Da completare</StatusBadge>}
        <StatusBadge color="gray" data-testid={`admin-news-audience-${n.id}`}>{audLabel(n.audience, services)}</StatusBadge>
        {n.kind === "commerciale" && <StatusBadge color="blue" data-testid={`admin-news-kind-${n.id}`}>Commerciale</StatusBadge>}
        {n.version > 1 && <StatusBadge color="gray" data-testid={`admin-news-version-${n.id}`}>Pubblicazione n. {n.version}</StatusBadge>}
        <span className="text-xs text-slate-400">{n.status === "bozza" ? `Bozza del ${fmt(n.created_at)}` : `Pubblicata il ${fmt(n.published_at)}`}</span>
      </div>
      <h3 className="mt-2 text-base font-bold text-slate-900 font-display">{n.titolo}</h3>
      <p className="mt-1 text-sm text-slate-700 whitespace-pre-wrap">{n.descrizione}</p>
      {n.product_id && (n.product ? <div className="mt-1" data-testid={`admin-news-product-${n.id}`}><span className="text-xs text-slate-500 inline-flex items-center gap-1 mt-2"><Store className="w-3.5 h-3.5" />Anteprima collegamento · {n.product.name}</span><br /><NewsProductButton product={n.product} testid={`admin-news-product-btn-${n.id}`} /></div>
        : <p className="mt-2 text-xs text-red-600" data-testid={`admin-news-product-missing-${n.id}`}>Prodotto collegato non più visibile nel Marketplace: il pulsante non viene mostrato.</p>)}
      <details className="mt-2 text-xs text-slate-500">
        <summary className="cursor-pointer py-1">Tracciabilità</summary>
        <div className="mt-1 space-y-0.5">
          <div>{n.release_id ? <>Rilascio: <b>{n.release_id}</b> ({n.release_date || "—"})</> : "Creata manualmente"} · generata da: {{ ai: "AI", manual: "Super Admin", incompleta: "informazioni insufficienti", fixed: "testo approvato" }[n.generator] || "testo di riserva"}</div>
          {n.edited && <div>Testo generato: {n.generated_titolo} — {n.generated_descrizione}</div>}
          {n.approved_by && <div>Approvata da {n.approved_by.name || n.approved_by.email} il {fmt(n.published_at)}</div>}
          {n.withdrawn_at && <div>Ritirata da {n.withdrawn_by?.name || n.withdrawn_by?.email} il {fmt(n.withdrawn_at)}</div>}
          {(n.publications || []).length > 1 && <div data-testid={`admin-news-history-${n.id}`}>Storico pubblicazioni: {n.publications.map((p) => `n. ${p.version} il ${fmt(p.published_at)}${p.withdrawn_at ? ` (ritirata ${fmt(p.withdrawn_at)})` : ""}`).join(" · ")}</div>}
          {(n.source_notes || []).length > 0 && <div>Note interne: {n.source_notes.join(" · ")}</div>}
        </div>
      </details>
      <div className="mt-3 flex flex-wrap gap-2">
        {n.status === "bozza" && <>
          <Button size="sm" onClick={() => act(n, "publish")} className="h-8 text-xs bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid={`news-publish-${n.id}`}><Check />Approva e pubblica</Button>
          <TextAction icon={Pencil} onClick={() => onEdit(n)} data-testid={`news-edit-${n.id}`}>Modifica</TextAction>
        </>}
        {n.status === "ritirata" && <><TextAction icon={Check} onClick={() => act(n, "publish")} data-testid={`news-republish-${n.id}`}>Ripubblica</TextAction>
          <TextAction icon={Pencil} onClick={() => onEdit(n)} data-testid={`news-edit-${n.id}`}>Modifica</TextAction></>}
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
      <p className="mt-1 text-xs text-amber-800">Le bozze vengono create automaticamente solo dal server di produzione all'avvio di un nuovo rilascio. Qui puoi simulare un rilascio per provare il flusso: le bozze simulate restano marcate TEST e ogni rilascio si simula una sola volta.</p>
      <div className="mt-3 space-y-2">
        {env.releases.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-slate-800">{r.id}</span><span className="text-slate-500">{r.areas.join(", ")}</span>
            <TextAction icon={Rocket} disabled={busy === r.id || r.simulated} onClick={() => sim(r.id)} data-testid={`news-simulate-${r.id}`}>{r.simulated ? "Già simulato" : "Simula rilascio in produzione"}</TextAction>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChecksPanel({ env, onCheck }) {
  if (!env) return null;
  const last = env.checks?.[0];
  const errs = env.releases.filter((r) => r.error);
  return (
    <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4 text-sm" data-testid="news-checks-panel">
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="font-semibold text-slate-800">Controllo automatico dei rilasci · {env.production ? "Produzione" : "Anteprima"}</div>
        <TextAction icon={RefreshCw} onClick={onCheck} data-testid="news-check-now">Controlla ora</TextAction>
      </div>
      {last ? <p className={`mt-1 text-xs ${last.outcome === "error" ? "text-red-600" : "text-slate-600"}`} data-testid="news-last-check">Ultimo controllo: {fmt(last.at)} · {last.message}</p>
        : <p className="mt-1 text-xs text-slate-500" data-testid="news-last-check">Nessun controllo registrato.</p>}
      {errs.map((r) => <p key={r.id} className="mt-1 text-xs text-red-600" data-testid={`news-release-error-${r.id}`}>Errore rilascio {r.id}: {r.error}</p>)}
      <p className="mt-1 text-xs text-slate-400">Rilasci nel registro: {env.releases.length} · rilevati in produzione: {env.releases.filter((r) => r.detected).length}. Il controllo avviene a ogni avvio del server dopo una pubblicazione.</p>
    </div>
  );
}

export default function PlatformNews() {
  const [items, setItems] = useState([]);
  const [env, setEnv] = useState(null);
  const [editing, setEditing] = useState(null);
  const [services, setServices] = useState([]);
  const load = useCallback(async () => {
    try { const [a, b] = await Promise.all([api.get("/platform/news"), api.get("/platform/news/env")]); setItems(a.data); setEnv(b.data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, []);
  useEffect(() => { load(); api.get("/platform/marketplace/services").then(({ data }) => setServices(data.services || [])).catch(() => {}); }, [load]);
  const refresh = () => { load(); window.dispatchEvent(new Event(NEWS_READ_EVENT)); };
  const check = async () => { try { const { data } = await api.post("/platform/news/check"); toast.success(data.production ? `${data.drafts} bozze create` : "Anteprima: controllo registrato, nessuna bozza automatica"); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const act = async (n, action) => {
    try {
      if (action === "delete") await api.delete(`/platform/news/${n.id}`); else await api.post(`/platform/news/${n.id}/${action}`);
      toast.success({ publish: n.status === "ritirata" ? "Novità ripubblicata: torna visibile anche a chi l'aveva letta" : "Novità pubblicata", withdraw: "Novità ritirata", delete: "Bozza eliminata" }[action]); refresh();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const drafts = items.filter((n) => n.status === "bozza");
  const published = items.filter((n) => n.status !== "bozza").sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  const list = (arr, empty, tid) => arr.length === 0
    ? <p className="text-sm text-slate-400 py-8 text-center" data-testid={tid}>{empty}</p>
    : <div className="space-y-3">{arr.map((n) => <NewsCard key={n.id} n={n} act={act} onEdit={setEditing} services={services} />)}</div>;
  return (
    <div className="animate-fade-up max-w-3xl" data-testid="platform-news-page">
      <PageHeader title="Novità" subtitle="Comunicazioni preparate automaticamente da CRMEvent per ogni rilascio in produzione" action={<Button onClick={() => setEditing({})} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="news-create"><Plus className="w-4 h-4 mr-1" />Nuova novità</Button>} />
      <ChecksPanel env={env} onCheck={check} />
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
      {editing && <EditDialog item={editing} onClose={() => setEditing(null)} onSaved={load} services={services} />}
    </div>
  );
}
