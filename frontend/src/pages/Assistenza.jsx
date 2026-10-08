import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Video, Clock, Coins, Check, X, CalendarDays, ExternalLink, MonitorUp } from "lucide-react";

const INCLUDED = ["Supporto dedicato con un esperto CRMEvent", "Condivisione dello schermo su Google Meet", "Configurazione di eventi, staff, team, turni e permessi", "Risposte alle domande sull'uso della piattaforma"];
const EXCLUDED = ["Inserimento dei dati al posto tuo", "Sviluppo di funzioni personalizzate", "Consulenza organizzativa sull'evento", "Assistenza su software esterni a CRMEvent"];
const dayLabel = (k) => new Date(`${k}T12:00:00`).toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "short" });
const when = (slot) => new Date(`${slot.slice(0, 10)}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "2-digit", month: "long", year: "numeric" }) + ` alle ${slot.slice(11)}`;
const STATUS = { confermata: ["green", "Confermata"], annullata: ["gray", "Annullata"], errore: ["red", "Errore"] };

export function SlotPicker({ slots, value, onChange, testid = "slot" }) {
  const days = useMemo(() => [...new Set(slots.map((s) => s.slot_key.slice(0, 10)))], [slots]);
  const [day, setDay] = useState(null);
  const d = day && days.includes(day) ? day : days[0];
  if (!slots.length) return <p className="text-sm text-slate-500" data-testid={`${testid}-empty`}>Nessuna disponibilità nei prossimi giorni.</p>;
  return (
    <div className="space-y-3">
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1" data-testid={`${testid}-days`}>
        {days.map((k) => (
          <button key={k} type="button" onClick={() => setDay(k)} data-testid={`${testid}-day-${k}`}
            className={`shrink-0 rounded-lg border px-3 py-2 text-sm capitalize transition-colors ${k === d ? "border-[#0ABAB5] bg-[#0ABAB5]/10 text-slate-900 font-semibold" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}>{dayLabel(k)}</button>
        ))}
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2" data-testid={`${testid}-times`}>
        {slots.filter((s) => s.slot_key.startsWith(d)).map((s) => (
          <button key={s.slot_key} type="button" onClick={() => onChange(s.slot_key)} data-testid={`${testid}-${s.slot_key}`}
            className={`rounded-lg border h-11 text-sm font-medium transition-colors ${value === s.slot_key ? "border-[#0ABAB5] bg-[#0ABAB5] text-slate-900" : "border-slate-200 text-slate-700 hover:border-[#0ABAB5]"}`}>{s.slot_key.slice(11)}</button>
        ))}
      </div>
    </div>
  );
}

function Book({ info, onBooked }) {
  const navigate = useNavigate();
  const [slots, setSlots] = useState([]);
  const [slot, setSlot] = useState(null);
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/video-support/slots").then(({ data }) => setSlots(data.slots || [])).catch(() => setSlots([])), []);
  useEffect(() => { if (info.ready) load(); }, [info.ready, load]);
  const planMode = info.plan?.mode === "plan";
  const cost = planMode ? 0 : info.service.unit_cost;
  const enough = planMode || info.balance >= cost;
  const book = async () => {
    setBusy(true);
    try {
      await api.post("/video-support/bookings", { slot_key: slot, confirm_cost: cost, note });
      toast.success("Videochiamata prenotata: trovi il link in Le mie prenotazioni");
      setConfirm(false); setSlot(null); setNote(""); onBooked();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail?.message || e.response?.data?.detail)); setConfirm(false); load(); onBooked(true); }
    finally { setBusy(false); }
  };
  if (planMode && !info.available) return <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600 space-y-3" data-testid="support-video-plan-blocked"><p>{info.plan.reason}</p><Button onClick={() => navigate("/profilo?tab=abbonamento")} className="bg-[#0ABAB5] hover:bg-[#09a39f] text-slate-900 font-semibold" data-testid="support-video-plans-cta">Scopri i piani</Button></div>;
  if (!info.available) return <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600" data-testid="support-video-unavailable">Il servizio di assistenza in videochiamata non è ancora disponibile. Ti avviseremo nella sezione Novità quando potrai prenotarlo.</div>;
  if (!info.ready) return <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-600" data-testid="support-video-not-ready">Le prenotazioni non sono al momento disponibili. Riprova più tardi.</div>;
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 space-y-4" data-testid="support-video-book">
      <div className="flex items-center gap-2 font-semibold text-slate-800"><CalendarDays className="w-4 h-4 text-[#0ABAB5]" />Scegli giorno e orario</div>
      <SlotPicker slots={slots} value={slot} onChange={setSlot} />
      <Textarea placeholder="Di cosa vuoi parlare? (facoltativo)" value={note} onChange={(e) => setNote(e.target.value)} rows={3} data-testid="support-video-note" />
      {!enough && <p className="text-sm text-red-600" data-testid="support-video-insufficient">Crediti insufficienti: servono {cost} crediti, il saldo è {info.balance}.</p>}
      <Button disabled={!slot || !enough} onClick={() => setConfirm(true)} className="w-full sm:w-auto h-11 bg-[#0ABAB5] hover:bg-[#09a39f] text-slate-900 font-semibold" data-testid="support-video-book-btn"><Video className="w-4 h-4 mr-2" />Prenota videochiamata</Button>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent className="max-w-md" data-testid="support-video-confirm">
          <DialogHeader><DialogTitle>Confermi la prenotazione?</DialogTitle>
            <DialogDescription>Assistenza in videochiamata di 30 minuti su Google Meet.</DialogDescription></DialogHeader>
          <div className="rounded-lg bg-slate-50 border border-slate-200 p-3 text-sm space-y-1.5">
            <div className="capitalize"><b className="font-semibold">{slot && when(slot)}</b></div>
            <div>{planMode ? <b className="font-semibold" data-testid="support-video-confirm-cost">Inclusa nel piano {info.plan.plan_label}{info.plan.unlimited ? "" : ` · ne restano ${info.plan.remaining - 1} dopo questa`}</b> : <>Costo: <b className="font-semibold" data-testid="support-video-confirm-cost">{cost} crediti</b> · saldo dopo la prenotazione: {info.balance - cost}</>}</div>
            <div className="text-xs text-slate-500">{planMode ? "Annullando almeno 24 ore prima la videochiamata non viene conteggiata; annullamenti tardivi e mancata partecipazione la consumano. Puoi riprogrammare gratuitamente una volta, fino a 24 ore prima." : "Annullando almeno 24 ore prima i crediti vengono riaccreditati; entro le 24 ore non è previsto riaccredito. Puoi riprogrammare gratuitamente una volta, fino a 24 ore prima."}</div>
          </div>
          <DialogFooter className="gap-2"><Button variant="outline" onClick={() => setConfirm(false)}>Annulla</Button>
            <Button disabled={busy} onClick={book} className="bg-[#0ABAB5] hover:bg-[#09a39f] text-slate-900 font-semibold" data-testid="support-video-confirm-btn">{busy ? "Prenotazione..." : planMode ? "Conferma prenotazione" : `Conferma e usa ${cost} crediti`}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MyBookings({ reloadKey, onChange }) {
  const [rows, setRows] = useState(null);
  const [res, setRes] = useState(null);
  const [slots, setSlots] = useState([]);
  const [slot, setSlot] = useState(null);
  const load = useCallback(() => api.get("/video-support/bookings").then(({ data }) => setRows(data.bookings || [])).catch(() => setRows([])), []);
  useEffect(() => { load(); }, [load, reloadKey]);
  const cancel = async (b) => {
    const plan = b.charge_mode === "plan";
    const msg = b.can_cancel_refund ? (plan ? "Annullare la prenotazione? La videochiamata non verrà conteggiata." : `Annullare la prenotazione? I ${b.credits_charged} crediti verranno riaccreditati.`) : (plan ? "Mancano meno di 24 ore: annullando la videochiamata resta conteggiata. Confermi?" : "Mancano meno di 24 ore: annullando NON è previsto il riaccredito dei crediti. Confermi?");
    if (!window.confirm(msg)) return;
    try { const { data } = await api.post(`/video-support/bookings/${b.id}/cancel`, {}); toast.success(data.refunded ? `Prenotazione annullata · ${data.refunded} crediti riaccreditati` : "Prenotazione annullata"); load(); onChange(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const openRes = async (b) => { setRes(b); setSlot(null); const { data } = await api.get("/video-support/slots"); setSlots(data.slots || []); };
  const doRes = async () => {
    try { await api.post(`/video-support/bookings/${res.id}/reschedule`, { slot_key: slot }); toast.success("Prenotazione riprogrammata"); setRes(null); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  if (rows === null) return <p className="text-sm text-slate-400">Caricamento...</p>;
  if (!rows.length) return <p className="text-sm text-slate-500" data-testid="my-bookings-empty">Non hai ancora prenotazioni.</p>;
  return (
    <div className="space-y-3" data-testid="my-bookings">
      {rows.map((b) => (
        <div key={b.id} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`my-booking-${b.id}`}>
          <div className="flex items-start justify-between gap-2"><div className="font-semibold text-slate-900 capitalize">{when(b.slot_key)}</div><StatusBadge color={STATUS[b.status]?.[0]}>{STATUS[b.status]?.[1]}</StatusBadge></div>
          <div className="text-xs text-slate-500 mt-1">{b.user_name} · {b.charge_mode === "plan" ? `inclusa nel piano${b.quota_refunded ? " · non conteggiata" : ""}` : `${b.credits_charged} crediti`}{b.refunded ? ` · ${b.refunded} riaccreditati` : ""}{b.simulated ? " · SIMULAZIONE" : ""}</div>
          {b.note && <p className="text-sm text-slate-600 mt-1">{b.note}</p>}
          {b.status === "confermata" && (
            <div className="flex flex-wrap gap-2 mt-3">
              <a href={b.meet_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 rounded-lg bg-[#0ABAB5] px-3 h-9 text-sm font-semibold text-slate-900" data-testid={`my-booking-meet-${b.id}`}><ExternalLink className="w-4 h-4" />Apri Google Meet</a>
              {b.can_reschedule && <Button size="sm" variant="outline" className="h-9" onClick={() => openRes(b)} data-testid={`my-booking-reschedule-${b.id}`}>Riprogramma</Button>}
              <Button size="sm" variant="outline" className="h-9 text-red-600" onClick={() => cancel(b)} data-testid={`my-booking-cancel-${b.id}`}>Annulla</Button>
            </div>
          )}
        </div>
      ))}
      <Dialog open={!!res} onOpenChange={(o) => !o && setRes(null)}>
        <DialogContent className="max-w-lg" data-testid="reschedule-dialog">
          <DialogHeader><DialogTitle>Riprogramma la videochiamata</DialogTitle><DialogDescription>Puoi riprogrammare gratuitamente una sola volta.</DialogDescription></DialogHeader>
          <SlotPicker slots={slots} value={slot} onChange={setSlot} testid="reschedule-slot" />
          <DialogFooter><Button disabled={!slot} onClick={doRes} className="bg-[#0ABAB5] text-slate-900 font-semibold" data-testid="reschedule-confirm">Conferma nuovo orario</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Intro({ info }) {
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-4 sm:p-6">
        <div className="flex items-center gap-2 mb-2"><Video className="w-5 h-5 text-[#0ABAB5]" /><h2 className="font-semibold text-slate-900">{info.service.name || "Assistenza in videochiamata"}</h2></div>
        <p className="text-sm text-slate-600 leading-relaxed" data-testid="support-video-description">{info.service.description}</p>
        <div className="grid sm:grid-cols-2 gap-4 mt-4">
          <ul className="space-y-1.5 text-sm" data-testid="support-video-included"><li className="font-semibold text-slate-800">Cosa è compreso</li>{INCLUDED.map((t) => <li key={t} className="flex gap-2 text-slate-600"><Check className="w-4 h-4 text-[#0ABAB5] shrink-0 mt-0.5" />{t}</li>)}</ul>
          <ul className="space-y-1.5 text-sm" data-testid="support-video-excluded"><li className="font-semibold text-slate-800">Cosa non è compreso</li>{EXCLUDED.map((t) => <li key={t} className="flex gap-2 text-slate-600"><X className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />{t}</li>)}</ul>
        </div>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 space-y-3">
        <div className="flex items-center gap-2 text-sm text-slate-600"><Clock className="w-4 h-4 text-[#0ABAB5]" />Durata: <b className="font-semibold text-slate-900">{info.duration_min} minuti</b></div>
        <div className="flex items-center gap-2 text-sm text-slate-600"><MonitorUp className="w-4 h-4 text-[#0ABAB5]" />Google Meet con condivisione schermo</div>
        {info.plan?.mode === "plan" ? (
          <div className="rounded-lg bg-[#0ABAB5]/10 px-3 py-2 text-sm text-slate-800" data-testid="support-video-plan">{info.plan.support === "email" ? "Piano " + info.plan.plan_label + ": assistenza via email" : info.plan.unlimited ? `Piano ${info.plan.plan_label}: videochiamate illimitate e prioritarie` : `Videochiamate utilizzate: ${info.plan.used ?? 0} di ${info.plan.quota ?? 0}${info.plan.trial ? " (prova)" : " questo mese"}`}</div>
        ) : (<>
        <div className="flex items-center gap-2 text-sm text-slate-600"><Coins className="w-4 h-4 text-[#0ABAB5]" />Costo: <b className="font-semibold text-slate-900" data-testid="support-video-cost">{info.available ? `${info.service.unit_cost} crediti` : "—"}</b></div>
        <div className="rounded-lg bg-[#0ABAB5]/10 px-3 py-2 text-sm text-slate-800">Saldo organizzazione: <b className="font-semibold" data-testid="support-video-balance">{info.balance} crediti</b></div>
        </>)}
      </div>
    </div>
  );
}

export default function Assistenza() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const tab = pathname.endsWith("/prenotazioni") ? "mine" : "book";
  const [info, setInfo] = useState(null);
  const [rk, setRk] = useState(0);
  const loadInfo = useCallback(() => api.get("/video-support/info").then(({ data }) => setInfo(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), []);
  useEffect(() => { loadInfo(); }, [loadInfo]);
  const tabBtn = (k, label, to) => <button type="button" onClick={() => navigate(to)} data-testid={`support-tab-${k}`} className={`h-10 px-4 rounded-lg text-sm font-semibold transition-colors ${tab === k ? "bg-[#0ABAB5] text-slate-900" : "text-slate-600 hover:bg-slate-100"}`}>{label}</button>;
  return (
    <div className="animate-fade-up space-y-4" data-testid="support-video-page">
      <PageHeader title="Assistenza" subtitle="Prenota una sessione dedicata in videochiamata con il team CRMEvent" />
      <div className="flex gap-2">{tabBtn("book", "Prenota", "/assistenza")}{tabBtn("mine", "Le mie prenotazioni", "/assistenza/prenotazioni")}</div>
      {!info ? <p className="text-sm text-slate-400">Caricamento...</p> : tab === "book" ? (
        <>
          <Intro info={info} />
          <Book info={info} onBooked={(failed) => { loadInfo(); if (!failed) { setRk((x) => x + 1); navigate("/assistenza/prenotazioni"); } }} />
        </>
      ) : <MyBookings reloadKey={rk} onChange={loadInfo} />}
    </div>
  );
}
