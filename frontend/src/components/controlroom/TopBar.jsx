import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Siren, Users, ShieldCheck, Ambulance, Truck, Activity, PhoneOff, AlertOctagon, Settings2 } from "lucide-react";
import { EVENT_STATES, label } from "./meta";

const KPI = [["volontari_presenti", "Volontari presenti", Users], ["postazioni_presidiate", "Postazioni presidiate", ShieldCheck], ["ambulanze_disponibili", "Ambulanze disponibili", Ambulance],
  ["mezzi_operativi", "Mezzi operativi", Truck], ["risorse_impegnate", "Risorse impegnate", Activity], ["non_raggiungibili", "Non raggiungibili", PhoneOff],
  ["interventi_aperti", "Interventi aperti", Siren], ["interventi_urgenti", "Interventi urgenti", AlertOctagon]];

function Clock() {
  const [t, setT] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setT(new Date()), 1000); return () => clearInterval(i); }, []);
  return <span className="font-mono tabular-nums" data-testid="cr-clock">{t.toLocaleTimeString("it-IT")}</span>;
}

export function TopBar({ d, onStatus, onNewIntervention, onSettings }) {
  const ev = d.event, s = d.settings, st = label(EVENT_STATES, s.status);
  const date = ev.data_inizio ? new Date(ev.data_inizio).toLocaleDateString("it-IT", { weekday: "short", day: "numeric", month: "long", year: "numeric" }) : "Data da definire";
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4" data-testid="cr-topbar">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-full sm:basis-auto">
          <div className="truncate text-lg font-bold text-slate-900 sm:text-xl" data-testid="cr-event-name">{ev.nome}</div>
          <div className="mt-0.5 flex flex-wrap gap-x-4 text-xs text-slate-500"><span data-testid="cr-event-date">{date}</span><Clock />
            <span data-testid="cr-responsabile">Responsabile: <b className="text-slate-700">{s.responsabile || "non indicato"}</b>{s.responsabile_tel && <a href={`tel:${s.responsabile_tel}`} className="ml-1 text-[#088F8A]">{s.responsabile_tel}</a>}</span></div>
        </div>
        {d.perms.edit ? (
          <select value={s.status} onChange={(e) => onStatus(e.target.value)} className={`h-10 rounded-full border-0 px-4 text-xs font-bold ${st[2]}`} data-testid="cr-status-select">
            {EVENT_STATES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        ) : <span className={`rounded-full px-4 py-2 text-xs font-bold ${st[2]}`} data-testid="cr-status">{st[1]}</span>}
        {d.perms.edit && <Button variant="outline" size="icon" onClick={onSettings} className="h-10 w-10 rounded-full" title="Impostazioni Control Room" data-testid="cr-settings-btn"><Settings2 className="h-4 w-4" /></Button>}
        {d.perms.edit && <Button onClick={onNewIntervention} className="h-10 rounded-full bg-red-600 px-5 font-bold text-white hover:bg-red-700" data-testid="cr-new-intervention-btn"><Siren className="mr-2 h-4 w-4" />NUOVO INTERVENTO</Button>}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
        {KPI.map(([k, l, I]) => {
          const v = d.kpi[k], warn = (k === "non_raggiungibili" || k === "interventi_urgenti") && v > 0;
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
