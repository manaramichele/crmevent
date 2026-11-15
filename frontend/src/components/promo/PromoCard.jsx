import { useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtDate } from "@/lib/promoMaterials";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Copy, Download, ExternalLink, Mail, Pencil, History, Eye, Rocket, Undo2 } from "lucide-react";
import { PromoEditDialog } from "@/components/promo/PromoEditDialog";
import { PromoVersionsDialog } from "@/components/promo/PromoVersionsDialog";
import { PromoEmailPreview } from "@/components/promo/PromoEmailPreview";

export const copyText = async (txt, what) => {
  try { await navigator.clipboard.writeText(txt); toast.success(`${what} copiato`); }
  catch { window.prompt(`Copia ${what.toLowerCase()}:`, txt); }
};

const Act = ({ icon: I, children, ...p }) => <Button size="sm" variant="outline" className="h-8" {...p}><I className="h-3.5 w-3.5 mr-1" />{children}</Button>;

function Field({ label, value, testid }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24 shrink-0 text-slate-500">{label}</span>
      <span className="min-w-0 flex-1 truncate rounded bg-slate-100 px-2 py-1 text-slate-700" data-testid={`${testid}-value`}>{value || "—"}</span>
      <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => copyText(value, label)} data-testid={testid}><Copy className="h-3.5 w-3.5" /></Button>
    </div>
  );
}

export function PromoCard({ m, onChange }) {
  const [prod, setProd] = useState(null);
  const [dlg, setDlg] = useState(null);
  const s = m.slug;
  useEffect(() => { api.get(`/promo-materials/${s}/html`).then((r) => setProd(r.data)).catch(() => {}); }, [s, m.updated_at]);
  const site = prod?.site || "";
  const pageUrl = `${site}/video/${s}`;
  const published = m.status === "pubblicato";
  const downloadHtml = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([prod.html], { type: "text/html" }));
    a.download = `crmevent-${s}-newsletter.html`;
    a.click();
  };
  const setStatus = async (st) => {
    await api.post(`/promo-materials/${s}/status?status=${st}`);
    toast.success(st === "pubblicato" ? "Materiale pubblicato: la pagina video è ora pubblica" : "Materiale riportato in bozza");
    onChange();
  };
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3" data-testid={`promo-card-${s}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-slate-900" data-testid={`promo-name-${s}`}>{m.name}</div>
          <div className="text-xs text-slate-500">Creato {fmtDate(m.created_at)} · Aggiornato {fmtDate(m.updated_at)} · v{m.version}</div>
        </div>
        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${published ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`} data-testid={`promo-status-${s}`}>{published ? "Pubblicato" : "Bozza"}</span>
      </div>
      <img src={m.preview} alt={`Anteprima ${m.name}`} className="w-full rounded-lg border border-slate-200" data-testid={`promo-preview-${s}`} />
      <div className="flex flex-wrap gap-2">
        <a href={`/video/${s}`} target="_blank" rel="noreferrer"><Act icon={ExternalLink} data-testid={`promo-open-${s}`}>Anteprima video</Act></a>
        <a href={m.mp4} download={`crmevent-${s}-demo.mp4`}><Act icon={Download} data-testid={`promo-dl-video-${s}`}>Scarica MP4</Act></a>
        <a href={m.preview} download={`crmevent-${s}-anteprima.jpg`}><Act icon={Download} data-testid={`promo-dl-image-${s}`}>Scarica JPG</Act></a>
        <Act icon={Eye} onClick={() => setDlg("email")} data-testid={`promo-email-preview-${s}`}>Anteprima email</Act>
        <Act icon={Download} onClick={downloadHtml} disabled={!prod} data-testid={`promo-dl-html-${s}`}>Scarica HTML</Act>
        <Act icon={Mail} onClick={() => copyText(prod.html, "Codice HTML")} disabled={!prod} data-testid={`promo-copy-html-${s}`}>Copia HTML</Act>
        <Act icon={Copy} onClick={() => copyText(pageUrl, "Link video")} disabled={!prod} data-testid={`promo-copy-page-${s}`}>Copia link video</Act>
        <Act icon={Copy} onClick={() => copyText(`${site}${m.preview}`, "Link immagine")} disabled={!prod} data-testid={`promo-copy-image-${s}`}>Copia link immagine</Act>
        <Act icon={Pencil} onClick={() => setDlg("edit")} data-testid={`promo-edit-${s}`}>Modifica</Act>
        <Act icon={History} onClick={() => setDlg("versions")} data-testid={`promo-versions-${s}`}>Versioni</Act>
      </div>
      <div className="space-y-1.5 border-t border-slate-100 pt-3">
        <Field label="Oggetto" value={m.subject} testid={`promo-copy-subject-${s}`} />
        <Field label="Anteprima testo" value={m.preheader} testid={`promo-copy-preheader-${s}`} />
        <Field label="URL video" value={prod && pageUrl} testid={`promo-url-page-${s}`} />
        <Field label="URL immagine" value={prod && `${site}${m.preview}`} testid={`promo-url-image-${s}`} />
      </div>
      <div className="flex justify-end">
        {published
          ? <Button size="sm" variant="ghost" onClick={() => setStatus("bozza")} data-testid={`promo-unpublish-${s}`}><Undo2 className="h-4 w-4 mr-1" />Riporta in bozza</Button>
          : <Button size="sm" onClick={() => setStatus("pubblicato")} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid={`promo-publish-${s}`}><Rocket className="h-4 w-4 mr-1" />Approva e pubblica</Button>}
      </div>
      {dlg === "email" && <PromoEmailPreview m={m} onClose={() => setDlg(null)} />}
      {dlg === "edit" && <PromoEditDialog m={m} onClose={() => setDlg(null)} onSaved={onChange} />}
      {dlg === "versions" && <PromoVersionsDialog m={m} onClose={() => setDlg(null)} onRestored={onChange} />}
    </div>
  );
}
