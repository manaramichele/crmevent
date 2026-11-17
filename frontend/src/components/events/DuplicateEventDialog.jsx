import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";

const OPTS = [["copy_maps", "Percorsi, mappe, discipline e distanze (GPX/KML/KMZ)"], ["copy_teams", "Struttura dei Team (senza persone assegnate)"], ["copy_activities", "Attività (riportate a \"da fare\", date spostate sulla nuova edizione)"], ["copy_planner", "Progetti e planimetrie Event Planner (copia: l'originale resta invariato)"]];
const nextYear = (d) => (d ? `${Number(d.slice(0, 4)) + 1}${d.slice(4, 10)}` : "");
const nextEdition = (e) => (e && /^\d{4}$/.test(e.trim()) ? String(Number(e.trim()) + 1) : "");

export function DuplicateEventDialog({ row, onClose, onDone }) {
  const [f, setF] = useState({ nome: row.nome || "", edizione: nextEdition(row.edizione) || String(new Date().getFullYear() + 1), data_inizio: nextYear(row.data_inizio), copy_maps: true, copy_teams: true, copy_activities: true, copy_planner: false });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/events/${row.id}/duplicate`, { ...f, nome: f.nome.trim(), data_inizio: f.data_inizio || null, edizione: f.edizione || null });
      toast.success(`Nuova edizione creata: ${data.nome}`);
      onDone(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid="duplicate-event-dialog">
        <DialogTitle>Duplica evento</DialogTitle>
        <DialogDescription>Crea una nuova edizione di "{row.nome}" nella stessa organizzazione.</DialogDescription>
        <div className="space-y-3">
          <label className="block text-xs text-slate-500">Nome del nuovo evento<Input value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} className="mt-1 text-sm text-slate-900" data-testid="duplicate-name" /></label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs text-slate-500">Data inizio<Input type="date" value={f.data_inizio} onChange={(e) => setF({ ...f, data_inizio: e.target.value })} className="mt-1 text-sm text-slate-900" data-testid="duplicate-date" /></label>
            <label className="block text-xs text-slate-500">Anno / edizione<Input value={f.edizione} onChange={(e) => setF({ ...f, edizione: e.target.value })} maxLength={40} className="mt-1 text-sm text-slate-900" data-testid="duplicate-edition" /></label>
          </div>
          <p className="text-[11px] text-slate-500">Le altre date (allestimento, fine, disallestimento, attività) vengono spostate dello stesso intervallo.</p>
          <div className="space-y-2 rounded-lg bg-slate-50 p-3">
            <div className="text-xs font-semibold text-slate-700">Cosa copiare</div>
            {OPTS.map(([k, l]) => (
              <label key={k} className="flex items-start gap-2 text-sm text-slate-700"><Checkbox checked={f[k]} onCheckedChange={(v) => setF({ ...f, [k]: !!v })} className="mt-0.5" data-testid={`duplicate-${k}`} />{l}</label>))}
          </div>
          <p className="text-[11px] text-slate-500" data-testid="duplicate-never">Non vengono mai copiati: iscritti e dati personali, assegnazioni di staff e volontari, sponsor, ospitalità, pagamenti e fatture, video Event Map, crediti, acquisti e attivazioni dei moduli, statistiche e risultati.</p>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose} data-testid="duplicate-cancel">Annulla</Button>
            <Button onClick={submit} disabled={busy || f.nome.trim().length < 2} className="bg-tiffany text-slate-900 hover:bg-tiffany-hover font-semibold" data-testid="duplicate-confirm">{busy ? "Duplicazione..." : "Duplica evento"}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
