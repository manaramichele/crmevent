import { PageHeader } from "@/components/crm";
import { Availability } from "@/pages/PlatformVideoSupport";

export default function PlatformDemo() {
  return (
    <div className="animate-fade-up space-y-4" data-testid="demo-admin-page">
      <PageHeader title="Demo" subtitle="Fasce orarie per le demo gratuite prenotate dai nuovi organizzatori dopo la registrazione (30 minuti, Google Meet). Stesso calendario dell'assistenza: nessuna sovrapposizione. Le prenotazioni compaiono tra i Lead con stato demo confermata." />
      <Availability base="/platform/demo/config" testid="demo" />
    </div>
  );
}
