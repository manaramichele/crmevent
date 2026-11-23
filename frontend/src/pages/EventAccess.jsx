import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ShieldCheck } from "lucide-react";

export default function EventAccess() {
  const { token } = useParams();
  const nav = useNavigate();
  const { checkAuth } = useAuth();
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState("");
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get(`/public/event-access/${token}`).then(({ data }) => setInfo(data)).catch((e) => setErr(formatApiError(e.response?.data?.detail))); }, [token]);
  const send = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/public/event-access/${token}/code`); setSent(true); } catch (e) { setErr(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const verify = async () => {
    setBusy(true); setErr("");
    try { await api.post(`/public/event-access/${token}/verify`, { code }); await checkAuth(); nav("/miei-eventi", { replace: true }); }
    catch (e) { setErr(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4" data-testid="event-access-page">
        <div className="flex items-center gap-2 text-tiffany-active"><ShieldCheck className="w-5 h-5" /><span className="text-xs font-semibold uppercase tracking-wide">Accesso riservato</span></div>
        <h1 className="font-display text-2xl font-bold text-slate-900">I tuoi eventi{info?.org_name ? ` con ${info.org_name}` : ""}</h1>
        {info && <p className="text-sm text-slate-600">Ciao {info.name}. Per sicurezza inviamo un codice di verifica a <b data-testid="event-access-email">{info.email}</b>.</p>}
        {err && <p className="text-sm text-red-600" data-testid="event-access-error">{err}</p>}
        {info && !sent && <Button onClick={send} disabled={busy} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-access-send-code">Invia il codice</Button>}
        {sent && <div className="space-y-2">
          <Input inputMode="numeric" maxLength={6} placeholder="Codice a 6 cifre" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} data-testid="event-access-code" />
          <Button onClick={verify} disabled={busy || code.length !== 6} className="w-full bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="event-access-verify">Accedi</Button>
          <button type="button" onClick={send} className="text-xs text-slate-500 underline" data-testid="event-access-resend">Invia un nuovo codice</button>
        </div>}
      </div>
    </div>
  );
}
