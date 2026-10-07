import "@/App.css";
import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useSearchParams } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import VolunteerLayout from "@/components/VolunteerLayout";
import LandingPage from "@/pages/LandingPage";
import DemoPage from "@/pages/DemoPage";
import Partecipa from "@/pages/Partecipa";import Pricing from "@/pages/Pricing";
import Register from "@/pages/Register";
import CompleteOrg from "@/pages/CompleteOrg";
import CompleteProfile from "@/pages/CompleteProfile";
import Legal from "@/pages/Legal";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import ResetPassword from "@/pages/ResetPassword";
import Activate from "@/pages/Activate";
import Profile from "@/pages/Profile";
import Account from "@/pages/Account";
import Platform from "@/pages/Platform";
import OrgDetail from "@/pages/OrgDetail";
import PricingAdmin from "@/pages/PricingAdmin";
import PlatformCredits from "@/pages/PlatformCredits";
import PlatformMessages from "@/pages/PlatformMessages";
import PlatformNews from "@/pages/PlatformNews";
import News from "@/pages/News";
import PipelineTemplates from "@/pages/PipelineTemplates";
import PipelineAttentionPage from "@/pages/PipelineAttentionPage";
import Invite from "@/pages/Invite";
import { trackPageView } from "@/lib/analytics";
import AuditLog from "@/pages/AuditLog";
import Dashboard from "@/pages/Dashboard";
import Events from "@/pages/Events";
import Companies from "@/pages/Companies";
import Persons from "@/pages/Persons";
import Hospitality from "@/pages/Hospitality";
import Briefing from "@/pages/Briefing";
import SponsorsPartners from "@/pages/SponsorsPartners";
import Activities from "@/pages/Activities";
import Followups from "@/pages/Followups";
import Leads from "@/pages/Leads";
import SettingsPage from "@/pages/Settings";
import Support from "@/pages/Support";
import Social from "@/pages/Social";
import SocialCalendar from "@/pages/SocialCalendar";
import SocialSettings from "@/pages/SocialSettings";
import MarketingBrevo from "@/pages/MarketingBrevo";
import EventPipeline from "@/pages/EventPipeline";
import LeadFinder from "@/pages/LeadFinder";
import VolunteerDashboard from "@/pages/VolunteerDashboard";
import VolunteerEvent from "@/pages/VolunteerEvent";
import { can, isOrgAdmin } from "@/lib/perms";

const isVol = (u) => u && (u.role === "staff" || u.role === "volunteer");
const isSuper = (u) => u && u.role === "superadmin";

function CalendarToast() {
  const [params, setParams] = useSearchParams();
  useEffect(() => {
    const c = params.get("calendar");
    if (c === "connected") { toast.success("Google Calendar collegato"); params.delete("calendar"); setParams(params, { replace: true }); }
    else if (c === "error") { toast.error("Errore collegamento Google Calendar"); params.delete("calendar"); setParams(params, { replace: true }); }
  }, [params, setParams]);
  return null;
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading || user === null) return <div className="min-h-screen flex items-center justify-center text-slate-400">Caricamento...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (!isSuper(user) && user.needs_org) return <Navigate to="/completa-organizzazione" replace />;
  if (!isSuper(user) && !user.needs_org && user.needs_phone) return <Navigate to="/completa-profilo" replace />;
  if (isVol(user)) return <VolunteerLayout>{children}</VolunteerLayout>;
  return <Layout>{children}</Layout>;
}

function AdminOnly({ children }) {
  const { user } = useAuth();
  // Super Admin can operate inside a selected org (scoped server-side).
  if (isVol(user)) return <Navigate to="/app" replace />;
  return children;
}

function SuperAdminOnly({ children }) {
  const { user } = useAuth();
  if (!isSuper(user)) return <Navigate to="/app" replace />;
  return children;
}

function NoAccess() {
  return (
    <div className="max-w-lg mx-auto text-center py-24" data-testid="no-access">
      <div className="font-display text-2xl font-bold text-slate-900">Accesso non consentito</div>
      <p className="text-slate-500 mt-2">Non hai i permessi per questa sezione. Chiedi all'Admin Organizzatore di abilitarla.</p>
    </div>
  );
}

// Guardia UI per sezione (il backend applica comunque i permessi).
function Perm({ s, children }) {
  const { user } = useAuth();
  if (isVol(user)) return <Navigate to="/app" replace />;
  if (s === "admin" ? !isOrgAdmin(user) : !can(user, s, "view")) return <NoAccess />;
  return children;
}

function HomeRoute() {
  const { user } = useAuth();
  return isVol(user) ? <VolunteerDashboard /> : can(user, "dashboard") ? <Dashboard /> : <NoAccess />;
}

function Shell() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <>
      <CalendarToast />
      <RouteTracker />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/demo" element={<DemoPage />} />
        <Route path="/partecipa/:code" element={<Partecipa />} />
        <Route path="/prezzi" element={<Pricing />} />
        <Route path="/registrati" element={<Register />} />
        <Route path="/completa-organizzazione" element={<CompleteOrg />} />
        <Route path="/completa-profilo" element={<CompleteProfile />} />
        <Route path="/privacy" element={<Legal type="privacy" />} />
        <Route path="/privacy-policy" element={<Navigate to="/privacy" replace />} />
        <Route path="/cookie" element={<Legal type="cookie" />} />
        <Route path="/termini" element={<Legal type="termini" />} />
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/attiva" element={<Activate />} />
        <Route path="/invito" element={<Invite />} />
        <Route path="/app" element={<Protected><HomeRoute /></Protected>} />
        <Route path="/profilo" element={<Protected><Profile /></Protected>} />
        <Route path="/account" element={<Protected><Perm s="admin"><Account /></Perm></Protected>} />
        <Route path="/permessi" element={<Navigate to="/profilo" replace />} />
        <Route path="/piattaforma" element={<Protected><SuperAdminOnly><Platform /></SuperAdminOnly></Protected>} />
        <Route path="/piattaforma/prezzi" element={<Protected><SuperAdminOnly><PricingAdmin /></SuperAdminOnly></Protected>} />
        <Route path="/piattaforma/crediti" element={<Protected><SuperAdminOnly><PlatformCredits /></SuperAdminOnly></Protected>} />
        <Route path="/piattaforma/modelli-pipeline" element={<Protected><SuperAdminOnly><PipelineTemplates /></SuperAdminOnly></Protected>} />
        <Route path="/piattaforma/messaggi" element={<Protected><SuperAdminOnly><PlatformMessages /></SuperAdminOnly></Protected>} />
        <Route path="/piattaforma/novita" element={<Protected><SuperAdminOnly><PlatformNews /></SuperAdminOnly></Protected>} />
        <Route path="/novita" element={<Protected><News /></Protected>} />
        <Route path="/piattaforma/org/:id" element={<Protected><SuperAdminOnly><OrgDetail /></SuperAdminOnly></Protected>} />
        <Route path="/audit" element={<Protected><SuperAdminOnly><AuditLog /></SuperAdminOnly></Protected>} />
        <Route path="/evento/:id" element={<Protected><VolunteerEvent /></Protected>} />
        <Route path="/eventi" element={<Protected><Perm s="eventi"><Events /></Perm></Protected>} />
        <Route path="/eventi/:id/briefing" element={<Protected><Perm s="briefing"><Briefing /></Perm></Protected>} />
        <Route path="/eventi/:id/pipeline" element={<Protected><Perm s="pipeline"><EventPipeline /></Perm></Protected>} />
        <Route path="/pipeline/attenzione" element={<Protected><Perm s="pipeline"><PipelineAttentionPage /></Perm></Protected>} />
        <Route path="/aziende" element={<Protected><Perm s="aziende"><Companies /></Perm></Protected>} />
        <Route path="/persone" element={<Protected><Perm s="anagrafiche"><Persons mode="anagrafiche" /></Perm></Protected>} />
        <Route path="/staff-volontari" element={<Protected><Perm s="staff"><Persons mode="staff" /></Perm></Protected>} />
        <Route path="/ospitalita" element={<Protected><Perm s="ospitalita"><Hospitality /></Perm></Protected>} />
        <Route path="/sponsor" element={<Protected><Perm s="sponsor"><SponsorsPartners /></Perm></Protected>} />
        <Route path="/attivita" element={<Protected><Perm s="attivita"><Activities /></Perm></Protected>} />
        <Route path="/followup" element={<Protected><Perm s="followup"><Followups /></Perm></Protected>} />
        <Route path="/lead" element={<Navigate to="/marketing/organizzatori?tab=leads" replace />} />
        <Route path="/supporto" element={<Protected><SuperAdminOnly><Support /></SuperAdminOnly></Protected>} />
        <Route path="/impostazioni" element={<Protected><Perm s="admin"><SettingsPage /></Perm></Protected>} />
        <Route path="/marketing/organizzatori" element={<Protected><AdminOnly><LeadFinder /></AdminOnly></Protected>} />
        <Route path="/marketing/social" element={<Protected><AdminOnly><Social /></AdminOnly></Protected>} />
        <Route path="/marketing/calendario" element={<Protected><AdminOnly><SocialCalendar /></AdminOnly></Protected>} />
        <Route path="/marketing/impostazioni" element={<Protected><AdminOnly><SocialSettings /></AdminOnly></Protected>} />
        <Route path="/marketing/brevo" element={<Protected><SuperAdminOnly><MarketingBrevo /></SuperAdminOnly></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

function RouteTracker() {
  const location = useLocation();
  useEffect(() => { trackPageView(location.pathname + location.search); }, [location.pathname, location.search]);
  return null;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors />
        <Shell />
      </BrowserRouter>
    </AuthProvider>
  );
}
