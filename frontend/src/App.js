import "@/App.css";
import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useSearchParams } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import VolunteerLayout from "@/components/VolunteerLayout";
import LandingPage from "@/pages/LandingPage";
import Pricing from "@/pages/Pricing";
import Register from "@/pages/Register";
import CompleteOrg from "@/pages/CompleteOrg";
import Legal from "@/pages/Legal";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import ResetPassword from "@/pages/ResetPassword";
import Activate from "@/pages/Activate";
import Profile from "@/pages/Profile";
import Account from "@/pages/Account";
import Platform from "@/pages/Platform";
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
import VolunteerDashboard from "@/pages/VolunteerDashboard";
import VolunteerEvent from "@/pages/VolunteerEvent";

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

function HomeRoute() {
  const { user } = useAuth();
  return isVol(user) ? <VolunteerDashboard /> : <Dashboard />;
}

function Shell() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <>
      <CalendarToast />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/prezzi" element={<Pricing />} />
        <Route path="/registrati" element={<Register />} />
        <Route path="/completa-organizzazione" element={<CompleteOrg />} />
        <Route path="/privacy-policy" element={<Legal type="privacy" />} />
        <Route path="/privacy" element={<Navigate to="/privacy-policy" replace />} />
        <Route path="/cookie" element={<Legal type="cookie" />} />
        <Route path="/termini" element={<Legal type="termini" />} />
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/attiva" element={<Activate />} />
        <Route path="/app" element={<Protected><HomeRoute /></Protected>} />
        <Route path="/profilo" element={<Protected><Profile /></Protected>} />
        <Route path="/account" element={<Protected><AdminOnly><Account /></AdminOnly></Protected>} />
        <Route path="/piattaforma" element={<Protected><SuperAdminOnly><Platform /></SuperAdminOnly></Protected>} />
        <Route path="/evento/:id" element={<Protected><VolunteerEvent /></Protected>} />
        <Route path="/eventi" element={<Protected><AdminOnly><Events /></AdminOnly></Protected>} />
        <Route path="/eventi/:id/briefing" element={<Protected><AdminOnly><Briefing /></AdminOnly></Protected>} />
        <Route path="/aziende" element={<Protected><AdminOnly><Companies /></AdminOnly></Protected>} />
        <Route path="/persone" element={<Protected><AdminOnly><Persons /></AdminOnly></Protected>} />
        <Route path="/ospitalita" element={<Protected><AdminOnly><Hospitality /></AdminOnly></Protected>} />
        <Route path="/sponsor" element={<Protected><AdminOnly><SponsorsPartners /></AdminOnly></Protected>} />
        <Route path="/attivita" element={<Protected><AdminOnly><Activities /></AdminOnly></Protected>} />
        <Route path="/followup" element={<Protected><AdminOnly><Followups /></AdminOnly></Protected>} />
        <Route path="/lead" element={<Protected><SuperAdminOnly><Leads /></SuperAdminOnly></Protected>} />
        <Route path="/supporto" element={<Protected><SuperAdminOnly><Support /></SuperAdminOnly></Protected>} />
        <Route path="/impostazioni" element={<Protected><AdminOnly><SettingsPage /></AdminOnly></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
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
