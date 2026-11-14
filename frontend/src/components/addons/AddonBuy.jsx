import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { eur } from "@/components/addons/addonInfo";

// Event Planner: abbonamento per organizzazione (tutti gli eventi), 1 evento incluso in Silver/Gold, omaggi Super Admin.
function PlannerBuy({ s, load, onDone }) {
  const [cycle, setCycle] = useState("yearly");
  const [eventId, setEventId] = useState("");
  const [busy, setBusy] = useState(false);
  const sub = s.org_subscription;
  const cyc = (s.cycles || []).find((c) => c.key === cycle) || (s.cycles || [])[0];
  const incl = (s.events || []).filter((e) => e.active && e.source === "included");
  const act = async () => {
    setBusy(true);
    try { await api.post(`/addons/planner/events/${eventId}/activate`); toast.success("Evento incluso nel piano attivato"); load(); onDone?.(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  const pay = async () => {
    setBusy(true);
    try { const { data } = await api.post("/addons/planner/checkout", { origin_url: window.location.origin, cycle: cyc.key }); window.location.href = data.checkout_url; return; } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  if (s.unrestricted) return <p className="text-sm text-emerald-700 font-semibold" data-testid="planner-unrestricted">Event Planner incluso per la tua organizzazione.</p>;
  if (sub) return (
    <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800" data-testid="planner-sub-active">
      <b>{sub.source === "purchase" ? "Abbonamento Event Planner attivo" : "Omaggio Event Planner attivo"}</b> per tutti gli eventi dell'organizzazione.
      <div className="text-xs mt-1" data-testid="planner-sub-expiry">{sub.expires_at ? `${sub.source === "purchase" ? (sub.cancel_at_period_end ? "Termina il" : "Rinnovo il") : "Scade il"} ${new Date(sub.expires_at).toLocaleDateString("it-IT")}` : "Senza scadenza"}{sub.cycle ? ` · pagamento ${sub.cycle === "yearly" ? "annuale" : "semestrale"}` : ""}</div>
    </div>);
  const evs = (s.events || []).filter((e) => !e.active);
  return (
    <div className="space-y-3" data-testid="addon-buy-planner">
      {s.included > 0 && (
        <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600 space-y-2" data-testid="planner-included">
          <div>Piano {s.plan_label}: <b>1 evento incluso</b>{incl.length ? <> · attivo su <b>{incl.map((e) => e.nome).join(", ")}</b></> : ""}</div>
          {s.included_free > 0 && <div className="flex gap-2"><select value={eventId} onChange={(e) => setEventId(e.target.value)} className="flex-1 h-9 rounded-lg border border-slate-200 px-2 text-sm" data-testid="planner-included-event"><option value="">Scegli l'evento incluso…</option>{evs.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</select>
            <Button size="sm" disabled={!eventId || busy} onClick={act} data-testid="planner-included-activate">Attiva</Button></div>}
        </div>)}
      <div className="text-xs text-slate-500">{s.included > 0 ? "Per usarlo su tutti gli altri eventi attiva l'abbonamento:" : "Abbonamento valido per tutti gli eventi dell'organizzazione."}</div>
      {s.monthly_price == null ? <p className="text-sm text-slate-500" data-testid="planner-no-price">Prezzo in definizione: a breve disponibile.</p> : <>
        <div className="grid gap-2 sm:grid-cols-2" data-testid="planner-cycles">{s.cycles.map((c) => (
          <button key={c.key} type="button" onClick={() => setCycle(c.key)} data-testid={`planner-cycle-${c.key}`}
            className={`rounded-lg border px-3 py-2 text-left ${cyc?.key === c.key ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200 hover:bg-slate-50"}`}>
            <div className="text-sm font-semibold">{c.label}</div><div className="text-xs text-slate-500">{eur(c.total)} € ogni {c.months} mesi</div></button>))}</div>
        {cyc && <div className="text-sm" data-testid="planner-total"><b>{eur(s.monthly_price)} €/mese</b> · totale da pagare ora: <b>{eur(cyc.total)} €</b> per {cyc.months} mesi, rinnovo {cyc.key === "yearly" ? "annuale" : "semestrale"}</div>}
        {s.can_purchase ? <Button disabled={busy || !cyc} onClick={pay} className="w-full h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="addon-buy-submit">{busy ? "Attendi..." : "Conferma e vai al pagamento"}</Button>
          : <p className="text-sm text-slate-600" data-testid="addon-buy-noperm">L'acquisto è riservato all'Admin Organizzatore o agli utenti autorizzati.</p>}</>}
    </div>
  );
}

// Acquisto / attivazione Event Planner o Event Map per un evento (usato nel Marketplace).
export default function AddonBuy({ product, eventId: initialEvent, onDone }) {
  const [s, setS] = useState(null);
  const [eventId, setEventId] = useState(initialEvent || "");
  const [pkg, setPkg] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api.get(`/addons/${product}`).then(({ data }) => setS(data)).catch(() => setS({ events: [] }));
  useEffect(() => { load(); }, [product]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!s) return <p className="text-sm text-slate-400">Caricamento...</p>;
  if (product === "planner") return <PlannerBuy s={s} load={load} onDone={onDone} />;
  const free = s.unrestricted || s.included_free > 0 || s.grant_free > 0;
  const evs = (s.events || []).filter((e) => !e.active);
  const packages = s.packages || [];
  const price = packages.find((p) => p.id === pkg)?.price;
  const go = async () => {
    setBusy(true);
    try {
      if (free) {
        await api.post(`/addons/${product}/events/${eventId}/activate`);
        toast.success("Attivazione completata per l'evento selezionato");
        load(); onDone?.();
      } else {
        const { data } = await api.post(`/addons/${product}/checkout`, { origin_url: window.location.origin, event_id: eventId || null, package_id: pkg || null });
        window.location.href = data.checkout_url;
        return;
      }
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  if (!s.can_purchase) return <p className="text-sm text-slate-600" data-testid="addon-buy-noperm">L'attivazione è riservata all'Admin Organizzatore o agli utenti autorizzati.</p>;
  return (
    <div className="space-y-3" data-testid={`addon-buy-${product}`}>
      <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600" data-testid="addon-buy-summary">
        {s.unrestricted ? "Funzionalità inclusa per la tua organizzazione." : <>Eventi inclusi nel piano {s.plan_label || "attuale"}: <b>{s.included_used}/{s.included}</b>{s.grant_free > 0 && <> · attivazioni disponibili: <b>{s.grant_free}</b></>}</>}
        {product === "eventmap" && !s.unrestricted && <> · video disponibili: <b>{s.videos_available}</b> (generati {s.videos_used})</>}
      </div>
      {!free && product === "eventmap" && (packages.length ? (
        <select value={pkg} onChange={(e) => setPkg(e.target.value)} className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm" data-testid="addon-buy-package">
          <option value="">Seleziona il pacchetto…</option>
          {packages.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.events} {p.events === 1 ? "evento" : "eventi"} · {p.videos} video{p.validity_days ? ` · ${p.validity_days} giorni` : ""} · {p.price != null ? `${eur(p.price)} €` : "prezzo in definizione"}</option>)}
        </select>) : <p className="text-sm text-slate-500" data-testid="addon-buy-no-packages">Pacchetti in definizione: a breve disponibili.</p>)}
      <select value={eventId} onChange={(e) => setEventId(e.target.value)} className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm" data-testid="addon-buy-event">
        <option value="">{product === "eventmap" && !free ? "Evento da attivare subito (facoltativo)…" : "Seleziona l'evento…"}</option>
        {evs.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
      </select>
      {!free && <div className="text-sm" data-testid="addon-buy-price">Prezzo: <b>{price != null ? `${eur(price)} €` : "in definizione"}</b>{product === "planner" && " per evento"}</div>}
      <Button disabled={busy || (free ? !eventId : (price == null || (product === "planner" ? !eventId : !pkg)))} onClick={go}
        className="w-full h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="addon-buy-submit">
        {busy ? "Attendi..." : free ? "Attiva sull'evento (incluso)" : "Conferma e vai al pagamento"}
      </Button>
    </div>
  );
}
