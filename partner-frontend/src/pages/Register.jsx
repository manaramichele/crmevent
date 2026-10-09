import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button, Field, Input } from "@/components/ui";
import AuthShell, { GoogleButton } from "@/components/AuthShell";
import FiscalFields from "@/components/FiscalFields";

export const Consent = ({ checked, onChange, testid }) => (
  <label className="flex items-start gap-2 text-sm text-slate-600"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 accent-[#0ABAB5]" data-testid={testid} />
    <span>Accetto il <a href="https://crmevent.it/termini" target="_blank" rel="noreferrer" className="underline">Regolamento Partner</a> e ho letto l'<a href="https://crmevent.it/privacy" target="_blank" rel="noreferrer" className="underline">informativa privacy</a>.</span></label>
);

export default function Register() {
  const nav = useNavigate();
  const { setPartner } = useAuth();
  const [f, setF] = useState({ nome: "", cognome: "", email: "", password: "", telefono: "", soggetto: "privato", categoria: "" });
  const [accept, setAccept] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const ch = (k) => (e) => set(k, e.target.value);
  const submit = async (e) => {
    e.preventDefault();
    if (!accept) return toast.error("Devi accettare il Regolamento Partner e l'informativa privacy");
    setBusy(true);
    try { const { data } = await api.post("/partner/register", { ...f, accept_terms: true }); setPartner(data); toast.success("Candidatura inviata"); nav("/dashboard", { replace: true }); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Diventa Partner" subtitle="Registrazione gratuita. Il team CRMEvent verificherà la candidatura.">
      <GoogleButton label="Registrati con Google" />
      <form onSubmit={submit} className="space-y-4" data-testid="register-form">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nome"><Input value={f.nome} onChange={ch("nome")} required data-testid="input-nome" /></Field>
          <Field label="Cognome"><Input value={f.cognome} onChange={ch("cognome")} required data-testid="input-cognome" /></Field>
        </div>
        <Field label="Email"><Input type="email" value={f.email} onChange={ch("email")} required autoComplete="email" data-testid="input-email" /></Field>
        <Field label="Cellulare (con prefisso, es. +39)"><Input type="tel" value={f.telefono} onChange={ch("telefono")} required minLength={6} placeholder="+39 333 1234567" data-testid="input-telefono" /></Field>
        <Field label="Password (min. 8 caratteri)"><Input type="password" minLength={8} value={f.password} onChange={ch("password")} required autoComplete="new-password" data-testid="input-password" /></Field>
        <FiscalFields form={f} set={set} />
        <p className="text-xs text-slate-500">L'IBAN ti verrà richiesto nell'area partner prima della prima liquidazione.</p>
        <Consent checked={accept} onChange={setAccept} testid="accept-terms" />
        <Button type="submit" disabled={busy} className="w-full" data-testid="register-submit">{busy ? "Invio..." : "Invia candidatura"}</Button>
      </form>
      <p className="text-sm text-slate-500 text-center">Hai già un account? <Link to="/login" className="font-semibold text-tiffany-fg hover:underline" data-testid="link-login">Accedi</Link></p>
    </AuthShell>
  );
}
