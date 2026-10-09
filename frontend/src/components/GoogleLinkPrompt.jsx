import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";

// Conferma con password per collegare Google a un account esistente (Super Admin o conflitto).
export default function GoogleLinkPrompt({ onDone }) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { const { data } = await api.post("/oauth/google/link", { password: pw }); toast.success("Account Google collegato"); onDone(data); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="rounded-xl border border-[#0ABAB5]/40 bg-[#0ABAB5]/5 p-4 mb-5 space-y-3" data-testid="google-link-prompt">
      <div className="flex items-start gap-2 text-sm text-slate-700"><ShieldCheck className="w-4 h-4 mt-0.5 text-[#0ABAB5] shrink-0" />
        <span>Per sicurezza conferma la password del tuo account CRMEvent per collegare l'accesso con Google.</span></div>
      <Input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Password CRMEvent" autoComplete="current-password" required data-testid="google-link-password" />
      <Button type="submit" disabled={busy || !pw} className="w-full bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="google-link-submit">{busy ? "Verifica..." : "Collega e accedi"}</Button>
    </form>
  );
}
