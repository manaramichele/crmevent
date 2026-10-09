import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button, Field, Input } from "@/components/ui";
import AuthShell from "@/components/AuthShell";
import FiscalFields from "@/components/FiscalFields";
import { Consent } from "@/pages/Register";

export default function CompleteProfile() {
  const nav = useNavigate();
  const { partner, setPartner } = useAuth();
  const [f, setF] = useState({ soggetto: "privato" });
  const [accept, setAccept] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (partner) setF((s) => ({ ...s, ...Object.fromEntries(Object.entries(partner).filter(([, v]) => v != null)), soggetto: partner.soggetto || "privato" })); }, [partner]);
  if (partner === false) return <Navigate to="/login" replace />;
  if (!partner) return null;
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const submit = async (e) => {
    e.preventDefault();
    if (!accept) return toast.error("Devi accettare il Regolamento Partner e l'informativa privacy");
    setBusy(true);
    const { nome, cognome, telefono, categoria, soggetto, ragione_sociale, codice_fiscale, partita_iva, regime_fiscale, indirizzo, sito_web, social } = f;
    try { const { data } = await api.patch("/partner/profile", { nome, cognome, telefono, categoria, soggetto, ragione_sociale, codice_fiscale, partita_iva, regime_fiscale, indirizzo, sito_web, social, accept_terms: true }); setPartner(data); nav("/dashboard", { replace: true }); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Completa il profilo" subtitle={`Accesso come ${partner.email}. Servono pochi dati per attivare il tuo account partner.`}>
      <form onSubmit={submit} className="space-y-4" data-testid="complete-profile-form">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nome"><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} required data-testid="cp-nome" /></Field>
          <Field label="Cognome"><Input value={f.cognome || ""} onChange={(e) => set("cognome", e.target.value)} required data-testid="cp-cognome" /></Field>
        </div>
        <Field label="Cellulare (con prefisso)"><Input type="tel" value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} required minLength={6} placeholder="+39 333 1234567" data-testid="cp-telefono" /></Field>
        <FiscalFields form={f} set={set} />
        <Consent checked={accept} onChange={setAccept} testid="cp-accept" />
        <Button type="submit" disabled={busy} className="w-full" data-testid="cp-submit">{busy ? "Salvataggio..." : "Continua"}</Button>
      </form>
    </AuthShell>
  );
}
