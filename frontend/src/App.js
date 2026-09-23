import "@/App.css";
import { useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useSearchParams } from "react-router-dom";
import { Toaster, toast } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import VolunteerLayout from "@/components/VolunteerLayout";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import ResetPassword from "@/pages/ResetPassword";
import Activate from "@/pages/Activate";
import Profile from "@/pages/Profile";
import Dashboard from "@/pages/Dashboard";
import Events from "@/pages/Events";
import Companies from "@/pages/Companies";
import Persons from "@/pages/Persons";
import SponsorsPartners from "@/pages/SponsorsPartners";
import StaffVolunteers from "@/pages/StaffVolunteers";
import Activities from "@/pages/Activities";
import Followups from "@/pages/Followups";
import SettingsPage from "@/pages/Settings";
import VolunteerDashboard from "@/pages/VolunteerDashboard";
import VolunteerEvent from "@/pages/VolunteerEvent";

const isVol = (u) => u && (u.role === "staff" || u.role === "volunteer");

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
  if (isVol(user)) return <VolunteerLayout>{children}</VolunteerLayout>;
  return <Layout>{children}</Layout>;
}

function AdminOnly({ children }) {
  const { user } = useAuth();
  if (isVol(user)) return <Navigate to="/" replace />;
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
        <Route path="/login" element={<Login />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/attiva" element={<Activate />} />
        <Route path="/" element={<Protected><HomeRoute /></Protected>} />
        <Route path="/profilo" element={<Protected><Profile /></Protected>} />
        <Route path="/evento/:id" element={<Protected><VolunteerEvent /></Protected>} />
        <Route path="/eventi" element={<Protected><AdminOnly><Events /></AdminOnly></Protected>} />
        <Route path="/aziende" element={<Protected><AdminOnly><Companies /></AdminOnly></Protected>} />
        <Route path="/persone" element={<Protected><AdminOnly><Persons /></AdminOnly></Protected>} />
        <Route path="/sponsor" element={<Protected><AdminOnly><SponsorsPartners /></AdminOnly></Protected>} />
        <Route path="/staff" element={<Protected><AdminOnly><StaffVolunteers /></AdminOnly></Protected>} />
        <Route path="/attivita" element={<Protected><AdminOnly><Activities /></AdminOnly></Protected>} />
        <Route path="/followup" element={<Protected><AdminOnly><Followups /></AdminOnly></Protected>} />
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
