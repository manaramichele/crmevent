import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { can, isOrgAdmin } from "@/lib/perms";
import { PageHeader } from "@/components/crm";
import { CalendarPlus, UserPlus, Building2, Users, ListPlus, Map, Handshake, BedDouble, FileText, BellRing, Mail, Headset, Store, Zap, ArrowRight } from "lucide-react";

const ACTIONS = [
  { id: "evento", label: "Crea evento", desc: "Apri Eventi e crea un nuovo evento", to: "/eventi", icon: CalendarPlus, sec: "eventi" },
  { id: "staff", label: "Aggiungi staff o volontario", desc: "Inserisci una persona nello Staff", to: "/staff-volontari", icon: UserPlus, sec: "staff" },
  { id: "attivita", label: "Nuova attività", desc: "Pianifica un'attività", to: "/attivita", icon: ListPlus, sec: "attivita" },
  { id: "azienda", label: "Nuova azienda", desc: "Aggiungi un'azienda", to: "/aziende", icon: Building2, sec: "aziende" },
  { id: "anagrafica", label: "Nuova anagrafica", desc: "Aggiungi un contatto", to: "/persone", icon: Users, sec: "anagrafiche" },
  { id: "percorso", label: "Nuovo percorso", desc: "Apri un evento e carica GPX o mappe", to: "/eventi", icon: Map, sec: "mappe" },
  { id: "sponsor", label: "Nuovo sponsor", desc: "Registra sponsor e partner", to: "/sponsor", icon: Handshake, sec: "sponsor" },
  { id: "ospitalita", label: "Gestisci ospitalità", desc: "Camere e pasti", to: "/ospitalita", icon: BedDouble, sec: "ospitalita" },
  { id: "briefing", label: "Nuovo briefing", desc: "Apri un evento e prepara il briefing", to: "/eventi", icon: FileText, sec: "briefing" },
  { id: "followup", label: "Nuovo follow-up", desc: "Programma un promemoria", to: "/followup", icon: BellRing, sec: "followup" },
  { id: "invita", label: "Invita utente", desc: "Aggiungi un collaboratore CRM", to: "/profilo?tab=utenti", icon: Mail, admin: true },
  { id: "assistenza", label: "Assistenza", desc: "Scrivici o prenota una videochiamata", to: "/assistenza", icon: Headset, always: true },
  { id: "marketplace", label: "Marketplace", desc: "Servizi aggiuntivi per la tua organizzazione", to: "/marketplace", icon: Store, always: true },
];

export default function QuickActions() {
  const { user } = useAuth();
  const list = ACTIONS.filter((a) => a.always || (a.admin ? isOrgAdmin(user) : can(user, a.sec, "create")));
  return (
    <div className="animate-fade-up space-y-5" data-testid="quick-actions-page">
      <PageHeader title="Azioni rapide" subtitle="Le operazioni più frequenti, in base al tuo piano e ai tuoi permessi." />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {list.map((a) => (
          <Link key={a.id} to={a.to} data-testid={`quick-action-${a.id}`}
            className="group flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition-[transform,box-shadow,border-color] hover:-translate-y-0.5 hover:shadow-md hover:border-[#0ABAB5]">
            <span className="w-11 h-11 rounded-xl flex items-center justify-center shrink-0" style={{ background: "rgba(10,186,181,0.12)" }}><a.icon className="w-5 h-5 text-[#088F8A]" /></span>
            <span className="flex-1 min-w-0"><span className="block font-semibold text-slate-900">{a.label}</span><span className="block text-xs text-slate-500 truncate">{a.desc}</span></span>
            <ArrowRight className="w-4 h-4 text-slate-300 transition-transform group-hover:translate-x-1 group-hover:text-[#0ABAB5]" />
          </Link>
        ))}
      </div>
      {!list.some((a) => !a.always) && <p className="text-sm text-slate-500 flex items-center gap-2" data-testid="quick-actions-empty"><Zap className="w-4 h-4" />Non hai azioni operative disponibili con i permessi attuali.</p>}
    </div>
  );
}
