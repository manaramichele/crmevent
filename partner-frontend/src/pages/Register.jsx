import { useState } from "react";
import { Link } from "react-router-dom";
import { MailCheck } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button, Field, Input, Select } from "@/components/ui";
import AuthShell from "@/components/AuthShell";

const TIPOLOGIE = [["persona_fisica", "Persona fisica"], ["professionista", "Professionista"], ["azienda", "Azienda"], ["influencer", "Influencer"]];
const PHONE_RX = /^\+?[0-9][0-9\s\-./()]{6,20}$/;

export const Consent = ({ checked, onChange, testid }) => (
  <label className="flex items-start gap-2 text-sm text-slate-600"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 accent-[#0ABAB5]" data-testid={testid} />
    <span>Accetto il <a href="https://crmevent.it/termini" target="_blank" rel="noreferrer" className="underline">Regolamento Partner</a> e ho letto l'<a href="https://crmevent.it/privacy" target="_blank" rel="noreferrer" className="underline">informativa privacy</a>.</span></label>
);

const Check = ({ checked, onChange, testid, children }) => (
  <label className="flex items-start gap-2 text-sm text-slate-600"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-1 shrink-0 accent-[#0ABAB5]" data-testid={testid} /><span className="min-w-0">{children}</span></label>
);

function validate(f) {
  const e = {};
  if (!f.nome.trim()) e.nome = "Obbligatorio";
  if (!f.cognome.trim()) e.cognome = "Obbligatorio";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) e.email = "Email non valida";
  if (!PHONE_RX.test(f.telefono.trim())) e.telefono = "Cellulare non valido (es. +39 333 1234567)";
  if (!f.tipologia) e.tipologia = "Seleziona la tipologia";
  if (f.tipologia === "azienda" && !f.ragione_sociale.trim()) e.ragione_sociale = "Obbligatoria per le aziende";
  if (f.password.length < 8) e.password = "Almeno 8 caratteri";
  if (f.password_confirm !== f.password) e.password_confirm = "Le password non coincidono";
  if (!f.accept_terms) e.accept_terms = "Obbligatorio";
  if (!f.accept_privacy) e.accept_privacy = "Obbligatorio";
  return e;
}

function Done({ email }) {
  return (
    <div className="rounded-3xl border border-tiffany/40 bg-tiffany-light p-6 space-y-3" data-testid="register-success">
      <MailCheck className="w-8 h-8 text-tiffany-fg" />
      <h2 className="text-xl font-extrabold">Candidatura inviata</h2>
      <p className="text-sm text-slate-700 break-words">Abbiamo inviato una conferma a <b>{email}</b>. Il tuo account è <b>in attesa di approvazione</b>: riceverai un'email con le istruzioni di accesso appena il team CRMEvent avrà verificato la richiesta.</p>
      <Link to="/" className="inline-block text-sm font-semibold text-tiffany-fg hover:underline" data-testid="register-success-home">Torna alla home</Link>
    </div>
  );
}

export default function Register() {
  const [f, setF] = useState({ nome: "", cognome: "", email: "", telefono: "", tipologia: "", ragione_sociale: "", password: "", password_confirm: "", accept_terms: false, accept_privacy: false });
  const [errs, setErrs] = useState({});
  const [apiErr, setApiErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const ch = (k) => (e) => set(k, e.target.value);
  const submit = async (e) => {
    e.preventDefault();
    const v = validate(f);
    setErrs(v); setApiErr("");
    if (Object.keys(v).length) return;
    setBusy(true);
    try { const { data } = await api.post("/partner/register", { ...f, email: f.email.trim(), ragione_sociale: f.ragione_sociale.trim() || null }); setDone(data.email); window.scrollTo({ top: 0, behavior: "smooth" }); }
    catch (err) { setApiErr(err.response ? formatApiError(err.response.data?.detail) : "Impossibile contattare il server. Controlla la connessione e riprova."); }
    finally { setBusy(false); }
  };
  if (done) return <AuthShell title="Grazie!" subtitle="La tua richiesta è stata registrata."><Done email={done} /></AuthShell>;
  const rsRequired = f.tipologia === "azienda";
  return (
    <AuthShell title="Diventa Partner" subtitle="Registrazione gratuita. Il team CRMEvent verificherà la candidatura.">
      <form onSubmit={submit} noValidate className="space-y-4" data-testid="register-form">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Nome" error={errs.nome}><Input value={f.nome} onChange={ch("nome")} autoComplete="given-name" data-testid="input-nome" /></Field>
          <Field label="Cognome" error={errs.cognome}><Input value={f.cognome} onChange={ch("cognome")} autoComplete="family-name" data-testid="input-cognome" /></Field>
        </div>
        <Field label="Email" error={errs.email}><Input type="email" value={f.email} onChange={ch("email")} autoComplete="email" data-testid="input-email" /></Field>
        <Field label="Cellulare (con prefisso internazionale)" error={errs.telefono}><Input type="tel" value={f.telefono} onChange={ch("telefono")} placeholder="+39 333 1234567" autoComplete="tel" data-testid="input-telefono" /></Field>
        <Field label="Tipologia partner" error={errs.tipologia}>
          <Select value={f.tipologia} onChange={ch("tipologia")} data-testid="select-tipologia"><option value="">Seleziona</option>{TIPOLOGIE.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
        </Field>
        {f.tipologia && f.tipologia !== "persona_fisica" && <Field label={rsRequired ? "Ragione sociale" : "Ragione sociale (se presente)"} error={errs.ragione_sociale}><Input value={f.ragione_sociale} onChange={ch("ragione_sociale")} autoComplete="organization" data-testid="input-ragione-sociale" /></Field>}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Field label="Password (min. 8 caratteri)" error={errs.password}><Input type="password" value={f.password} onChange={ch("password")} autoComplete="new-password" data-testid="input-password" /></Field>
          <Field label="Conferma password" error={errs.password_confirm}><Input type="password" value={f.password_confirm} onChange={ch("password_confirm")} autoComplete="new-password" data-testid="input-password-confirm" /></Field>
        </div>
        <div className="space-y-2">
          <Check checked={f.accept_terms} onChange={(v) => set("accept_terms", v)} testid="accept-terms">Accetto le <a href="https://crmevent.it/termini" target="_blank" rel="noreferrer" className="underline">condizioni del programma Partner</a>.{errs.accept_terms && <span className="block text-xs text-red-600">Obbligatorio</span>}</Check>
          <Check checked={f.accept_privacy} onChange={(v) => set("accept_privacy", v)} testid="accept-privacy">Ho letto e accetto la <a href="https://crmevent.it/privacy" target="_blank" rel="noreferrer" className="underline">Privacy Policy</a>.{errs.accept_privacy && <span className="block text-xs text-red-600">Obbligatorio</span>}</Check>
        </div>
        {apiErr && <p className="rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700 break-words" role="alert" data-testid="register-error">{apiErr}</p>}
        <Button type="submit" disabled={busy} className="w-full" data-testid="register-submit">{busy ? "Invio..." : "Invia candidatura"}</Button>
      </form>
      <p className="text-sm text-slate-500 text-center">Hai già un account? <Link to="/login" className="font-semibold text-tiffany-fg hover:underline" data-testid="link-login">Accedi</Link></p>
    </AuthShell>
  );
}
