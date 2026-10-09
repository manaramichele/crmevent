import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button, Field, Input } from "@/components/ui";
import AuthShell, { GoogleButton } from "@/components/AuthShell";

const GERR = { unverified: "L'email Google non è verificata.", conflict: "Questa email è collegata a un altro account Google.", state: "Sessione scaduta, riprova.", denied: "Accesso con Google annullato." };

export default function Login() {
  const nav = useNavigate();
  const { partner, setPartner } = useAuth();
  const [f, setF] = useState({ email: "", password: "" });
  const [busy, setBusy] = useState(false);
  useEffect(() => { const g = new URLSearchParams(window.location.search).get("google_error"); if (g) toast.error(GERR[g] || "Accesso con Google non riuscito."); }, []);
  useEffect(() => { if (partner) nav(partner.profile_complete ? "/dashboard" : "/completa-profilo", { replace: true }); }, [partner, nav]);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post("/partner/login", f); setPartner(data); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Accedi all'area partner" subtitle="Bentornato: controlla clienti e commissioni.">
      <GoogleButton />
      <form onSubmit={submit} className="space-y-4" data-testid="login-form">
        <Field label="Email"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required autoComplete="email" data-testid="login-email" /></Field>
        <Field label="Password"><Input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required autoComplete="current-password" data-testid="login-password" /></Field>
        <Button type="submit" disabled={busy} className="w-full" data-testid="login-submit">{busy ? "Accesso..." : "Accedi"}</Button>
        <p className="text-right text-sm"><Link to="/password-dimenticata" className="text-slate-500 hover:text-ink hover:underline" data-testid="link-forgot">Password dimenticata?</Link></p>
      </form>
      <p className="text-sm text-slate-500 text-center">Non sei ancora partner? <Link to="/registrati" className="font-semibold text-tiffany-fg hover:underline" data-testid="link-register">Registrati</Link></p>
    </AuthShell>
  );
}
