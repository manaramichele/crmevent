import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { SlotPicker } from "@/pages/Assistenza";
import { toast } from "sonner";
import { Plus, Trash2, Save, ExternalLink, CalendarCheck } from "lucide-react";

const DAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"];
const STATUS = { confermata: ["green", "Confermata"], annullata: ["gray", "Annullata"], errore: ["red", "Errore"] };
const when = (k) => `${k.slice(8, 10)}/${k.slice(5, 7)}/${k.slice(0, 4)} ${k.slice(11)}`;

function Availability() {
  const [cfg, setCfg] = useState(null);
  const [closed, setClosed] = useState("");
  const load = useCallback(() => api.get("/platform/video-support/config").then(({ data }) => setCfg(data)), []);
  useEffect(() => { load(); }, [load]);
  if (!cfg) return null;
  const setW = (i, k, v) => setCfg((c) => ({ ...c, weekly: c.weekly.map((w, j) => (j === i ? { ...w, [k]: v } : w)) }));
  const save = async () => {
    try { const { data } = await api.put("/platform/video-support/config", { weekly: cfg.weekly, closed_dates: cfg.closed_dates, min_notice_hours: Number(cfg.min_notice_hours), horizon_days: Number(cfg.horizon_days) }); setCfg(data); toast.success("Disponibilità salvate"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6 space-y-4" data-testid="vs-config">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-slate-800">Le mie disponibilità</h2>
        <span className="text-xs text-slate-500" data-testid="vs-calendar-status">{cfg.simulation ? "Google Meet in SIMULAZIONE (ambiente di sviluppo)" : cfg.calendar_connected ? `Google Calendar collegato (${cfg.calendar_email}) · gli orari occupati vengono esclusi senza mostrarne i dettagli` : "Collega Google Calendar dalle Impostazioni per abilitare le prenotazioni"}</span>
      </div>
      <div className="space-y-2">
        {cfg.weekly.map((w, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2" data-testid={`vs-window-${i}`}>
            <select className="h-10 rounded-md border border-slate-200 px-2 text-sm" value={w.weekday} onChange={(e) => setW(i, "weekday", Number(e.target.value))}>{DAYS.map((d, k) => <option key={d} value={k}>{d}</option>)}</select>
            <Input type="time" step={1800} className="h-10 w-28" value={w.start} onChange={(e) => setW(i, "start", e.target.value)} />
            <span className="text-slate-400">–</span>
            <Input type="time" step={1800} className="h-10 w-28" value={w.end} onChange={(e) => setW(i, "end", e.target.value)} />
            <Button variant="ghost" size="icon" onClick={() => setCfg((c) => ({ ...c, weekly: c.weekly.filter((_, j) => j !== i) }))} data-testid={`vs-window-del-${i}`}><Trash2 className="w-4 h-4" /></Button>
          </div>
        ))}
        <Button variant="outline" size="sm" onClick={() => setCfg((c) => ({ ...c, weekly: [...c.weekly, { weekday: 0, start: "10:00", end: "12:00" }] }))} data-testid="vs-window-add"><Plus className="w-4 h-4 mr-1" />Aggiungi fascia</Button>
      </div>
      <div className="space-y-2">
        <div className="text-sm font-medium text-slate-700">Giorni di chiusura</div>
        <div className="flex flex-wrap gap-2">{cfg.closed_dates.map((d) => <button key={d} type="button" className="rounded-full bg-slate-100 px-3 py-1 text-xs" onClick={() => setCfg((c) => ({ ...c, closed_dates: c.closed_dates.filter((x) => x !== d) }))}>{d} ×</button>)}</div>
        <div className="flex gap-2"><Input type="date" className="h-10 w-44" value={closed} onChange={(e) => setClosed(e.target.value)} data-testid="vs-closed-input" />
          <Button variant="outline" disabled={!closed} onClick={() => { setCfg((c) => ({ ...c, closed_dates: [...new Set([...c.closed_dates, closed])] })); setClosed(""); }} data-testid="vs-closed-add">Aggiungi</Button></div>
      </div>
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2">Preavviso minimo (ore)<Input type="number" min={0} className="h-10 w-20" value={cfg.min_notice_hours} onChange={(e) => setCfg((c) => ({ ...c, min_notice_hours: e.target.value }))} data-testid="vs-notice" /></label>
        <label className="flex items-center gap-2">Prenotabile fino a (giorni)<Input type="number" min={1} className="h-10 w-20" value={cfg.horizon_days} onChange={(e) => setCfg((c) => ({ ...c, horizon_days: e.target.value }))} data-testid="vs-horizon" /></label>
      </div>
      <Button onClick={save} className="bg-slate-900 text-white" data-testid="vs-config-save"><Save className="w-4 h-4 mr-1.5" />Salva disponibilità</Button>
    </div>
  );
}

function BookingCard({ b, onAction }) {
  const [note, setNote] = useState(b.admin_note || "");
  const saveNote = async () => { try { await api.put(`/platform/video-support/bookings/${b.id}/note`, { admin_note: note }); toast.success("Nota salvata"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2" data-testid={`vs-booking-${b.id}`}>
      <div className="flex items-start justify-between gap-2"><div><div className="font-semibold text-slate-900">{when(b.slot_key)}</div><div className="text-sm text-slate-600">{b.org_name} · {b.user_name}</div><div className="text-xs text-slate-500 break-all">{b.user_email}</div></div>
        <StatusBadge color={STATUS[b.status]?.[0]}>{STATUS[b.status]?.[1]}</StatusBadge></div>
      <div className="text-xs text-slate-500">{b.charge_mode === "plan" ? `Inclusa nel piano${b.quota_consumed && !b.quota_refunded ? " · conteggiata" : ""}${b.quota_refunded ? " · restituita" : ""}` : `${b.credits_charged} crediti addebitati`}{b.refunded ? ` · ${b.refunded} riaccreditati` : ""}{b.cancelled_by ? ` · annullata da ${b.cancelled_by}` : ""}{b.simulated ? " · SIMULAZIONE" : ""}{b.error ? ` · errore ${b.error} (nessun addebito)` : ""}</div>
      {b.note && <p className="text-sm text-slate-600">Richiesta: {b.note}</p>}
      {b.meet_link && b.status === "confermata" && <a href={b.meet_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-semibold text-[#088F8A]" data-testid={`vs-meet-${b.id}`}><ExternalLink className="w-4 h-4" />{b.meet_link}</a>}
      <div className="flex gap-2"><Textarea rows={1} className="min-h-10" placeholder="Note interne" value={note} onChange={(e) => setNote(e.target.value)} data-testid={`vs-note-${b.id}`} /><Button variant="outline" onClick={saveNote} data-testid={`vs-note-save-${b.id}`}><Save className="w-4 h-4" /></Button></div>
      {b.status === "confermata" && <div className="flex gap-2">
        <Button size="sm" variant="outline" onClick={() => onAction("reschedule", b)} data-testid={`vs-reschedule-${b.id}`}>Riprogramma</Button>
        <Button size="sm" variant="outline" className="text-red-600" onClick={() => onAction("cancel", b)} data-testid={`vs-cancel-${b.id}`}>{b.charge_mode === "plan" ? "Annulla" : "Annulla e riaccredita"}</Button>
      </div>}
      {b.charge_mode === "plan" && b.quota_consumed && !b.quota_refunded && b.status !== "errore" && <Button size="sm" variant="outline" onClick={() => onAction("restore", b)} data-testid={`vs-restore-quota-${b.id}`}>Restituisci videochiamata (rettifica)</Button>}
    </div>
  );
}

export default function PlatformVideoSupport() {
  const [rows, setRows] = useState([]);
  const [res, setRes] = useState(null);
  const [slots, setSlots] = useState([]);
  const [slot, setSlot] = useState(null);
  const load = useCallback(() => api.get("/platform/video-support/bookings").then(({ data }) => setRows(data.bookings || [])), []);
  useEffect(() => { load(); }, [load]);
  const onAction = async (kind, b) => {
    if (kind === "restore") {
      if (!window.confirm(`Restituire la videochiamata a ${b.org_name}?`)) return;
      try { await api.post(`/platform/video-support/bookings/${b.id}/restore-quota`); toast.success("Videochiamata restituita"); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
      return;
    }
    if (kind === "cancel") {
      if (!window.confirm(b.charge_mode === "plan" ? `Annullare la prenotazione di ${b.org_name}? La videochiamata non verrà conteggiata.` : `Annullare la prenotazione di ${b.org_name}? I ${b.credits_charged} crediti verranno riaccreditati.`)) return;
      try { await api.post(`/platform/video-support/bookings/${b.id}/cancel`, {}); toast.success("Annullata e riaccreditata"); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    } else { setRes(b); setSlot(null); const { data } = await api.get("/platform/video-support/slots"); setSlots(data.slots || []); }
  };
  const doRes = async () => {
    try { await api.post(`/platform/video-support/bookings/${res.id}/reschedule`, { slot_key: slot }); toast.success("Riprogrammata"); setRes(null); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="animate-fade-up space-y-4" data-testid="vs-admin-page">
      <PageHeader title="Prenotazioni assistenza" subtitle="Disponibilità e videochiamate Google Meet prenotate dalle organizzazioni. Il servizio si attiva da Servizi e crediti." />
      <Availability />
      <div className="flex items-center gap-2 font-semibold text-slate-800"><CalendarCheck className="w-4 h-4 text-[#0ABAB5]" />Prenotazioni ({rows.length})</div>
      {rows.length === 0 ? <p className="text-sm text-slate-500" data-testid="vs-bookings-empty">Nessuna prenotazione.</p> : <div className="grid gap-3 lg:grid-cols-2">{rows.map((b) => <BookingCard key={b.id} b={b} onAction={onAction} />)}</div>}
      <Dialog open={!!res} onOpenChange={(o) => !o && setRes(null)}>
        <DialogContent className="max-w-lg" data-testid="vs-reschedule-dialog">
          <DialogHeader><DialogTitle>Riprogramma</DialogTitle><DialogDescription>{res?.org_name} · {res?.user_name}</DialogDescription></DialogHeader>
          <SlotPicker slots={slots} value={slot} onChange={setSlot} testid="vs-slot" />
          <DialogFooter><Button disabled={!slot} onClick={doRes} className="bg-[#0ABAB5] text-slate-900 font-semibold" data-testid="vs-reschedule-confirm">Conferma</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
