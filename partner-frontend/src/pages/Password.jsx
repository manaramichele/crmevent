import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { Button, Field, Input } from "@/components/ui";
import AuthShell from "@/components/AuthShell";

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    try { await api.post("/partner/forgot-password", { email }); setSent(true); } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };
  return (
    <AuthShell title="Recupera la password" subtitle="Ti invieremo un link per reimpostarla.">
      {sent ? <p className="rounded-xl bg-tiffany-light text-tiffany-fg p-4 text-sm" data-testid="forgot-sent">Se l'email è registrata come partner, riceverai a breve un link valido per 1 ora.</p> : (
        <form onSubmit={submit} className="space-y-4" data-testid="forgot-form">
          <Field label="Email"><Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="forgot-email" /></Field>
          <Button type="submit" className="w-full" data-testid="forgot-submit">Invia link</Button>
        </form>)}
      <p className="text-sm text-center"><Link to="/login" className="font-semibold text-tiffany-fg hover:underline">Torna all'accesso</Link></p>
    </AuthShell>
  );
}

export function ResetPassword() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    if (pw !== pw2) return toast.error("Le password non coincidono");
    try { await api.post("/partner/reset-password", { token: sp.get("token") || "", password: pw }); toast.success("Password aggiornata: ora puoi accedere"); nav("/login", { replace: true }); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };
  return (
    <AuthShell title="Nuova password" subtitle="Scegli una password di almeno 8 caratteri.">
      <form onSubmit={submit} className="space-y-4" data-testid="reset-form">
        <Field label="Nuova password"><Input type="password" minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} required data-testid="reset-password" /></Field>
        <Field label="Ripeti password"><Input type="password" minLength={8} value={pw2} onChange={(e) => setPw2(e.target.value)} required data-testid="reset-password2" /></Field>
        <Button type="submit" className="w-full" data-testid="reset-submit">Salva password</Button>
      </form>
    </AuthShell>
  );
}
