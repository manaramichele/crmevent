import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

// Creazione rapida Team dal dropdown "+ Aggiungi nuovo Team".
// Il Team viene associato automaticamente all'Evento su cui si sta lavorando (eventoId).
export default function TeamQuickCreate({ eventoId, onClose, onCreated }) {
  const [nome, setNome] = useState("");
  const [area, setArea] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (!nome.trim()) { toast.error("Inserisci il nome del Team"); return; }
    if (!eventoId) { toast.error("Seleziona prima l'Evento"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/teams", { nome: nome.trim(), area: area.trim() || undefined, evento_id: eventoId });
      toast.success("Team creato");
      onCreated && onCreated(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose && onClose(); }}>
      <DialogContent className="w-[95vw] max-w-md" data-testid="team-quick-create">
        <DialogHeader>
          <DialogTitle className="font-display">Nuovo Team</DialogTitle>
          <DialogDescription>Verrà associato automaticamente all'evento selezionato.</DialogDescription>
        </DialogHeader>
        {!eventoId ? (
          <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">Seleziona prima l'Evento nel form, poi riapri "+ Aggiungi nuovo Team".</div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5"><Label className="text-xs">Nome Team *</Label><Input autoFocus value={nome} onChange={(e) => setNome(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save()} data-testid="team-quick-nome" /></div>
            <div className="space-y-1.5"><Label className="text-xs">Area (facoltativa)</Label><Input value={area} onChange={(e) => setArea(e.target.value)} data-testid="team-quick-area" /></div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose && onClose()} data-testid="team-quick-cancel">Annulla</Button>
          <Button onClick={save} disabled={busy || !eventoId} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="team-quick-save">Crea Team</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
