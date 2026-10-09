import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/Auth";
import Landing from "@/pages/Landing";
import Register from "@/pages/Register";
import Login from "@/pages/Login";
import CompleteProfile from "@/pages/CompleteProfile";
import Dashboard from "@/pages/Dashboard";
import { ForgotPassword, ResetPassword } from "@/pages/Password";

function Private({ children }) {
  const { partner } = useAuth();
  if (partner === null) return <div className="min-h-screen grid place-items-center text-slate-400" data-testid="auth-loading">Caricamento...</div>;
  if (!partner) return <Navigate to="/login" replace />;
  if (!partner.profile_complete) return <Navigate to="/completa-profilo" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter basename={process.env.REACT_APP_BASENAME || ""}>
      <AuthProvider>
        <Toaster richColors position="top-center" />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/registrati" element={<Register />} />
          <Route path="/login" element={<Login />} />
          <Route path="/completa-profilo" element={<CompleteProfile />} />
          <Route path="/password-dimenticata" element={<ForgotPassword />} />
          <Route path="/reimposta-password" element={<ResetPassword />} />
          <Route path="/dashboard" element={<Private><Dashboard /></Private>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
