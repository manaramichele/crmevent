import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Siren, Users, ShieldCheck, Ambulance, Truck, Activity, PhoneOff, AlertOctagon, Settings2, Bell, Volume2, VolumeX, KeyRound } from "lucide-react";
import { EVENT_STATES, label, fmtTime } from "./meta";

const KPI = [["volontari_presenti", "Volontari presenti", Users], ["postazioni_presidiate", "Postazioni presidiate", ShieldCheck], ["ambulanze_disponibili", "Ambulanze disponibili", Ambulance],
  ["mezzi_operativi", "Mezzi operativi", Truck], ["risorse_impegnate", "Risorse impegnate", Activity], ["non_raggiungibili", "Non raggiungibili", PhoneOff],
  ["interventi_aperti", "Interventi aperti", Siren], ["interventi_critici", "Interventi critici", AlertOctagon]];
const ROLE = { responsabile: "Responsabile Control Room", coordinatore: "Coordinatore di settore", visualizzatore: "Visualizzatore", operatore: "Operatore" };

function Clock() {
  const [t, setT] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setT(new Date()), 1000); return () => clearInterval(i); }, []);
  return <span className="font-mono tabular-nums" data-testid="cr-clock">{t.toLocaleTimeString("it-IT", { timeZone: "Europe/Rome" })}</span>;
}

function Bell_({ d, onRead, openItv }) {
  const [open, setOpen] = useState(false);
  const toggle = () => { if (!open && d.unread) onRead(); setOpen(!open); };
  return (
    <div className="relative">
      <Button variant="outline" size="icon" onClick={toggle} className="relative h-10 w-10 rounded-full" title="Notifiche" data-testid="cr-notif-btn"><Bell className="h-4 w-4" />
        {d.unread > 0 && <span className="absolute -right-1 -top-1 rounded-full bg-red-600 px-1.5 text-[10px] font-bold text-white" data-testid="cr-notif-count">{d.unread}</span>}</Button>
      {open && <div className="absolute right-0 top-12 z-50 max-h-96 w-[min(340px,90vw)] overflow-y-auto rounded-xl border border-slate-200 bg-white p-2 shadow-xl" data-testid="cr-notif-list">
        {d.notifications.map((n) => <button key={n.id} type="button" onClick={() => { if (n.intervention_id) openItv(n.intervention_id); setOpen(false); }} className="flex w-full gap-2 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-slate-50">
          <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${n.level === "critical" ? "bg-red-600" : n.level === "warn" ? "bg-amber-500" : "bg-sky-500"}`} /><span className="flex-1">{n.text}</span><span className="font-mono text-slate-400">{fmtTime(n.at).slice(0, 5)}</span></button>)}
        {!d.notifications.length && <div className="p-3 text-center text-xs text-slate-400">Nessuna notifica</div>}
        <div className="border-t border-slate-100 px-2 pt-1.5 text-[10px] text-slate-400">Le notifiche non sostituiscono telefono e radio previsti dal piano operativo.</div>
      </div>}
    </div>
  );
}

export function TopBar({ d, onStatus, onNewIntervention, onSettings, onAccess, sound, onSound, onReadNotifs, openItv }) {
  const ev = d.event, s = d.settings, st = label(EVENT_STATES, s.status), resp = d.perms.role === "responsabile";
  const date = ev.data_inizio ? new Date(ev.data_inizio).toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "long", year: "numeric" }) : "Data da definire";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid="cr-topbar">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-full sm:basis-auto">
          <div className="truncate text-lg font-bold text-slate-900 sm:text-xl" data-testid="cr-event-name">{ev.nome}</div>
          <div className="mt-0.5 flex flex-wrap gap-x-4 text-xs text-slate-500"><span data-testid="cr-event-date">{date}</span><Clock />
            <span data-testid="cr-responsabile">Responsabile: <b className="text-slate-700">{s.responsabile || "non indicato"}</b>{s.responsabile_tel && <a href={`tel:${s.responsabile_tel}`} className="ml-1 text-[#088F8A]">{s.responsabile_tel}</a>}</span>
            <span data-testid="cr-my-role">Il tuo ruolo: <b className="text-slate-700">{ROLE[d.perms.role]}</b></span></div>
        </div>
        {resp ? (
          <select value={s.status} onChange={(e) => onStatus(e.target.value)} className={`h-10 rounded-full border-0 px-4 text-xs font-bold ${st[2]}`} data-testid="cr-status-select">
            {EVENT_STATES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        ) : <span className={`rounded-full px-4 py-2 text-xs font-bold ${st[2]}`} data-testid="cr-status">{st[1]}</span>}
        <Button variant="outline" size="icon" onClick={onSound} className="h-10 w-10 rounded-full" title={sound ? "Segnale acustico attivo" : "Segnale acustico disattivato"} data-testid="cr-sound-toggle">{sound ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}</Button>
        <Bell_ d={d} onRead={onReadNotifs} openItv={openItv} />
        {resp && <Button variant="outline" size="icon" onClick={onAccess} className="h-10 w-10 rounded-full" title="Ruoli e accessi operatori" data-testid="cr-access-btn"><KeyRound className="h-4 w-4" /></Button>}
        {resp && <Button variant="outline" size="icon" onClick={onSettings} className="h-10 w-10 rounded-full" title="Impostazioni Control Room" data-testid="cr-settings-btn"><Settings2 className="h-4 w-4" /></Button>}
        {onNewIntervention && <Button onClick={onNewIntervention} className="hidden h-10 rounded-full bg-red-600 px-5 font-bold text-white hover:bg-red-700 lg:inline-flex" data-testid="cr-new-intervention-btn"><Siren className="mr-2 h-4 w-4" />+ NUOVO INTERVENTO</Button>}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
        {KPI.map(([k, l, I]) => {
          const v = d.kpi[k], warn = (k === "non_raggiungibili" || k === "interventi_critici") && v > 0;
          return (
            <div key={k} className={`rounded-xl border px-3 py-2 ${warn ? "border-red-200 bg-red-50" : "border-slate-100 bg-slate-50"}`} data-testid={`cr-kpi-${k}`}>
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500"><I className={`h-3.5 w-3.5 ${warn ? "text-red-600" : "text-[#088F8A]"}`} />{l}</div>
              <div className={`text-xl font-bold tabular-nums ${warn ? "text-red-700" : "text-slate-900"}`}>{v}{k === "postazioni_presidiate" && <span className="text-sm font-medium text-slate-400"> / {d.kpi.postazioni_attive}</span>}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
