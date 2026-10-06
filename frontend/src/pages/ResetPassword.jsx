import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const token = params.get("token");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw !== pw2) return toast.error("Le password non coincidono");
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: pw });
      toast.success("Password reimpostata. Ora puoi accedere.");
      nav("/login");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-slate-200 rounded-xl p-8 shadow-sm space-y-4">
        <div className="mb-2"><img src="/logo-crmevent.png?v=4" alt="CRMEvent" className="h-8 w-auto" /></div>
        <h2 className="font-display text-xl font-bold text-slate-900">Nuova password</h2>
        <div className="space-y-1.5"><Label>Nuova password</Label><Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} data-testid="reset-pw" required /></div>
        <div className="space-y-1.5"><Label>Conferma password</Label><Input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} data-testid="reset-pw2" required /></div>
        <Button type="submit" disabled={loading || !token} data-testid="reset-submit" className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">{loading ? "..." : "Reimposta password"}</Button>
      </form>
    </div>
  );
}
