import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { RadioTower, CheckCircle2, MapPinned, Siren, Users, Smartphone, ClipboardList, ShieldAlert } from "lucide-react";

const FEATURES = [[MapPinned, "Mappa operativa", "Percorso, postazioni, ristori, punti critici e mezzi su un'unica mappa."], [Users, "Risorse e postazioni", "Staff, volontari, ambulanze, mezzi e forze dell'ordine autorizzate."],
  [Siren, "Interventi", "Segnalazioni con priorità, squadre assegnate e stati fino alla chiusura."], [Smartphone, "Accesso mobile", "Gli operatori confermano la presenza, segnalano e ricevono incarichi."],
  [ClipboardList, "Diario e report", "Registro cronologico automatico ed export finale PDF ed Excel."]];

function Intro({ ev, info, onBuy, busy }) {
  return (
    <div className="space-y-6" data-testid="cr-intro">
      <div className="rounded-2xl bg-slate-900 p-6 text-white sm:p-8">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#5EEAD4]"><RadioTower className="h-4 w-4" />Control Room</div>
        <h2 className="mt-2 text-2xl font-bold sm:text-3xl">Tutto l'evento sotto controllo</h2>
        <p className="mt-2 max-w-2xl text-sm text-slate-300">Gestisci volontari, postazioni, mezzi di soccorso e interventi durante la manifestazione. Una centrale operativa digitale per coordinare il personale, monitorare il percorso e affrontare rapidamente ogni situazione.</p>
        <div className="mt-5 flex flex-wrap items-center gap-4">
          <div><div className="text-3xl font-bold" data-testid="cr-price">119 € <span className="text-base font-medium text-slate-300">per evento + IVA</span></div><div className="text-xs text-slate-400">Non incluso negli abbonamenti · operatori illimitati</div></div>
          {ev && (info.can_purchase
            ? <Button onClick={onBuy} disabled={busy || ev.pending} className="h-11 rounded-full bg-[#0ABAB5] px-6 font-semibold text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-activate-btn">{busy ? "Apertura pagamento…" : "ATTIVA CONTROL ROOM"}</Button>
            : <div className="text-sm text-slate-300" data-testid="cr-admin-only">Solo un amministratore dell'organizzazione può attivare Control Room.</div>)}
        </div>
        {ev?.pending && <div className="mt-3 text-xs text-amber-300" data-testid="cr-pending">Pagamento in attesa di conferma: Control Room si attiverà appena Stripe lo conferma.</div>}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">{FEATURES.map(([I, t, d]) => <div key={t} className="rounded-xl border border-slate-200 bg-white p-4"><I className="h-5 w-5 text-[#088F8A]" /><div className="mt-2 text-sm font-semibold">{t}</div><div className="mt-1 text-xs text-slate-500">{d}</div></div>)}</div>
      <p className="flex items-start gap-2 text-xs text-slate-500"><ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />Control Room supporta il coordinamento con i responsabili sanitari e i servizi di emergenza ma non sostituisce le procedure ufficiali di soccorso. Dispositivi GPS, SIM, SMS e servizi esterni esclusi dal prezzo.</p>
    </div>
  );
}

export default function ControlRoom() {
  const [params, setParams] = useSearchParams();
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);
  const eid = params.get("event");
  const load = () => api.get("/controlroom/events").then((r) => setInfo(r.data)).catch(() => setInfo({ events: [] }));
  useEffect(() => {
    const sid = params.get("session_id");
    if (sid) {
      api.get("/controlroom/confirmation", { params: { session_id: sid } }).then((r) => {
        if (r.data.status === "active") toast.success("Pagamento confermato: Control Room è attiva per l'evento");
        else toast.info("Pagamento in verifica: l'attivazione avverrà appena Stripe lo conferma");
      }).catch(() => {}).finally(() => { params.delete("session_id"); setParams(params, { replace: true }); load(); });
    } else load();
    if (params.get("canceled")) toast.info("Pagamento annullato: nessun addebito");
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const ev = info?.events.find((e) => e.id === eid) || info?.events[0];
  const buy = async () => {
    setBusy(true);
    try { const { data } = await api.post(`/controlroom/events/${ev.id}/checkout`, { origin_url: window.location.origin }); window.location.href = data.checkout_url; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };
  return (
    <div className="animate-fade-up space-y-5" data-testid="control-room-page">
      <PageHeader title="Control Room" subtitle="Centrale operativa dell'evento" />
      {!info ? <div className="text-sm text-slate-400">Caricamento…</div> : info.events.length === 0 ? <div className="text-sm text-slate-500" data-testid="cr-no-events">Crea prima un evento in <Link to="/eventi" className="font-semibold text-[#088F8A]">Eventi</Link>.</div> : (
        <>
          <select value={ev.id} onChange={(e) => setParams({ event: e.target.value })} className="h-10 w-full max-w-md rounded-md border border-slate-200 bg-white px-3 text-sm" data-testid="cr-event-select">
            {info.events.map((e) => <option key={e.id} value={e.id}>{e.nome}{e.active ? " · attiva" : ""}</option>)}
          </select>
          {ev.active ? (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6" data-testid="cr-dashboard">
              <div className="flex items-center gap-2 font-semibold text-emerald-800"><CheckCircle2 className="h-5 w-5" />Control Room attiva per {ev.nome}</div>
              <p className="mt-2 text-sm text-emerald-900/80">La dashboard operativa con mappa, risorse, interventi e accesso mobile è in fase di realizzazione e comparirà qui automaticamente, senza ulteriori acquisti.</p>
            </div>
          ) : <Intro ev={ev} info={info} onBuy={buy} busy={busy} />}
        </>
      )}
    </div>
  );
}
