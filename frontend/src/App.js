import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import AuthCallback from "@/pages/AuthCallback";
import Dashboard from "@/pages/Dashboard";
import Events from "@/pages/Events";
import Companies from "@/pages/Companies";
import Persons from "@/pages/Persons";
import SponsorsPartners from "@/pages/SponsorsPartners";
import StaffVolunteers from "@/pages/StaffVolunteers";
import Activities from "@/pages/Activities";
import Followups from "@/pages/Followups";
import SettingsPage from "@/pages/Settings";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading || user === null) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400">Caricamento...</div>;
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Layout>{children}</Layout>;
}

function Shell() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/eventi" element={<Protected><Events /></Protected>} />
      <Route path="/aziende" element={<Protected><Companies /></Protected>} />
      <Route path="/persone" element={<Protected><Persons /></Protected>} />
      <Route path="/sponsor" element={<Protected><SponsorsPartners /></Protected>} />
      <Route path="/staff" element={<Protected><StaffVolunteers /></Protected>} />
      <Route path="/attivita" element={<Protected><Activities /></Protected>} />
      <Route path="/followup" element={<Protected><Followups /></Protected>} />
      <Route path="/impostazioni" element={<Protected><SettingsPage /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
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
