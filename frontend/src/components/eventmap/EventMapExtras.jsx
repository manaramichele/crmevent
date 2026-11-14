import { useEffect, useState } from "react";
import { Plus, Trash2, Save, CupSoda, Mountain } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";

const row = "rounded-lg border border-slate-200 p-2 grid gap-2 grid-cols-[1fr_88px_auto]";

export function DateField({ eid, st, onSaved }) {
  const [v, setV] = useState(st.settings?.date || st.event.data_iso || "");
  const save = async (date) => {
    try { await api.put(`/eventmap/events/${eid}/settings`, { date: date && date !== st.event.data_iso ? date : null }); onSaved(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const custom = !!st.settings?.date;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="em-date">
      <span className="text-slate-500">Data nel video</span>
      <Input type="date" value={v} onChange={(e) => setV(e.target.value)} onBlur={() => save(v)} className="h-9 w-[170px]" data-testid="em-date-input" />
      {custom ? <button type="button" className="text-xs font-semibold text-[#088F8A]" onClick={() => { setV(st.event.data_iso || ""); save(null); }} data-testid="em-date-reset">Usa la data dell'evento</button>
        : <span className="text-xs text-slate-400">dall'anagrafica dell'evento</span>}
    </div>
  );
}

export function SpeedPick({ list, value, onChange }) {
  return (
    <div className="grid gap-2 sm:grid-cols-3" data-testid="em-speed">
      {list.map((s) => (
        <button key={s.key} type="button" onClick={() => onChange(s.key)} data-testid={`em-speed-${s.key}`}
          className={`rounded-lg border px-3 py-2 text-left transition-colors ${value === s.key ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 hover:bg-slate-50"}`}>
          <div className="text-sm font-semibold">{s.label}</div><div className={`text-xs ${value === s.key ? "text-slate-300" : "text-slate-500"}`}>{s.note}</div>
        </button>))}
    </div>
  );
}

export function ElevationToggle({ track, value, onChange }) {
  const ok = !!track?.has_elevation;
  return (
    <div className="space-y-1" data-testid="em-elevation">
      <label className="flex items-center gap-3 text-sm"><Switch checked={ok && value} disabled={!ok} onCheckedChange={onChange} data-testid="em-elevation-switch" /><Mountain className="w-4 h-4 text-slate-500" />Mostra altimetria nel video</label>
      {track && (ok ? <p className="text-xs text-slate-500" data-testid="em-elevation-info">Quote da {track.ele_min} a {track.ele_max} m · dislivello positivo {track.ele_gain} m</p>
        : <p className="text-xs text-amber-700" data-testid="em-elevation-missing">Il file GPX non contiene dati altimetrici validi: il grafico non verrà mostrato.</p>)}
    </div>
  );
}

function AidRow({ a, i, total, set, del }) {
  return (
    <div className={row} data-testid={`em-aid-row-${i}`}>
      <Input value={a.name} maxLength={40} placeholder="Nome ristoro" onChange={(e) => set(i, { name: e.target.value })} data-testid={`em-aid-name-${i}`} />
      <Input type="number" step="0.1" min={0} max={total} value={a.km} onChange={(e) => set(i, { km: e.target.value })} placeholder="km" data-testid={`em-aid-km-${i}`} />
      <Button type="button" variant="ghost" size="sm" onClick={() => del(i)} aria-label="Elimina ristoro" data-testid={`em-aid-del-${i}`}><Trash2 className="w-4 h-4" /></Button>
      <Input value={a.desc || ""} maxLength={120} placeholder="Descrizione (facoltativa)" onChange={(e) => set(i, { desc: e.target.value })} className="col-span-3" data-testid={`em-aid-desc-${i}`} />
      {a.source === "gpx" && <span className="text-[11px] text-sky-700 col-span-3">Importato dal GPX</span>}
    </div>
  );
}

export function AidEditor({ track, show, onShow, onSaved }) {
  const [items, setItems] = useState([]);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { setItems(track?.aid_stations || []); setDirty(false); }, [track]);
  if (!track) return null;
  const total = +(track.distance_m / 1000).toFixed(2);
  const set = (i, p) => { setItems((x) => x.map((a, k) => (k === i ? { ...a, ...p } : a))); setDirty(true); };
  const del = (i) => { setItems((x) => x.filter((_, k) => k !== i)); setDirty(true); };
  const add = () => { setItems((x) => [...x, { name: "", km: "", desc: "", source: "manual" }]); setDirty(true); };
  const save = async () => {
    try {
      await api.put(`/eventmap/tracks/${track.id}/aid-stations`, { items: items.map((a) => ({ ...a, km: Number(String(a.km).replace(",", ".")) })) });
      toast.success("Punti ristoro salvati"); setDirty(false); onSaved();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const invalid = items.some((a) => !a.name.trim() || a.km === "" || Number(String(a.km).replace(",", ".")) > total);
  return (
    <div className="space-y-2" data-testid="em-aid">
      <label className="flex items-center gap-3 text-sm"><Switch checked={show} onCheckedChange={onShow} data-testid="em-aid-switch" /><CupSoda className="w-4 h-4 text-slate-500" />Mostra punti ristoro nel video</label>
      {!items.length && <p className="text-xs text-slate-500" data-testid="em-aid-empty">{(track.aid_detected || []).length ? "Nessun ristoro nel video." : "Il GPX non contiene ristori riconoscibili."} Puoi aggiungerli indicando il chilometro (percorso di {String(total).replace(".", ",")} km).</p>}
      {items.map((a, i) => <AidRow key={i} a={a} i={i} total={total} set={set} del={del} />)}
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant="outline" onClick={add} disabled={items.length >= 30} data-testid="em-aid-add"><Plus className="w-4 h-4 mr-1" />Aggiungi ristoro</Button>
        {dirty && <Button type="button" size="sm" onClick={save} disabled={invalid} data-testid="em-aid-save"><Save className="w-4 h-4 mr-1" />Salva ristori</Button>}
      </div>
    </div>
  );
}
