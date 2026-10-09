import { createContext, useCallback, useContext, useEffect, useState } from "react";
import api from "@/lib/api";

const Ctx = createContext(null);

export function AuthProvider({ children }) {
  const [partner, setPartner] = useState(null); // null = verifica, false = anonimo
  const refresh = useCallback(() => api.get("/partner/me").then(({ data }) => setPartner(data)).catch(() => setPartner(false)), []);
  useEffect(() => { refresh(); }, [refresh]);
  const logout = async () => { try { await api.post("/partner/logout"); } catch {} setPartner(false); };
  return <Ctx.Provider value={{ partner, setPartner, refresh, logout }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
