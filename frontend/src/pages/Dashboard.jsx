import { useEffect, useState } from "react";
import api from "@/lib/api";
import { GlobalSearch } from "@/components/Layout";
import { useCollection, SectionCard, formatEUR } from "@/components/crm";
import PipelineAttention from "@/components/PipelineAttention";
import OrgMessagesBanner from "@/components/OrgMessagesBanner";
import MyTeams from "@/components/MyTeams";
import TrialButton from "@/components/TrialButton";
import { useAuth } from "@/context/AuthContext";
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

const LG_COLS = { 1: "lg:grid-cols-1", 2: "lg:grid-cols-2", 3: "lg:grid-cols-3", 4: "lg:grid-cols-4", 5: "lg:grid-cols-5" };

function KpiGroup({ title, items, testid, maxCols = 5 }) {
  const shown = items.filter((k) => k.value !== undefined);
  if (!shown.length) return null;
  return (
    <div data-testid={testid}>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-3">{title}</h2>
      <div className={`grid grid-cols-2 ${LG_COLS[Math.min(shown.length, maxCols)]} gap-3 sm:gap-4`}>
        {shown.map((k) => <Kpi key={k.testid} {...k} />)}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const { items: events } = useCollection("/events");
  const [eventoId, setEventoId] = useState("all");
  const [data, setData] = useState(null);

  // Dashboard costruita dai permessi effettivi restituiti dal backend a ogni caricamento (anche al ritorno sulla scheda)
  useEffect(() => {
    const load = async () => {
      const params = eventoId !== "all" ? { evento_id: eventoId } : {};
      try { const { data } = await api.get("/dashboard", { params }); setData(data); } catch { setData((d) => d || { sections: {} }); }
    };
    load();
    const onFocus = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", onFocus);
    return () => document.removeEventListener("visibilitychange", onFocus);
  }, [eventoId]);

  if (!data) return <div className="text-slate-400">Caricamento dashboard...</div>;

  const S = data.sections || {};
  const pipeline = (data.pipeline_chart || []).map((p) => ({ ...p, name: FASE_LABEL[p.fase] || p.fase }));
  const FASE_COLORS = { prospect: "#94A3B8", contattato: "#0EA5E9", proposta_inviata: "#F59E0B", in_trattativa: "#0ABAB5", confermato: "#10B981", perso: "#EF4444" };
  const PIE_COLORS = ["#0ABAB5", "#0EA5E9", "#F59E0B", "#10B981", "#94A3B8"];
  const ev = data.eventi, crm = data.crm, com = data.commerciale, att = data.attivita, st = data.staff;
  const nothing = !ev && !crm && !com && !att && !st && !S.pipeline && !data.my_teams?.length;

  return (
    <div className="animate-fade-up space-y-6" data-testid="dashboard">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 font-display">Dashboard</h1>
            {user?.role !== "superadmin" && <TrialButton saas={user?.saas} />}
          </div>
          <p className="text-sm text-slate-500 mt-1">Panoramica delle sezioni a cui hai accesso</p>
          <div className="mt-3 w-full sm:w-80" data-testid="dashboard-search"><GlobalSearch /></div>
        </div>
        {S.eventi && <div className="w-full sm:w-64">
          <Select value={eventoId} onValueChange={setEventoId}>
            <SelectTrigger data-testid="dashboard-event-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti gli eventi</SelectItem>
              {events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>}
      </div>

      <OrgMessagesBanner />

      <MyTeams teams={data.my_teams} />

      {S.pipeline && <PipelineAttention />}

      {nothing && <div className="bg-white border border-slate-200 rounded-xl p-6 text-sm text-slate-500" data-testid="dashboard-empty">Non ci sono riepiloghi disponibili per le sezioni a cui hai accesso.</div>}

      {ev && <KpiGroup title="Eventi" testid="dash-group-eventi" items={[
        { icon: CalendarDays, label: "Eventi attivi", value: ev.attivi, testid: "kpi-eventi-attivi" },
        { icon: Clock, label: "Prossimi eventi", value: ev.prossimi, color: "blue", testid: "kpi-eventi-prossimi" },
        { icon: CheckCircle2, label: "Eventi conclusi", value: ev.conclusi, color: "green", testid: "kpi-eventi-conclusi" },
        { icon: CalendarDays, label: "Totale eventi", value: ev.totali, testid: "kpi-eventi-totali" },
      ]} />}

      {crm && <KpiGroup title="CRM" testid="dash-group-crm" items={[
        { icon: Building2, label: "Aziende totali", value: crm.aziende, testid: "kpi-aziende" },
        { icon: Users, label: "Anagrafiche totali", value: crm.persone, testid: "kpi-persone" },
        { icon: UserCheck, label: "Nuovi contatti", value: crm.nuovi_contatti, color: "blue", testid: "kpi-nuovi-contatti" },
        { icon: Target, label: "Prospect", value: crm.prospect, color: "orange", testid: "kpi-prospect" },
      ]} />}

      {com && <KpiGroup title="Commerciale" testid="dash-group-commerciale" items={[
        { icon: Handshake, label: "Trattative aperte", value: com.trattative_aperte, testid: "kpi-trattative" },
        { icon: TrendingUp, label: "Proposte inviate", value: com.proposte_inviate, color: "orange", testid: "kpi-proposte" },
        { icon: CheckCircle2, label: "Sponsor confermati", value: com.sponsor_confermati, color: "green", testid: "kpi-sponsor-confermati" },
        { icon: Wallet, label: "Valore pipeline", value: formatEUR(com.valore_pipeline), testid: "kpi-valore-pipeline" },
        { icon: Wallet, label: "Valore confermato", value: formatEUR(com.valore_confermato), color: "green", testid: "kpi-valore-confermato" },
      ]} />}

      {com && <div className="grid grid-cols-1 lg:grid-cols-12 gap-6" data-testid="dash-commercial-charts">
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
      </div>}

      {(att || st) && <div className={`grid grid-cols-1 ${att && st ? "lg:grid-cols-2" : ""} gap-6`}>
        {att && <KpiGroup title="Attività" testid="dash-group-attivita" maxCols={st ? 2 : 4} items={[
          { icon: Clock, label: "Follow-up di oggi", value: att.followup_oggi, color: "orange", testid: "kpi-fu-oggi" },
          { icon: AlertTriangle, label: "Follow-up scaduti", value: att.followup_scaduti, color: "red", testid: "kpi-fu-scaduti" },
          { icon: ListIcon, label: "Prossime attività", value: att.prossime, testid: "kpi-att-prossime" },
          { icon: CheckCircle2, label: "Completate", value: att.completate, color: "green", testid: "kpi-att-completate" },
        ]} />}
        {st && <KpiGroup title="Staff & Volontari" testid="dash-group-staff" maxCols={att ? 2 : 4} items={[
          { icon: UserCog, label: "Staff confermati", value: st.staff_confermati, color: "green", testid: "kpi-staff-confermati" },
          { icon: Users, label: "Volontari confermati", value: st.volontari_confermati, color: "green", testid: "kpi-volontari" },
          { icon: AlertTriangle, label: "Da riconfermare", value: st.da_riconfermare, color: "orange", testid: "kpi-da-riconfermare" },
          { icon: AlertTriangle, label: "Turni scoperti", value: st.turni_scoperti, color: "red", testid: "kpi-turni-scoperti" },
          { icon: Users, label: "Volontari richiesti (Team)", value: st.volontari_richiesti, testid: "kpi-vol-richiesti" },
          { icon: CheckCircle2, label: "Volontari assegnati", value: st.volontari_assegnati, color: "green", testid: "kpi-vol-assegnati" },
          { icon: AlertTriangle, label: st.volontari_esubero ? `Volontari mancanti (+${st.volontari_esubero} esubero)` : "Volontari mancanti", value: st.volontari_mancanti, color: st.volontari_mancanti ? "red" : "green", testid: "kpi-vol-mancanti" },
        ]} />}
      </div>}
    </div>
  );
}

function ListIcon(props) { return <ListChecksSvg {...props} />; }
function ListChecksSvg(props) {
  return <svg {...props} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 17 2 2 4-4"/><path d="m3 7 2 2 4-4"/><path d="M13 6h8"/><path d="M13 12h8"/><path d="M13 18h8"/></svg>;
}
