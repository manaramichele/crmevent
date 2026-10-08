import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export default function PlanUpgrade() {
  const { user } = useAuth();
  return (
    <div className="max-w-lg mx-auto text-center py-20" data-testid="plan-upgrade">
      <div className="w-12 h-12 rounded-full bg-[#0ABAB5]/10 mx-auto flex items-center justify-center"><Lock className="w-5 h-5 text-[#0ABAB5]" /></div>
      <div className="font-display text-2xl font-bold text-slate-900 mt-4">Funzione non inclusa nel tuo piano</div>
      <p className="text-slate-500 mt-2">Il piano {user?.saas?.plan_label || user?.saas?.paid_plan_label || "attuale"} non comprende questa sezione. Passa a un piano superiore per utilizzarla: i tuoi dati restano conservati.</p>
      <Link to="/profilo?tab=abbonamento" data-testid="plan-upgrade-cta" className="mt-6 inline-flex h-11 items-center rounded-xl bg-[#0ABAB5] px-6 text-sm font-semibold text-slate-900 transition-colors hover:bg-[#09A8A3]">Scopri i piani</Link>
    </div>
  );
}
