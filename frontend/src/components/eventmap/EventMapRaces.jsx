import { useState } from "react";
import { Plus, Pencil, Copy, Trash2, Upload, Flag } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const kmTxt = (m) => `${(m / 1000).toFixed(3).replace(/\.?0+$/, "").replace(".", ",")} km`;
export const raceKm = (r, track) => (r?.distance_km ? r.distance_km * 1000 : track?.distance_m);

export function RaceBar({ races, tracks, rid, onSelect, onNew, onEdit, onCopy, saving }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2" data-testid="em-race-bar">
      <div className="flex items-center gap-2 text-sm font-semibold"><Flag className="w-4 h-4 text-[#088F8A]" />Seleziona gara
        <span className="ml-auto text-xs font-normal text-slate-400" data-testid="em-save-state">{saving}</span></div>
      <div className="flex flex-wrap gap-2">
        <select value={rid || ""} onChange={(e) => onSelect(e.target.value)} className="h-10 min-w-[240px] flex-1 rounded-lg border border-slate-200 px-3 text-sm" data-testid="em-race-select">
          {!races.length && <option value="">Nessuna gara: creane una</option>}
          {races.map((r) => { const t = tracks.find((x) => x.id === r.track_id); const d = raceKm(r, t); return <option key={r.id} value={r.id}>{r.name}{d ? ` · ${kmTxt(d)}` : " · senza GPX"}</option>; })}
        </select>
        <Button variant="outline" onClick={onNew} data-testid="em-race-new"><Plus className="w-4 h-4 mr-1" />Nuova gara</Button>
        <Button variant="outline" onClick={onEdit} disabled={!rid} data-testid="em-race-edit"><Pencil className="w-4 h-4 mr-1" />Modifica gara</Button>
        <Button variant="outline" onClick={onCopy} disabled={!rid || races.length < 2} data-testid="em-race-copy"><Copy className="w-4 h-4 mr-1" />Duplica impostazioni</Button>
      </div>
    </div>
  );
}

export function RaceDialog({ open, race, onClose, onSave, onDelete }) {
  const [name, setName] = useState("");
  const [confirm, setConfirm] = useState(false);
  const onOpen = (o) => { if (!o) onClose(); };
  return (
    <Dialog open={open} onOpenChange={onOpen}>
      <DialogContent onOpenAutoFocus={() => { setName(race?.name || ""); setConfirm(false); }} data-testid="em-race-dialog">
        <DialogHeader><DialogTitle>{race ? "Modifica gara" : "Nuova gara"}</DialogTitle></DialogHeader>
        <label className="text-sm font-medium">Nome della gara
          <Input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="Es. Mezza Maratona" className="mt-1" data-testid="em-race-name-input" /></label>
        <p className="text-xs text-slate-500">{race ? "Titolo, data, GPX e impostazioni video si modificano nella pagina, sotto il selettore." : "La nuova gara parte con le impostazioni predefinite: potrai associare il GPX e personalizzare titolo, data e video."}</p>
        <DialogFooter className="gap-2 sm:justify-between">
          {race ? (confirm
            ? <Button variant="destructive" onClick={onDelete} data-testid="em-race-delete-confirm">Conferma eliminazione</Button>
            : <Button variant="ghost" className="text-red-600" onClick={() => setConfirm(true)} data-testid="em-race-delete"><Trash2 className="w-4 h-4 mr-1" />Elimina gara</Button>) : <span />}
          <Button disabled={!name.trim()} onClick={() => onSave(name.trim())} data-testid="em-race-save">{race ? "Salva" : "Crea gara"}</Button>
        </DialogFooter>
        {confirm && <p className="text-xs text-slate-500" data-testid="em-race-delete-note">Vengono eliminate solo le impostazioni della gara: il file GPX e i video già generati restano disponibili.</p>}
      </DialogContent>
    </Dialog>
  );
}

export function CopyDialog({ open, races, rid, onClose, onCopy }) {
  const others = races.filter((r) => r.id !== rid);
  const [src, setSrc] = useState("");
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent onOpenAutoFocus={() => setSrc(others[0]?.id || "")} data-testid="em-copy-dialog">
        <DialogHeader><DialogTitle>Duplica impostazioni da un'altra gara</DialogTitle></DialogHeader>
        <select value={src} onChange={(e) => setSrc(e.target.value)} className="h-10 w-full rounded-lg border border-slate-200 px-3 text-sm" data-testid="em-copy-source">
          {others.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
        <p className="text-xs text-slate-500">Vengono copiati stile, formato, durata, velocità, musica, logo, altimetria e ristori. Nome, titolo, sottotitolo, data, distanza e GPX restano quelli della gara selezionata.</p>
        <DialogFooter><Button disabled={!src} onClick={() => onCopy(src)} data-testid="em-copy-confirm">Copia impostazioni</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DistanceField({ race, track, onChange }) {
  const [v, setV] = useState(race.distance_km ? String(race.distance_km).replace(".", ",") : track ? (track.distance_m / 1000).toFixed(3).replace(".", ",") : "");
  const commit = () => {
    const n = Number(v.replace(",", "."));
    onChange(!v.trim() || !n || n <= 0 || (track && Math.abs(n * 1000 - track.distance_m) < 1) ? null : n);
  };
  return (
    <div className="space-y-1"><span className="text-xs text-slate-500">Distanza (km)</span>
      <Input value={v} inputMode="decimal" onChange={(e) => setV(e.target.value)} onBlur={commit} className="h-9" data-testid="em-race-distance" />
      {race.distance_km ? <button type="button" className="text-xs font-semibold text-[#088F8A]" onClick={() => { setV(track ? (track.distance_m / 1000).toFixed(3).replace(".", ",") : ""); onChange(null); }} data-testid="em-race-distance-reset">Usa la distanza del GPX</button>
        : <span className="text-xs text-slate-400">dal file GPX</span>}
    </div>
  );
}

export function RaceFields({ race, st, upd, onUpload, onFromMap, busy }) {
  const track = st.tracks.find((t) => t.id === race.track_id);
  const evDate = st.event.data_iso || "";
  return (
    <div className="space-y-3" data-testid="em-race-fields">
      <div className="text-sm font-semibold">1. Dati della gara</div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1"><span className="text-xs text-slate-500">Titolo nel video</span>
          <Input value={race.title || ""} maxLength={60} onChange={(e) => upd({ title: e.target.value })} placeholder={st.event.nome} className="h-9" data-testid="em-race-title" /></label>
        <label className="space-y-1"><span className="text-xs text-slate-500">Sottotitolo</span>
          <Input value={race.subtitle || ""} maxLength={60} onChange={(e) => upd({ subtitle: e.target.value })} placeholder="Es. 21,097 KM" className="h-9" data-testid="em-race-subtitle" /></label>
        <div className="space-y-1"><span className="text-xs text-slate-500">Data della gara</span>
          <Input type="date" value={race.date || evDate} onChange={(e) => upd({ date: e.target.value && e.target.value !== evDate ? e.target.value : null })} className="h-9" data-testid="em-race-date" />
          {race.date ? <button type="button" className="text-xs font-semibold text-[#088F8A]" onClick={() => upd({ date: null })} data-testid="em-race-date-reset">Usa la data dell'evento</button>
            : <span className="text-xs text-slate-400">dall'anagrafica dell'evento</span>}</div>
        <DistanceField key={`${race.id}-${race.track_id}`} race={race} track={track} onChange={(d) => upd({ distance_km: d })} />
      </div>
      <div className="space-y-2"><span className="text-xs text-slate-500">Seleziona percorso</span>
        <select value={race.track_id || ""} onChange={(e) => upd({ track_id: e.target.value || null, distance_km: null })} className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm" data-testid="em-track-select">
          <option value="">Seleziona un file GPX…</option>{st.tracks.map((t) => <option key={t.id} value={t.id}>{t.name} · {kmTxt(t.distance_m)} · {t.points} punti</option>)}</select>
        <div className="flex flex-wrap gap-2">
          <select value="" onChange={(e) => e.target.value && onFromMap(e.target.value)} className="h-9 min-w-[220px] flex-1 rounded-md border border-slate-200 px-2 text-sm" data-testid="em-route-select">
            <option value="">{st.routes?.length ? "Scegli da Percorsi Eventi…" : "Nessun percorso in Percorsi Eventi"}</option>
            {(st.routes || []).map((m) => <option key={m.map_id} value={m.map_id}>{m.nome}{m.gare?.length ? ` · ${m.gare.join(", ")}` : ""} · {m.format}{m.distance ? ` · ${m.distance} km` : ""} · agg. {new Date(m.updated_at).toLocaleDateString("it-IT")}</option>)}</select>
          <label className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-sm font-semibold cursor-pointer hover:bg-slate-50" data-testid="em-upload-label"><Upload className="w-4 h-4" />{busy ? "Caricamento…" : "Carica nuovo file"}
            <input type="file" accept=".gpx" className="hidden" onChange={(e) => { onUpload(e.target.files?.[0]); e.target.value = ""; }} data-testid="em-upload-input" /></label>
        </div>
        {track && !track.has_elevation && <p className="text-xs text-amber-700" data-testid="em-no-elevation">Questo percorso non contiene dati altimetrici: il profilo altimetrico non sarà disponibile.</p>}
        {race.route_update && track?.source_map_id && <div className="flex flex-wrap items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 p-2 text-sm text-sky-900" data-testid="em-route-update">
          <span className="flex-1">È disponibile una versione aggiornata del percorso. Vuoi utilizzarla?</span>
          <Button size="sm" variant="outline" onClick={() => onFromMap(track.source_map_id)} data-testid="em-route-update-use">Usa versione aggiornata</Button></div>}</div>
    </div>
  );
}

export function UnassignedBanner({ st, onCreate }) {
  const n = st.unassigned_tracks?.length || 0;
  if (!n || (st.races.length && n === 0)) return null;
  return (
    <div className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm flex flex-wrap items-center gap-3" data-testid="em-unassigned">
      <span className="flex-1">{n === 1 ? "1 file GPX già caricato non è associato a nessuna gara." : `${n} file GPX già caricati non sono associati a nessuna gara.`} Puoi creare le schede gara partendo da questi file, senza caricarli di nuovo.</span>
      <Button size="sm" onClick={onCreate} data-testid="em-unassigned-create">Crea schede gara dai GPX</Button>
    </div>
  );
}
