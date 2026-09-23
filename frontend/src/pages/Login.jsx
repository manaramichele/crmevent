import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { CalendarDays } from "lucide-react";
import { toast } from "sonner";

export default function Login() {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [loading, setLoading] = useState(false);

  const ch = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const url = mode === "login" ? "/auth/login" : "/auth/register";
      const payload = mode === "login" ? { email: form.email, password: form.password } : form;
      const { data } = await api.post(url, payload);
      setUser(data);
      toast.success("Accesso effettuato");
      nav("/");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-slate-900 p-12 relative overflow-hidden">
        <div className="absolute -right-24 -top-24 w-96 h-96 rounded-full bg-tiffany/20 blur-3xl" />
        <div className="absolute -left-16 bottom-0 w-80 h-80 rounded-full bg-tiffany/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-tiffany flex items-center justify-center"><CalendarDays className="w-6 h-6 text-slate-900" /></div>
          <span className="font-display font-extrabold text-white text-xl">CRM<span className="text-tiffany">Event</span></span>
        </div>
        <div className="relative">
          <h1 className="font-display text-4xl font-bold text-white leading-tight">Il CRM per organizzatori di eventi.</h1>
          <p className="text-slate-300 mt-4 max-w-md">Centralizza eventi, aziende, contatti, sponsor, staff e pipeline commerciale in un unico gestionale multi-evento.</p>
        </div>
        <div className="relative text-slate-500 text-sm">crmevent.it</div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 bg-white">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2 mb-8 justify-center">
            <div className="w-9 h-9 rounded-lg bg-tiffany flex items-center justify-center"><CalendarDays className="w-5 h-5 text-slate-900" /></div>
            <span className="font-display font-extrabold text-slate-900 text-lg">CRM<span className="text-tiffany-active">Event</span></span>
          </div>
          <h2 className="font-display text-2xl font-bold text-slate-900">{mode === "login" ? "Accedi" : "Crea account"}</h2>
          <p className="text-sm text-slate-500 mb-6">{mode === "login" ? "Entra nel tuo gestionale eventi." : "Registrati per iniziare."}</p>

          <button onClick={googleLogin} data-testid="google-login-button"
            className="w-full h-11 rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center justify-center gap-2 font-medium text-slate-700 transition-colors mb-4">
            <img src="https://www.google.com/favicon.ico" alt="" className="w-4 h-4" />Continua con Google
          </button>

          <div className="flex items-center gap-3 my-4">
            <div className="flex-1 h-px bg-slate-200" /><span className="text-xs text-slate-400">oppure</span><div className="flex-1 h-px bg-slate-200" />
          </div>

          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <div className="space-y-1.5">
                <Label htmlFor="name">Nome completo</Label>
                <Input id="name" data-testid="name-input" value={form.name} onChange={ch("name")} required placeholder="Mario Rossi" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" data-testid="email-input" value={form.email} onChange={ch("email")} required placeholder="nome@azienda.it" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" data-testid="password-input" value={form.password} onChange={ch("password")} required placeholder="••••••••" />
            </div>
            <Button type="submit" disabled={loading} data-testid="submit-auth-button"
              className="w-full h-11 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.98]">
              {loading ? "Attendere..." : mode === "login" ? "Accedi" : "Registrati"}
            </Button>
          </form>

          <p className="text-sm text-slate-500 mt-6 text-center">
            {mode === "login" ? "Non hai un account? " : "Hai già un account? "}
            <button onClick={() => setMode(mode === "login" ? "register" : "login")} data-testid="toggle-auth-mode" className="text-tiffany-active font-semibold hover:underline">
              {mode === "login" ? "Registrati" : "Accedi"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
