import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function Activate() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { setUser } = useAuth();
  const token = params.get("token");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (pw !== pw2) return toast.error("Le password non coincidono");
    setLoading(true);
    try {
      const { data } = await api.post("/auth/activate", { token, password: pw });
      setUser(data);
      toast.success("Account attivato. Benvenuto!");
      nav("/");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-slate-200 rounded-xl p-8 shadow-sm space-y-4">
        <div className="mb-2"><img src="/logo-crmevent.png" alt="crmevent" className="h-8 w-auto" /></div>
        <h2 className="font-display text-xl font-bold text-slate-900">Attiva il tuo account</h2>
        <p className="text-sm text-slate-500">Imposta la password per accedere alla tua area personale.</p>
        <div className="space-y-1.5"><Label>Password</Label><Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} data-testid="activate-pw" required /></div>
        <div className="space-y-1.5"><Label>Conferma password</Label><Input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} data-testid="activate-pw2" required /></div>
        <Button type="submit" disabled={loading || !token} data-testid="activate-submit" className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">{loading ? "..." : "Attiva account"}</Button>
      </form>
    </div>
  );
}
