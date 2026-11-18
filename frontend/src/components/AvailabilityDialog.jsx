import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge } from "@/components/crm";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Link2, Copy, ExternalLink, RefreshCw, Ban, ClipboardList, Users, Mail } from "lucide-react";
import { toast } from "sonner";

function LinkRow({ flag, label, url, copyLabel, openLabel, lang }) {
  const copy = async () => { try { await navigator.clipboard.writeText(url); toast.success(`${copyLabel}: copiato`); } catch { toast.error("Impossibile copiare"); } };
  return (
    <div>
      <div className="text-xs font-semibold text-slate-600 mb-1">{flag} {label}</div>
      <Input readOnly value={url} className="font-mono text-sm" data-testid={lang === "it" ? "avail-link-url" : "avail-link-url-en"} onFocus={(e) => e.target.select()} />
      <div className="flex flex-wrap gap-2 mt-2">
        <Button variant="outline" size="sm" onClick={copy} data-testid={`avail-copy-${lang}`}><Copy className="w-4 h-4 mr-1.5" />{copyLabel}</Button>
        <Button variant="outline" size="sm" onClick={() => window.open(url, "_blank")} data-testid={`avail-open-${lang}`}><ExternalLink className="w-4 h-4 mr-1.5" />{openLabel}</Button>
      </div>
    </div>
  );
}

function Confirm({ trigger, title, text, action, onConfirm, testid, danger }) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader><AlertDialogTitle>{title}</AlertDialogTitle><AlertDialogDescription>{text}</AlertDialogDescription></AlertDialogHeader>
        <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel><AlertDialogAction className={danger ? "bg-red-500 hover:bg-red-600" : ""} onClick={onConfirm} data-testid={testid}>{action}</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function EmailPreview({ eventId }) {
  const [pv, setPv] = useState(null);
  const show = async (kind, role) => { try { setPv((await api.get(`/events/${eventId}/staff-email-preview`, { params: { kind, role } })).data); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const btns = [["nuovo", "staff", "Nuovo Staff"], ["nuovo", "volunteer", "Nuovo Volontario"], ["esistente", "staff", "Account già attivo"], ["disponibilita", "volunteer", "Disponibilità ricevuta"]];
  return (
    <div className="mt-4 pt-4 border-t border-slate-100" data-testid="staff-email-preview">
      <div className="text-sm font-semibold text-slate-700 mb-2 flex items-center gap-1.5"><Mail className="w-4 h-4 text-tiffany-active" />Anteprima email Staff e Volontari</div>
      <div className="flex flex-wrap gap-2">{btns.map(([k, r, l]) => <Button key={k + r} variant="outline" size="sm" onClick={() => show(k, r)} data-testid={`email-preview-${k}-${r}`}>{l}</Button>)}</div>
      {pv && (<div className="mt-3 rounded-lg border border-slate-200 overflow-hidden">
        <div className="px-3 py-2 bg-slate-50 text-xs text-slate-600" data-testid="email-preview-meta"><b>Da:</b> {pv.from_name} · <b>Oggetto:</b> {pv.subject}</div>
        <iframe title="Anteprima email" srcDoc={pv.html} sandbox="" className="w-full h-[520px] bg-white" data-testid="email-preview-frame" />
      </div>)}
    </div>
  );
}

export default function AvailabilityDialog({ eventId, open, onOpenChange }) {
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn, ok) => { setBusy(true); try { await fn(); if (ok) toast.success(ok); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); } };
  const loadLink = useCallback(() => run(async () => setLink((await api.get(`/events/${eventId}/availability/link`)).data)), [eventId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (open) { loadLink(); } }, [open, loadLink]);
  const genLink = () => run(async () => setLink((await api.post(`/events/${eventId}/availability/link`)).data), "Link pubblico generato");
  const deactivate = () => run(async () => { await api.post(`/events/${eventId}/availability/link/deactivate`); setLink((await api.get(`/events/${eventId}/availability/link`)).data); }, "Link disattivato");
  const withLang = (l) => link.url + (link.url.includes("?") ? "&" : "?") + "lang=" + l;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="availability-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2"><ClipboardList className="w-5 h-5 text-tiffany-active" />Raccolta disponibilità</DialogTitle>
          <DialogDescription>Chi compila il modulo entra direttamente in Staff / Volontari con stato Da classificare.</DialogDescription>
        </DialogHeader>
        {link?.active ? (
          <div className="space-y-4">
            <StatusBadge color="green">Link attivo</StatusBadge>
            <LinkRow flag="🇮🇹" label="Link partecipazione — Italiano" url={withLang("it")} copyLabel="Copia link IT" openLabel="Apri IT" lang="it" />
            <LinkRow flag="🇬🇧" label="Link partecipazione — English" url={withLang("en")} copyLabel="Copy EN link" openLabel="Open EN" lang="en" />
            <div className="flex flex-wrap gap-2 pt-3 border-t border-slate-100">
              <Confirm trigger={<Button variant="outline" size="sm" data-testid="avail-regen"><RefreshCw className="w-4 h-4 mr-1.5" />Rigenera link</Button>} title="Rigenerare il link?"
                text="Il link precedente verrà invalidato immediatamente. Le disponibilità già raccolte restano salvate." action="Rigenera" onConfirm={genLink} testid="avail-regen-confirm" />
              <Confirm danger trigger={<Button variant="outline" size="sm" className="text-red-500 hover:text-red-600" data-testid="avail-deactivate"><Ban className="w-4 h-4 mr-1.5" />Disattiva link</Button>} title="Disattivare il link?"
                text="La pagina pubblica non accetterà più nuove disponibilità. Potrai rigenerare un link in seguito." action="Disattiva" onConfirm={deactivate} testid="avail-deactivate-confirm" />
            </div>
          </div>
        ) : (
          <div className="text-center py-6">
            <StatusBadge color="gray">Nessun link attivo</StatusBadge>
            <p className="text-sm text-slate-500 mt-3 mb-4">Genera un link pubblico da condividere: le persone potranno indicare la propria disponibilità senza accedere a CRMEvent.</p>
            <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={genLink} disabled={busy} data-testid="avail-generate"><Link2 className="w-4 h-4 mr-1.5" />{busy ? "Generazione..." : "Genera link pubblico"}</Button>
          </div>
        )}
        <Link to="/staff-volontari" onClick={() => onOpenChange(false)} className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-tiffany-active hover:underline" data-testid="avail-go-staff">
          <Users className="w-4 h-4" />Vedi le persone in Staff / Volontari → Da classificare
        </Link>
        <EmailPreview eventId={eventId} />
      </DialogContent>
    </Dialog>
  );
}
