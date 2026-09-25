import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const hash = window.location.hash;
    const sid = new URLSearchParams(hash.replace("#", "")).get("session_id");
    (async () => {
      try {
        const { data } = await api.post("/auth/session", {}, { headers: { "X-Session-ID": sid } });
        setUser(data);
        const dest = (data && !data.needs_org) ? "/app" : (data && data.needs_org ? "/completa-organizzazione" : "/app");
        window.history.replaceState(null, "", dest);
        nav(dest, { replace: true });
      } catch {
        nav("/login", { replace: true });
      }
    })();
  }, [nav, setUser]);

  return <div className="min-h-screen flex items-center justify-center text-slate-400">Accesso in corso...</div>;
}
