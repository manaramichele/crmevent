import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function Login() {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState("login"); // login | forgot
  const [form, setForm] = useState({ email: "", password: "" });
  const [loading, setLoading] = useState(false);
  const ch = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "forgot") {
        await api.post("/auth/forgot-password", { email: form.email });
        toast.success("Se l'email esiste, riceverai un link per reimpostare la password.");
        setMode("login");
      } else {
        const { data } = await api.post("/auth/login", { email: form.email, password: form.password });
        setUser(data);
        nav(data.needs_org ? "/completa-organizzazione" : "/app");
      }
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-black p-12 relative overflow-hidden">
        <div className="absolute -right-24 -top-24 w-96 h-96 rounded-full bg-tiffany/20 blur-3xl" />
        <div className="absolute -left-16 bottom-0 w-80 h-80 rounded-full bg-tiffany/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <img src="/logo-crmevent-dark.png?v=2" alt="CRMEvent" className="h-20 w-auto" />
        </div>
        <div className="relative">
          <h1 className="font-display text-4xl font-bold text-white leading-tight">La piattaforma operativa per eventi, staff e volontari.</h1>
          <p className="text-slate-300 mt-4 max-w-md">Eventi, aziende, sponsor, team, turni e mappe in un unico gestionale.</p>
        </div>
        <div className="relative text-slate-500 text-sm">crmevent.it</div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 bg-white">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center justify-center mb-8">
            <img src="/logo-crmevent.png?v=2" alt="CRMEvent" className="h-16 sm:h-14 w-auto" />
          </div>
          <h2 className="font-display text-2xl font-bold text-slate-900">
            {mode === "login" ? "Accedi" : "Recupera password"}
          </h2>
          <p className="text-sm text-slate-500 mb-6">
            {mode === "forgot" ? "Inserisci la tua email per ricevere il link di reset." : "Entra nel tuo gestionale eventi."}
          </p>

          {mode !== "forgot" && (
            <>
              <button onClick={googleLogin} data-testid="google-login-button"
                className="w-full h-11 rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center justify-center gap-2 font-medium text-slate-700 transition-colors mb-4">
                <img src="https://www.google.com/favicon.ico" alt="" className="w-4 h-4" />Continua con Google
              </button>
              <div className="flex items-center gap-3 my-4"><div className="flex-1 h-px bg-slate-200" /><span className="text-xs text-slate-400">oppure</span><div className="flex-1 h-px bg-slate-200" /></div>
            </>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5"><Label htmlFor="email">Email</Label>
              <Input id="email" type="email" data-testid="email-input" value={form.email} onChange={ch("email")} required /></div>
            {mode !== "forgot" && (
              <div className="space-y-1.5">
                <div className="flex justify-between items-center"><Label htmlFor="password">Password</Label>
                  {mode === "login" && <button type="button" onClick={() => setMode("forgot")} data-testid="forgot-link" className="text-xs text-tiffany-active hover:underline">Password dimenticata?</button>}
                </div>
                <Input id="password" type="password" data-testid="password-input" value={form.password} onChange={ch("password")} required /></div>
            )}
            <Button type="submit" disabled={loading} data-testid="submit-auth-button"
              className="w-full h-11 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.98]">
              {loading ? "Attendere..." : mode === "login" ? "Accedi" : "Invia link"}
            </Button>
          </form>

          <p className="text-sm text-slate-500 mt-6 text-center">
            {mode === "forgot" ? (
              <button onClick={() => setMode("login")} className="text-tiffany-active font-semibold hover:underline">Torna al login</button>
            ) : (<>Non hai un account? <Link to="/registrati" data-testid="go-register" className="text-tiffany-active font-semibold hover:underline">Prova CRMEvent gratis</Link></>)}
          </p>
        </div>
      </div>
    </div>
  );
}
