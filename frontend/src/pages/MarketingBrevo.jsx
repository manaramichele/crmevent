import { AvailabilityEmailPanel } from "@/components/AvailabilityEmailPanel";
import { RegisteredUsersPanel } from "@/components/RegisteredUsersPanel";
import { OrgListsPanel } from "@/components/OrgListsPanel";
import { MailCheck } from "lucide-react";

export default function MarketingBrevo() {
  return (
    <div className="max-w-6xl space-y-6" data-testid="marketing-brevo-page">
      <div>
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-900 bg-tiffany rounded-full px-2.5 py-1 mb-1" data-testid="platform-scope-badge">Marketing CRMEvent — Piattaforma</span>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><MailCheck className="w-6 h-6 text-tiffany-active" />Email &amp; Brevo</h1>
        <p className="text-slate-500 text-sm mt-1">Utenti registrati e template per la raccolta disponibilità · gestione centralizzata riservata al Super Admin.</p>
      </div>
      <RegisteredUsersPanel />
      <OrgListsPanel />
      <AvailabilityEmailPanel />
    </div>
  );
}
