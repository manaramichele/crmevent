import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { MeetLink, notifyBookings } from "@/components/BookingShared";

const BK = { da_confermare: "Prenotazione da confermare", confermata: "Prenotazione confermata", riprogrammata: "Prenotazione riprogrammata", annullata: "Prenotazione annullata" };

function BookingInfo({ r, onSync }) {
  const b = r.booking;
  if (r.status !== "confermata" && !b) return null;
  const ok = b && ["confermata", "riprogrammata"].includes(b.demo_status);
  return (
    <div className="lg:col-span-7 flex flex-wrap items-center gap-2 text-xs" data-testid={`demo-req-booking-${r.id}`}>
      {b && <span className="text-slate-600">{BK[b.demo_status]}{b.demo_slot ? ` · ${fmtSlot(b.demo_slot)}` : ""}</span>}
      {ok && b.demo_meet_link && <MeetLink href={b.demo_meet_link} simulated={b.demo_meet_simulated} testid={`demo-req-meet-${r.id}`} />}
      {ok && !b.demo_meet_link && <span className="text-amber-700" data-testid={`demo-req-meet-error-${r.id}`}>Meet non creato. {b.demo_meet_error}</span>}
      {r.status === "confermata" && (!ok || !b.demo_meet_link) && <Button size="sm" variant="outline" className="h-7" onClick={() => onSync(r)} data-testid={`demo-req-sync-${r.id}`}>{ok ? "Riprova Meet" : "Crea prenotazione"}</Button>}
    </div>
  );
}

export const DEMO_REQ_STATUS = { nuova: "Nuova", da_confermare: "Da confermare", confermata: "Confermata", completata: "Completata", annullata: "Annullata" };
const BADGE = { nuova: "bg-sky-100 text-sky-800", da_confermare: "bg-amber-100 text-amber-800", confermata: "bg-emerald-100 text-emerald-800", completata: "bg-slate-200 text-slate-700", annullata: "bg-rose-100 text-rose-700" };
const fmtSlot = (s) => s ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)} ${s.slice(11)}` : "-";
const fmtDate = (iso) => iso ? new Date(iso).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "-";
const sel = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";

function StatusSelect({ r, onChange }) {
  return (
    <select value={r.status} onChange={(e) => onChange(r, e.target.value)} className={`${sel} ${BADGE[r.status]}`} data-testid={`demo-req-status-${r.id}`} aria-label="Stato">
      {Object.entries(DEMO_REQ_STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
    </select>
  );
}

function Row({ r, onChange, onSync }) {
  return (
    <div className="grid gap-2 lg:grid-cols-[1.3fr_1.2fr_1.6fr_1fr_1fr_1.6fr_150px] lg:items-center px-4 py-3 border-b border-slate-100 text-sm" data-testid={`demo-req-row-${r.id}`}>
      <div className="font-semibold">{r.nome}</div>
      <div className="text-slate-600">{r.organizzazione || "-"}</div>
      <div className="text-slate-600 break-all"><a href={`mailto:${r.email}`} className="text-[#088F8A]">{r.email}</a>{r.telefono && <div>{r.telefono}</div>}</div>
      <div><span className="lg:hidden text-slate-400">Preferenza: </span>{fmtSlot(r.preferred_slot)}</div>
      <div className="text-slate-500"><span className="lg:hidden text-slate-400">Inviata: </span>{fmtDate(r.created_at)}</div>
      <div className="text-slate-600 whitespace-pre-line">{r.note || <span className="text-slate-300">-</span>}</div>
      <StatusSelect r={r} onChange={onChange} />
      <BookingInfo r={r} onSync={onSync} />
    </div>
  );
}

export default function PlatformDemoRequests() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("");
  const load = useCallback(() => api.get("/platform/demo/requests", { params: status ? { status } : {} }).then(({ data }) => setItems(data.items)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), [status]);
  useEffect(() => { load(); }, [load]);
  const report = (data) => {
    const b = data.booking;
    if (b && ["confermata", "riprogrammata"].includes(b.demo_status) && !b.demo_meet_link) toast.warning(`Prenotazione demo salvata, ma il Meet non è stato creato: ${b.demo_meet_error || "nessuna conferma da Google"}`, { duration: 10000 });
    else toast.success(b ? `Stato aggiornato · ${BK[b.demo_status]}` : "Stato aggiornato");
  };
  const change = async (r, s) => {
    try { const { data } = await api.patch(`/platform/demo/requests/${r.id}`, { status: s }); report(data); load(); notifyBookings(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); load(); }
  };
  const sync = async (r) => {
    try { const { data } = await api.post(`/platform/demo/requests/${r.id}/booking`); report(data); load(); notifyBookings(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <div className="animate-fade-up space-y-4" data-testid="demo-requests-page">
      <PageHeader title="Richieste demo" subtitle="Richieste di demo gratuita inviate dagli utenti. Data e ora sono preferenze da confermare." />
      <select value={status} onChange={(e) => setStatus(e.target.value)} className={sel} data-testid="demo-req-filter">
        <option value="">Tutti gli stati</option>
        {Object.entries(DEMO_REQ_STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <div className="rounded-xl border border-slate-200 bg-white overflow-hidden" data-testid="demo-req-list">
        <div className="hidden lg:grid grid-cols-[1.3fr_1.2fr_1.6fr_1fr_1fr_1.6fr_150px] px-4 py-2 bg-slate-50 text-xs font-semibold text-slate-500 uppercase">
          <span>Nome e cognome</span><span>Organizzazione</span><span>Email e telefono</span><span>Data e ora richieste</span><span>Data invio</span><span>Note</span><span>Stato</span>
        </div>
        {items === null ? <p className="p-6 text-sm text-slate-500">Caricamento...</p>
          : items.length ? items.map((r) => <Row key={r.id} r={r} onChange={change} onSync={sync} />)
          : <p className="p-6 text-sm text-slate-500" data-testid="demo-req-empty">Nessuna richiesta demo.</p>}
      </div>
    </div>
  );
}
