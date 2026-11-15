import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

const TEXT = [["name", "Nome funzionalità"], ["title", "Titolo pagina video"], ["subtitle", "Sottotitolo"], ["subject", "Oggetto email"], ["preheader", "Testo di anteprima"], ["headline", "Titolo principale email"], ["button_label", "Testo pulsante"]];

export function PromoEditDialog({ m, onClose, onSaved }) {
  const [f, setF] = useState({ ...m, benefits_txt: (m.benefits || []).join("\n"), html_override: m.html_override || "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      const body = { ...Object.fromEntries(TEXT.map(([k]) => [k, f[k] || ""])), description: f.description || "", body: f.body || "", benefits: f.benefits_txt.split("\n"), html_override: f.html_override };
      await api.put(`/promo-materials/${m.slug}`, body);
      toast.success("Materiale aggiornato: la versione precedente è stata conservata");
      onSaved(); onClose();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Salvataggio non riuscito"); }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid={`promo-edit-dialog-${m.slug}`}>
        <DialogHeader><DialogTitle>Modifica · {m.name}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {TEXT.map(([k, l]) => <div key={k}><Label>{l}</Label><Input value={f[k] || ""} onChange={set(k)} data-testid={`promo-field-${k}`} /></div>)}
        </div>
        <div><Label>Descrizione pagina video</Label><Textarea rows={3} value={f.description || ""} onChange={set("description")} data-testid="promo-field-description" /></div>
        <div><Label>Testo email (paragrafi separati da una riga vuota)</Label><Textarea rows={6} value={f.body || ""} onChange={set("body")} data-testid="promo-field-body" /></div>
        <div><Label>Vantaggi (uno per riga)</Label><Textarea rows={3} value={f.benefits_txt} onChange={set("benefits_txt")} data-testid="promo-field-benefits" /></div>
        <div><Label>HTML personalizzato (facoltativo: sostituisce il modello; usa {"{{SITE}}"} per l'indirizzo del sito)</Label><Textarea rows={5} className="font-mono text-xs" value={f.html_override} onChange={set("html_override")} data-testid="promo-field-html" /></div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={busy} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="promo-edit-save">Salva</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
