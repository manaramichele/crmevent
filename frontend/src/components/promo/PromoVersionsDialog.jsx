import { useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtDate } from "@/lib/promoMaterials";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const REASON = { modifica: "Prima della modifica", stato: "Prima del cambio di stato", ripristino: "Prima del ripristino" };

export function PromoVersionsDialog({ m, onClose, onRestored }) {
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get(`/promo-materials/${m.slug}/versions`).then((r) => setRows(r.data)); }, [m.slug]);
  const restore = async (v) => {
    if (!window.confirm(`Ripristinare la versione v${v.version}? Lo stato attuale verrà conservato nello storico.`)) return;
    await api.post(`/promo-materials/${m.slug}/versions/${v.id}/restore`);
    toast.success("Versione ripristinata");
    onRestored(); onClose();
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl" data-testid={`promo-versions-dialog-${m.slug}`}>
        <DialogHeader><DialogTitle>Versioni · {m.name}</DialogTitle></DialogHeader>
        {rows === null ? <div className="text-sm text-slate-400">Caricamento…</div> : rows.length === 0 ? <div className="text-sm text-slate-500" data-testid="promo-versions-empty">Nessuna versione precedente.</div> : (
          <div className="max-h-[60vh] divide-y overflow-y-auto">
            {rows.map((v) => (
              <div key={v.id} className="flex items-center gap-3 py-2 text-sm" data-testid={`promo-version-${v.id}`}>
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-slate-800">v{v.version} · {v.data?.subject}</div>
                  <div className="text-xs text-slate-500">{fmtDate(v.created_at)} · {REASON[v.reason] || v.reason} · {v.created_by}</div>
                </div>
                <Button size="sm" variant="outline" onClick={() => restore(v)} data-testid={`promo-restore-${v.id}`}>Ripristina</Button>
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
