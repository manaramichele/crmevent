import { useState, useRef, useEffect } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import {
  LayoutDashboard, CalendarDays, Building2, Users, Handshake, UserCog,
  ListChecks, BellRing, Settings, ChevronLeft, Search, LogOut, Menu, X, CircleUserRound,
} from "lucide-react";
import { StatusBadge } from "@/components/crm";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, id: "dashboard" },
  { to: "/eventi", label: "Eventi", icon: CalendarDays, id: "eventi" },
  { to: "/aziende", label: "Aziende", icon: Building2, id: "aziende" },
  { to: "/persone", label: "Persone", icon: Users, id: "persone" },
  { to: "/sponsor", label: "Sponsor & Partner", icon: Handshake, id: "sponsor" },
  { to: "/staff", label: "Staff & Volontari", icon: UserCog, id: "staff" },
  { to: "/attivita", label: "Attività", icon: ListChecks, id: "attivita" },
  { to: "/followup", label: "Follow-up", icon: BellRing, id: "followup" },
  { to: "/impostazioni", label: "Impostazioni", icon: Settings, id: "impostazioni" },
];

function Logo({ collapsed }) {
  return collapsed ? (
    <img src="/icon-crmevent.png" alt="crmevent" className="w-9 h-9 rounded-lg mx-auto" />
  ) : (
    <img src="/logo-crmevent.png" alt="crmevent" className="h-8 w-auto" />
  );
}

function GlobalSearch() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState([]);
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const nav = useNavigate();

  useEffect(() => {
    const h = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  useEffect(() => {
    if (q.length < 2) { setRes([]); return; }
    const t = setTimeout(async () => {
      try { const { data } = await api.get("/search", { params: { q } }); setRes(data.results); setOpen(true); } catch {}
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  const routeFor = { evento: "/eventi", azienda: "/aziende", persona: "/persone" };

  return (
    <div ref={box} className="relative w-full max-w-md">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
      <input
        data-testid="global-search-input"
        value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => q.length >= 2 && setOpen(true)}
        placeholder="Ricerca globale..."
        className="w-full h-10 pl-9 pr-3 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm transition-all"
      />
      {open && res.length > 0 && (
        <div className="absolute mt-2 w-full bg-white border border-slate-200 rounded-lg shadow-lg z-50 overflow-hidden">
          {res.map((r) => (
            <button key={`${r.tipo}-${r.id}`} data-testid={`search-result-${r.id}`}
              onClick={() => { nav(routeFor[r.tipo] || "/"); setOpen(false); setQ(""); }}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-slate-50 text-left transition-colors">
              <StatusBadge color="tiffany">{r.tipo}</StatusBadge>
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-800 truncate">{r.label}</div>
                {r.sub && <div className="text-xs text-slate-400 truncate">{r.sub}</div>}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Notifications() {
  const [data, setData] = useState({ count: 0, items: [] });
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    const load = async () => { try { const { data } = await api.get("/notifications"); setData(data); } catch {} };
    load();
    const h = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div ref={box} className="relative">
      <button data-testid="notifications-button" onClick={() => setOpen((o) => !o)}
        className="relative w-10 h-10 rounded-lg hover:bg-slate-100 flex items-center justify-center transition-colors">
        <BellRing className="w-5 h-5 text-slate-600" />
        {data.count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-tiffany text-slate-900 text-[10px] font-bold flex items-center justify-center ring-2 ring-white">{data.count}</span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-white border border-slate-200 rounded-lg shadow-lg z-50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 font-semibold text-sm text-slate-800">Notifiche</div>
          <div className="max-h-80 overflow-y-auto">
            {data.items.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-slate-400">Nessuna notifica</div>
            ) : data.items.map((it) => (
              <div key={it.id} className="px-4 py-3 border-b border-slate-50 flex items-start gap-2">
                <StatusBadge color={it.tipo === "scaduto" ? "red" : "orange"}>{it.tipo === "scaduto" ? "Scaduto" : "Oggi"}</StatusBadge>
                <div className="text-sm text-slate-700">{it.titolo}<div className="text-xs text-slate-400">{it.scadenza}</div></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const sidebar = (
    <aside className={`${collapsed ? "w-20" : "w-64"} shrink-0 bg-white border-r border-slate-200 h-screen sticky top-0 hidden lg:flex flex-col transition-all duration-300`}>
      <div className="h-16 flex items-center justify-between px-4 border-b border-slate-100">
        <Logo collapsed={collapsed} />
      </div>
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} data-testid={`sidebar-link-${n.id}`}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive ? "bg-tiffany-light text-tiffany-fg" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}>
            {({ isActive }) => (<>
              <n.icon className={`w-5 h-5 shrink-0 ${isActive ? "text-tiffany-active" : ""}`} />
              {!collapsed && <span className="truncate">{n.label}</span>}
            </>)}
          </NavLink>
        ))}
      </nav>
      <button onClick={() => setCollapsed((c) => !c)} data-testid="sidebar-toggle"
        className="m-3 h-9 rounded-lg hover:bg-slate-100 flex items-center justify-center text-slate-500 transition-colors">
        <ChevronLeft className={`w-5 h-5 transition-transform ${collapsed ? "rotate-180" : ""}`} />
      </button>
    </aside>
  );

  return (
    <div className="flex min-h-screen bg-white">
      {sidebar}
      {/* mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-64 bg-white p-3 shadow-xl">
            <div className="h-12 flex items-center justify-between mb-2"><Logo /><button onClick={() => setMobileOpen(false)}><X className="w-5 h-5" /></button></div>
            <nav className="space-y-1">
              {NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.end} onClick={() => setMobileOpen(false)}
                  className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ${isActive ? "bg-tiffany-light text-tiffany-fg" : "text-slate-600 hover:bg-slate-50"}`}>
                  <n.icon className="w-5 h-5" /><span>{n.label}</span>
                </NavLink>
              ))}
            </nav>
          </aside>
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-slate-200 flex items-center gap-3 px-4 lg:px-6">
          <button className="lg:hidden w-10 h-10 flex items-center justify-center rounded-lg hover:bg-slate-100" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-button"><Menu className="w-5 h-5" /></button>
          <div className="flex-1"><GlobalSearch /></div>
          <Notifications />
          <div className="relative">
            <button data-testid="profile-button" onClick={() => setMenuOpen((o) => !o)} className="flex items-center gap-2 h-10 px-2 rounded-lg hover:bg-slate-100 transition-colors">
              {user?.picture ? <img src={user.picture} alt="" className="w-8 h-8 rounded-full object-cover" /> : <CircleUserRound className="w-8 h-8 text-slate-400" />}
              <span className="hidden sm:block text-sm font-medium text-slate-700 max-w-[120px] truncate">{user?.name}</span>
            </button>
            {menuOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-white border border-slate-200 rounded-lg shadow-lg z-50 overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-100">
                  <div className="text-sm font-semibold text-slate-800 truncate">{user?.name}</div>
                  <div className="text-xs text-slate-400 truncate">{user?.email}</div>
                </div>
                <button onClick={() => { setMenuOpen(false); navigate("/profilo"); }} data-testid="profilo-link" className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 transition-colors">
                  <CircleUserRound className="w-4 h-4" />Profilo & Account
                </button>
                <button onClick={logout} data-testid="logout-button" className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-slate-50 transition-colors border-t border-slate-100">
                  <LogOut className="w-4 h-4" />Esci
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-8 bg-slate-50/40">{children}</main>
      </div>
    </div>
  );
}
