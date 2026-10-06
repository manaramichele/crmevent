import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useCollection, SectionCard, formatEUR } from "@/components/crm";
import PipelineAttention from "@/components/PipelineAttention";
import OrgMessagesBanner from "@/components/OrgMessagesBanner";
import { OnboardingCard } from "@/components/Onboarding";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from "recharts";
import {
  CalendarDays, Building2, Users, TrendingUp, Handshake, UserCog,
  Clock, AlertTriangle, CheckCircle2, Wallet, Target, UserCheck,
} from "lucide-react";

const FASE_LABEL = {
  prospect: "Prospect", contattato: "Contattato", proposta_inviata: "Proposta inviata",
  in_trattativa: "In trattativa", confermato: "Confermato", perso: "Perso",
};

function Kpi({ icon: Icon, label, value, color = "tiffany", testid }) {
  const ring = { tiffany: "text-tiffany-active bg-tiffany-light", green: "text-emerald-600 bg-emerald-50", orange: "text-amber-600 bg-amber-50", red: "text-red-500 bg-red-50", blue: "text-sky-600 bg-sky-50" }[color];
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm hover:shadow-md transition-shadow p-5" data-testid={testid}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium tracking-wide uppercase text-slate-500">{label}</span>
        <span className={`w-9 h-9 rounded-lg flex items-center justify-center ${ring}`}><Icon className="w-4.5 h-4.5" /></span>
      </div>
      <div className="mt-3 text-3xl font-bold text-slate-900 font-display">{value}</div>
    </div>
  );
}

export default function Dashboard() {
  const { items: events } = useCollection("/events");
  const [eventoId, setEventoId] = useState("all");
  const [data, setData] = useState(null);

  useEffect(() => {
    const load = async () => {
      const params = eventoId !== "all" ? { evento_id: eventoId } : {};
      const { data } = await api.get("/dashboard", { params });
      setData(data);
    };
    load();
  }, [eventoId]);

  if (!data) return <div className="text-slate-400">Caricamento dashboard...</div>;

  const pipeline = data.pipeline_chart.map((p) => ({ ...p, name: FASE_LABEL[p.fase] || p.fase }));
  const FASE_COLORS = { prospect: "#94A3B8", contattato: "#0EA5E9", proposta_inviata: "#F59E0B", in_trattativa: "#0ABAB5", confermato: "#10B981", perso: "#EF4444" };
  const PIE_COLORS = ["#0ABAB5", "#0EA5E9", "#F59E0B", "#10B981", "#94A3B8"];

  return (
    <div className="animate-fade-up space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 font-display">Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1">Panoramica operativa e commerciale</p>
        </div>
        <div className="w-full sm:w-64">
          <Select value={eventoId} onValueChange={setEventoId}>
            <SelectTrigger data-testid="dashboard-event-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti gli eventi</SelectItem>
              {events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      <OrgMessagesBanner />

      <OnboardingCard />

      <PipelineAttention />

      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">Eventi</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Kpi icon={CalendarDays} label="Eventi attivi" value={data.eventi.attivi} testid="kpi-eventi-attivi" />
          <Kpi icon={Clock} label="Prossimi eventi" value={data.eventi.prossimi} color="blue" testid="kpi-eventi-prossimi" />
          <Kpi icon={CheckCircle2} label="Eventi conclusi" value={data.eventi.conclusi} color="green" testid="kpi-eventi-conclusi" />
          <Kpi icon={CalendarDays} label="Totale eventi" value={data.eventi.totali} testid="kpi-eventi-totali" />
        </div>
      </div>

      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">CRM</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Kpi icon={Building2} label="Aziende totali" value={data.crm.aziende} testid="kpi-aziende" />
          <Kpi icon={Users} label="Anagrafiche totali" value={data.crm.persone} testid="kpi-persone" />
          <Kpi icon={UserCheck} label="Nuovi contatti" value={data.crm.nuovi_contatti} color="blue" testid="kpi-nuovi-contatti" />
          <Kpi icon={Target} label="Prospect" value={data.crm.prospect} color="orange" testid="kpi-prospect" />
        </div>
      </div>

      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">Commerciale</h2>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
          <Kpi icon={Handshake} label="Trattative aperte" value={data.commerciale.trattative_aperte} testid="kpi-trattative" />
          <Kpi icon={TrendingUp} label="Proposte inviate" value={data.commerciale.proposte_inviate} color="orange" testid="kpi-proposte" />
          <Kpi icon={CheckCircle2} label="Sponsor confermati" value={data.commerciale.sponsor_confermati} color="green" testid="kpi-sponsor-confermati" />
          <Kpi icon={Wallet} label="Valore pipeline" value={formatEUR(data.commerciale.valore_pipeline)} testid="kpi-valore-pipeline" />
          <Kpi icon={Wallet} label="Valore confermato" value={formatEUR(data.commerciale.valore_confermato)} color="green" testid="kpi-valore-confermato" />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <SectionCard title="Pipeline commerciale" className="lg:col-span-8">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={pipeline} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EDF2F7" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#64748B" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "#64748B" }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: "#F8FAFC" }} contentStyle={{ borderRadius: 10, border: "1px solid #E2E8F0", fontSize: 12 }} />
              <Bar dataKey="count" radius={[6, 6, 0, 0]} name="Trattative">
                {pipeline.map((p) => <Cell key={p.fase} fill={FASE_COLORS[p.fase] || "#0ABAB5"} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>
        <SectionCard title="Relazioni per tipo" className="lg:col-span-4">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={data.tipo_chart} dataKey="count" nameKey="tipo" innerRadius={55} outerRadius={90} paddingAngle={3}>
                {data.tipo_chart.map((e, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
              </Pie>
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Tooltip contentStyle={{ borderRadius: 10, border: "1px solid #E2E8F0", fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">Attività</h2>
          <div className="grid grid-cols-2 gap-4">
            <Kpi icon={Clock} label="Follow-up di oggi" value={data.attivita.followup_oggi} color="orange" testid="kpi-fu-oggi" />
            <Kpi icon={AlertTriangle} label="Follow-up scaduti" value={data.attivita.followup_scaduti} color="red" testid="kpi-fu-scaduti" />
            <Kpi icon={ListIcon} label="Prossime attività" value={data.attivita.prossime} testid="kpi-att-prossime" />
            <Kpi icon={CheckCircle2} label="Completate" value={data.attivita.completate} color="green" testid="kpi-att-completate" />
          </div>
        </div>
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">Staff & Volontari</h2>
          <div className="grid grid-cols-2 gap-4">
            <Kpi icon={UserCog} label="Staff confermati" value={data.staff.staff_confermati} color="green" testid="kpi-staff-confermati" />
            <Kpi icon={Users} label="Volontari confermati" value={data.staff.volontari_confermati} color="green" testid="kpi-volontari" />
            <Kpi icon={AlertTriangle} label="Da riconfermare" value={data.staff.da_riconfermare} color="orange" testid="kpi-da-riconfermare" />
            <Kpi icon={AlertTriangle} label="Turni scoperti" value={data.staff.turni_scoperti} color="red" testid="kpi-turni-scoperti" />
          </div>
        </div>
      </div>
    </div>
  );
}

function ListIcon(props) { return <ListChecksSvg {...props} />; }
function ListChecksSvg(props) {
  return <svg {...props} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>;
}
