import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { useTeams, invalidateTeams } from "@/lib/teamsStore";
import { useWheelScroll } from "@/lib/useWheelScroll";
import TeamQuickCreate from "@/components/TeamQuickCreate";

// Selettore Team condiviso usato in TUTTE le maschere (Ruoli evento, Turni, Anagrafica, ...).
// - "— Nessun team —" sempre in cima (se allowNone)
// - Team dell'evento in ordine alfabetico A→Z
// - "+ Aggiungi nuovo Team" sempre visibile in fondo (footer sticky)
// Legge dal teamsStore globale: ogni create/edit/delete aggiorna in tempo reale ogni selettore.
export default function TeamSelect({
  value, onChange, eventoId, allowNone = true, placeholder = "— Nessun team —",
  testid = "team-select", align = "start", disabled = false,
  noEventHint = "Seleziona prima l'Evento per scegliere o creare un Team.",
}) {
  const { teams } = useTeams();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const bindWheel = useWheelScroll();

  const list = useMemo(() => (teams || [])
    .filter((t) => !eventoId || t.evento_id === eventoId)
    .sort((a, b) => (a.nome || "").localeCompare(b.nome || "", "it", { sensitivity: "base" })),
  [teams, eventoId]);

  const selected = (teams || []).find((t) => t.id === value);

  if (!eventoId) {
    return <div className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg px-3 py-2.5" data-testid={testid}>{noEventHint}</div>;
  }

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" role="combobox" disabled={disabled}
            className="w-full justify-between font-normal h-10" data-testid={testid}>
            <span className={selected ? "text-slate-800 truncate" : "text-slate-400 truncate"}>{selected ? selected.nome : placeholder}</span>
            <ChevronsUpDown className="w-4 h-4 text-slate-400 shrink-0" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="p-0 z-[200]" align={align}
          style={{ width: "var(--radix-popover-trigger-width)", minWidth: 220 }} data-testid={`${testid}-popover`}>
          <div ref={bindWheel} className="max-h-56 overflow-y-auto p-1">
            {allowNone && (
              <button type="button" onClick={() => { onChange(""); setOpen(false); }}
                className="w-full text-left text-sm px-2 py-1.5 rounded-md hover:bg-slate-100 flex items-center justify-between" data-testid={`${testid}-opt-none`}>
                <span className="text-slate-500">— Nessun team —</span>
                {!value && <Check className="w-4 h-4 text-tiffany-active" />}
              </button>
            )}
            {list.length === 0 ? (
              <div className="px-2 py-3 text-xs text-slate-400 text-center" data-testid={`${testid}-empty`}>Nessun team per questo evento.</div>
            ) : list.map((t) => (
              <button key={t.id} type="button" onClick={() => { onChange(t.id); setOpen(false); }}
                className="w-full text-left text-sm px-2 py-1.5 rounded-md hover:bg-slate-100 flex items-center justify-between" data-testid={`${testid}-opt-${t.id}`}>
                <span className="truncate">{t.nome}</span>
                {value === t.id && <Check className="w-4 h-4 text-tiffany-active shrink-0" />}
              </button>
            ))}
          </div>
          <div className="p-1 border-t border-slate-100">
            <button type="button" onClick={() => { setOpen(false); setCreating(true); }}
              className="w-full text-left text-sm text-tiffany-active font-semibold px-2 py-1.5 rounded hover:bg-tiffany-light/50 inline-flex items-center gap-1" data-testid={`${testid}-add`}>
              <Plus className="w-3.5 h-3.5" />Aggiungi nuovo Team
            </button>
          </div>
        </PopoverContent>
      </Popover>
      {creating && (
        <TeamQuickCreate eventoId={eventoId} onClose={() => setCreating(false)}
          onCreated={async (t) => { await invalidateTeams(); if (t?.id) onChange(t.id); setCreating(false); }} />
      )}
    </>
  );
}
