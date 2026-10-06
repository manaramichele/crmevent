import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Home, User, LogOut } from "lucide-react";
import SupportChat from "@/components/SupportChat";

export default function VolunteerLayout({ children }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const active = (p) => loc.pathname === p;

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <header className="sticky top-0 z-40 bg-white border-b border-slate-200 h-14 flex items-center justify-between px-4">
        <button onClick={() => nav("/app")} className="flex items-center gap-2">
          <img src="/logo-crmevent.png?v=4" alt="CRMEvent" className="h-11 sm:h-10 w-auto" />
        </button>
        <div className="flex items-center gap-1 text-sm">
          {user?.picture ? <img src={user.picture} alt="" className="w-8 h-8 rounded-full" /> : <span className="text-slate-600 font-medium max-w-[120px] truncate">{user?.name}</span>}
        </div>
      </header>

      <main className="flex-1 pb-20 max-w-2xl w-full mx-auto p-4">{children}</main>

      <nav className="fixed bottom-0 inset-x-0 bg-white border-t border-slate-200 h-16 flex items-center justify-around z-40">
        <button onClick={() => nav("/app")} data-testid="vol-nav-home" className={`flex flex-col items-center gap-0.5 text-xs ${active("/app") ? "text-tiffany-active" : "text-slate-500"}`}><Home className="w-5 h-5" />Eventi</button>
        <button onClick={() => nav("/profilo")} data-testid="vol-nav-profile" className={`flex flex-col items-center gap-0.5 text-xs ${active("/profilo") ? "text-tiffany-active" : "text-slate-500"}`}><User className="w-5 h-5" />Profilo</button>
        <button onClick={logout} data-testid="vol-logout" className="flex flex-col items-center gap-0.5 text-xs text-slate-500"><LogOut className="w-5 h-5" />Esci</button>
      </nav>
      <SupportChat bottomOffset />
    </div>
  );
}
