import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);   // null = checking, false = anon, object = user
  const [loading, setLoading] = useState(true);
  const [actingOrgId, setActingOrgId] = useState(() => localStorage.getItem("acting_org_id") || "");

  const setActingOrg = useCallback(async (id, reload = true, previousId = "") => {
    if (id) localStorage.setItem("acting_org_id", id);
    else localStorage.removeItem("acting_org_id");
    setActingOrgId(id || "");
    if (id) {
      try { await api.post("/platform/audit/org-access", { org_id: id, previous_org_id: previousId || null }); } catch {}
    }
    if (reload && id) window.location.reload();
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      const stored = localStorage.getItem("acting_org_id");
      if (stored && data.role !== "superadmin" && !data.support && !(data.organizations || []).some((o) => o.org_id === stored)) {
        localStorage.removeItem("acting_org_id");
        setActingOrgId("");
      }
      setUser(data);
    } catch {
      setUser(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    checkAuth();
  }, [checkAuth]);

  const startSupport = useCallback(async (userId, orgId) => {
    try {
      await api.post("/platform/impersonate", { user_id: userId, org_id: orgId || null });
      if (!sessionStorage.getItem("support_return")) sessionStorage.setItem("support_return", window.location.pathname + window.location.search);
      window.location.href = "/app";
      return { ok: true };
    } catch (e) {
      const d = e.response?.data?.detail;
      if (d?.code === "choose_org") return { choose: d.orgs };
      toast.error(formatApiError(d));
      return null;
    }
  }, []);

  const stopSupport = useCallback(async () => {
    try { await api.post("/platform/impersonate/stop"); } catch {}
    const back = sessionStorage.getItem("support_return") || "/piattaforma?sezione=utenti";
    sessionStorage.removeItem("support_return");
    window.location.href = back;
  }, []);

  const logout = async () => {
    if (user?.support) return stopSupport();
    try { await api.post("/auth/logout"); } catch {}
    localStorage.removeItem("acting_org_id");
    setActingOrgId("");
    setUser(false);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, checkAuth, logout, actingOrgId, setActingOrg, startSupport, stopSupport }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
