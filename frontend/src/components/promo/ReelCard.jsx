import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { fmtDate } from "@/lib/promoMaterials";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Copy, Download, Film, RefreshCw, Save, History } from "lucide-react";
import { copyText } from "@/components/promo/PromoCard";
import { useFileUrl, downloadFile } from "@/components/promo/reelFiles";
import { ReelProjectDialog } from "@/components/promo/ReelProjectDialog";
import { ReelVersionsDialog } from "@/components/promo/ReelVersionsDialog";

const STATI = [["da_pubblicare", "Da pubblicare"], ["programmato", "Programmato"], ["pubblicato", "Pubblicato"]];
const LINKS = [["link_instagram", "Post Instagram"], ["link_facebook", "Post Facebook"], ["link_youtube", "Video YouTube"]];

function ReelPlayer({ v, slug }) {
  const src = useFileUrl(v?.urls?.mp4);
  const poster = useFileUrl(v?.urls?.cover);
  if (!v) return <div className="flex aspect-[9/16] items-center justify-center rounded-xl bg-slate-900 text-xs text-slate-400">Nessuna versione</div>;
  return <video key={v.id} src={src || undefined} poster={poster || undefined} controls playsInline preload="metadata" className="aspect-[9/16] w-full rounded-xl bg-black" data-testid={`reel-video-${slug}`} />;
}

export function ReelCard({ r, assets, music, onChange }) {
  const [f, setF] = useState({ title: r.title, description: r.description, hashtags: r.hashtags, publish_status: r.publish_status, publish_date: r.publish_date || "", link_instagram: r.link_instagram || "", link_facebook: r.link_facebook || "", link_youtube: r.link_youtube || "" });
  const [dlg, setDlg] = useState(null);
  const s = r.slug;
  const cur = r.versions.find((v) => v.id === r.current_version_id) || r.versions.find((v) => v.status === "completed");
  const running = r.versions.find((v) => ["queued", "processing"].includes(v.status));
  const failed = r.versions[0]?.status === "error" ? r.versions[0] : null;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { await api.put(`/promo-reels/${s}`, { ...f, publish_date: f.publish_date || null }); toast.success("Dati di pubblicazione salvati"); onChange(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Salvataggio non riuscito"); }
  };
  const regen = async () => {
    try { await api.post(`/promo-reels/${s}/render`); toast.success("Rigenerazione avviata: verrà creata una nuova versione"); onChange(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Rigenerazione non avviata"); }
  };
  const name = `crmevent-${s}-v${cur?.version}`;
  return (
    <div className="grid gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-[220px_1fr]" data-testid={`reel-card-${s}`}>
      <div className="space-y-2">
        <ReelPlayer v={cur} slug={s} />
        <div className="text-center text-xs text-slate-500" data-testid={`reel-meta-${s}`}>{cur ? `v${cur.version} · ${cur.duration}s · ${(cur.size / 1e6).toFixed(1)} MB · ${fmtDate(cur.created_at)}` : "—"}</div>
        {running && <div className="rounded bg-amber-50 px-2 py-1 text-center text-xs text-amber-800" data-testid={`reel-running-${s}`}>Rigenerazione v{running.version} in corso… {running.progress || 0}%</div>}
        {failed && <div className="rounded bg-red-50 px-2 py-1 text-center text-xs text-red-700" data-testid={`reel-error-${s}`}>{failed.error}</div>}
      </div>
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-slate-900 px-2.5 py-0.5 text-xs font-semibold text-white">{r.kind === "principale" ? "Principale · 45 s" : "Reel · 15 s"}</span>
          <Input value={f.title} onChange={set("title")} className="h-8 flex-1 font-semibold" data-testid={`reel-title-${s}`} />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={!cur} onClick={() => downloadFile(cur.urls.mp4, `${name}.mp4`)} data-testid={`reel-dl-mp4-${s}`}><Download className="h-3.5 w-3.5 mr-1" />Scarica MP4</Button>
          <Button size="sm" variant="outline" disabled={!cur} onClick={() => downloadFile(cur.urls.mp4_nomusic, `${name}-senza-musica.mp4`)} data-testid={`reel-dl-nomusic-${s}`}><Download className="h-3.5 w-3.5 mr-1" />MP4 senza musica</Button>
          <Button size="sm" variant="outline" disabled={!cur} onClick={() => downloadFile(cur.urls.cover, `${name}-copertina.jpg`)} data-testid={`reel-dl-cover-${s}`}><Download className="h-3.5 w-3.5 mr-1" />Scarica JPG</Button>
          <Button size="sm" variant="outline" onClick={() => copyText(f.description, "Descrizione")} data-testid={`reel-copy-desc-${s}`}><Copy className="h-3.5 w-3.5 mr-1" />Copia descrizione</Button>
          <Button size="sm" variant="outline" onClick={() => copyText(f.hashtags, "Hashtag")} data-testid={`reel-copy-tags-${s}`}><Copy className="h-3.5 w-3.5 mr-1" />Copia hashtag</Button>
        </div>
        <div><Label className="text-xs">Descrizione Instagram</Label><Textarea rows={3} value={f.description} onChange={set("description")} data-testid={`reel-desc-${s}`} /></div>
        <div><Label className="text-xs">Hashtag</Label><Input value={f.hashtags} onChange={set("hashtags")} data-testid={`reel-tags-${s}`} /></div>
        <div className="grid gap-2 sm:grid-cols-2">
          <div><Label className="text-xs">Stato pubblicazione</Label>
            <select value={f.publish_status} onChange={set("publish_status")} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm" data-testid={`reel-status-${s}`}>{STATI.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
          <div><Label className="text-xs">Data pubblicazione</Label><Input type="date" value={f.publish_date} onChange={set("publish_date")} data-testid={`reel-date-${s}`} /></div>
          {LINKS.map(([k, l]) => <div key={k}><Label className="text-xs">{l}</Label><Input value={f[k]} onChange={set(k)} placeholder="https://…" data-testid={`reel-${k}-${s}`} /></div>)}
        </div>
        <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-3">
          <Button size="sm" variant="ghost" onClick={() => setDlg("versions")} data-testid={`reel-versions-${s}`}><History className="h-4 w-4 mr-1" />Versioni ({r.versions.length})</Button>
          <Button size="sm" variant="outline" onClick={() => setDlg("project")} data-testid={`reel-project-${s}`}><Film className="h-4 w-4 mr-1" />Progetto di montaggio</Button>
          <Button size="sm" variant="outline" onClick={regen} disabled={!!running} data-testid={`reel-render-${s}`}><RefreshCw className="h-4 w-4 mr-1" />Rigenera</Button>
          <Button size="sm" onClick={save} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid={`reel-save-${s}`}><Save className="h-4 w-4 mr-1" />Salva</Button>
        </div>
      </div>
      {dlg === "project" && <ReelProjectDialog r={r} assets={assets} music={music} onClose={() => setDlg(null)} onSaved={onChange} />}
      {dlg === "versions" && <ReelVersionsDialog r={r} onClose={() => setDlg(null)} onChange={onChange} />}
    </div>
  );
}
