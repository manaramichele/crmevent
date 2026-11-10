import { useEffect, useState } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";

const MQ = "(max-width: 767px), (pointer: coarse) and (max-width: 1024px)";

export function useIsMobilePicker() {
  const [m, setM] = useState(() => typeof window !== "undefined" && window.matchMedia(MQ).matches);
  useEffect(() => {
    const q = window.matchMedia(MQ);
    const on = () => setM(q.matches);
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, []);
  return m;
}

// Su smartphone il menu è un pannello dal basso basato su una Dialog annidata: diventa il blocco-scroll
// attivo e la lista è al suo interno, quindi iOS Safari la scorre in modo nativo (il Popover portalizzato
// fuori dalla modale veniva bloccato dal blocco-scroll della modale).
export function ResponsivePicker({ open, onOpenChange, trigger, title, children, testid, popoverProps = {}, mobile }) {
  if (!mobile) {
    return (
      <Popover open={open} onOpenChange={onOpenChange}>
        <PopoverTrigger asChild>{trigger}</PopoverTrigger>
        <PopoverContent data-testid={testid} {...popoverProps}>{children}</PopoverContent>
      </Popover>
    );
  }
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-[300] bg-black/40" />
        <DialogPrimitive.Content aria-describedby={undefined} data-testid={testid} data-sheet="true"
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="fixed inset-x-0 bottom-0 z-[301] flex max-h-[85dvh] flex-col rounded-t-2xl bg-white pb-[env(safe-area-inset-bottom)] shadow-2xl outline-none">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <DialogPrimitive.Title className="text-sm font-semibold text-slate-800">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close className="rounded-full p-1.5 text-slate-500 hover:bg-slate-100" data-testid={`${testid}-close`} aria-label="Chiudi"><X className="h-4 w-4" /></DialogPrimitive.Close>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export const listClass = (mobile, desktop) => (mobile ? "min-h-0 flex-1 overflow-y-auto overscroll-contain p-2 [&_button]:py-3 [&_button]:text-base" : desktop);
