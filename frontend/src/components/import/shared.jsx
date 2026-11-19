import { useState } from "react";
import { Check, ChevronsUpDown } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

export const SEL = "h-9 rounded-md border border-slate-200 bg-white px-2 text-sm";
export const STATUS = {
  nuovo: ["Nuovo", "bg-emerald-50 text-emerald-700"], esistente: ["Esistente", "bg-sky-50 text-sky-700"],
  possibile_duplicato: ["Possibile duplicato", "bg-amber-50 text-amber-700"], conflitto: ["Conflitto", "bg-orange-50 text-orange-700"],
  duplicato_file: ["Ripetuto nel file", "bg-slate-100 text-slate-600"], errore: ["Errore", "bg-red-50 text-red-700"],
};
export const ACTION = { crea: "Crea", aggiorna: "Aggiorna", collega: "Collega", ignora: "Ignora" };

export function Pill({ s }) {
  const [l, c] = STATUS[s] || [s, "bg-slate-100 text-slate-600"];
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap ${c}`}>{l}</span>;
}

// Menu ricercabile generico: options [{value,label,hint}]
export function SearchSelect({ value, onChange, options, placeholder = "Seleziona…", testid, emptyLabel }) {
  const [open, setOpen] = useState(false);
  const cur = options.find((o) => o.value === value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={`${SEL} w-full min-w-[170px] flex items-center justify-between text-left`} data-testid={testid}>
          <span className={`truncate ${cur ? "text-slate-900" : "text-slate-400"}`}>{cur ? cur.label : (emptyLabel || placeholder)}</span><ChevronsUpDown className="h-4 w-4 shrink-0 text-slate-400" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] min-w-[240px] p-0" align="start">
        <Command><CommandInput placeholder="Cerca…" /><CommandList><CommandEmpty>Nessun risultato</CommandEmpty><CommandGroup>
          {options.map((o) => (
            <CommandItem key={o.value || "_none"} value={`${o.label} ${o.hint || ""} ${o.value}`} onSelect={() => { onChange(o.value); setOpen(false); }} data-testid={testid ? `${testid}-opt-${o.value || "none"}` : undefined}>
              {value === o.value && <Check className="w-4 h-4 mr-1" />}<span className="flex-1">{o.label}</span>{o.hint && <span className="text-[11px] text-slate-400">{o.hint}</span>}
            </CommandItem>))}
        </CommandGroup></CommandList></Command>
      </PopoverContent>
    </Popover>
  );
}

export function download(path, name) {
  return import("@/lib/api").then(({ default: api }) => api.get(path, { responseType: "blob" })).then(({ data }) => {
    const url = URL.createObjectURL(data);
    const a = document.createElement("a");
    a.href = url; a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}
