import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { personName, businessName } from "@/lib/textCase";
import { trackEvent } from "@/lib/analytics";
import { startGoogle, googleErrorText } from "@/lib/googleAuth";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Sparkles, ShieldCheck, Gift } from "lucide-react";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";
import { getReferral, clearReferral } from "@/lib/referral";

export default function Register() {
  const { setUser } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ nome: "", cognome: "", email: "", password: "", org_name: "", telefono: "" });
  const [accept, setAccept] = useState(false);
  const [loading, setLoading] = useState(false);
  const ch = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const fix = (k, fn) => () => setForm((f) => ({ ...f, [k]: fn(f[k]) }));
  useEffect(() => { trackEvent("sign_up_start"); const qs = new URLSearchParams(window.location.search); const t = googleErrorText(qs.get("google_error")); if (t) toast.error(t); }, []);
  useEffect(() => {
    try { const l = JSON.parse(localStorage.getItem("crmevent_lead")); if (l) setForm((f) => ({ ...f, email: l.email || f.email, nome: l.nome || f.nome, cognome: l.cognome || f.cognome })); } catch {}
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!accept) { toast.error("Devi accettare le condizioni per registrarti"); return; }
    if (form.password.length < 8) { toast.error("La password deve avere almeno 8 caratteri"); return; }
    if (!form.telefono || !isValidPhoneNumber(form.telefono)) { toast.error("Inserisci un numero di cellulare valido."); return; }
    setLoading(true);
    try {
      const { data } = await api.post("/auth/register-organization", { ...form, accept_terms: accept, ref: getReferral() });
      setUser(data);
      trackEvent("sign_up", { method: "email" });
      try { localStorage.removeItem("crmevent_lead"); clearReferral(); } catch {}
      nav("/app", { replace: true });  // unico benvenuto: WelcomeDemo nel Layout
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    startGoogle({ intent: "register", legacyRedirect: window.location.origin + "/" });
  };

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-col justify-between w-1/2 bg-black p-12 relative overflow-hidden">
        <div className="absolute -right-24 -top-24 w-96 h-96 rounded-full bg-tiffany/20 blur-3xl" />
        <Link to="/" className="relative flex items-center gap-3"><img src="/logo-crmevent-dark.png?v=5" alt="CRMEvent" className="h-20 w-auto" /></Link>
        <div className="relative">
          <h1 className="font-display text-4xl font-bold text-white leading-tight">Crea la tua organizzazione su CRMEvent.</h1>
          <div className="mt-6 space-y-3 text-slate-200">
            <div className="flex items-center gap-2"><Gift className="w-5 h-5 text-tiffany" />14 giorni di prova gratuita</div>
            <div className="flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-tiffany" />Nessuna carta di credito richiesta</div>
          </div>
        </div>
        <div className="relative text-slate-500 text-sm">crmevent.it</div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6 bg-white overflow-y-auto">
        <div className="w-full max-w-md py-8">
          <div className="lg:hidden flex items-center justify-center mb-8"><Link to="/"><img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-14 w-auto" /></Link></div>
          <h2 className="font-display text-2xl font-bold text-slate-900">Inizia gratuitamente</h2>
          <p className="text-sm text-slate-500 mb-6">Crea il tuo account organizzatore e prova CRMEvent gratuitamente per 14 giorni.</p>

          <button onClick={googleLogin} data-testid="register-google-button"
            className="w-full h-11 rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center justify-center gap-2 font-medium text-slate-700 transition-colors mb-4">
            <img src="https://www.google.com/favicon.ico" alt="" className="w-4 h-4" />Continua con Google
          </button>
          <div className="flex items-center gap-3 my-4"><div className="flex-1 h-px bg-slate-200" /><span className="text-xs text-slate-400">oppure</span><div className="flex-1 h-px bg-slate-200" /></div>

          <form onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5"><Label htmlFor="nome">Nome</Label><Input id="nome" data-testid="reg-nome" value={form.nome} onChange={ch("nome")} onBlur={fix("nome", personName)} required /></div>
              <div className="space-y-1.5"><Label htmlFor="cognome">Cognome</Label><Input id="cognome" data-testid="reg-cognome" value={form.cognome} onChange={ch("cognome")} onBlur={fix("cognome", personName)} /></div>
            </div>
            <div className="space-y-1.5"><Label htmlFor="org">Nome organizzazione</Label><Input id="org" data-testid="reg-org" value={form.org_name} onChange={ch("org_name")} onBlur={fix("org_name", businessName)} placeholder="Es. La tua agenzia eventi" required /></div>
            <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" data-testid="reg-email" value={form.email} onChange={ch("email")} required /></div>
            <div className="space-y-1.5"><Label htmlFor="tel">Cellulare <span className="text-red-500">*</span></Label><PhoneInput id="tel" international defaultCountry="IT" value={form.telefono} onChange={(v) => setForm((f) => ({ ...f, telefono: v || "" }))} className="phone-input" data-testid="reg-telefono" /></div>
            <div className="space-y-1.5"><Label htmlFor="password">Password</Label><Input id="password" type="password" data-testid="reg-password" value={form.password} onChange={ch("password")} required /><p className="text-xs text-slate-400">Almeno 8 caratteri.</p></div>

            <label className="flex items-start gap-2.5 text-sm text-slate-600 cursor-pointer">
              <Checkbox checked={accept} onCheckedChange={(v) => setAccept(!!v)} data-testid="reg-accept" className="mt-0.5" />
              <span>Ho letto e accetto i <Link to="/termini" target="_blank" className="text-tiffany-active underline">Termini e Condizioni</Link>, la <Link to="/privacy-policy" target="_blank" className="text-tiffany-active underline">Privacy Policy</Link> e la <Link to="/cookie" target="_blank" className="text-tiffany-active underline">Cookie Policy</Link>.</span>
            </label>

            <Button type="submit" disabled={loading} data-testid="reg-submit"
              className="w-full h-11 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.98]">
              {loading ? "Creazione in corso..." : "Crea account gratuito"}
            </Button>
          </form>

          <p className="text-sm text-slate-500 mt-6 text-center">Hai già un account? <Link to="/login" className="text-tiffany-active font-semibold hover:underline">Accedi</Link></p>
        </div>
      </div>
    </div>
  );
}
