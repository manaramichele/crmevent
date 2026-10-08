import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChevronLeft, ChevronRight, Clock, Video, CheckCircle2 } from "lucide-react";

const WD = ["Lu", "Ma", "Me", "Gi", "Ve", "Sa", "Do"];
const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const longDay = (k) => new Date(`${k}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });

function Steps({ step }) {
  return (
    <div className="flex items-center gap-2 text-xs font-semibold" data-testid="demo-steps">
      {["Orario", "Dati", "Conferma"].map((l, i) => (
        <div key={l} className="flex items-center gap-2">
          <span className={`w-6 h-6 rounded-full flex items-center justify-center ${i <= step ? "bg-[#0ABAB5] text-slate-900" : "bg-slate-100 text-slate-400"}`}>{i + 1}</span>
          <span className={i <= step ? "text-slate-900" : "text-slate-400"}>{l}</span>
          {i < 2 && <span className="w-5 h-px bg-slate-200" />}
        </div>
      ))}
    </div>
  );
}

function MonthCalendar({ days, value, onChange }) {
  const first = days[0] ? new Date(`${days[0]}T12:00:00`) : new Date();
  const [m, setM] = useState(new Date(first.getFullYear(), first.getMonth(), 1));
  const set = useMemo(() => new Set(days), [days]);
  const cells = [];
  const lead = (m.getDay() + 6) % 7;
  for (let i = 0; i < lead; i++) cells.push(null);
  for (let d = 1; d <= new Date(m.getFullYear(), m.getMonth() + 1, 0).getDate(); d++) cells.push(new Date(m.getFullYear(), m.getMonth(), d));
  return (
    <div data-testid="demo-calendar">
      <div className="flex items-center justify-between mb-2">
        <button type="button" onClick={() => setM(new Date(m.getFullYear(), m.getMonth() - 1, 1))} className="w-8 h-8 rounded-lg hover:bg-slate-100 flex items-center justify-center" data-testid="demo-cal-prev"><ChevronLeft className="w-4 h-4" /></button>
        <span className="text-sm font-semibold capitalize">{m.toLocaleDateString("it-IT", { month: "long", year: "numeric" })}</span>
        <button type="button" onClick={() => setM(new Date(m.getFullYear(), m.getMonth() + 1, 1))} className="w-8 h-8 rounded-lg hover:bg-slate-100 flex items-center justify-center" data-testid="demo-cal-next"><ChevronRight className="w-4 h-4" /></button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] text-slate-400 mb-1">{WD.map((w) => <span key={w}>{w}</span>)}</div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((d, i) => {
          if (!d) return <span key={i} />;
          const k = ymd(d), ok = set.has(k), sel = value === k;
          return <button key={k} type="button" disabled={!ok} onClick={() => onChange(k)} data-testid={`demo-day-${k}`}
            className={`h-9 rounded-full text-sm transition-colors ${sel ? "bg-[#0ABAB5] text-slate-900 font-bold" : ok ? "bg-[#0ABAB5]/15 text-slate-900 font-semibold hover:bg-[#0ABAB5]/30" : "text-slate-300"}`}>{d.getDate()}</button>;
        })}
      </div>
    </div>
  );
}

function Picker({ slots, onPick }) {
  const days = useMemo(() => [...new Set(slots.map((s) => s.slot_key.slice(0, 10)))], [slots]);
  const [day, setDay] = useState(null);
  const d = day || days[0];
  if (!slots.length) return <p className="text-sm text-slate-500 py-6 text-center" data-testid="demo-no-slots">Al momento non ci sono orari disponibili. Riprova nei prossimi giorni.</p>;
  return (
    <div className="grid sm:grid-cols-[1fr_180px] gap-5">
      <MonthCalendar days={days} value={d} onChange={setDay} />
      <div>
        <div className="text-sm font-semibold capitalize mb-2">{d && longDay(d)}</div>
        <div className="grid grid-cols-3 sm:grid-cols-1 gap-2 max-h-56 overflow-y-auto" data-testid="demo-times">
          {slots.filter((s) => s.slot_key.startsWith(d)).map((s) => (
            <button key={s.slot_key} type="button" onClick={() => onPick(s.slot_key)} data-testid={`demo-time-${s.slot_key}`}
              className="h-10 rounded-lg border border-[#0ABAB5] text-sm font-semibold text-slate-900 hover:bg-[#0ABAB5] transition-colors">{s.slot_key.slice(11)}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function WelcomeDemo() {
  const { user, checkAuth } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("welcome");
  const [info, setInfo] = useState(null);
  const [slots, setSlots] = useState([]);
  const [slot, setSlot] = useState(null);
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const base = user && user.role !== "superadmin" && !user.support && !!user.org_id;
  const eligible = base;
  const autoOpen = base && user.org_role === "admin_org" && user.welcome_demo === "pending";

  const start = useCallback(async (v = "welcome") => {
    const { data } = await api.get("/demo/welcome"); setInfo(data); setF(data.prefill); setView(data.booking ? "booked" : v); setOpen(true);
  }, []);
  useEffect(() => { if (autoOpen) start().catch(() => {}); }, [autoOpen]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const h = () => start("pick").catch(() => {});
    window.addEventListener("welcome-demo:open", h);
    return () => window.removeEventListener("welcome-demo:open", h);
  }, [start]);
  useEffect(() => { if (open && view === "pick") api.get("/demo/slots").then(({ data }) => setSlots(data.slots || [])).catch(() => setSlots([])); }, [open, view]);

  const close = async () => {
    setOpen(false);
    if (user?.welcome_demo === "pending") { await api.post("/demo/welcome/dismiss").catch(() => {}); await checkAuth?.(); }
    navigate("/app");
  };
  const book = async () => {
    setBusy(true);
    try { const { data } = await api.post("/demo/welcome/book", { slot_key: slot, ...f }); setDone(data); setView("done"); checkAuth?.(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setView("pick"); }
    finally { setBusy(false); }
  };
  if (!eligible || !info) return null;
  const ch = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const step = view === "pick" ? 0 : view === "form" ? 1 : 2;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1.5rem)] max-h-[92dvh] overflow-y-auto p-5 sm:p-7" data-testid="welcome-demo-dialog">
        <img src="/logo-crmevent-header.png?v=1" alt="CRMEvent" className="h-10 w-auto" />
        {view === "welcome" && (<div className="space-y-4" data-testid="welcome-demo-intro">
          <DialogTitle className="font-display text-2xl sm:text-3xl font-bold">Benvenuto in CRMEvent!</DialogTitle>
          <DialogDescription className="text-slate-600 text-sm sm:text-base">La tua prova gratuita di 14 giorni è attiva. Vuoi scoprire come organizzare al meglio i tuoi eventi? Prenota una dimostrazione gratuita con noi.</DialogDescription>
          <div className="flex flex-wrap gap-3 text-xs text-slate-600"><span className="inline-flex items-center gap-1.5"><Clock className="w-4 h-4 text-[#0ABAB5]" />30 minuti</span><span className="inline-flex items-center gap-1.5"><Video className="w-4 h-4 text-[#0ABAB5]" />Google Meet</span></div>
          <div className="flex flex-col sm:flex-row gap-2 pt-2">
            <Button onClick={() => setView("pick")} className="h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="welcome-demo-book">Prenota una demo</Button>
            <Button variant="outline" onClick={close} className="h-11" data-testid="welcome-demo-skip">Lo farò in seguito</Button>
          </div>
        </div>)}
        {(view === "pick" || view === "form") && (<div className="space-y-4">
          <DialogTitle className="font-display text-xl font-bold">Prenota la tua demo gratuita</DialogTitle>
          <DialogDescription className="text-xs text-slate-500 flex flex-wrap gap-3"><span className="inline-flex items-center gap-1"><Clock className="w-3.5 h-3.5" />30 minuti</span><span className="inline-flex items-center gap-1"><Video className="w-3.5 h-3.5" />Google Meet · ora italiana</span></DialogDescription>
          <Steps step={step} />
          {view === "pick" ? <Picker slots={slots} onPick={(k) => { setSlot(k); setView("form"); }} /> : (
            <div className="space-y-3" data-testid="welcome-demo-form">
              <div className="rounded-lg bg-[#0ABAB5]/10 px-3 py-2 text-sm capitalize" data-testid="welcome-demo-selected">{longDay(slot.slice(0, 10))} · ore {slot.slice(11)}</div>
              <div className="grid sm:grid-cols-2 gap-3">
                <Input value={f.nome || ""} onChange={ch("nome")} placeholder="Nome*" data-testid="welcome-demo-nome" />
                <Input value={f.cognome || ""} onChange={ch("cognome")} placeholder="Cognome" data-testid="welcome-demo-cognome" />
                <Input value={f.email || ""} disabled data-testid="welcome-demo-email" />
                <Input value={f.telefono || ""} onChange={ch("telefono")} placeholder="Cellulare" data-testid="welcome-demo-telefono" />
                <Input className="sm:col-span-2" value={f.organizzazione || ""} onChange={ch("organizzazione")} placeholder="Organizzazione" data-testid="welcome-demo-org" />
              </div>
              <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-between">
                <Button variant="outline" onClick={() => setView("pick")} data-testid="welcome-demo-back">Cambia orario</Button>
                <Button disabled={busy || !f.nome?.trim()} onClick={book} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="welcome-demo-confirm">{busy ? "Prenotazione..." : "Conferma prenotazione"}</Button>
              </div>
            </div>
          )}
          <button type="button" onClick={close} className="text-xs text-slate-500 underline" data-testid="welcome-demo-later">Lo farò in seguito</button>
        </div>)}
        {(view === "done" || view === "booked") && (<div className="space-y-4 text-center py-2" data-testid="welcome-demo-done">
          <CheckCircle2 className="w-12 h-12 text-[#0ABAB5] mx-auto" />
          <DialogTitle className="font-display text-2xl font-bold">{view === "done" ? "La tua demo CRMEvent è confermata!" : "Hai già una demo prenotata"}</DialogTitle>
          <DialogDescription className="text-slate-600">{view === "done" ? "Riceverai via email tutti i dettagli per partecipare alla videochiamata." : `Ti aspettiamo ${info.booking?.demo_slot ? `${longDay(info.booking.demo_slot.slice(0, 10))} alle ${info.booking.demo_slot.slice(11)}` : ""}.`}</DialogDescription>
          {(done?.meet_link || info.booking?.demo_meet_link) && <a href={done?.meet_link || info.booking?.demo_meet_link} target="_blank" rel="noreferrer" className="text-sm font-semibold text-[#088F8A] break-all" data-testid="welcome-demo-meet">{done?.meet_link || info.booking?.demo_meet_link}</a>}
          <div><Button onClick={close} className="h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="welcome-demo-dashboard">Vai alla dashboard</Button></div>
        </div>)}
      </DialogContent>
    </Dialog>
  );
}
