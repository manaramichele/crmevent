import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Phone } from "lucide-react";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";

export default function CompleteProfile() {
  const { user, setUser, loading } = useAuth();
  const nav = useNavigate();
  const [telefono, setTelefono] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (loading || user === null) return <div className="min-h-screen flex items-center justify-center text-slate-400">Caricamento...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "superadmin" || user.needs_org || !user.needs_phone) return <Navigate to="/app" replace />;

  const submit = async (e) => {
    e.preventDefault();
    if (!telefono || !isValidPhoneNumber(telefono)) { toast.error("Inserisci un numero di cellulare valido."); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post("/auth/complete-profile", { telefono });
      setUser(data);
      toast.success("Profilo completato!");
      nav("/app");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl p-8">
        <img src="/logo-crmevent.png?v=2" alt="CRMEvent" className="h-12 w-auto mb-6" />
        <div className="inline-flex items-center gap-2 rounded-full bg-tiffany-light text-tiffany-fg px-3 py-1 text-xs font-semibold mb-4"><Phone className="w-3.5 h-3.5" />Ultimo passaggio</div>
        <h1 className="font-display text-2xl font-bold text-slate-900">Completa il tuo profilo</h1>
        <p className="text-sm text-slate-500 mt-1 mb-6">Ciao {user.name}, per continuare inserisci il tuo numero di cellulare.</p>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="tel">Cellulare <span className="text-red-500">*</span></Label>
            <PhoneInput id="tel" international defaultCountry="IT" value={telefono} onChange={(v) => setTelefono(v || "")} className="phone-input" numberInputProps={{ "data-testid": "complete-profile-tel-input" }} data-testid="complete-profile-tel" />
          </div>
          <Button type="submit" disabled={submitting} data-testid="complete-profile-submit" className="w-full h-11 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">{submitting ? "Attendere..." : "Completa la registrazione"}</Button>
        </form>
      </div>
    </div>
  );
}
