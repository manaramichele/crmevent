import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { personName } from "@/lib/textCase";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { BadgeCheck, LogOut } from "lucide-react";
import SupportBanner from "@/components/SupportBanner";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";

const splitName = (u) => {
  if (u?.nome) return [u.nome, u.cognome || ""];
  const parts = (u?.name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length && parts[0].includes("@")) return ["", ""];
  return [parts[0] || "", parts.slice(1).join(" ")];
};

function Field({ id, label, req, children, err }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}{req && <span className="text-red-500"> *</span>}</Label>
      {children}
      {err && <p className="text-xs text-red-600" data-testid={`${id}-error`}>{err}</p>}
    </div>
  );
}

// Popup obbligatorio: completamento registrazione (Google o account senza organizzazione). Nessuna chiusura senza completare.
export default function CompleteOrg() {
  const { user, setUser, loading, logout } = useAuth();
  const nav = useNavigate();
  const [n0, c0] = splitName(user);
  const [form, setForm] = useState({ nome: n0, cognome: c0, org_name: "", telefono: "" });
  const [accept, setAccept] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [errs, setErrs] = useState({});
  const [submitting, setSubmitting] = useState(false);

  if (loading || user === null) return <div className="min-h-screen flex items-center justify-center text-slate-400">Caricamento...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "superadmin" || !user.needs_org) return <Navigate to="/app" replace />;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e?.target ? e.target.value : e || "" }));
  const submit = async (e) => {
    e.preventDefault();
    const er = {};
    if (!form.nome.trim()) er.nome = "Inserisci il nome.";
    if (!form.cognome.trim()) er.cognome = "Inserisci il cognome.";
    if (!form.org_name.trim()) er.org = "Inserisci il nome dell'organizzazione.";
    if (!form.telefono || !isValidPhoneNumber(form.telefono)) er.tel = "Inserisci un numero di cellulare valido con prefisso.";
    if (!accept) er.terms = "Devi accettare Termini e Privacy Policy per continuare.";
    setErrs(er);
    if (Object.keys(er).length) return;
    setSubmitting(true);
    try {
      const { data } = await api.post("/auth/complete-organization", {
        org_name: form.org_name.trim(), telefono: form.telefono, accept_terms: true, marketing_consent: marketing,
        nome: personName(form.nome.trim()), cognome: personName(form.cognome.trim()),
      });
      setUser(data);
      toast.success("Organizzazione creata! Prova gratuita di 14 giorni attivata.");
      nav("/app", { replace: true });
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setSubmitting(false); }
  };

  return (
    <>
      <div className="sticky top-0 z-40"><SupportBanner /></div>
      <div className="fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-sm flex items-start sm:items-center justify-center p-3 pb-40 sm:p-6 overflow-y-auto" data-testid="complete-org-overlay">
        <div role="dialog" aria-modal="true" aria-labelledby="complete-org-title" className="w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 p-5 sm:p-8 my-4 animate-in fade-in zoom-in-95 duration-200" data-testid="complete-org-dialog">
          <img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-9 w-auto mb-4" />
          <h1 id="complete-org-title" className="font-display text-2xl font-bold text-slate-900">Completa la registrazione</h1>
          <p className="text-sm text-slate-500 mt-1 mb-5">Inserisci i dati mancanti per creare la tua organizzazione e iniziare gratuitamente con CRMEvent per 14 giorni.</p>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field id="complete-org-nome" label="Nome" req err={errs.nome}><Input id="complete-org-nome" data-testid="complete-org-nome" value={form.nome} onChange={set("nome")} autoComplete="given-name" /></Field>
              <Field id="complete-org-cognome" label="Cognome" req err={errs.cognome}><Input id="complete-org-cognome" data-testid="complete-org-cognome" value={form.cognome} onChange={set("cognome")} autoComplete="family-name" /></Field>
            </div>
            <Field id="complete-org-email" label="Email">
              <div className="relative">
                <Input id="complete-org-email" data-testid="complete-org-email" value={user.email || ""} readOnly className="bg-slate-50 text-slate-600 pr-28" />
                {user.auth_provider === "google" && <span className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5" data-testid="complete-org-email-verified"><BadgeCheck className="w-3 h-3" />Verificata</span>}
              </div>
            </Field>
            <Field id="complete-org-name" label="Nome organizzazione" req err={errs.org}><Input id="complete-org-name" data-testid="complete-org-name" value={form.org_name} onChange={set("org_name")} placeholder="Es. Associazione Eventi Milano" /></Field>
            <Field id="complete-org-tel" label="Cellulare" req err={errs.tel}><PhoneInput id="complete-org-tel" international defaultCountry="IT" value={form.telefono} onChange={set("telefono")} className="phone-input" data-testid="complete-org-tel" /></Field>
            <div className="space-y-2.5 pt-1">
              <label className="flex items-start gap-2.5 text-sm text-slate-600 cursor-pointer">
                <Checkbox checked={accept} onCheckedChange={(v) => setAccept(!!v)} data-testid="complete-org-accept" className="mt-0.5" />
                <span>Ho letto e accetto i <Link to="/termini" target="_blank" className="text-tiffany-active underline">Termini e Condizioni</Link> e la <Link to="/privacy-policy" target="_blank" className="text-tiffany-active underline">Privacy Policy</Link>. <span className="text-red-500">*</span></span>
              </label>
              {errs.terms && <p className="text-xs text-red-600" data-testid="complete-org-accept-error">{errs.terms}</p>}
              <label className="flex items-start gap-2.5 text-sm text-slate-600 cursor-pointer">
                <Checkbox checked={marketing} onCheckedChange={(v) => setMarketing(!!v)} data-testid="complete-org-marketing" className="mt-0.5" />
                <span>Facoltativo: desidero ricevere novità, consigli e offerte CRMEvent via email.</span>
              </label>
            </div>
            <Button type="submit" disabled={submitting} data-testid="complete-org-submit" className="w-full h-11 bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold">{submitting ? "Creazione in corso..." : "Crea organizzazione e inizia"}</Button>
          </form>
          <button type="button" onClick={logout} className="mt-4 mx-auto flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700" data-testid="complete-org-logout"><LogOut className="w-3.5 h-3.5" />Esci e completa più tardi</button>
        </div>
      </div>
    </>
  );
}
