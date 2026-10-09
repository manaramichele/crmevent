import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ArrowUpCircle } from "lucide-react";

export default function PlanLimitDialog() {
  const [d, setD] = useState(null);
  const navigate = useNavigate();
  useEffect(() => {
    const h = (e) => setD(e.detail);
    window.addEventListener("crmevent:plan-limit", h);
    return () => window.removeEventListener("crmevent:plan-limit", h);
  }, []);
  return (
    <Dialog open={!!d} onOpenChange={(o) => !o && setD(null)}>
      <DialogContent className="max-w-md w-[calc(100vw-1.5rem)]" data-testid="plan-limit-dialog">
        <ArrowUpCircle className="w-10 h-10 text-[#0ABAB5]" />
        <DialogTitle className="font-display text-xl font-bold">{d?.kind === "events" ? "Limite eventi raggiunto" : "Limite utenti raggiunto"}</DialogTitle>
        <DialogDescription className="text-slate-600" data-testid="plan-limit-message">{d?.message}</DialogDescription>
        <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end mt-2">
          <Button variant="outline" onClick={() => setD(null)} data-testid="plan-limit-close">Non ora</Button>
          <Button onClick={() => { setD(null); navigate("/profilo?tab=abbonamento"); }} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="plan-limit-upgrade">Cambia piano</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
