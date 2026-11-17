import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, SectionCard } from "@/components/crm";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import OptionListsManager from "@/components/OptionListsManager";

export default function SettingsPage() {
  const { user } = useAuth();
  const doReset = async () => {
    try { await api.post("/admin/reset-data"); toast.success("Database operativo azzerato"); setTimeout(() => window.location.reload(), 800); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeader title="Impostazioni" subtitle="Menu a tendina, integrazioni e manutenzione dati" />

      <OptionListsManager />
      {user?.role === "superadmin" && <OptionListsManager platform />}

      <SectionCard title="Google Calendar">
        <p className="text-sm text-slate-600">La sincronizzazione Google Calendar richiede la configurazione di <b>GOOGLE_CLIENT_ID</b> e <b>GOOGLE_CLIENT_SECRET</b> nei Secrets di produzione. Ogni utente collega poi il proprio calendario da <b>Profilo → Integrazioni</b>.</p>
      </SectionCard>

      {user?.role === "superadmin" && (
        <div className="bg-white border border-red-200 rounded-xl shadow-sm p-5">
          <div className="flex items-center gap-2 mb-2"><AlertTriangle className="w-5 h-5 text-red-500" /><h3 className="text-base font-semibold text-slate-800 font-display">Reset database operativo</h3></div>
          <p className="text-sm text-slate-600 mb-4">Elimina definitivamente tutti i dati operativi (eventi, aziende, persone, trattative, staff, team, turni, mappe, attività, follow-up e account staff/volontari) e disabilita il seed demo. L'account amministratore e le configurazioni restano. Usalo solo quando sei pronto a partire con i dati reali.</p>
          <AlertDialog>
            <AlertDialogTrigger asChild><Button className="bg-red-500 hover:bg-red-600 text-white" data-testid="reset-data-button">Azzera database operativo</Button></AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader><AlertDialogTitle>Confermi l'azzeramento?</AlertDialogTitle>
                <AlertDialogDescription>Tutti i dati operativi saranno eliminati in modo irreversibile. Questa azione non può essere annullata.</AlertDialogDescription></AlertDialogHeader>
              <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel>
                <AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={doReset} data-testid="confirm-reset">Sì, azzera tutto</AlertDialogAction></AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      )}
    </div>
  );
}
