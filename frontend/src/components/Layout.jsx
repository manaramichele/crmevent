import { useState, useRef, useEffect } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";
import {
  LayoutDashboard, CalendarDays, Building2, Users, UserCog, Handshake,
  ListChecks, BellRing, Settings, ChevronLeft, Search, LogOut, Menu, X, CircleUserRound, Inbox, LifeBuoy, BedDouble, CreditCard, Sparkles, AlertTriangle, ShieldCheck, ScrollText, Megaphone, CalendarRange, SlidersHorizontal, BadgeEuro, Coins, MailCheck, LayoutTemplate, KeyRound,
} from "lucide-react";
import { can, isOrgAdmin } from "@/lib/perms";
import { StatusBadge } from "@/components/crm";
import SupportChat from "@/components/SupportChat";
import ActivationGate from "@/components/ActivationGate";
import { TutorialLauncher, TutorialHint } from "@/components/Onboarding";
import { RechargeDialog } from "@/components/CreditsSection";

const ORG_NAV = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true, id: "dashboard", perm: "dashboard" },
  { to: "/eventi", label: "Eventi", icon: CalendarDays, id: "eventi", perm: "eventi" },
  { to: "/staff-volontari", label: "Staff / Volontari", icon: UserCog, id: "staff-volontari", perm: "staff" },
  { to: "/aziende", label: "Aziende", icon: Building2, id: "aziende", perm: "aziende" },
  { to: "/persone", label: "Anagrafiche", icon: Users, id: "persone", perm: "anagrafiche" },
  { to: "/ospitalita", label: "Ospitalità & Pasti", icon: BedDouble, id: "ospitalita", perm: "ospitalita" },
  { to: "/sponsor", label: "Sponsor & Partner", icon: Handshake, id: "sponsor", perm: "sponsor" },
  { to: "/attivita", label: "Attività", icon: ListChecks, id: "attivita", perm: "attivita" },
  { to: "/followup", label: "Follow-up", icon: BellRing, id: "followup", perm: "followup" },
  { to: "/account", label: "Account e abbonamento", icon: CreditCard, id: "account", perm: "admin" },
  { to: "/impostazioni", label: "Impostazioni", icon: Settings, id: "impostazioni", perm: "admin" },
  { to: "/permessi", label: "Permessi", icon: KeyRound, id: "permessi", perm: "admin" },
];

// Super Admin operational menu = same CRMEvent menu as organizers, minus org self-billing (e Permessi: invariato).
const SUPER_ORG_NAV = ORG_NAV.filter((n) => n.id !== "account" && n.id !== "permessi");
const orgNavFor = (u) => ORG_NAV.filter((n) => (n.perm === "admin" ? isOrgAdmin(u) : can(u, n.perm, "view")));

// Extra platform-administration group, only for Super Admin.
const PLATFORM_NAV = [
  { to: "/piattaforma", label: "Dashboard piattaforma", icon: ShieldCheck, id: "piattaforma", end: true },
  { to: "/piattaforma/crediti", label: "Servizi e crediti", icon: Coins, id: "crediti" },
  { to: "/piattaforma/modelli-pipeline", label: "Modelli Pipeline", icon: LayoutTemplate, id: "modelli-pipeline" },
  { to: "/piattaforma/messaggi", label: "Messaggi", icon: BellRing, id: "messaggi" },
  { to: "/supporto", label: "Supporto", icon: LifeBuoy, id: "supporto" },
  { to: "/audit", label: "Audit Log", icon: ScrollText, id: "audit" },
];

const PLATFORM_PATHS = ["/piattaforma", "/supporto", "/audit"];

const MARKETING_NAV = [
  { to: "/marketing/organizzatori", label: "Organizzatori", icon: Building2, id: "organizzatori" },
  { to: "/marketing/brevo", label: "Email & Brevo", icon: MailCheck, id: "marketing-brevo" },
  { to: "/marketing/social", label: "Social", icon: Megaphone, id: "social" },
  { to: "/marketing/calendario", label: "Calendario editoriale", icon: CalendarRange, id: "social-calendario" },
  { to: "/marketing/impostazioni", label: "Impostazioni Social", icon: SlidersHorizontal, id: "social-impostazioni" },
];

function OrgSwitcher({ orgs, actingOrgId, onChange }) {
  return (
    <div className="flex items-center gap-2 h-10 px-3 rounded-lg border border-amber-200 bg-amber-50" data-testid="org-switcher">
      <Building2 className="w-4 h-4 text-amber-600 shrink-0" />
      <span className="hidden md:block text-xs text-amber-700 font-medium whitespace-nowrap">Org attiva</span>
      <select
        data-testid="org-switcher-select"
        value={actingOrgId || ""}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent text-sm font-semibold text-amber-900 outline-none max-w-[180px] cursor-pointer"
      >
        {orgs.length === 0 && <option value="">Nessuna organizzazione</option>}
        {orgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
      </select>
    </div>
  );
}

function TrialBanner() {
  // Modello a crediti: la piattaforma base è gratuita. Nessun banner di prova/abbonamento.
  return null;
}

function CreditGuardBanner() {
  const { user } = useAuth();
  const [bal, setBal] = useState(null);
  const [recharge, setRecharge] = useState(false);
  useEffect(() => {
    if (user?.role === "superadmin") return;
    api.get("/credits/balance").then(({ data }) => setBal(data)).catch(() => {});
  }, [user]);
  if (user?.role === "superadmin" || !bal || bal.balance > 0) return null;
  return (
    <div className="px-4 lg:px-8 py-2.5 flex items-center gap-2 text-sm bg-red-50 text-red-800 border-b border-red-200" data-testid="credits-guard-banner">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span className="font-semibold">Crediti esauriti.</span>
      <span className="hidden sm:inline">Modalità sola consultazione — i tuoi dati restano disponibili.</span>
      <button onClick={() => setRecharge(true)} className="ml-auto rounded-md bg-red-600 text-white px-3 py-1 text-xs font-semibold hover:bg-red-700" data-testid="credits-guard-recharge">Ricarica crediti</button>
      <RechargeDialog open={recharge} onClose={() => setRecharge(false)} />
    </div>
  );
}

function Logo({ collapsed }) {
  return collapsed ? (
    <img src="/icon-crmevent.png?v=5" alt="CRMEvent" className="w-10 h-10 rounded-lg mx-auto" />
  ) : (
    <img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-10 w-auto" />
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
  const { user, logout, actingOrgId, setActingOrg } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [orgs, setOrgs] = useState([]);

  const isSuper = user?.role === "superadmin";
  const multiOrg = !isSuper && (user?.organizations?.length || 0) > 1;
  const showSwitcher = isSuper || multiOrg;

  useEffect(() => {
    if (isSuper) {
      api.get("/platform/organizations").then(({ data }) => {
        setOrgs(data);
        if (!actingOrgId && data.length) setActingOrg(data[0].id, false);
      }).catch(() => {});
    } else if (multiOrg) {
      api.get("/my/organizations").then(({ data }) => {
        setOrgs(data);
        const activeId = user?.active_org_id || user?.org_id;
        if (!actingOrgId && activeId) setActingOrg(activeId, false);
      }).catch(() => {});
    }
  }, [isSuper, multiOrg]); // eslint-disable-line react-hooks/exhaustive-deps

  // Lock the underlying page (touch + normal scroll) while the mobile drawer is open,
  // iOS/Safari-safe, and restore the exact scroll position on close.
  useEffect(() => {
    if (!mobileOpen) return;
    const scrollY = window.scrollY;
    const body = document.body;
    const prev = {
      position: body.style.position, top: body.style.top, left: body.style.left,
      right: body.style.right, width: body.style.width, overflow: body.style.overflow,
    };
    body.style.position = "fixed";
    body.style.top = `-${scrollY}px`;
    body.style.left = "0";
    body.style.right = "0";
    body.style.width = "100%";
    body.style.overflow = "hidden";
    return () => {
      body.style.position = prev.position;
      body.style.top = prev.top;
      body.style.left = prev.left;
      body.style.right = prev.right;
      body.style.width = prev.width;
      body.style.overflow = prev.overflow;
      window.scrollTo(0, scrollY);
    };
  }, [mobileOpen]);

  const navGroups = isSuper
    ? [{ items: SUPER_ORG_NAV }, { title: "Amministrazione piattaforma", items: PLATFORM_NAV }, { title: "Marketing CRMEvent — Piattaforma", items: MARKETING_NAV }]
    : [{ items: orgNavFor(user) }];

  const isPlatformRoute = PLATFORM_PATHS.some((p) => location.pathname.startsWith(p));
  const gateForOrg = isSuper && !actingOrgId && !isPlatformRoute;
  const activeOrgName = orgs.find((o) => o.id === actingOrgId)?.nome || user?.org_name;

  const renderLink = (n, onClick) => (
    <NavLink key={n.to} to={n.to} end={n.end} onClick={onClick} data-testid={`sidebar-link-${n.id}`}
      className={({ isActive }) =>
        `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
          isActive ? "bg-tiffany-light text-tiffany-fg" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
        }`}>
      {({ isActive }) => (<>
        <n.icon className={`w-5 h-5 shrink-0 ${isActive ? "text-tiffany-active" : ""}`} />
        {!(collapsed && !onClick) && <span className="truncate">{n.label}</span>}
      </>)}
    </NavLink>
  );

  const sidebar = (
    <aside className={`${collapsed ? "w-20" : "w-64"} shrink-0 bg-white border-r border-slate-200 h-screen sticky top-0 hidden lg:flex flex-col transition-all duration-300`}>
      <div className="h-16 flex items-center justify-between px-4 border-b border-slate-100">
        <button onClick={() => navigate("/")} data-testid="sidebar-logo-home" title="Vai al sito CRMEvent" className="flex items-center">
          <Logo collapsed={collapsed} />
        </button>
      </div>
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navGroups.map((g, gi) => (
          <div key={gi} className={gi > 0 ? "pt-4 mt-3 border-t border-slate-100" : ""}>
            {g.title && !collapsed && (
              <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400" data-testid="nav-group-platform">{g.title}</div>
            )}
            <div className="space-y-1">{g.items.map((n) => renderLink(n))}</div>
          </div>
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
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm" onClick={() => setMobileOpen(false)} data-testid="mobile-drawer-overlay" />
          <aside className="absolute left-0 top-0 h-[100dvh] max-h-[100dvh] w-64 bg-white shadow-xl flex flex-col" data-testid="mobile-drawer">
            <div className="h-14 flex items-center justify-between px-3 shrink-0 border-b border-slate-100"><button onClick={() => { setMobileOpen(false); navigate("/"); }} data-testid="mobile-logo-home" className="flex items-center"><Logo /></button><button onClick={() => setMobileOpen(false)} data-testid="mobile-menu-close"><X className="w-6 h-6" /></button></div>
            <nav className="flex-1 min-h-0 overflow-y-auto overscroll-contain [-webkit-overflow-scrolling:touch] px-3 py-3 space-y-1 pb-[calc(env(safe-area-inset-bottom)+24px)]" data-testid="mobile-drawer-nav">
              {navGroups.map((g, gi) => (
                <div key={gi} className={gi > 0 ? "pt-3 mt-2 border-t border-slate-100" : ""}>
                  {g.title && <div className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{g.title}</div>}
                  <div className="space-y-1">{g.items.map((n) => renderLink(n, () => setMobileOpen(false)))}</div>
                </div>
              ))}
            </nav>
          </aside>
        </div>
      )}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="min-h-[4.5rem] py-2.5 pt-[max(0.625rem,env(safe-area-inset-top))] sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-slate-200 flex items-center gap-3 px-4 lg:px-6">
          <button className="lg:hidden w-10 h-10 flex items-center justify-center rounded-lg hover:bg-slate-100" onClick={() => setMobileOpen(true)} data-testid="mobile-menu-button"><Menu className="w-5 h-5" /></button>
          {showSwitcher && <OrgSwitcher orgs={orgs} actingOrgId={actingOrgId || user?.active_org_id || user?.org_id} onChange={(id) => setActingOrg(id, true, actingOrgId)} />}
          <div className="flex-1"><GlobalSearch /></div>
          {!isSuper && <TutorialLauncher />}
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
        {user?.role !== "superadmin" && <TrialBanner sub={user?.subscription} onCta={() => navigate("/account")} />}
        {user?.role !== "superadmin" && <CreditGuardBanner />}
        {isSuper && actingOrgId && !isPlatformRoute && (
          <div className="px-4 lg:px-8 py-2.5 flex items-center gap-2 text-sm bg-amber-100 text-amber-900 border-b border-amber-300" data-testid="super-acting-banner">
            <ShieldCheck className="w-4 h-4 shrink-0" />
            <span className="font-semibold">Stai operando come Super Admin in: {activeOrgName || "…"}</span>
          </div>
        )}
        {!isSuper && <TutorialHint />}
        <main className="flex-1 p-4 lg:p-8 bg-slate-50/40">
          {gateForOrg ? (
            <div className="text-center text-slate-500 py-24" data-testid="no-org-selected">
              {orgs.length === 0
                ? "Nessuna organizzazione presente sulla piattaforma."
                : "Seleziona un'organizzazione attiva dal menu in alto per continuare."}
            </div>
          ) : children}
        </main>
      </div>
      <SupportChat />
      <ActivationGate />
    </div>
  );
}
