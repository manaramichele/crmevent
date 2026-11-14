import { PROMO, absUrl, pageUrl, brevoHtml } from "@/lib/promoMaterials";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Copy, Download, ExternalLink } from "lucide-react";

const copy = async (txt, what) => {
  try { await navigator.clipboard.writeText(txt); toast.success(`${what} copiato`); }
  catch { window.prompt(`Copia ${what.toLowerCase()}:`, txt); }
};

function UrlRow({ label, url, testid }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 shrink-0 text-slate-500">{label}</span>
      <code className="min-w-0 flex-1 truncate rounded bg-slate-100 px-2 py-1" data-testid={`${testid}-value`}>{url}</code>
      <Button size="sm" variant="outline" className="h-7 px-2" onClick={() => copy(url, label)} data-testid={testid}><Copy className="h-3.5 w-3.5" /></Button>
    </div>
  );
}

function PromoCard({ p }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3" data-testid={`promo-card-${p.slug}`}>
      <div className="font-semibold text-slate-900">{p.title} – {p.subtitle}</div>
      <a href={pageUrl(p)} target="_blank" rel="noreferrer"><img src={p.preview} alt={`Anteprima ${p.name}`} className="w-full rounded-lg border border-slate-200" data-testid={`promo-preview-${p.slug}`} /></a>
      <div className="flex flex-wrap gap-2">
        <a href={p.preview} download={`crmevent-${p.slug}-anteprima.jpg`}><Button size="sm" variant="outline" data-testid={`promo-dl-image-${p.slug}`}><Download className="h-4 w-4 mr-1" />Scarica immagine</Button></a>
        <a href={p.mp4} download={p.file}><Button size="sm" variant="outline" data-testid={`promo-dl-video-${p.slug}`}><Download className="h-4 w-4 mr-1" />Scarica video MP4</Button></a>
        <a href={pageUrl(p)} target="_blank" rel="noreferrer"><Button size="sm" variant="outline" data-testid={`promo-open-${p.slug}`}><ExternalLink className="h-4 w-4 mr-1" />Apri pagina video</Button></a>
      </div>
      <div className="space-y-1.5">
        <UrlRow label="Pagina video" url={pageUrl(p)} testid={`promo-copy-page-${p.slug}`} />
        <UrlRow label="Video MP4" url={absUrl(p.mp4)} testid={`promo-copy-mp4-${p.slug}`} />
        <UrlRow label="Immagine" url={absUrl(p.preview)} testid={`promo-copy-image-${p.slug}`} />
      </div>
      <Button size="sm" onClick={() => copy(brevoHtml(p), "Codice HTML")} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid={`promo-copy-html-${p.slug}`}><Copy className="h-4 w-4 mr-1" />Copia codice HTML per Brevo</Button>
    </div>
  );
}

export function PromoMaterialsPanel() {
  return (
    <div className="space-y-4" data-testid="promo-materials-panel">
      <p className="text-sm text-slate-500">Immagini 16:9 (1200×675, JPG) cliccabili per le newsletter: nelle email inserisci l'immagine con il link alla pagina video pubblica, senza incorporare l'MP4. In Brevo usa un blocco Immagine con «URL immagine» e «Link», oppure incolla il codice HTML in un blocco HTML.</p>
      <div className="grid gap-4 lg:grid-cols-2">{PROMO.map((p) => <PromoCard key={p.slug} p={p} />)}</div>
    </div>
  );
}
