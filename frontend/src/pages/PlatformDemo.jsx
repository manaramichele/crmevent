import { PageHeader } from "@/components/crm";
import { Availability } from "@/pages/PlatformVideoSupport";

export default function PlatformDemo() {
  return (
    <div className="animate-fade-up space-y-4" data-testid="demo-admin-page">
      <PageHeader title="Prenotazioni demo" subtitle="Fasce orarie per le demo gratuite prenotate dai nuovi organizzatori dopo la registrazione (30 minuti, Google Meet). Stesso calendario dell'assistenza: nessuna sovrapposizione. Gli orari sono proposti come preferenza: le richieste compaiono in Richieste demo e tra i Lead (da confermare)." />
      <Availability base="/platform/demo/config" testid="demo" />
    </div>
  );
}
