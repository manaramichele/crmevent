import { useCallback, useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ChevronLeft, ChevronRight, CheckCircle2 } from "lucide-react";

const WD = ["Lu", "Ma", "Me", "Gi", "Ve", "Sa", "Do"];
const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const longDay = (k) => new Date(`${k}T12:00:00`).toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });

function MonthCalendar({ days, value, onChange }) {
  const first = days[0] ? new Date(`${days[0]}T12:00:00`) : new Date();
  const [m, setM] = useState(new Date(first.getFullYear(), first.getMonth(), 1));
  const set = useMemo(() => new Set(days), [days]);
  const cells = [];
  for (let i = 0; i < (m.getDay() + 6) % 7; i++) cells.push(null);
  for (let d = 1; d <= new Date(m.getFullYear(), m.getMonth() + 1, 0).getDate(); d++) cells.push(new Date(m.getFullYear(), m.getMonth(), d));
  return (
    <div data-testid="demo-calendar">
      <div className="flex items-center justify-between mb-2">
        <button type="button" onClick={() => setM(new Date(m.getFullYear(), m.getMonth() - 1, 1))} className="w-8 h-8 rounded-lg hover:bg-slate-100 flex items-center justify-center" data-testid="demo-cal-prev" aria-label="Mese precedente"><ChevronLeft className="w-4 h-4" /></button>
        <span className="text-sm font-semibold capitalize">{m.toLocaleDateString("it-IT", { month: "long", year: "numeric" })}</span>
        <button type="button" onClick={() => setM(new Date(m.getFullYear(), m.getMonth() + 1, 1))} className="w-8 h-8 rounded-lg hover:bg-slate-100 flex items-center justify-center" data-testid="demo-cal-next" aria-label="Mese successivo"><ChevronRight className="w-4 h-4" /></button>
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

function Picker({ slots, value, onPick }) {
  const days = useMemo(() => [...new Set(slots.map((s) => s.slot_key.slice(0, 10)))], [slots]);
  const [day, setDay] = useState(null);
  const d = day || value?.slice(0, 10) || days[0];
  if (!slots.length) return <p className="text-sm text-slate-500 py-4 text-center" data-testid="demo-no-slots">Al momento non ci sono orari disponibili. Riprova nei prossimi giorni.</p>;
  return (
    <div className="grid sm:grid-cols-[1fr_170px] gap-4">
      <MonthCalendar days={days} value={d} onChange={setDay} />
      <div>
        <div className="text-sm font-semibold capitalize mb-2">{d && longDay(d)}</div>
        <div className="grid grid-cols-3 sm:grid-cols-1 gap-2 max-h-56 overflow-y-auto" data-testid="demo-times">
          {slots.filter((s) => s.slot_key.startsWith(d)).map((s) => (
            <button key={s.slot_key} type="button" onClick={() => onPick(s.slot_key)} data-testid={`demo-time-${s.slot_key}`}
              className={`h-10 rounded-lg border border-[#0ABAB5] text-sm font-semibold text-slate-900 transition-colors ${value === s.slot_key ? "bg-[#0ABAB5]" : "hover:bg-[#0ABAB5]/30"}`}>{s.slot_key.slice(11)}</button>
          ))}
        </div>
      </div>
    </div>
  );
}

function DemoForm({ f, setF, slots, busy, onSubmit, onClose }) {
  const ch = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  return (
    <div className="space-y-4" data-testid="welcome-demo-form">
      <div className="grid sm:grid-cols-2 gap-3">
        <Input value={f.nome || ""} onChange={ch("nome")} placeholder="Nome e cognome*" aria-label="Nome e cognome" data-testid="welcome-demo-nome" />
        <Input value={f.email || ""} disabled aria-label="Email" data-testid="welcome-demo-email" />
        <Input value={f.organizzazione || ""} onChange={ch("organizzazione")} placeholder="Organizzazione" aria-label="Organizzazione" data-testid="welcome-demo-org" />
        <Input value={f.telefono || ""} onChange={ch("telefono")} placeholder="Telefono (facoltativo)" aria-label="Telefono" data-testid="welcome-demo-telefono" />
      </div>
      <div>
        <div className="text-sm font-semibold mb-2">Data e ora preferite*</div>
        <Picker slots={slots} value={f.slot_key} onPick={(k) => setF((s) => ({ ...s, slot_key: k }))} />
        {f.slot_key && <div className="mt-2 rounded-lg bg-[#0ABAB5]/10 px-3 py-2 text-sm capitalize" data-testid="welcome-demo-selected">{longDay(f.slot_key.slice(0, 10))} · ore {f.slot_key.slice(11)}</div>}
        <p className="text-xs text-slate-500 mt-1">La data indicata è una preferenza: ti contatteremo per confermare l'appuntamento.</p>
      </div>
      <Textarea value={f.note || ""} onChange={ch("note")} placeholder="Note o richieste (facoltative)" rows={3} aria-label="Note" data-testid="welcome-demo-note" />
      <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
        <Button variant="outline" onClick={onClose} className="h-11" data-testid="welcome-demo-skip">Non ora</Button>
        <Button disabled={busy || !f.nome?.trim() || !f.slot_key} onClick={onSubmit} className="h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="welcome-demo-confirm">{busy ? "Invio in corso..." : "Richiedi una demo"}</Button>
      </div>
    </div>
  );
}

export default function WelcomeDemo() {
  const { user, checkAuth } = useAuth();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [slots, setSlots] = useState([]);
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  const eligible = user && user.role !== "superadmin" && !user.support && !!user.org_id;
  const autoOpen = eligible && user.welcome_demo === "pending";

  const start = useCallback(async () => {
    setDone(false); setOpen(true);
    const [w, s] = await Promise.all([api.get("/demo/welcome"), api.get("/demo/slots").catch(() => ({ data: { slots: [] } }))]);
    setF(w.data.prefill); setSlots(s.data.slots || []);
  }, []);
  useEffect(() => { if (autoOpen) start().catch(() => {}); }, [autoOpen]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const h = () => start().catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
    window.addEventListener("welcome-demo:open", h);
    return () => window.removeEventListener("welcome-demo:open", h);
  }, [start]);

  const close = async () => {
    setOpen(false);
    if (user?.welcome_demo === "pending") { await api.post("/demo/welcome/dismiss").catch(() => {}); await checkAuth?.(); }
  };
  const submit = async () => {
    setBusy(true);
    try {
      await api.post("/demo/requests", f);
      setDone(true); toast.success("Richiesta inviata! Ti contatteremo per confermare la demo."); checkAuth?.();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      api.get("/demo/slots").then(({ data }) => setSlots(data.slots || [])).catch(() => {});
    } finally { setBusy(false); }
  };
  if (!eligible) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-w-2xl w-[calc(100vw-1.5rem)] max-h-[92dvh] overflow-y-auto p-5 sm:p-7" data-testid="welcome-demo-dialog">
        <img src="/logo-crmevent-header.png?v=1" alt="CRMEvent" className="h-10 w-auto" />
        {done ? (
          <div className="space-y-4 text-center py-2" data-testid="welcome-demo-done">
            <CheckCircle2 className="w-12 h-12 text-[#0ABAB5] mx-auto" />
            <DialogTitle className="font-display text-2xl font-bold">Richiesta inviata!</DialogTitle>
            <DialogDescription className="text-slate-600">Ti contatteremo per confermare la demo.</DialogDescription>
            <Button onClick={close} className="h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="welcome-demo-dashboard">Chiudi</Button>
          </div>
        ) : (
          <div className="space-y-4" data-testid="welcome-demo-intro">
            <DialogTitle className="font-display text-2xl sm:text-3xl font-bold">Scopri CRMEvent con una demo gratuita</DialogTitle>
            <DialogDescription asChild>
              <div className="text-slate-600 text-sm sm:text-base space-y-2">
                <p>Vuoi scoprire come organizzare eventi, coordinare staff e volontari, gestire sponsor, attività e briefing?</p>
                <p>Prenota una breve dimostrazione personalizzata. Ti mostreremo come utilizzare CRMEvent per i tuoi eventi.</p>
              </div>
            </DialogDescription>
            <DemoForm f={f} setF={setF} slots={slots} busy={busy} onSubmit={submit} onClose={close} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
