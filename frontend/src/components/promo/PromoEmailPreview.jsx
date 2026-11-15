import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Monitor, Smartphone } from "lucide-react";

export function PromoEmailPreview({ m, onClose }) {
  const [html, setHtml] = useState("");
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    api.get(`/promo-materials/${m.slug}/html`, { params: { base: window.location.origin } }).then((r) => setHtml(r.data.html));
  }, [m.slug]);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-4xl" data-testid={`promo-email-dialog-${m.slug}`}>
        <DialogHeader><DialogTitle>Anteprima email · {m.name}</DialogTitle></DialogHeader>
        <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm">
          <div><span className="text-slate-500">Oggetto:</span> <strong data-testid="promo-email-subject">{m.subject}</strong></div>
          <div className="text-slate-500" data-testid="promo-email-preheader">{m.preheader}</div>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant={mobile ? "outline" : "default"} onClick={() => setMobile(false)} data-testid="promo-email-desktop"><Monitor className="h-4 w-4 mr-1" />Desktop</Button>
          <Button size="sm" variant={mobile ? "default" : "outline"} onClick={() => setMobile(true)} data-testid="promo-email-mobile"><Smartphone className="h-4 w-4 mr-1" />Smartphone</Button>
        </div>
        <div className="flex justify-center rounded-lg border border-slate-200 bg-slate-100 p-2">
          <iframe title="Anteprima email" srcDoc={html} sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" className="h-[60vh] rounded bg-white transition-[width] duration-300" style={{ width: mobile ? 375 : "100%" }} data-testid="promo-email-iframe" />
        </div>
        <p className="text-xs text-slate-500">L'anteprima usa le immagini di questo ambiente; il codice copiato o scaricato usa gli indirizzi pubblici di crmevent.it.</p>
      </DialogContent>
    </Dialog>
  );
}
