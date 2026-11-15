import api from "@/lib/api";
import { fmtDate } from "@/lib/promoMaterials";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { downloadFile } from "@/components/promo/reelFiles";

const ST = { completed: "Pronta", processing: "In corso", queued: "In coda", error: "Errore" };

export function ReelVersionsDialog({ r, onClose, onChange }) {
  const use = async (v) => {
    try { await api.post(`/promo-reels/${r.slug}/versions/${v.id}/current`); toast.success(`Versione v${v.version} in uso`); onChange(); }
    catch { toast.error("Operazione non riuscita"); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl" data-testid={`reel-versions-dialog-${r.slug}`}>
        <DialogHeader><DialogTitle>Versioni · {r.title}</DialogTitle></DialogHeader>
        <div className="max-h-[60vh] divide-y overflow-y-auto">
          {r.versions.map((v) => (
            <div key={v.id} className="flex flex-wrap items-center gap-2 py-2 text-sm" data-testid={`reel-version-${v.id}`}>
              <div className="min-w-0 flex-1">
                <div className="font-medium text-slate-800">v{v.version} · {ST[v.status] || v.status}{v.id === r.current_version_id && <span className="ml-2 rounded bg-emerald-100 px-1.5 text-xs text-emerald-800">in uso</span>}</div>
                <div className="text-xs text-slate-500">{fmtDate(v.created_at)} · {v.created_by}{v.duration ? ` · ${v.duration}s` : ""}</div>
              </div>
              {v.status === "completed" && <>
                <Button size="sm" variant="outline" onClick={() => downloadFile(v.urls.mp4, `crmevent-${r.slug}-v${v.version}.mp4`)} data-testid={`reel-version-dl-${v.id}`}>MP4</Button>
                {v.id !== r.current_version_id && <Button size="sm" variant="outline" onClick={() => use(v)} data-testid={`reel-version-use-${v.id}`}>Usa questa</Button>}
              </>}
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
