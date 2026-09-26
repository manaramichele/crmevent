import { createContext, useContext, useEffect, useState, useCallback } from "react";
import api from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);   // null = checking, false = anon, object = user
  const [loading, setLoading] = useState(true);
  const [actingOrgId, setActingOrgId] = useState(() => localStorage.getItem("acting_org_id") || "");

  const setActingOrg = useCallback((id, reload = true) => {
    if (id) localStorage.setItem("acting_org_id", id);
    else localStorage.removeItem("acting_org_id");
    setActingOrgId(id || "");
    if (reload && id) window.location.reload();
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
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

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch {}
    localStorage.removeItem("acting_org_id");
    setActingOrgId("");
    setUser(false);
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, checkAuth, logout, actingOrgId, setActingOrg }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
