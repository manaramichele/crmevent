import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, SectionCard } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus, Bell, Download, Send } from "lucide-react";
import { MKT_ICONS, PRICE_TYPES, STATUS, ServiceIcon, priceLabel } from "@/lib/marketplace";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const EMPTY = { name: "", description: "", icon: "Package", image: null, category: "Altro", price: null, price_type: "one_time", usage_unit: "", usage_limits: "", terms: "", status: "coming_soon", visible: true, purchasable: false, tech_ready: false, billing_method: "stripe", scope: "org", sort: 100 };
const d = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : "—");
const Sel = ({ value, onChange, opts, testid }) => <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} className="w-full h-10 rounded-md border border-slate-200 px-2 text-sm">{Object.entries(opts).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>;
const Chk = ({ label, value, onChange, testid }) => <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} data-testid={testid} />{label}</label>;

function Editor({ svc, cats, onClose, onSaved }) {
  const [f, setF] = useState({ ...EMPTY, ...svc });
  const set = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const img = (e) => { const file = e.target.files?.[0]; if (!file) return; if (file.size > 300000) { toast.error("Immagine max 300 KB"); return; } const r = new FileReader(); r.onload = () => set("image")(r.result); r.readAsDataURL(file); };
  const save = async () => {
    const body = { ...f, price: f.price === "" || f.price == null ? null : Number(f.price), sort: Number(f.sort) || 100 };
    ["id", "key", "created_at", "updated_at", "active_count", "interest_count", "purchasable_now"].forEach((k) => delete body[k]);
    try { if (svc?.id) await api.put(`/platform/marketplace/services/${svc.id}`, body); else await api.post("/platform/marketplace/services", body); toast.success("Servizio salvato"); onSaved(); }
    catch (e) { err(e); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid="mkt-admin-editor">
        <DialogTitle>{svc?.id ? "Modifica servizio" : "Nuovo servizio"}</DialogTitle>
        <div className="grid sm:grid-cols-2 gap-3 text-xs">
          <label className="sm:col-span-2">Nome<Input value={f.name} onChange={(e) => set("name")(e.target.value)} data-testid="mkt-admin-name" /></label>
          <label className="sm:col-span-2">Descrizione<Textarea rows={3} value={f.description} onChange={(e) => set("description")(e.target.value)} data-testid="mkt-admin-desc" /></label>
          <label>Categoria<Sel value={f.category} onChange={set("category")} opts={Object.fromEntries(cats.map((c) => [c, c]))} testid="mkt-admin-category" /></label>
          <label>Icona<Sel value={f.icon} onChange={set("icon")} opts={Object.fromEntries(Object.keys(MKT_ICONS).map((k) => [k, k]))} testid="mkt-admin-icon" /></label>
          <label>Immagine (opzionale, max 300 KB)<input type="file" accept="image/*" onChange={img} className="block text-xs mt-1" data-testid="mkt-admin-image" />{f.image && <button type="button" className="text-red-600 mt-1" onClick={() => set("image")(null)}>Rimuovi immagine</button>}</label>
          <label>Ambito<Sel value={f.scope} onChange={set("scope")} opts={{ org: "Organizzazione", event: "Singolo evento" }} testid="mkt-admin-scope" /></label>
          <label>Prezzo €<Input type="number" step="0.01" value={f.price ?? ""} onChange={(e) => set("price")(e.target.value)} data-testid="mkt-admin-price" /></label>
          <label>Tipo di prezzo<Sel value={f.price_type} onChange={set("price_type")} opts={PRICE_TYPES} testid="mkt-admin-price-type" /></label>
          {f.price_type === "usage" && <label>Unità di consumo<Input value={f.usage_unit || ""} onChange={(e) => set("usage_unit")(e.target.value)} placeholder="es. messaggio" /></label>}
          <label>Addebito<Sel value={f.billing_method} onChange={set("billing_method")} opts={{ stripe: "Stripe" }} testid="mkt-admin-billing" /></label>
          <label className="sm:col-span-2">Limiti di utilizzo<Input value={f.usage_limits || ""} onChange={(e) => set("usage_limits")(e.target.value)} data-testid="mkt-admin-limits" /></label>
          <label className="sm:col-span-2">Condizioni e durata<Input value={f.terms || ""} onChange={(e) => set("terms")(e.target.value)} data-testid="mkt-admin-terms" /></label>
          <label>Stato commerciale<Sel value={f.status} onChange={set("status")} opts={{ coming_soon: "Prossimamente", available: "Disponibile", suspended: "Sospeso" }} testid="mkt-admin-status" /></label>
          <label>Ordine<Input type="number" value={f.sort} onChange={(e) => set("sort")(e.target.value)} /></label>
        </div>
        <div className="flex flex-wrap gap-4 rounded-lg bg-slate-50 p-3">
          <Chk label="Pubblicato (visibile)" value={f.visible} onChange={set("visible")} testid="mkt-admin-visible" />
          <Chk label="Modulo tecnicamente pronto" value={f.tech_ready} onChange={(v) => setF((s) => ({ ...s, tech_ready: v, purchasable: v ? s.purchasable : false }))} testid="mkt-admin-tech" />
          <Chk label="Acquisto abilitato" value={f.purchasable} onChange={set("purchasable")} testid="mkt-admin-purchasable" />
        </div>
        <p className="text-xs text-slate-500">Un servizio è acquistabile solo se pubblicato, "Disponibile", tecnicamente pronto, con acquisto abilitato e prezzo configurato. I servizi a consumo non sono acquistabili finché il sistema di addebito non è approvato.</p>
        <Button onClick={save} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="mkt-admin-save">Salva</Button>
      </DialogContent>
    </Dialog>
  );
}

const csvCell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
const NSTATUS = { inviato: "Avvisato", errore: "Errore invio", brevo_non_configurato: "Brevo non configurato" };

function Interests({ svc, onClose }) {
  const [rows, setRows] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get(`/platform/marketplace/services/${svc.id}/interests`).then(({ data }) => setRows(data)).catch(err), [svc.id]);
  useEffect(() => { load(); }, [load]);
  const csv = () => {
    const lines = [["Organizzazione", "Richiesto da", "Email", "Data richiesta", "Stato avviso"], ...rows.map((r) => [r.org_name, r.name, r.email, d(r.created_at), r.notified_at ? `Avvisato ${d(r.notified_at)}` : NSTATUS[r.notify_status] || "In attesa"])];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["\ufeff" + lines.map((l) => l.map(csvCell).join(";")).join("\n")], { type: "text/csv;charset=utf-8" }));
    a.download = `interessati-${svc.key}.csv`; a.click();
  };
  const notify = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/platform/marketplace/services/${svc.id}/interests/notify`); toast.success(`Avvisi inviati: ${data.sent}${data.failed ? ` · errori: ${data.failed}` : ""}`); load(); }
    catch (e) { err(e); }
    setBusy(false);
  };
  const pending = (rows || []).filter((r) => !r.notified_at).length;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid="mkt-admin-interests">
        <DialogTitle>Interessati · {svc.name}</DialogTitle>
        <p className="text-xs text-slate-500">Quando il servizio passa a "Disponibile" gli interessati ricevono in automatico un'email tramite Brevo.</p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={!rows?.length} onClick={csv} data-testid="mkt-admin-interests-csv"><Download className="w-4 h-4 mr-1" />Esporta CSV</Button>
          {svc.status === "available" && <Button size="sm" disabled={busy || !pending} onClick={notify} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="mkt-admin-interests-notify"><Send className="w-4 h-4 mr-1" />Invia avvisi in attesa ({pending})</Button>}
        </div>
        {!rows ? <p className="text-sm text-slate-400">Caricamento...</p> : !rows.length ? <p className="text-sm text-slate-500" data-testid="mkt-admin-interests-empty">Nessun interessato per ora.</p> : (
          <div className="overflow-x-auto rounded-xl border border-slate-200"><table className="w-full min-w-[620px] text-sm" data-testid="mkt-admin-interests-table">
            <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Organizzazione", "Richiesto da", "Email", "Data", "Avviso"].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
            <tbody>{rows.map((r) => <tr key={r.id} className="border-t border-slate-100"><td className="px-3 py-2">{r.org_name}</td><td className="px-3 py-2">{r.name}</td><td className="px-3 py-2">{r.email}</td><td className="px-3 py-2">{d(r.created_at)}</td><td className="px-3 py-2">{r.notified_at ? `Avvisato ${d(r.notified_at)}` : NSTATUS[r.notify_status] || "In attesa"}</td></tr>)}</tbody>
          </table></div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Catalog() {
  const [data, setData] = useState(null);
  const [edit, setEdit] = useState(null);
  const [intr, setIntr] = useState(null);
  const load = useCallback(() => api.get("/platform/marketplace/services").then(({ data }) => setData(data)).catch(err), []);
  useEffect(() => { load(); }, [load]);
  if (!data) return <p className="text-sm text-slate-400">Caricamento...</p>;
  return (
    <div className="space-y-3">
      <Button onClick={() => setEdit({})} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="mkt-admin-new"><Plus className="w-4 h-4 mr-1" />Nuovo servizio</Button>
      <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        {data.services.map((s) => (
          <div key={s.id} className="flex flex-col sm:flex-row sm:items-center gap-3 p-3" data-testid={`mkt-admin-row-${s.key}`}>
            <ServiceIcon s={s} className="w-10 h-10" />
            <div className="flex-1 min-w-0"><div className="font-semibold">{s.name} <span className="text-xs text-slate-400">· {s.category}</span></div>
              <div className="text-xs text-slate-500">{STATUS[s.status]} · {s.visible ? "pubblicato" : "nascosto"} · {s.tech_ready ? "pronto" : "non pronto"} · {s.purchasable_now ? "acquistabile" : "non acquistabile"} · {priceLabel(s)} · {PRICE_TYPES[s.price_type]} · attivi {s.active_count}</div></div>
            <Button size="sm" variant="outline" onClick={() => setIntr(s)} data-testid={`mkt-admin-interests-${s.key}`}><Bell className="w-3.5 h-3.5 mr-1" />Organizzazioni interessate {s.interest_count || 0}</Button>
            <Button size="sm" variant="outline" onClick={() => setEdit(s)} data-testid={`mkt-admin-edit-${s.key}`}>Modifica</Button>
          </div>
        ))}
      </div>
      {intr && <Interests svc={intr} onClose={() => { setIntr(null); load(); }} />}
      {edit && <Editor svc={edit} cats={data.categories} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
    </div>
  );
}

function Purchases() {
  const [rows, setRows] = useState(null);
  const load = useCallback(() => api.get("/platform/marketplace/purchases").then(({ data }) => setRows(data)).catch(err), []);
  useEffect(() => { load(); }, [load]);
  const setStatus = async (p, status) => { try { await api.put(`/platform/marketplace/purchases/${p.id}/status`, { status }); load(); } catch (e) { err(e); } };
  if (!rows) return <p className="text-sm text-slate-400">Caricamento...</p>;
  if (!rows.length) return <p className="text-sm text-slate-500" data-testid="mkt-admin-purchases-empty">Nessun acquisto registrato.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[760px] text-sm" data-testid="mkt-admin-purchases">
      <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Organizzazione", "Servizio", "Stato", "Prezzo", "Data", "Rinnovo", ""].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
      <tbody>{rows.map((p) => <tr key={p.id} className="border-t border-slate-100"><td className="px-3 py-2">{p.org_name}</td><td className="px-3 py-2">{p.service_name}</td><td className="px-3 py-2">{STATUS[p.status]}</td><td className="px-3 py-2">{priceLabel(p)}</td><td className="px-3 py-2">{d(p.activated_at || p.created_at)}</td><td className="px-3 py-2">{d(p.current_period_end)}</td>
        <td className="px-3 py-2">{p.status === "active" ? <Button size="sm" variant="outline" onClick={() => setStatus(p, "suspended")}>Sospendi</Button> : p.status === "suspended" ? <Button size="sm" variant="outline" onClick={() => setStatus(p, "active")}>Riattiva</Button> : null}</td></tr>)}</tbody>
    </table></div>
  );
}

export default function MarketplaceAdmin() {
  return (
    <div className="animate-fade-up space-y-4" data-testid="mkt-admin-page">
      <PageHeader title="Marketplace" subtitle="Catalogo dei servizi extra (non inclusi negli abbonamenti), pubblicazione, disponibilità tecnica e acquisti delle organizzazioni" />
      <Tabs defaultValue="catalog"><TabsList className="mb-4"><TabsTrigger value="catalog" data-testid="mkt-admin-tab-catalog">Catalogo</TabsTrigger><TabsTrigger value="purchases" data-testid="mkt-admin-tab-purchases">Acquisti</TabsTrigger></TabsList>
        <TabsContent value="catalog"><SectionCard title="Servizi"><Catalog /></SectionCard></TabsContent>
        <TabsContent value="purchases"><SectionCard title="Storico acquisti"><Purchases /></SectionCard></TabsContent>
      </Tabs>
    </div>
  );
}
