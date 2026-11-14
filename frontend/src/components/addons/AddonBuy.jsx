import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { eur } from "@/components/addons/addonInfo";

// Acquisto / attivazione Event Planner o Event Map per un evento (usato nel Marketplace).
export default function AddonBuy({ product, onDone }) {
  const [s, setS] = useState(null);
  const [eventId, setEventId] = useState("");
  const [pkg, setPkg] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api.get(`/addons/${product}`).then(({ data }) => setS(data)).catch(() => setS({ events: [] }));
  useEffect(() => { load(); }, [product]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!s) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const free = s.unrestricted || s.included_free > 0 || s.grant_free > 0;
  const evs = (s.events || []).filter((e) => !e.active);
  const packages = s.packages || [];
  const price = product === "planner" ? s.price : packages.find((p) => p.id === pkg)?.price;
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
