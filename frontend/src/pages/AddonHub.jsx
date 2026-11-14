import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { CheckCircle2, Lock, Store, ArrowRight } from "lucide-react";
import { DemoVideo } from "@/components/landing/PlannerDemoSection";
import { ADDONS, SOURCE_LABEL, eur } from "@/components/addons/addonInfo";

function PriceLine({ info, s }) {
  if (info.product === "planner") return <span data-testid="addon-info-price">{s.price != null ? `${eur(s.price)} € per evento` : "Prezzo in definizione"}</span>;
  if (!s.packages?.length) return <span data-testid="addon-info-price">Pacchetti in definizione</span>;
  const min = Math.min(...s.packages.filter((p) => p.price != null).map((p) => p.price));
  return <span data-testid="addon-info-price">{Number.isFinite(min) ? `Pacchetti da ${eur(min)} €` : "Prezzo in definizione"}</span>;
}

function InfoPage({ info, s }) {
  const v = info.video;
  return (
    <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr] items-start" data-testid="addon-info-page">
      <div className={v.vertical ? "mx-auto w-full max-w-[280px]" : ""}>
        <DemoVideo mp4={v.mp4} webm={v.webm} poster={v.poster} label={`Video dimostrativo di ${info.name}`} testid="addon-info-video" className={v.vertical ? "aspect-[9/16]" : "aspect-video"} />
        {info.product === "eventmap" && <p className="mt-2 text-center text-xs text-slate-400">Video generato da Event Map con una traccia GPX reale</p>}
      </div>
      <div className="space-y-5">
        <div><h2 className="font-display text-2xl font-bold text-slate-900">{info.tagline}</h2><p className="mt-2 text-slate-600">{info.description}</p></div>
        <ul className="space-y-2" data-testid="addon-info-benefits">{info.benefits.map((b) => <li key={b} className="flex gap-2 text-sm text-slate-700"><CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0 text-[#0ABAB5]" />{b}</li>)}</ul>
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm space-y-1">
          <div className="font-semibold text-slate-900"><PriceLine info={info} s={s} /></div>
          <div className="text-slate-500">{s.included > 0 ? `Il tuo piano include ${info.name} su ${s.included} ${s.included === 1 ? "evento" : "eventi"}: già tutti assegnati.` : `Il tuo piano attuale non include eventi ${info.name}. Silver ne include 1, Gold 3.`}</div>
        </div>
        <Link to={`/marketplace?servizio=${info.slug}`} className="inline-flex h-11 items-center gap-2 rounded-lg bg-[#0ABAB5] px-6 font-semibold text-slate-900 hover:bg-[#09A8A3]" data-testid="addon-info-marketplace"><Store className="w-4 h-4" />Attiva dal Marketplace</Link>
      </div>
    </div>
  );
}

function EventRow({ e, info, s, onActivate, busy }) {
  const nav = useNavigate();
  const canFree = s.unrestricted || s.included_free > 0 || s.grant_free > 0;
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2 py-3 border-b border-slate-100 last:border-0" data-testid={`addon-event-${e.id}`}>
      <div className="flex-1 min-w-0"><div className="font-semibold text-slate-900 truncate">{e.nome}</div>
        <div className="text-xs text-slate-500">{e.active ? `${SOURCE_LABEL[e.source] || "Attivo"}${e.expires_at ? ` · scade il ${new Date(e.expires_at).toLocaleDateString("it-IT")}` : ""}` : e.assigned ? "Attivazione non più coperta dal piano: i dati restano conservati" : "Non attivo"}</div></div>
      {e.active ? (info.product === "planner"
        ? <Button size="sm" onClick={() => nav(`/eventi/${e.id}/planner`)} className="bg-slate-900 text-white" data-testid={`addon-open-${e.id}`}>Apri Event Planner <ArrowRight className="w-3.5 h-3.5 ml-1" /></Button>
        : <Button size="sm" onClick={() => nav(`/event-map/${e.id}`)} className="bg-slate-900 text-white" data-testid={`addon-open-${e.id}`}>Apri Event Map <ArrowRight className="w-3.5 h-3.5 ml-1" /></Button>)
        : canFree && s.can_purchase ? <Button size="sm" disabled={busy} onClick={() => onActivate(e.id)} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid={`addon-activate-${e.id}`}>Attiva (incluso)</Button>
          : <Link to={`/marketplace?servizio=${info.slug}&evento=${e.id}`} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50" data-testid={`addon-buy-${e.id}`}><Lock className="w-3.5 h-3.5" />Attiva dal Marketplace</Link>}
    </div>
  );
}

export default function AddonHub({ slug }) {
  const info = ADDONS[slug];
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const [params, setParams] = useSearchParams();
  const done = useRef(false);
  const load = () => api.get(`/addons/${info.product}`).then(({ data }) => setS(data)).catch(() => setS(null));
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const sid = params.get("session_id");
    if (params.get("canceled")) { toast.info("Pagamento annullato: nessun addebito"); setParams({}, { replace: true }); }
    if (sid) api.get("/addons-checkout/confirmation", { params: { session_id: sid } }).then(({ data }) => toast[data.status === "active" ? "success" : "info"](data.status === "active" ? "Pagamento confermato: attivazione disponibile" : "Pagamento in verifica"))
      .catch(() => {}).finally(() => { setParams({}, { replace: true }); load(); });
    else load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const activate = async (eid) => {
    setBusy(true);
    try { await api.post(`/addons/${info.product}/events/${eid}/activate`); toast.success(`${info.name} attivato sull'evento`); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  const hasRights = s && (s.unrestricted || s.included_free > 0 || s.grant_free > 0 || s.events?.some((e) => e.active));
  return (
    <div className="animate-fade-up space-y-6" data-testid={`addon-hub-${slug}`}>
      <PageHeader title={info.name} subtitle={info.tagline} />
      {!s ? <p className="text-sm text-slate-400">Caricamento...</p> : !hasRights ? <InfoPage info={info} s={s} /> : (
        <>
          <div className="grid gap-3 sm:grid-cols-3" data-testid="addon-counters">
            <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs text-slate-400 uppercase font-semibold">Inclusi nel piano</div><div className="text-xl font-bold" data-testid="addon-included">{s.unrestricted ? "Illimitati" : `${s.included_used} / ${s.included}`}</div></div>
            <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs text-slate-400 uppercase font-semibold">Attivazioni extra disponibili</div><div className="text-xl font-bold" data-testid="addon-grant-free">{s.grant_free}</div></div>
            {info.product === "eventmap"
              ? <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs text-slate-400 uppercase font-semibold">Video</div><div className="text-sm text-slate-700 mt-1" data-testid="addon-videos">{s.unrestricted ? "Illimitati" : <>Disponibili <b className="text-lg">{s.videos_available}</b> · generati <b>{s.videos_used}</b> · in elaborazione <b>{s.videos_in_progress || 0}</b></>}</div></div>
              : <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-xs text-slate-400 uppercase font-semibold">Evento aggiuntivo</div><div className="text-xl font-bold"><PriceLine info={info} s={s} /></div></div>}
          </div>
          <div className="rounded-xl border border-slate-200 bg-white px-4" data-testid="addon-events">
            {!s.events.length ? <p className="py-6 text-sm text-slate-500">Crea prima un evento dalla sezione <Link to="/eventi" className="font-semibold text-[#088F8A]">Eventi</Link>.</p>
              : s.events.map((e) => <EventRow key={e.id} e={e} info={info} s={s} onActivate={activate} busy={busy} />)}
          </div>
          {!s.unrestricted && s.included_free === 0 && s.grant_free === 0 && <p className="text-sm text-slate-500" data-testid="addon-exhausted">Hai utilizzato tutti gli eventi disponibili. Per altri eventi: <Link to={`/marketplace?servizio=${info.slug}`} className="font-semibold text-[#088F8A]">attiva dal Marketplace</Link> (<PriceLine info={info} s={s} />).</p>}
        </>
      )}
    </div>
  );
}
