import { useSearchParams } from "react-router-dom";
import { Handshake } from "lucide-react";
import PartnerRegistry from "@/components/partners/PartnerRegistry";
import PartnerStats from "@/components/partners/PartnerStats";
import PartnerOrgs from "@/components/partners/PartnerOrgs";
import PartnerCommissions from "@/components/partners/PartnerCommissions";
import PartnerConfig from "@/components/partners/PartnerConfig";

const TABS = [["anagrafiche", "Anagrafiche", PartnerRegistry], ["statistiche", "Statistiche", PartnerStats], ["organizzatori", "Organizzatori", PartnerOrgs],
  ["commissioni", "Commissioni", PartnerCommissions], ["configurazione", "Configurazione", PartnerConfig]];

export default function PlatformPartners() {
  const [sp, setSp] = useSearchParams();
  const tab = TABS.find((t) => t[0] === sp.get("area")) || TABS[0];
  const View = tab[2];
  return (
    <div className="animate-fade-up space-y-5" data-testid="platform-partners">
      <div>
        <h1 className="font-display text-3xl font-bold text-slate-900 flex items-center gap-2"><Handshake className="w-7 h-7 text-[#0ABAB5]" />Partner</h1>
        <p className="text-slate-500 mt-1">Programma CRMEvent Partner: anagrafiche, risultati, organizzazioni attribuite, commissioni e regole.</p>
      </div>
      <div role="tablist" className="inline-flex max-w-full overflow-x-auto rounded-lg bg-slate-100 p-1 gap-1" data-testid="partner-tabs">
        {TABS.map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={tab[0] === k} onClick={() => setSp({ area: k }, { replace: true })} data-testid={`partner-tab-${k}`}
            className={`h-8 px-3.5 shrink-0 rounded-md text-sm font-medium transition-[background-color,color,box-shadow] ${tab[0] === k ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>{l}</button>
        ))}
      </div>
      <View />
    </div>
  );
}
