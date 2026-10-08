import { useSearchParams } from "react-router-dom";
import { AvailabilityEmailPanel } from "@/components/AvailabilityEmailPanel";
import { RegisteredUsersPanel } from "@/components/RegisteredUsersPanel";
import { OrgListsPanel } from "@/components/OrgListsPanel";
import { FunnelPanel } from "@/components/FunnelPanel";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { MailCheck } from "lucide-react";

const TABS = ["funnel", "staff", "liste"];

export default function MarketingBrevo() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.includes(params.get("tab")) ? params.get("tab") : "funnel";
  return (
    <div className="max-w-6xl space-y-6" data-testid="marketing-brevo-page">
      <div>
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-900 bg-tiffany rounded-full px-2.5 py-1 mb-1" data-testid="platform-scope-badge">Marketing CRMEvent — Piattaforma</span>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><MailCheck className="w-6 h-6 text-tiffany-active" />Email &amp; Brevo</h1>
        <p className="text-slate-500 text-sm mt-1">Automazioni email, liste e contatti · gestione centralizzata riservata al Super Admin.</p>
      </div>
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabsList className="mb-4 w-full sm:w-auto overflow-x-auto justify-start h-auto flex-nowrap" data-testid="brevo-tabs">
          <TabsTrigger value="funnel" className="h-9" data-testid="brevo-tab-funnel">Funnel CRMEvent</TabsTrigger>
          <TabsTrigger value="staff" className="h-9" data-testid="brevo-tab-staff">Staff &amp; Volontari</TabsTrigger>
          <TabsTrigger value="liste" className="h-9" data-testid="brevo-tab-liste">Liste e contatti</TabsTrigger>
        </TabsList>
        <TabsContent value="funnel"><FunnelPanel /></TabsContent>
        <TabsContent value="staff"><AvailabilityEmailPanel /></TabsContent>
        <TabsContent value="liste" className="space-y-6"><RegisteredUsersPanel /><OrgListsPanel /></TabsContent>
      </Tabs>
    </div>
  );
}
