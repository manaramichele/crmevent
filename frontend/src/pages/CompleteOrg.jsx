import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import SupportBanner from "@/components/SupportBanner";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";

export default function CompleteOrg() {
  const { user, setUser, loading } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ org_name: "", telefono: "" });
  const [accept, setAccept] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (loading || user === null) return <div className="min-h-screen flex items-center justify-center text-slate-400">Caricamento...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "superadmin" || !user.needs_org) return <Navigate to="/app" replace />;

  const submit = async (e) => {
    e.preventDefault();
    if (!accept) { toast.error("Devi accettare le condizioni per continuare"); return; }
    if (!form.telefono || !isValidPhoneNumber(form.telefono)) { toast.error("Inserisci un numero di cellulare valido."); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post("/auth/complete-organization", { ...form, accept_terms: accept });
      setUser(data);
      toast.success("Organizzazione creata! Prova gratuita di 14 giorni attivata.");
      nav("/app");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setSubmitting(false); }
  };

  return (
    <>
    <div className="sticky top-0 z-40"><SupportBanner /></div>
    <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl p-8">
        <Link to="/"><img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-12 w-auto mb-6" /></Link>
        <div className="inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold mb-4"><Sparkles className="w-3.5 h-3.5" />Ultimo passaggio</div>
        <h1 className="font-display text-2xl font-bold text-slate-900">Crea la tua organizzazione</h1>
        <p className="text-sm text-slate-500 mt-1 mb-6">Ciao {user.name}, dai un nome alla tua organizzazione per iniziare la prova gratuita di 14 giorni.</p>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5"><Label htmlFor="org">Nome organizzazione</Label><Input id="org" data-testid="complete-org-name" value={form.org_name} onChange={(e) => setForm((f) => ({ ...f, org_name: e.target.value }))} required /></div>
          <div className="space-y-1.5"><Label htmlFor="tel">Cellulare <span className="text-red-500">*</span></Label><PhoneInput id="tel" international defaultCountry="IT" value={form.telefono} onChange={(v) => setForm((f) => ({ ...f, telefono: v || "" }))} className="phone-input" data-testid="complete-org-tel" /></div>
          <label className="flex items-start gap-2.5 text-sm text-slate-600 cursor-pointer">
            <Checkbox checked={accept} onCheckedChange={(v) => setAccept(!!v)} data-testid="complete-org-accept" className="mt-0.5" />
            <span>Ho letto e accetto i <Link to="/termini" target="_blank" className="text-tiffany-active underline">Termini e Condizioni</Link>, la <Link to="/privacy-policy" target="_blank" className="text-tiffany-active underline">Privacy Policy</Link> e la <Link to="/cookie" target="_blank" className="text-tiffany-active underline">Cookie Policy</Link>.</span>
          </label>
          <Button type="submit" disabled={submitting} data-testid="complete-org-submit" className="w-full h-11 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">{submitting ? "Attendere..." : "Inizia la prova gratuita"}</Button>
        </form>
      </div>
    </div>
    </>
  );
}
