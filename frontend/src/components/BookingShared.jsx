import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { CalendarCheck, ExternalLink, Save } from "lucide-react";

export const notifyBookings = () => window.dispatchEvent(new Event("bookings:changed"));
export const when = (k) => (k ? `${k.slice(8, 10)}/${k.slice(5, 7)}/${k.slice(0, 4)} ${k.slice(11, 16)}` : "-");
export const nowKey = () => {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
};
const sel = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";

export function BookingFilters({ statuses, status, setStatus, whenF, setWhen, count, testid }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2" data-testid={`${testid}-filters`}>
      <div className="flex items-center gap-2 font-semibold text-slate-800"><CalendarCheck className="w-4 h-4 text-[#0ABAB5]" />Prenotazioni <span data-testid={`${testid}-count`}>({count})</span></div>
      <div className="flex flex-wrap gap-2">
        <select className={sel} value={whenF} onChange={(e) => setWhen(e.target.value)} data-testid={`${testid}-filter-when`}><option value="future">Future</option><option value="past">Passate</option><option value="all">Tutte</option></select>
        <select className={sel} value={status} onChange={(e) => setStatus(e.target.value)} data-testid={`${testid}-filter-status`}><option value="">Tutti gli stati</option>{Object.entries(statuses).map(([k, v]) => <option key={k} value={k}>{v[1]}</option>)}</select>
      </div>
    </div>
  );
}

export function MeetLink({ href, simulated, testid }) {
  return <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm font-semibold text-[#088F8A] break-all" data-testid={testid}><ExternalLink className="w-4 h-4 shrink-0" />{href}{simulated ? " (simulato)" : ""}</a>;
}

export function NoteEditor({ initial, url, testid }) {
  const [note, setNote] = useState(initial || "");
  const save = async () => { try { await api.put(url, { admin_note: note }); toast.success("Nota salvata"); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  return <div className="flex gap-2"><Textarea rows={1} className="min-h-10" placeholder="Note interne" value={note} onChange={(e) => setNote(e.target.value)} data-testid={`${testid}-note`} /><Button variant="outline" onClick={save} aria-label="Salva nota" data-testid={`${testid}-note-save`}><Save className="w-4 h-4" /></Button></div>;
}
