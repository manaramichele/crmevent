import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Download, Loader2, Play, RotateCcw, Lock, Unlock, History, AlertTriangle, Trash2 } from "lucide-react";
import { kmTxt } from "@/components/eventmap/EventMapRaces";

const ST = { queued: ["In coda", "bg-slate-100 text-slate-700"], processing: ["In elaborazione", "bg-amber-100 text-amber-800"],
  completed: ["Completato", "bg-green-100 text-green-800"], error: ["Errore", "bg-red-100 text-red-700"] };
const PAUSES = [[0, "Disattivata"], [2, "2 secondi"], [3, "3 secondi"], [5, "5 secondi"]];

export function AidPausePick({ race, upd }) {
  const v = race.aid_pause ?? 3;
  const custom = !PAUSES.some(([s]) => s === v);
  return (
    <div className="space-y-2" data-testid="em-aid-pause">
      <div className="flex flex-wrap gap-2">
        {PAUSES.map(([s, l]) => <button key={s} type="button" onClick={() => upd({ aid_pause: s })} className={`rounded-lg border px-3 py-1.5 text-sm ${!custom && v === s ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"}`} data-testid={`em-aid-pause-${s}`}>{l}{s === 3 ? " (predefinita)" : ""}</button>)}
        <button type="button" onClick={() => upd({ aid_pause: custom ? v : 4 })} className={`rounded-lg border px-3 py-1.5 text-sm ${custom ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"}`} data-testid="em-aid-pause-custom">Personalizzata</button>
        {custom && <Input type="number" min={1} max={10} step={0.5} value={v} onChange={(e) => upd({ aid_pause: Math.min(10, Math.max(1, Number(e.target.value) || 1)) })} className="h-9 w-24" data-testid="em-aid-pause-input" />}
      </div>
      {v > 0 && <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={!!race.aid_pause_auto} onChange={(e) => upd({ aid_pause_auto: e.target.checked })} data-testid="em-aid-pause-auto" />Allunga la pausa per i testi lunghi (fino a 3 secondi in più)</label>}
      <p className="text-xs text-slate-500">Ai ristori il cursore rallenta, si ferma mostrando nome, chilometro e descrizione, poi riparte. Le pause rientrano nella durata del video.</p>
    </div>
  );
}

export function TimingWarning({ timing, onUse }) {
  if (!timing || timing.ok) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900" data-testid="em-timing-warning">
      <AlertTriangle className="h-4 w-4" />
      <span className="flex-1">Con {timing.pause_s} s di pause ai ristori restano solo {timing.move_s} s per il percorso: il cursore risulterebbe troppo veloce.{timing.suggest ? ` Ti consigliamo ${timing.suggest} secondi.` : " Riduci la pausa o il numero di ristori."}</span>
      {timing.suggest && <Button size="sm" variant="outline" onClick={() => onUse(timing.suggest)} data-testid="em-timing-use">Usa {timing.suggest} secondi</Button>}
    </div>
  );
}

export async function fetchVideo(v, download, confirm) {
  try {
    const { data } = await api.get(`/eventmap/videos/${v.id}/file`, { params: download ? { download: 1, ...(confirm ? { confirm: 1 } : {}) } : {}, responseType: "blob" });
    return new Blob([data], { type: "video/mp4" });
  } catch (e) {
    let msg = "Impossibile recuperare il video. Riprova.";
    try { msg = formatApiError(JSON.parse(await e.response.data.text()).detail); } catch (_) { /* risposta non JSON */ }
    toast.error(msg);
    return null;
  }
}

const videoName = (v) => `event-map-${v.race_name || (v.track_name || "percorso").replace(/\.gpx$/i, "")}-${v.format.replace(":", "x")}-${v.duration}s${v.version > 1 ? `-v${v.version}` : ""}`.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") + ".mp4";
const when = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "");

function SaTools({ g, versions, onDone, evName, v }) {
  const [open, setOpen] = useState(false);
  const [del, setDel] = useState(false);
  const act = async (url, msg, method = "post") => { try { await api[method](url); toast.success(msg); setDel(false); onDone(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const deleted = !!g.deleted_at;
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50 p-2 text-xs space-y-2" data-testid={`em-sa-tools-${g.id}`}>
      <div className="flex flex-wrap gap-2">
        <span className="font-semibold text-violet-800">Super Admin</span>
        {g.status === "definitivo" && <button type="button" className="inline-flex items-center gap-1 font-semibold text-violet-800" onClick={() => act(`/eventmap/video-groups/${g.id}/unlock`, "Video sbloccato: l'organizzatore può di nuovo modificarlo")} data-testid={`em-sa-unlock-${g.id}`}><Unlock className="h-3.5 w-3.5" />Sblocca</button>}
        <button type="button" className="inline-flex items-center gap-1 font-semibold text-violet-800" onClick={() => setOpen(!open)} data-testid={`em-sa-history-${g.id}`}><History className="h-3.5 w-3.5" />Storico e versioni</button>
        {!deleted && <button type="button" title="ELIMINA VIDEO" aria-label="Elimina video" className="ml-auto inline-flex items-center gap-1 font-semibold text-red-700" onClick={() => setDel(true)} data-testid={`em-sa-delete-${g.id}`}><Trash2 className="h-3.5 w-3.5" />Elimina video</button>}
        {deleted && <><button type="button" className="font-semibold text-violet-800" onClick={() => act(`/eventmap/video-groups/${g.id}/undelete`, "Video ripristinato nell'archivio")} data-testid={`em-sa-undelete-${g.id}`}>Ripristina</button>
          <button type="button" className="font-semibold text-red-700" onClick={() => window.confirm("Eliminare definitivamente i file di tutte le versioni? L'operazione non si può annullare.") && act(`/eventmap/video-groups/${g.id}/purge`, "Video eliminato definitivamente", "delete")} data-testid={`em-sa-purge-${g.id}`}>Elimina definitivamente</button></>}
        {g.credit_consumed && !g.credit_refunded && <button type="button" className="font-semibold text-violet-800" onClick={() => window.confirm("Restituire 1 credito video all'organizzazione? L'azione viene registrata.") && act(`/eventmap/video-groups/${g.id}/refund-credit`, "Credito restituito")} data-testid={`em-sa-refund-${g.id}`}>Restituisci credito</button>}
      </div>
      {open && <div className="space-y-1">
        {versions.filter((v) => v.status === "completed").map((v) => <div key={v.id} className="flex items-center gap-2"><span className="flex-1">v{v.version || 1} · {when(v.created_at)}{v.id === g.current_version_id ? " · attuale" : ""}{v.id === g.first_download?.version_id ? " · scaricata dal cliente" : ""}</span>
          {v.id !== g.current_version_id && <button type="button" className="font-semibold text-violet-800" onClick={() => act(`/eventmap/video-groups/${g.id}/restore/${v.id}`, `Versione v${v.version || 1} ripristinata`)} data-testid={`em-sa-restore-${v.id}`}>Ripristina</button>}</div>)}
        {(g.history || []).slice().reverse().map((h, i) => <div key={i} className="text-slate-600">{when(h.at)} · {h.action}{h.version ? ` v${h.version}` : ""} · {h.by}{h.note ? ` · ${h.note}` : ""}</div>)}
      </div>}
      <Dialog open={del} onOpenChange={setDel}>
        <DialogContent data-testid="em-delete-dialog">
          <DialogHeader><DialogTitle>Elimina video</DialogTitle>
            <DialogDescription>Vuoi eliminare questo video? L'operazione comporterà la rimozione del video dall'archivio dell'organizzazione.</DialogDescription></DialogHeader>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm" data-testid="em-delete-details">
            <dt className="text-slate-500">Evento</dt><dd>{evName}</dd><dt className="text-slate-500">Gara</dt><dd>{g.race_name || v?.race_label || "–"}</dd>
            <dt className="text-slate-500">Titolo</dt><dd>{v?.title || "–"}</dd><dt className="text-slate-500">Stato</dt><dd>{g.status === "definitivo" ? "Definitivo" : "Modificabile"} · {(ST[v?.status] || ST.queued)[0]}</dd>
            <dt className="text-slate-500">Generato il</dt><dd>{when(v?.created_at)}</dd><dt className="text-slate-500">Primo download</dt><dd>{g.first_download ? when(g.first_download.at) : "Mai scaricato"}</dd></dl>
          <p className="text-xs text-slate-500">Il file resta conservato e il video si può ripristinare. Crediti, GPX e altri video della gara non cambiano.</p>
          <DialogFooter className="gap-2"><Button variant="outline" onClick={() => setDel(false)} data-testid="em-delete-cancel">Annulla</Button>
            <Button variant="destructive" onClick={() => act(`/eventmap/video-groups/${g.id}`, "Video eliminato dall'archivio", "delete")} data-testid="em-delete-confirm">Conferma eliminazione</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function VideoGroupCard({ g, versions, sa, label, onRegen, onReload, evName }) {
  const cur = versions.find((v) => v.id === g.current_version_id) || versions[0];
  const [vid, setVid] = useState(cur?.id);
  useEffect(() => { setVid(cur?.id); }, [cur?.id]);
  const v = versions.find((x) => x.id === vid) || cur;
  const [url, setUrl] = useState(null);
  const [busy, setBusy] = useState("");
  const [ask, setAsk] = useState(false);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  useEffect(() => { setUrl(null); }, [vid]);
  if (!v) return null;
  const [stl, cls] = ST[v.status] || ST.queued;
  const editable = g.status === "modificabile";
  const working = versions.some((x) => x.status === "queued" || x.status === "processing");
  const play = async () => { setBusy("play"); const b = await fetchVideo(v, false); if (b) setUrl(URL.createObjectURL(b)); setBusy(""); };
  const download = async (confirm) => {
    setAsk(false); setBusy("dl");
    const b = await fetchVideo(v, true, confirm);
    if (b) {
      const u = URL.createObjectURL(b);
      const a = document.createElement("a");
      a.href = u; a.download = videoName(v); document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(u), 60000);
      if (confirm) { toast.success("Video scaricato: ora è definitivo"); onReload(); }
    }
    setBusy("");
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2" data-testid={`em-video-${g.id}`}>
      <div className="text-sm font-semibold text-slate-900" data-testid={`em-video-label-${g.id}`}>{label} {kmTxt(v.distance_display_m || v.distance_m)} – Video {v.format} – {v.duration} secondi</div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-bold ${editable ? "bg-sky-100 text-sky-800" : "bg-slate-900 text-white"}`} data-testid={`em-video-lock-${g.id}`}>{editable ? "MODIFICABILE" : <><Lock className="h-3 w-3" />DEFINITIVO</>}</span>
        <span className={`rounded-full px-2 py-0.5 font-semibold ${cls}`} data-testid={`em-video-status-${g.id}`}>{stl}{v.status === "processing" ? ` · ${v.progress || 0}%` : ""}</span>
        {g.deleted_at && <span className="rounded-full bg-red-100 px-2 py-0.5 font-bold text-red-700" data-testid={`em-video-deleted-${g.id}`}>ELIMINATO {when(g.deleted_at)}</span>}
        {versions.length > 1 && <select value={v.id} onChange={(e) => setVid(e.target.value)} className="h-7 rounded border border-slate-200 px-1" data-testid={`em-video-version-${g.id}`}>{versions.map((x) => <option key={x.id} value={x.id}>v{x.version || 1}{x.id === g.current_version_id ? " (attuale)" : ""}</option>)}</select>}
      </div>
      {v.status === "completed" ? (url
        ? <video src={url} controls autoPlay playsInline className={`w-full rounded-lg bg-black ${v.format === "9:16" ? "max-h-[420px] object-contain" : ""}`} data-testid={`em-video-player-${g.id}`} />
        : <button type="button" onClick={play} disabled={!!busy} className="w-full h-32 rounded-lg bg-slate-900 text-white flex items-center justify-center gap-2 text-sm font-semibold hover:bg-slate-800" data-testid={`em-video-play-${g.id}`}>
            {busy === "play" ? <Loader2 className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5" />}Riproduci</button>
      ) : v.status === "error" ? <p className="text-xs text-red-600">{v.error}</p> : <div className="h-24 flex items-center justify-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>}
      <p className="text-xs text-slate-500" data-testid={`em-video-note-${g.id}`}>{editable ? "Puoi modificare e rigenerare il video tutte le volte che vuoi. Dopo il primo download non potrai più modificarlo."
        : g.first_download ? `Scaricato il ${when(g.first_download.at)} da ${g.first_download.by} (v${g.first_download.version}). I download successivi sono sempre gratuiti.` : "Video definitivo: download sempre disponibile."}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500"><span className="flex-1 min-w-[120px]">{v.title ? `${v.title} · ` : ""}{when(v.created_at)}</span>
        {(editable || sa) && !working && <button type="button" onClick={() => onRegen(g, v)} className="inline-flex items-center gap-1 font-semibold text-slate-700" data-testid={`em-video-regen-${g.id}`}><RotateCcw className="w-3.5 h-3.5" />Modifica e rigenera</button>}
        {v.status === "completed" && <button type="button" onClick={() => (editable && !sa ? setAsk(true) : download(false))} disabled={!!busy} className="inline-flex items-center gap-1 font-semibold text-[#088F8A] disabled:opacity-60" data-testid={`em-video-download-${g.id}`}>{busy === "dl" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}Scarica video</button>}</div>
      {sa && <SaTools g={g} versions={versions} onDone={onReload} evName={evName} v={v} />}
      <Dialog open={ask} onOpenChange={setAsk}>
        <DialogContent data-testid="em-first-download-dialog">
          <DialogHeader><DialogTitle>Primo download</DialogTitle>
            <DialogDescription>Con il primo download il video diventerà definitivo e non potrai più modificarlo. Vuoi continuare?</DialogDescription></DialogHeader>
          <DialogFooter className="gap-2"><Button variant="outline" onClick={() => setAsk(false)} data-testid="em-first-download-cancel">Annulla</Button>
            <Button onClick={() => download(true)} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="em-first-download-confirm">Conferma e scarica</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
