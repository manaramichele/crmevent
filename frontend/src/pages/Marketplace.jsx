import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Store, CheckCircle2, Clock } from "lucide-react";
import { ServiceIcon, PRICE_TYPES, STATUS, priceLabel } from "@/lib/marketplace";

const badge = (s) => (s.active ? ["Attivo", "bg-emerald-100 text-emerald-800"] : s.status === "suspended" ? ["Sospeso", "bg-red-100 text-red-700"]
  : s.purchasable_now ? ["Disponibile", "bg-[#0ABAB5]/15 text-slate-900"] : ["Prossimamente", "bg-slate-100 text-slate-600"]);

function Card({ s, onOpen }) {
  const [label, cls] = badge(s);
  return (
    <button type="button" onClick={() => onOpen(s)} data-testid={`mkt-card-${s.key}`}
      className="text-left flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition-[transform,box-shadow] duration-200 hover:-translate-y-1 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0ABAB5]">
      <div className="flex items-start justify-between gap-3"><ServiceIcon s={s} /><span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${cls}`} data-testid={`mkt-status-${s.key}`}>{label}</span></div>
      <div className="mt-4 font-semibold text-slate-900">{s.name}</div>
      <div className="text-xs text-[#088F8A] font-medium mt-0.5">{s.category}</div>
      <p className="text-sm text-slate-500 mt-2 line-clamp-3 flex-1">{s.description}</p>
      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-800">{priceLabel(s)}</span><span className="text-slate-500">{PRICE_TYPES[s.price_type]}</span>
      </div>
    </button>
  );
}

function Detail({ s, canPurchase, onClose }) {
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (s?.scope === "event") api.get("/events").then(({ data }) => setEvents(data || [])).catch(() => {}); }, [s]);
  if (!s) return null;
  const buy = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/marketplace/services/${s.id}/checkout`, { origin_url: window.location.origin, event_id: eventId || null }); window.location.href = data.checkout_url; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto rounded-2xl" data-testid="mkt-detail">
        <div className="flex items-center gap-3"><ServiceIcon s={s} /><div><DialogTitle className="text-xl font-bold">{s.name}</DialogTitle><div className="text-xs text-[#088F8A]">{s.category}</div></div></div>
        <DialogDescription className="text-sm text-slate-600">{s.description}</DialogDescription>
        <div className="grid grid-cols-2 gap-3 text-sm rounded-xl bg-slate-50 p-3">
          <div><div className="text-xs text-slate-400">Prezzo</div><b data-testid="mkt-detail-price">{priceLabel(s)}</b></div>
          <div><div className="text-xs text-slate-400">Modalità</div><b>{PRICE_TYPES[s.price_type]}</b></div>
          {s.usage_limits && <div className="col-span-2"><div className="text-xs text-slate-400">Limiti di utilizzo</div>{s.usage_limits}</div>}
          {s.terms && <div className="col-span-2"><div className="text-xs text-slate-400">Condizioni e durata</div>{s.terms}</div>}
        </div>
        <p className="text-xs text-slate-500">Servizio extra a pagamento, non incluso negli abbonamenti BRONZE, SILVER e GOLD. Appartiene all'organizzazione.</p>
        {s.active ? <div className="flex items-center gap-2 text-sm text-emerald-700 font-semibold" data-testid="mkt-detail-active"><CheckCircle2 className="w-4 h-4" />Servizio attivo per la tua organizzazione</div>
          : !s.purchasable_now ? <div className="flex items-center gap-2 text-sm text-slate-600 font-medium" data-testid="mkt-detail-unavailable"><Clock className="w-4 h-4" />{s.status === "coming_soon" ? "Prossimamente disponibile" : s.reason}</div>
            : !canPurchase ? <p className="text-sm text-slate-600" data-testid="mkt-detail-noperm">L'acquisto è riservato all'Admin Organizzatore o agli utenti autorizzati.</p>
              : (<div className="space-y-3">
                {s.scope === "event" && <select value={eventId} onChange={(e) => setEventId(e.target.value)} className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm" data-testid="mkt-detail-event"><option value="">Seleziona l'evento…</option>{events.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</select>}
                <Button disabled={busy || (s.scope === "event" && !eventId)} onClick={buy} className="w-full h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="mkt-detail-buy">{busy ? "Attendi..." : "Conferma e vai al pagamento"}</Button>
              </div>)}
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
  const load = () => api.get("/marketplace/services").then(({ data }) => setData(data)).catch(() => setData({ services: [], categories: [] }));
  useEffect(() => {
    const sid = params.get("session_id");
    if (sid) api.get("/marketplace/checkout-confirmation", { params: { session_id: sid } }).then(({ data }) => {
      toast[data.status === "active" ? "success" : "info"](data.status === "active" ? "Servizio attivato" : "Pagamento in verifica: il servizio si attiverà appena confermato");
    }).catch(() => {}).finally(() => { setParams({}, { replace: true }); load(); });
    else load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const list = useMemo(() => (data?.services || []).filter((s) => (!cat || s.category === cat) && (!q || `${s.name} ${s.description}`.toLowerCase().includes(q.toLowerCase()))), [data, q, cat]);
  const cats = [...new Set((data?.services || []).map((s) => s.category))];
  return (
    <div className="animate-fade-up space-y-5" data-testid="marketplace-page">
      <PageHeader title="Marketplace CRMEvent" subtitle="Espandi le funzionalità di CRMEvent con servizi aggiuntivi pensati per la tua organizzazione e i tuoi eventi." />
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1 max-w-md"><Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca un servizio" className="pl-9" data-testid="mkt-search" /></div>
        <div className="flex gap-2 overflow-x-auto pb-1" data-testid="mkt-categories">
          {["", ...cats].map((c) => <button key={c || "all"} type="button" onClick={() => setCat(c)} data-testid={`mkt-cat-${c || "tutte"}`}
            className={`shrink-0 h-9 px-3.5 rounded-full text-sm font-medium border transition-colors ${cat === c ? "bg-[#0ABAB5] border-[#0ABAB5] text-slate-900" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>{c || "Tutte"}</button>)}
        </div>
      </div>
      {!data ? <p className="text-sm text-slate-400">Caricamento...</p> : !list.length ? <div className="text-center py-16 text-slate-500" data-testid="mkt-empty"><Store className="w-8 h-8 mx-auto mb-2 text-slate-300" />Nessun servizio trovato</div> : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{list.map((s) => <Card key={s.id} s={s} onOpen={setOpen} />)}</div>
      )}
      <Detail s={open} canPurchase={data?.can_purchase} onClose={() => setOpen(null)} />
      <span className="hidden">{STATUS.active}</span>
    </div>
  );
}
