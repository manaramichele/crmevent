import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Store, CheckCircle2, Clock, Bell, BellRing } from "lucide-react";
import { ServiceIcon, PRICE_TYPES, STATUS, priceLabel } from "@/lib/marketplace";
import { YouTubeTutorial } from "@/components/marketplace/YouTubeTutorial";

const fmtDate = (s) => (s ? new Date(s).toLocaleDateString("it-IT") : null);

function ActivePurchase({ s, canPurchase, onChanged }) {
  const [busy, setBusy] = useState("");
  const p = (s.purchases || []).find((x) => ["active", "past_due"].includes(x.status));
  if (!p) return null;
  const run = async (kind) => {
    if (kind === "cancel" && !window.confirm(p.stripe_subscription_id ? "Disdire questo servizio? Resterà attivo fino alla fine del periodo già pagato. Gli altri servizi non cambiano." : "Disattivare questo servizio gratuito?")) return;
    setBusy(kind);
    try {
      if (kind === "portal") { const { data } = await api.post("/marketplace/portal", { origin_url: window.location.origin }); window.location.href = data.url; return; }
      await api.post(`/marketplace/purchases/${p.id}/${kind}`);
      toast.success(kind === "cancel" ? "Disdetta registrata" : "Disdetta annullata");
      onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  return (
    <div className="rounded-xl border border-slate-200 p-3 text-xs text-slate-600 space-y-2" data-testid="mkt-detail-subscription">
      {p.status === "past_due" && <div className="font-semibold text-red-600" data-testid="mkt-detail-pastdue">Pagamento non riuscito: aggiorna il metodo di pagamento per non perdere il servizio.</div>}
      {p.source === "demo" && <div data-testid="mkt-detail-demo-active">Attivato gratuitamente (organizzazione Demo) il {fmtDate(p.activated_at)}, senza scadenza.</div>}
      {p.source === "manual" && <div>Attivato gratuitamente dal team CRMEvent.</div>}
      {p.source === "free" && <div>Servizio gratuito attivato il {fmtDate(p.activated_at)}.</div>}
      {p.current_period_end && <div data-testid="mkt-detail-renewal">{p.cancel_at_period_end ? `Disdetto: resta attivo fino al ${fmtDate(p.current_period_end)}` : `Rinnovo automatico il ${fmtDate(p.current_period_end)}`}</div>}
      {canPurchase && (
        <div className="flex flex-wrap gap-2">
          {p.stripe_subscription_id && !p.cancel_at_period_end && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("cancel")} data-testid="mkt-detail-cancel">Disdici servizio</Button>}
          {p.stripe_subscription_id && p.cancel_at_period_end && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("resume")} data-testid="mkt-detail-resume">Annulla disdetta</Button>}
          {p.source === "free" && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("cancel")} data-testid="mkt-detail-cancel">Disattiva</Button>}
          {p.source === "stripe" && <Button size="sm" variant="outline" disabled={!!busy} onClick={() => run("portal")} data-testid="mkt-detail-portal">{busy === "portal" ? "Apertura..." : "Gestisci pagamenti"}</Button>}
        </div>
      )}
    </div>
  );
}

const badge = (s) => (s.active ? ["Attivo", "bg-emerald-100 text-emerald-800"] : s.status === "suspended" ? ["Sospeso", "bg-red-100 text-red-700"]
  : s.purchasable_now ? ["Disponibile", "bg-[#0ABAB5]/15 text-slate-900"] : s.activation === "superadmin" && s.status === "available" ? ["Su attivazione", "bg-[#0ABAB5]/15 text-slate-900"] : ["Prossimamente", "bg-slate-100 text-slate-600"]);

function NotifyButton({ s, onToggle, full }) {
  const [busy, setBusy] = useState(false);
  if (s.status !== "coming_soon") return null;
  const click = async (e) => {
    e.stopPropagation();
    setBusy(true);
    try { const { data } = await api.post(`/marketplace/services/${s.id}/notify`); onToggle(s.id, data.notify_me); toast.success(s.notified_label ? `${s.notified_label}: ti avviseremo appena il servizio sarà disponibile` : "Ti avviseremo via email appena sarà disponibile"); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setBusy(false);
  };
  const on = s.notify_me;
  return on ? (
    <span data-testid={`mkt-notify-${s.key}${full ? "-detail" : ""}`} onClick={(e) => e.stopPropagation()}
      className={`inline-flex items-center justify-center gap-1.5 rounded-full border border-[#0ABAB5] bg-[#0ABAB5]/15 text-[#088F8A] text-xs font-semibold ${full ? "w-full h-11 text-sm" : "h-8 px-3"}`}>
      <BellRing className="w-3.5 h-3.5" />{s.notified_label || (s.key === "planimetrie-mappe" ? "Avviso attivato" : "Ti avviseremo")}
    </span>
  ) : (
    <button type="button" disabled={busy || on} onClick={click} onKeyDown={(e) => e.stopPropagation()} data-testid={`mkt-notify-${s.key}${full ? "-detail" : ""}`}
      className={`inline-flex items-center justify-center gap-1.5 rounded-full border text-xs font-semibold transition-colors touch-manipulation disabled:cursor-default ${busy ? "opacity-60" : ""} ${full ? "w-full h-11 text-sm" : "h-10 sm:h-8 px-4 sm:px-3"} ${on ? "border-[#0ABAB5] bg-[#0ABAB5]/15 text-[#088F8A]" : "border-slate-200 text-slate-700 hover:border-[#0ABAB5] hover:text-[#088F8A]"}`}>
      {on ? <BellRing className="w-3.5 h-3.5" /> : <Bell className="w-3.5 h-3.5" />}{on ? "Ti avviseremo" : s.notify_label || "Avvisami"}
    </button>
  );
}

function Card({ s, onOpen, onToggle }) {
  const [label, cls] = badge(s);
  return (
    <div role="button" tabIndex={0} onClick={() => onOpen(s)} onKeyDown={(e) => e.key === "Enter" && onOpen(s)} data-testid={`mkt-card-${s.key}`}
      className="cursor-pointer text-left flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-[transform,box-shadow] duration-200 hover:-translate-y-1 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0ABAB5]">
      <div className="flex items-start justify-between gap-3"><ServiceIcon s={s} /><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${cls}`} data-testid={`mkt-status-${s.key}`}>{label}</span></div>
      <div className="mt-4 font-semibold text-slate-900">{s.name}</div>
      <div className="text-xs text-[#088F8A] font-medium mt-0.5">{s.category}</div>
      <p className="text-sm text-slate-500 mt-2 line-clamp-3 flex-1">{s.description}</p>
      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-800">{priceLabel(s)}</span><span className="text-slate-500">{PRICE_TYPES[s.price_type]}</span>
      </div>
      {s.demo_free && s.purchasable_now && !s.active && <div className="mt-2 text-[11px] font-semibold text-amber-700" data-testid={`mkt-card-demo-free-${s.key}`}>Gratuito per organizzazione Demo</div>}
      {s.status === "coming_soon" && <div className="mt-3"><NotifyButton s={s} onToggle={onToggle} /></div>}
    </div>
  );
}

function Detail({ s, canPurchase, onClose, onToggle, onChanged }) {
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (s?.scope === "event") api.get("/events").then(({ data }) => setEvents(data || [])).catch(() => {}); }, [s]);
  if (!s) return null;
  const buy = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/marketplace/services/${s.id}/checkout`, { origin_url: window.location.origin, event_id: eventId || null });
      if (data.activated) { toast.success("Servizio attivato gratuitamente"); setBusy(false); onChanged(); return; }
      window.location.href = data.checkout_url;
    }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto rounded-2xl pb-0" data-testid="mkt-detail">
        <div className="flex items-center gap-3"><ServiceIcon s={s} /><div><DialogTitle className="text-xl font-bold">{s.name}</DialogTitle><div className="text-xs text-[#088F8A]">{s.category}</div></div></div>
        <DialogDescription className="text-sm text-slate-600">{s.description}</DialogDescription>
        <YouTubeTutorial id={s.video_id} title={s.video_title} />
        <div className="grid grid-cols-2 gap-3 text-sm rounded-xl bg-slate-50 p-3">
          <div><div className="text-xs text-slate-400">Prezzo{s.demo_free ? " di listino" : ""}</div><b data-testid="mkt-detail-price">{priceLabel(s)}</b>{s.demo_free && <div className="text-xs font-semibold text-amber-700" data-testid="mkt-detail-demo-free">Gratuito per organizzazione Demo</div>}</div>
          <div><div className="text-xs text-slate-400">Modalità</div><b>{PRICE_TYPES[s.price_type]}</b></div>
          {s.usage_limits && <div className="col-span-2"><div className="text-xs text-slate-400">Limiti di utilizzo</div>{s.usage_limits}</div>}
          {s.features?.length > 0 && <div className="col-span-2 space-y-3" data-testid="mkt-detail-features"><div className="text-xs text-slate-400">Funzionalità previste</div>{s.features.map((g) => (
            <div key={g.title}><div className="text-sm font-semibold text-slate-800">{g.title}</div>
              <ul className="mt-1 space-y-0.5">{g.items.map((it) => <li key={it} className="flex gap-2 text-sm text-slate-600"><span className="mt-2 w-1.5 h-1.5 rounded-full bg-[#0ABAB5] shrink-0" />{it}</li>)}</ul></div>))}</div>}
          {s.terms && <div className="col-span-2"><div className="text-xs text-slate-400">{s.status === "coming_soon" ? "Funzionalità previste" : "Condizioni e durata"}</div>{s.terms}</div>}
        </div>
        <p className="text-xs text-slate-500">Servizio extra, indipendente dagli abbonamenti BRONZE, SILVER e GOLD: acquistabile con qualsiasi piano, anche gratuito o scaduto. Appartiene all'organizzazione.</p>
        <div className="sticky bottom-0 -mx-6 px-6 py-4 bg-white border-t border-slate-100 space-y-3" data-testid="mkt-detail-actions">
        {s.active ? <div className="flex items-center gap-2 text-sm text-emerald-700 font-semibold" data-testid="mkt-detail-active"><CheckCircle2 className="w-4 h-4" />Servizio attivo per la tua organizzazione{s.key === "comunicati-stampa" && <Link to="/comunicati-stampa" className="ml-auto inline-flex items-center h-9 px-4 rounded-full bg-[#0ABAB5] text-slate-900 font-semibold hover:bg-[#09A8A3]" data-testid="mkt-open-press">Apri servizio</Link>}{s.key === "archivio-iscritti" && <Link to="/iscritti" className="ml-auto inline-flex items-center h-9 px-4 rounded-full bg-[#0ABAB5] text-slate-900 font-semibold hover:bg-[#09A8A3]" data-testid="mkt-open-iscritti">Apri servizio</Link>}</div>
          : !s.purchasable_now ? <div className="flex items-center gap-2 text-sm text-slate-600 font-medium" data-testid="mkt-detail-unavailable"><Clock className="w-4 h-4" />{s.status === "coming_soon" ? "Prossimamente disponibile" : s.reason}</div>
            : !canPurchase ? <p className="text-sm text-slate-600" data-testid="mkt-detail-noperm">L'acquisto è riservato all'Admin Organizzatore o agli utenti autorizzati.</p>
              : (<div className="space-y-3">
                {s.scope === "event" && <select value={eventId} onChange={(e) => setEventId(e.target.value)} className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm" data-testid="mkt-detail-event"><option value="">Seleziona l'evento…</option>{events.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</select>}
                <Button disabled={busy || (s.scope === "event" && !eventId)} onClick={buy} className="w-full h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="mkt-detail-buy">{busy ? "Attendi..." : s.free || s.demo_free ? "Attiva gratuitamente" : "Conferma e vai al pagamento"}</Button>
              </div>)}
        {s.active && <ActivePurchase s={s} canPurchase={canPurchase} onChanged={onChanged} />}
        {s.status === "coming_soon" && !s.active && <NotifyButton s={s} onToggle={onToggle} full />}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function Marketplace() {
  const [data, setData] = useState(null);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [open, setOpen] = useState(null);
  const [params, setParams] = useSearchParams();
  const load = () => api.get("/marketplace/services").then(({ data }) => { setData(data); setOpen((o) => (o ? data.services.find((x) => x.id === o.id) || null : o)); }).catch(() => setData({ services: [], categories: [] }));
  const handled = useRef(false);
  useEffect(() => {
    if (handled.current) return;
    handled.current = true;
    const sid = params.get("session_id");
    if (params.get("canceled")) { toast.info("Pagamento annullato: nessun addebito, il servizio non è stato attivato"); setParams({}, { replace: true }); }
    if (sid) api.get("/marketplace/checkout-confirmation", { params: { session_id: sid } }).then(({ data }) => {
      toast[data.status === "active" ? "success" : "info"](data.status === "active" ? "Servizio attivato" : "Pagamento in verifica: il servizio si attiverà appena confermato");
    }).catch(() => {}).finally(() => { setParams({}, { replace: true }); load(); });
    else load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const list = useMemo(() => (data?.services || []).filter((s) => (!cat || s.category === cat) && (!q || `${s.name} ${s.description}`.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => Number(!!b.active) - Number(!!a.active)), [data, q, cat]);
  const cats = [...new Set((data?.services || []).map((s) => s.category))];
  const toggle = (id, v) => {
    setData((d) => ({ ...d, services: d.services.map((x) => (x.id === id ? { ...x, notify_me: v } : x)) }));
    setOpen((o) => (o?.id === id ? { ...o, notify_me: v } : o));
  };
  return (
    <div className="animate-fade-up space-y-5" data-testid="marketplace-page">
      <PageHeader title="Marketplace" subtitle="Espandi le funzionalità di CRMEvent con servizi aggiuntivi pensati per la tua organizzazione e i tuoi eventi." />
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-md"><Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca un servizio" className="pl-9" data-testid="mkt-search" /></div>
        <div className="flex gap-2 overflow-x-auto pb-1" data-testid="mkt-categories">
          {["", ...cats].map((c) => <button key={c || "all"} type="button" onClick={() => setCat(c)} data-testid={`mkt-cat-${c || "tutte"}`}
            className={`shrink-0 h-9 px-3.5 rounded-full text-sm font-medium border transition-colors ${cat === c ? "bg-[#0ABAB5] border-[#0ABAB5] text-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>{c || "Tutte"}</button>)}
        </div>
      </div>
      {!data ? <p className="text-sm text-slate-400">Caricamento...</p> : !list.length ? <div className="text-center py-16 text-slate-500" data-testid="mkt-empty"><Store className="w-8 h-8 mx-auto mb-2 text-slate-300" />Nessun servizio trovato</div> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{list.map((s) => <Card key={s.id} s={s} onOpen={setOpen} onToggle={toggle} />)}</div>
      )}
      <Detail s={open} canPurchase={data?.can_purchase} onClose={() => setOpen(null)} onToggle={toggle} onChanged={load} />
      <span className="hidden">{STATUS.active}</span>
    </div>
  );
}
