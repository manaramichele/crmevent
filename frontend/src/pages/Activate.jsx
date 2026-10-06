import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

function PwField({ label, value, onChange, testid }) {
  const [show, setShow] = useState(false);
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <div className="relative">
        <Input type={show ? "text" : "password"} value={value} onChange={onChange} data-testid={testid} required className="pr-10" />
        <button type="button" onClick={() => setShow((s) => !s)} data-testid={`${testid}-toggle`}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600" aria-label={show ? "Nascondi password" : "Mostra password"}>
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
    </div>
  );
}

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
      nav("/app");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <form onSubmit={submit} className="w-full max-w-sm bg-white border border-slate-200 rounded-xl p-8 shadow-sm space-y-4">
        <div className="mb-2 flex justify-center"><img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-8 w-auto" /></div>
        <h2 className="font-display text-xl font-bold text-slate-900">Attiva il tuo account</h2>
        <p className="text-sm text-slate-500">Imposta la password per accedere alla tua area personale.</p>
        <PwField label="Password" value={pw} onChange={(e) => setPw(e.target.value)} testid="activate-pw" />
        <PwField label="Conferma password" value={pw2} onChange={(e) => setPw2(e.target.value)} testid="activate-pw2" />
        <Button type="submit" disabled={loading || !token} data-testid="activate-submit" className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">{loading ? "..." : "Attiva account"}</Button>
      </form>
    </div>
  );
}
