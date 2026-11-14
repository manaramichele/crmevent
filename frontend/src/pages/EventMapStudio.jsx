import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ArrowLeft, Upload, Film, Download, Loader2, Play, Pause, Image as ImageIcon } from "lucide-react";

const ST = { queued: ["In attesa", "bg-slate-100 text-slate-700"], processing: ["In elaborazione", "bg-amber-100 text-amber-800"], completed: ["Completato", "bg-emerald-100 text-emerald-800"], error: ["Errore", "bg-red-100 text-red-700"] };
const km = (m) => `${(m / 1000).toFixed(1).replace(".", ",")} km`;

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

const videoName = (v) => `event-map-${(v.track_name || "percorso").replace(/\.gpx$/i, "")}-${v.format.replace(":", "x")}-${v.duration}s`.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") + ".mp4";

// Il file passa da una richiesta API autenticata (cookie + X-Org-Id): un link diretto non porterebbe l'organizzazione attiva.
async function fetchVideo(v, download) {
  try {
    const { data } = await api.get(`/eventmap/videos/${v.id}/file`, { params: download ? { download: 1 } : {}, responseType: "blob" });
    return new Blob([data], { type: "video/mp4" });
  } catch (e) {
    let msg = "Impossibile recuperare il video. Riprova.";
    try { msg = formatApiError(JSON.parse(await e.response.data.text()).detail); } catch (_) { /* risposta non JSON */ }
    toast.error(msg);
    return null;
  }
}

function VideoCard({ v }) {
  const [label, cls] = ST[v.status] || ST.queued;
  const [url, setUrl] = useState(null);
  const [busy, setBusy] = useState("");
  const vertical = v.format === "9:16";
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  const play = async () => { setBusy("play"); const b = await fetchVideo(v, false); if (b) setUrl(URL.createObjectURL(b)); setBusy(""); };
  const download = async () => {
    setBusy("dl");
    const b = await fetchVideo(v, true);
    if (b) {
      const u = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = u; a.download = videoName(v); document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(u), 60000);
    }
    setBusy("");
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2" data-testid={`em-video-${v.id}`}>
      <div className="flex items-center gap-2 text-xs"><span className={`rounded-full px-2 py-0.5 font-semibold ${cls}`} data-testid={`em-video-status-${v.id}`}>{label}{v.status === "processing" ? ` · ${v.progress || 0}%` : ""}</span>
        <span className="text-slate-500">{v.format} · {v.duration}s · {v.music || "senza musica"}</span></div>
      {v.status === "completed" ? (url
        ? <video src={url} controls autoPlay playsInline className={`w-full rounded-lg bg-black ${vertical ? "max-h-[420px] object-contain" : ""}`} data-testid={`em-video-player-${v.id}`} />
        : <button type="button" onClick={play} disabled={!!busy} className="w-full h-32 rounded-lg bg-slate-900 text-white flex items-center justify-center gap-2 text-sm font-semibold hover:bg-slate-800" data-testid={`em-video-play-${v.id}`}>
            {busy === "play" ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}Riproduci</button>
      ) : v.status === "error" ? <p className="text-xs text-red-600">{v.error}</p> : <div className="h-24 flex items-center justify-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>}
      <div className="flex items-center justify-between text-xs text-slate-500"><span>{v.track_name} · {km(v.distance_m)}</span>
        {v.status === "completed" && <button type="button" onClick={download} disabled={!!busy} className="inline-flex items-center gap-1 font-semibold text-[#088F8A] disabled:opacity-60" data-testid={`em-video-download-${v.id}`}>{busy === "dl" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}Scarica MP4</button>}</div>
    </div>
  );
}

export default function EventMapStudio() {
  const { id } = useParams();
  const [st, setSt] = useState(null);
  const [opt, setOpt] = useState(null);
  const [f, setF] = useState({ track_id: "", style: "dark", format: "9:16", duration: 30, music: "sportiva", logo: undefined });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState("");
  const load = useCallback(() => api.get(`/eventmap/events/${id}`).then(({ data }) => {
    setSt(data); setF((x) => ({ ...x, track_id: x.track_id || data.tracks[0]?.id || "", logo: x.logo !== undefined ? x.logo : (data.event.has_logo ? "event" : data.logos[0]?.id || null) }));
  }).catch((e) => { toast.error(formatApiError(e.response?.data?.detail)); setSt((x) => x || { missing: true }); }), [id]);
  useEffect(() => { load(); api.get("/eventmap/options").then(({ data }) => setOpt(data)); }, [load]);
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
    try { const { data } = await api.post(`/eventmap/events/${id}/tracks`, fd); toast.success(`Traccia caricata: ${km(data.distance_m)}`); setF((x) => ({ ...x, track_id: data.id })); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  const fromMap = async (mid) => {
    setBusy("upload");
    try { const { data } = await api.post(`/eventmap/events/${id}/tracks/from-map/${mid}`); setF((x) => ({ ...x, track_id: data.id })); await load(); toast.success("Traccia dell'evento importata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  const uploadLogo = async (file) => {
    if (!file) return;
    setBusy("logo");
    const fd = new FormData(); fd.append("file", file);
    try { const { data } = await api.post(`/eventmap/events/${id}/logos`, fd); toast.success(data.transparent ? "Logo caricato" : "Logo caricato (senza trasparenza: comparirà su un riquadro bianco)"); setF((x) => ({ ...x, logo: data.id })); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  const deleteLogo = async (lid) => {
    try { await api.delete(`/eventmap/events/${id}/logos/${lid}`); setF((x) => ({ ...x, logo: x.logo === lid ? (st.event.has_logo ? "event" : null) : x.logo })); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const doPreview = async () => {
    setBusy("preview");
    try { const { data } = await api.post(`/eventmap/tracks/${f.track_id}/preview`, { style: f.style, format: f.format, logo: f.logo }, { responseType: "blob" }); setPreview(URL.createObjectURL(data)); }
    catch { toast.error("Anteprima non riuscita"); }
    setBusy("");
  };
  const generate = async () => {
    setBusy("gen");
    try { await api.post(`/eventmap/events/${id}/videos`, f); toast.success("Video in coda di elaborazione"); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy("");
  };
  if (st?.missing) return <p className="text-sm text-slate-600" data-testid="em-missing">Evento non trovato. <Link to="/event-map" className="font-semibold text-[#088F8A]">Torna a Event Map</Link></p>;
  if (!st || !opt) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const rg = st.rights;
  const fmts = opt.formats.map((x) => ({ ...x, disabled: !rg.formats.includes(x.key) }));
  return (
    <div className="animate-fade-up space-y-6" data-testid="em-studio">
      <Link to="/event-map" className="inline-flex items-center gap-1 text-sm text-slate-500"><ArrowLeft className="w-4 h-4" />Event Map</Link>
      <PageHeader title={st.event.nome} subtitle={`Event Map${st.event.data ? ` · ${st.event.data}` : ""}`} />
      {!rg.active ? <p className="text-sm text-slate-600" data-testid="em-not-active">Event Map non è attivo per questo evento. <Link to={`/marketplace?servizio=event-map&evento=${id}`} className="font-semibold text-[#088F8A]">Attivalo dal Marketplace</Link>.</p> : (
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-5 rounded-xl border border-slate-200 bg-white p-5">
          <div className="text-sm" data-testid="em-counters">Video disponibili: <b data-testid="em-remaining">{rg.videos_remaining ?? "illimitati"}</b> · generati {rg.videos_used} · in elaborazione {rg.in_progress}{rg.expires_at ? ` · scadenza ${new Date(rg.expires_at).toLocaleDateString("it-IT")}` : ""}</div>
          <div className="space-y-2"><div className="text-sm font-semibold">1. Traccia GPX</div>
            <select value={f.track_id} onChange={(e) => setF({ ...f, track_id: e.target.value })} className="w-full h-10 rounded-lg border border-slate-200 px-3 text-sm" data-testid="em-track-select">
              <option value="">Seleziona una traccia…</option>{st.tracks.map((t) => <option key={t.id} value={t.id}>{t.name} · {km(t.distance_m)} · {t.points} punti</option>)}</select>
            <div className="flex flex-wrap gap-2">
              <label className="inline-flex h-9 items-center gap-1.5 rounded-md border border-slate-200 px-3 text-sm font-semibold cursor-pointer hover:bg-slate-50" data-testid="em-upload-label"><Upload className="w-4 h-4" />{busy === "upload" ? "Caricamento…" : "Carica GPX"}
                <input type="file" accept=".gpx" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="em-upload-input" /></label>
              {st.maps.map((m) => <Button key={m.id} size="sm" variant="outline" onClick={() => fromMap(m.id)} data-testid={`em-from-map-${m.id}`}>Usa «{m.nome || m.titolo || "percorso"}»</Button>)}
            </div></div>
          <div className="space-y-2"><div className="text-sm font-semibold">2. Stile mappa</div><Choice items={opt.styles} value={f.style} onChange={(v) => setF({ ...f, style: v })} testid="em-style" /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">3. Formato</div><Choice items={fmts} value={f.format} onChange={(v) => setF({ ...f, format: v })} testid="em-format" /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">4. Durata</div><Choice items={opt.durations.map((d) => ({ key: d, label: `${d} secondi` }))} value={f.duration} onChange={(v) => setF({ ...f, duration: v })} testid="em-duration" /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">5. Musica (brani originali CRMEvent)</div><MusicPick list={opt.music} value={f.music} onChange={(v) => setF({ ...f, music: v })} /></div>
          <div className="space-y-2"><div className="text-sm font-semibold">6. Logo evento</div><LogoPick eid={id} st={st} value={f.logo} onChange={(v) => setF({ ...f, logo: v })} onUpload={uploadLogo} onDelete={deleteLogo} busy={busy === "logo"} /></div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={!f.track_id || !!busy} onClick={doPreview} data-testid="em-preview-btn"><ImageIcon className="w-4 h-4 mr-1" />{busy === "preview" ? "Anteprima…" : "Anteprima"}</Button>
            <Button disabled={!f.track_id || !!busy || rg.videos_remaining === 0} onClick={generate} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="em-generate-btn"><Film className="w-4 h-4 mr-1" />{busy === "gen" ? "Invio…" : "Genera video"}</Button>
          </div>
          {rg.videos_remaining === 0 && <p className="text-sm text-slate-500" data-testid="em-no-videos">Hai esaurito i video disponibili: <Link to={`/marketplace?servizio=event-map&evento=${id}`} className="font-semibold text-[#088F8A]">acquista un pacchetto</Link>.</p>}
        </div>
        <div className="space-y-3">
          {preview ? <img src={preview} alt="Anteprima del percorso" className="mx-auto max-h-[520px] rounded-xl border border-slate-200" data-testid="em-preview-img" /> : <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">L'anteprima mostra il percorso completo sulla mappa con lo stile e il formato scelti.</div>}
        </div>
      </div>)}
      <div className="space-y-3"><h2 className="font-display text-lg font-bold">Archivio video</h2>
        {!st.videos.length ? <p className="text-sm text-slate-500" data-testid="em-archive-empty">Nessun video generato per questo evento.</p>
          : <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" data-testid="em-archive">{st.videos.map((v) => <VideoCard key={v.id} v={v} />)}</div>}
      </div>
    </div>
  );
}
