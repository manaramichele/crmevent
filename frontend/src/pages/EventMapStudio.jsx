import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { SpeedPick, ElevationToggle, AidEditor } from "@/components/eventmap/EventMapExtras";
import { RaceBar, RaceDialog, CopyDialog, RaceFields, UnassignedBanner } from "@/components/eventmap/EventMapRaces";
import { VideoGroupCard, AidPausePick, TimingWarning } from "@/components/eventmap/EventMapVideos";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ArrowLeft, Upload, Film, Play, Pause, Image as ImageIcon } from "lucide-react";


function Choice({ items, value, onChange, testid }) {
  return (
    <div className="flex flex-wrap gap-2" data-testid={testid}>{items.map((it) => (
      <button key={it.key} type="button" disabled={it.disabled} onClick={() => onChange(it.key)} title={it.note} data-testid={`${testid}-${it.key}`}
        className={`h-9 px-3 rounded-full text-sm font-medium border transition-colors disabled:opacity-40 ${value === it.key ? "bg-slate-900 border-slate-900 text-white" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"}`}>{it.label}{it.disabled && it.note ? ` (${it.note})` : ""}</button>))}
    </div>
  );
}

function MusicPick({ list, value, onChange }) {
  const [playing, setPlaying] = useState(null);
  const [audio] = useState(() => new Audio());
  useEffect(() => () => audio.pause(), [audio]);
  const toggle = (m) => {
    if (playing === m.key) { audio.pause(); setPlaying(null); return; }
    audio.src = m.preview; audio.currentTime = 0; audio.play().catch(() => {}); setPlaying(m.key);
  };
  return (
    <div className="grid gap-2 sm:grid-cols-2" data-testid="em-music">
      <button type="button" onClick={() => onChange(null)} data-testid="em-music-none" className={`h-11 rounded-lg border px-3 text-left text-sm ${!value ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"}`}>Nessuna musica</button>
      {list.map((m) => (
        <div key={m.key} className={`h-11 rounded-lg border px-3 flex items-center gap-2 text-sm ${value === m.key ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"}`}>
          <button type="button" onClick={() => onChange(m.key)} className="flex-1 text-left" data-testid={`em-music-${m.key}`}>{m.label}</button>
          <button type="button" onClick={() => toggle(m)} className="text-[#088F8A]" aria-label="Ascolta anteprima" data-testid={`em-music-play-${m.key}`}>{playing === m.key ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}</button>
        </div>))}
    </div>
  );
}

function LogoThumb({ eid, lid }) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url = null;
    api.get(`/eventmap/events/${eid}/logos/${lid}/image`, { responseType: "blob" }).then(({ data }) => { url = URL.createObjectURL(data); setSrc(url); }).catch(() => setSrc(""));
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [eid, lid]);
  return src ? <img src={src} alt="Logo evento" className="h-12 w-auto max-w-[140px] object-contain" data-testid={`em-logo-thumb-${lid}`} /> : <div className="h-12 w-16 rounded bg-slate-100" />;
}

function LogoPick({ eid, st, value, onChange, onUpload, onDelete, busy }) {
  const opts = [...(st.event.has_logo ? [{ id: "event", label: "Logo dell'evento" }] : []), ...st.logos.map((l) => ({ id: l.id, label: l.name }))];
  const box = "rounded-lg border p-2 flex flex-col items-center justify-center gap-1 text-xs min-w-[120px] bg-[repeating-conic-gradient(#f1f5f9_0_25%,#fff_0_50%)] bg-[length:16px_16px]";
  return (
    <div className="space-y-2" data-testid="em-logo">
      <div className="flex flex-wrap gap-2">
        {opts.map((o) => (
          <div key={o.id} className="relative">
            <button type="button" onClick={() => onChange(o.id)} className={`${box} ${value === o.id ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"}`} data-testid={`em-logo-opt-${o.id}`}>
              <LogoThumb eid={eid} lid={o.id} /><span className="max-w-[140px] truncate text-slate-600">{o.label}</span></button>
            {o.id !== "event" && <button type="button" onClick={() => onDelete(o.id)} aria-label="Rimuovi logo" className="absolute -right-2 -top-2 h-6 w-6 rounded-full border border-slate-200 bg-white text-slate-500 hover:text-red-600" data-testid={`em-logo-del-${o.id}`}>×</button>}
          </div>))}
        <button type="button" onClick={() => onChange(null)} className={`rounded-lg border px-3 text-sm min-h-[76px] ${!value ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"}`} data-testid="em-logo-none">Senza logo</button>
      </div>
      <label className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-sm font-semibold cursor-pointer hover:bg-slate-50" data-testid="em-logo-upload-label"><Upload className="w-4 h-4" />{busy ? "Caricamento…" : st.event.has_logo || st.logos.length ? "Sostituisci con un PNG" : "Carica logo PNG"}
        <input type="file" accept="image/png" className="hidden" onChange={(e) => { onUpload(e.target.files?.[0]); e.target.value = ""; }} data-testid="em-logo-upload-input" /></label>
      <p className="text-xs text-slate-500">PNG, preferibilmente con sfondo trasparente (max 5 MB). Il logo resta fisso in alto a destra per tutta la durata del video.</p>
    </div>
  );
}

export default function EventMapStudio() {
  const { id } = useParams();
  const [st, setSt] = useState(null);
  const [opt, setOpt] = useState(null);
  const [f, setF] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const [saving, setSaving] = useState("");
  const [dlg, setDlg] = useState("");
  const [filter, setFilter] = useState("");
  const dirty = useRef(false);
  const fRef = useRef(null);
  fRef.current = f;
  const load = useCallback(() => api.get(`/eventmap/events/${id}`).then(({ data }) => {
    setSt(data);
    setF((x) => (x && data.races.some((r) => r.id === x.id) ? x : data.races[0] ? { ...data.races[0] } : null));
    return data;
  }).catch((e) => { toast.error(formatApiError(e.response?.data?.detail)); setSt((x) => x || { missing: true }); }), [id]);
  useEffect(() => { load(); api.get("/eventmap/options").then(({ data }) => setOpt(data)); }, [load]);
  const flush = useCallback(async () => {
    const r = fRef.current;
    if (!dirty.current || !r) return true;
    dirty.current = false; setSaving("Salvataggio…");
    const keys = ["title", "subtitle", "date", "distance_km", "track_id", "logo", "style", "format", "duration", "music", "speed", "show_aid", "show_elevation", "aid_pause", "aid_pause_auto"];
    try {
      const { data } = await api.put(`/eventmap/races/${r.id}`, Object.fromEntries(keys.map((k) => [k, r[k] ?? null])));
      setSt((s) => ({ ...s, races: s.races.map((x) => (x.id === data.id ? data : x)) })); setSaving("Modifiche salvate"); return true;
    } catch (e) { dirty.current = true; setSaving("Modifiche non salvate"); toast.error(formatApiError(e.response?.data?.detail)); return false; }
  }, []);
  useEffect(() => {
    if (!dirty.current) return undefined;
    const t = setTimeout(flush, 700);
    return () => clearTimeout(t);
  }, [f, flush]);
  useEffect(() => () => { flush(); }, [flush]);
  const upd = (p) => { dirty.current = true; setPreview(null); setF((x) => ({ ...x, ...p })); };
  const selectRace = async (rid, patch) => {
    if (!(await flush())) return;
    const r = rid === fRef.current?.id ? fRef.current : st.races.find((x) => x.id === rid);
    setPreview(null); setSaving("");
    if (patch) { dirty.current = true; setF({ ...r, ...patch }); } else setF(r ? { ...r } : null);
  };
  const saveRace = async (name) => {
    try {
      if (dlg === "edit") { await flush(); const { data } = await api.put(`/eventmap/races/${f.id}`, { name }); setF((x) => ({ ...x, name: data.name })); }
      else { await flush(); const { data } = await api.post(`/eventmap/events/${id}/races`, { name }); setF({ ...data }); toast.success(`Gara «${data.name}» creata`); }
      setDlg(""); await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const deleteRace = async () => {
    try { await api.delete(`/eventmap/races/${f.id}`); dirty.current = false; setF(null); setDlg(""); await load(); toast.success("Gara eliminata: GPX e video restano disponibili"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const copyFrom = async (src) => {
    try { await flush(); const { data } = await api.post(`/eventmap/races/${f.id}/copy-from/${src}`); setF({ ...data }); setDlg(""); await load(); toast.success("Impostazioni copiate"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const fromTracks = async () => {
    try { const { data } = await api.post(`/eventmap/events/${id}/races/from-tracks`); await load(); toast.success(`${data.created.length} schede gara create`); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const [target, setTarget] = useState(null);
  const regen = (g, v) => {
    const rid = g.race_id || v.race_id || st.races.find((r) => r.track_id === v.track_id)?.id;
    if (!rid || !st.races.some((r) => r.id === rid)) { toast.error("La gara di questo video non esiste più: crea una gara e associa il GPX"); return; }
    selectRace(rid, { style: v.style, format: v.format, duration: v.duration, music: v.music, logo: v.logo, speed: v.speed || "normal", show_aid: v.show_aid !== false,
      show_elevation: v.show_elevation !== false, aid_pause: v.aid_pause ?? 3, aid_pause_auto: !!v.aid_pause_auto });
    setTarget(g);
    window.scrollTo({ top: 0, behavior: "smooth" });
    toast.success("Impostazioni del video caricate: modificale e rigenera senza consumare crediti");
  };
  const pending = st?.videos?.some((v) => v.status === "queued" || v.status === "processing");
  useEffect(() => {
    if (!pending) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [pending, load]);
  const upload = async (file) => {
    if (!file) return;
    setBusy("upload");
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post(`/eventmap/events/${id}/tracks`, fd); toast.success(data.duplicate ? `File già presente: uso «${data.name}»` : `Traccia caricata: ${kmTxt(data.distance_m)}`); await load(); upd({ track_id: data.id, distance_km: null }); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  const fromMap = async (mid) => {
    setBusy("upload");
    try { const { data } = await api.post(`/eventmap/events/${id}/tracks/from-map/${mid}`); await load(); upd({ track_id: data.id, distance_km: null }); toast.success(data.duplicate ? "Traccia già importata: associata alla gara" : "Traccia dell'evento importata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  const uploadLogo = async (file) => {
    if (!file) return;
    setBusy("logo");
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post(`/eventmap/events/${id}/logos`, fd); toast.success(data.transparent ? "Logo caricato" : "Logo caricato (senza trasparenza: comparirà su un riquadro bianco)"); await load(); upd({ logo: data.id }); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  const deleteLogo = async (lid) => {
    try { await api.delete(`/eventmap/events/${id}/logos/${lid}`); if (f.logo === lid) upd({ logo: st.event.has_logo ? "event" : null }); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const doPreview = async () => {
    setBusy("preview");
    try { if (await flush()) { const { data } = await api.post(`/eventmap/races/${f.id}/preview`, {}, { responseType: "blob" }); setPreview(URL.createObjectURL(data)); } }
    catch { toast.error("Anteprima non riuscita"); }
    setBusy("");
  };
  const generate = async () => {
    setBusy("gen");
    try {
      if (await flush()) {
        if (target) { await api.post(`/eventmap/video-groups/${target.id}/versions`, { race_id: f.id }); toast.success("Nuova versione in elaborazione: nessun credito consumato"); setTarget(null); }
        else { await api.post(`/eventmap/races/${f.id}/videos`); toast.success(`Video «${f.name}» in coda di elaborazione`); }
        await load();
      }
    }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  if (st?.missing) return <p className="text-sm text-slate-600" data-testid="em-missing">Evento non trovato. <Link to="/event-map" className="font-semibold text-[#088F8A]">Torna a Event Map</Link></p>;
  if (!st || !opt) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const rg = st.rights;
  const track = f && st.tracks.find((t) => t.id === f.track_id);
  const fmts = opt.formats.map((x) => ({ ...x, disabled: !rg.formats.includes(x.key) }));
  const raceOf = (x) => x.race_id || st.races.find((r) => r.track_id === x.track_id)?.id;
  const groups = (st.groups || []).map((g) => ({ g, versions: st.videos.filter((v) => (v.group_id || v.id) === g.id).sort((a, b) => (b.version || 1) - (a.version || 1)) }))
    .filter(({ g, versions }) => versions.length && (!filter || (g.race_id || raceOf(versions[0])) === filter));
  const editing = st.races.find((r) => r.id === f?.id);
  const timing = editing?.timing;
  return (
    <div className="animate-fade-up space-y-6" data-testid="em-studio">
      <Link to="/event-map" className="inline-flex items-center gap-1 text-sm text-slate-500"><ArrowLeft className="w-4 h-4" />Event Map</Link>
      <PageHeader title={st.event.nome} subtitle={`Event Map${st.event.data ? ` · ${st.event.data}` : ""}`} />
      {rg.active && <UnassignedBanner st={st} onCreate={fromTracks} />}
      {rg.active && <RaceBar races={st.races} tracks={st.tracks} rid={f?.id} saving={saving} onSelect={(rid) => selectRace(rid)} onNew={() => setDlg("new")} onEdit={() => setDlg("edit")} onCopy={() => setDlg("copy")} />}
      <RaceDialog open={dlg === "new" || dlg === "edit"} race={dlg === "edit" ? editing : null} onClose={() => setDlg("")} onSave={saveRace} onDelete={deleteRace} />
      <CopyDialog open={dlg === "copy"} races={st.races} rid={f?.id} onClose={() => setDlg("")} onCopy={copyFrom} />
      {!rg.active ? <p className="text-sm text-slate-600" data-testid="em-not-active">Event Map non è attivo per questo evento. <Link to={`/marketplace?servizio=event-map&evento=${id}`} className="font-semibold text-[#088F8A]">Attivalo dal Marketplace</Link>.</p> : !f ? <p className="rounded-xl border border-dashed border-slate-200 p-6 text-sm text-slate-500" data-testid="em-no-race">Crea la prima gara con «Nuova gara» per associare un file GPX e preparare il video.</p> : (
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-5">
          <div className="text-sm" data-testid="em-counters">Video disponibili: <b data-testid="em-remaining">{rg.videos_remaining ?? "illimitati"}</b> · generati {rg.videos_used} · in elaborazione {rg.in_progress}{rg.expires_at ? ` · scadenza ${new Date(rg.expires_at).toLocaleDateString("it-IT")}` : ""}</div>
          <RaceFields key={f.id} race={f} st={st} upd={upd} onUpload={upload} onFromMap={fromMap} busy={busy === "upload"} />
          <div className="space-y-2"><div className="text-sm font-semibold">2. Stile mappa</div><Choice items={opt.styles} value={f.style} onChange={(v) => upd({ style: v })} testid="em-style" /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">3. Formato</div><Choice items={fmts} value={f.format} onChange={(v) => upd({ format: v })} testid="em-format" /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">4. Durata</div><Choice items={opt.durations.map((d) => ({ key: d, label: `${d} secondi` }))} value={f.duration} onChange={(v) => upd({ duration: v })} testid="em-duration" /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">5. Musica (brani originali CRMEvent)</div><MusicPick list={opt.music} value={f.music} onChange={(v) => upd({ music: v })} /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">6. Logo della gara</div><LogoPick eid={id} st={st} value={f.logo} onChange={(v) => upd({ logo: v })} onUpload={uploadLogo} onDelete={deleteLogo} busy={busy === "logo"} /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">7. Velocità animazione</div><SpeedPick list={opt.speeds} value={f.speed} onChange={(v) => upd({ speed: v })} /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">8. Punti ristoro e di interesse</div><AidEditor track={track} show={f.show_aid} onShow={(v) => upd({ show_aid: v })} onSaved={load} /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">9. Altimetria</div><ElevationToggle track={track} value={f.show_elevation} onChange={(v) => upd({ show_elevation: v })} /></div>
          {f.show_aid !== false && <div className="space-y-2"><div className="text-sm font-semibold">10. Pausa ai ristori</div><AidPausePick race={f} upd={upd} /></div>}
          <TimingWarning timing={timing} onUse={(d) => upd({ duration: d })} />
          {target && <div className="flex flex-wrap items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900" data-testid="em-regen-target"><span className="flex-1">Stai modificando un video già acquistato: la nuova versione non consuma crediti e la precedente resta in archivio.</span>
            <Button size="sm" variant="ghost" onClick={() => setTarget(null)} data-testid="em-regen-cancel">Annulla modifica</Button></div>}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={!f.track_id || !!busy} onClick={doPreview} data-testid="em-preview-btn"><ImageIcon className="w-4 h-4 mr-1" />{busy === "preview" ? "Anteprima…" : "Anteprima"}</Button>
            <Button disabled={!f.track_id || !!busy || (!target && rg.videos_remaining === 0)} onClick={generate} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="em-generate-btn"><Film className="w-4 h-4 mr-1" />{busy === "gen" ? "Invio…" : target ? "Rigenera video (senza crediti)" : "Genera video"}</Button>
          </div>
          <p className="text-xs text-slate-500" data-testid="em-edit-note">Puoi modificare e rigenerare il video tutte le volte che vuoi. Dopo il primo download non potrai più modificarlo.</p>
          {rg.videos_remaining === 0 && <p className="text-sm text-slate-500" data-testid="em-no-videos">Hai esaurito i video disponibili: <Link to={`/marketplace?servizio=event-map&evento=${id}`} className="font-semibold text-[#088F8A]">acquista un pacchetto</Link>.</p>}
        </div>
        <div className="space-y-3 lg:sticky lg:top-4 lg:self-start">
          {preview ? <img src={preview} alt="Anteprima del percorso" className="mx-auto max-h-[520px] rounded-xl border border-slate-200" data-testid="em-preview-img" /> : <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">L'anteprima mostra un momento lungo il percorso e la scena finale, con data, velocità, ristori, altimetria, logo e stile scelti. Non consuma video.</div>}
        </div>
      </div>)}
      <div className="space-y-3"><div className="flex flex-wrap items-center gap-3"><h2 className="font-display text-lg font-bold flex-1">Archivio video</h2>
        {st.races.length > 1 && <select value={filter} onChange={(e) => setFilter(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-3 text-sm" data-testid="em-archive-filter"><option value="">Tutte le gare</option>{st.races.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select>}</div>
        {!groups.length ? <p className="text-sm text-slate-500" data-testid="em-archive-empty">Nessun video generato {filter ? "per questa gara" : "per questo evento"}.</p>
          : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="em-archive">{groups.map(({ g, versions }) => <VideoGroupCard key={g.id} g={g} versions={versions} sa={st.is_superadmin} label={versions[0].race_label} onRegen={regen} onReload={load} />)}</div>}
      </div>
    </div>
  );
}
