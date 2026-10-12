import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Availability } from "@/pages/PlatformVideoSupport";
import { SlotPicker } from "@/pages/Assistenza";
import { BookingFilters, MeetLink, NoteEditor, notifyBookings, when } from "@/components/BookingShared";
import { toast } from "sonner";
import { AlertTriangle, RefreshCw } from "lucide-react";

const ST = { da_confermare: ["amber", "Da confermare"], confermata: ["green", "Confermata"], riprogrammata: ["blue", "Riprogrammata"], annullata: ["gray", "Annullata"] };

function MeetState({ b, busy, onRetry }) {
  if (b.demo_status === "annullata" || b.demo_status === "da_confermare") return null;
  if (b.demo_meet_link) return <MeetLink href={b.demo_meet_link} simulated={b.demo_meet_simulated} testid={`demo-meet-${b.id}`} />;
  return (
    <div className="rounded-lg bg-amber-50 border border-amber-200 p-2 text-xs text-amber-800 flex flex-wrap items-center gap-2" data-testid={`demo-meet-error-${b.id}`}>
      <AlertTriangle className="w-4 h-4 shrink-0" /><span className="flex-1 min-w-0">Meet non creato. {b.demo_meet_error || "Nessuna conferma da Google Calendar."}</span>
      <Button size="sm" variant="outline" disabled={busy} onClick={onRetry} data-testid={`demo-meet-retry-${b.id}`}><RefreshCw className="w-3.5 h-3.5 mr-1" />Riprova Meet</Button>
    </div>
  );
}

function DemoCard({ b, onAction, busy }) {
  const active = b.demo_status !== "annullata";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2 min-w-0" data-testid={`demo-booking-${b.id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0"><div className="font-semibold text-slate-900" data-testid={`demo-booking-when-${b.id}`}>{when(b.demo_slot)}</div>
          <div className="text-sm text-slate-600">{[b.nome, b.cognome].filter(Boolean).join(" ")} · {b.organizzazione || "-"}</div>
          <div className="text-xs text-slate-500 break-all">{b.email}{b.telefono ? ` · ${b.telefono}` : ""}</div></div>
        <StatusBadge color={ST[b.demo_status]?.[0]} data-testid={`demo-booking-status-${b.id}`}>{ST[b.demo_status]?.[1] || b.demo_status}</StatusBadge>
      </div>
      <div className="text-xs text-slate-500">{b.demo_source === "richiesta_demo_app" ? "Da Richieste demo (app)" : "Da modulo demo del sito"}</div>
      <MeetState b={b} busy={busy} onRetry={() => onAction("meet", b)} />
      <NoteEditor initial={b.demo_admin_note} url={`/platform/demo/bookings/${b.id}/note`} testid={`demo-${b.id}`} />
      {active && <div className="flex flex-wrap gap-2">
        {b.demo_status === "da_confermare" && <Button size="sm" disabled={busy} className="bg-[#0ABAB5] text-slate-900" onClick={() => onAction("confirm", b)} data-testid={`demo-confirm-${b.id}`}>Conferma</Button>}
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onAction("reschedule", b)} data-testid={`demo-reschedule-${b.id}`}>Riprogramma</Button>
        <Button size="sm" variant="outline" disabled={busy} className="text-red-600" onClick={() => onAction("cancel", b)} data-testid={`demo-cancel-${b.id}`}>Annulla</Button>
      </div>}
    </div>
  );
}

export default function PlatformDemo() {
  const [rows, setRows] = useState(null);
  const [status, setStatus] = useState("");
  const [whenF, setWhen] = useState("future");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [slots, setSlots] = useState([]);
  const [slot, setSlot] = useState(null);
  const load = useCallback(() => api.get("/platform/demo/bookings", { params: { when: whenF, ...(status ? { status } : {}) } }).then(({ data }) => setRows(data.bookings)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), [status, whenF]);
  useEffect(() => { load(); }, [load]);
  const run = async (b, action, slot_key) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/platform/demo/bookings/${b.id}/action`, { action, slot_key });
      if (action !== "cancel" && data.demo_meet_status === "errore") toast.warning(`Prenotazione salvata, ma il Meet non è stato creato: ${data.demo_meet_error}`, { duration: 10000 });
      else toast.success({ confirm: "Demo confermata", reschedule: "Demo riprogrammata", cancel: "Demo annullata", meet: "Link Meet creato" }[action]);
      setRes(null); load(); notifyBookings();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const onAction = async (action, b) => {
    if (action === "cancel" && !window.confirm(`Annullare la demo di ${b.nome || b.email} del ${when(b.demo_slot)}?`)) return;
    if (action !== "reschedule") return run(b, action);
    setRes(b); setSlot(null);
    try { const { data } = await api.get("/platform/demo/slots", { params: { exclude: b.id } }); setSlots(data.slots || []); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="animate-fade-up space-y-4" data-testid="demo-admin-page">
      <PageHeader title="Prenotazioni demo" subtitle="Disponibilità e demo gratuite di 30 minuti su Google Meet. Stesso calendario dell'assistenza: nessuna sovrapposizione. Le richieste confermate da Richieste demo compaiono qui." />
      <Availability base="/platform/demo/config" testid="demo" />
      <BookingFilters statuses={ST} status={status} setStatus={setStatus} whenF={whenF} setWhen={setWhen} count={rows?.length || 0} testid="demo-bookings" />
      {rows === null ? <p className="text-sm text-slate-500">Caricamento...</p>
        : rows.length === 0 ? <p className="text-sm text-slate-500" data-testid="demo-bookings-empty">Nessuna prenotazione demo.</p>
        : <div className="grid gap-3 lg:grid-cols-2" data-testid="demo-bookings-list">{rows.map((b) => <DemoCard key={b.id} b={b} onAction={onAction} busy={busy} />)}</div>}
      <Dialog open={!!res} onOpenChange={(o) => !o && setRes(null)}>
        <DialogContent className="max-w-lg" data-testid="demo-reschedule-dialog">
          <DialogHeader><DialogTitle>Riprogramma demo</DialogTitle><DialogDescription>{res?.nome} · {res?.organizzazione || res?.email}</DialogDescription></DialogHeader>
          {slots.length ? <SlotPicker slots={slots} value={slot} onChange={setSlot} testid="demo-slot" /> : <p className="text-sm text-slate-500">Nessun orario libero nelle disponibilità demo.</p>}
          <DialogFooter><Button disabled={!slot || busy} onClick={() => run(res, "reschedule", slot)} className="bg-[#0ABAB5] text-slate-900 font-semibold" data-testid="demo-reschedule-confirm">Conferma</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
