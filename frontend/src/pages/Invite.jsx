import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { personName } from "@/lib/textCase";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ShieldCheck, AlertTriangle, Eye, EyeOff } from "lucide-react";
import PhoneInput, { isValidPhoneNumber } from "react-phone-number-input";
import "react-phone-number-input/style.css";

const Card = ({ children }) => (
  <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50">
    <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl p-8 shadow-sm" data-testid="invite-page">{children}</div>
  </div>
);

const PwField = ({ value, onChange, placeholder, testid }) => {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input type={show ? "text" : "password"} placeholder={placeholder} value={value} onChange={onChange} data-testid={testid} className="pr-11" />
      <button
        type="button"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => setShow((s) => !s)}
        tabIndex={-1}
        aria-label={show ? "Nascondi password" : "Mostra password"}
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-slate-400 hover:text-slate-600"
        data-testid={`${testid}-toggle`}
      >
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  );
};

export default function Invite() {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const done = useRef(false);
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [invite, setInvite] = useState(null);
  const [me, setMe] = useState(undefined); // undefined=loading, null=anon, obj=user
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", password: "", telefono: "" });
  const [login, setLogin] = useState({ password: "" });

  useEffect(() => {
    if (done.current) return; done.current = true;
    const sid = new URLSearchParams(window.location.hash.replace("#", "")).get("session_id");
    (async () => {
      if (sid) {
        // returning from Google — exchange session then accept
        try {
          await api.post("/auth/session", {}, { headers: { "X-Session-ID": sid } });
          await api.post(`/invites/${token}/accept`);
          const { data } = await api.get("/auth/me");
          setUser(data);
          toast.success("Invito accettato");
          window.location.href = data && data.needs_phone ? "/completa-profilo" : "/app";
          return;
        } catch (e) { setError(formatApiError(e.response?.data?.detail)); }
      }
      try { const { data } = await api.get(`/invites/${token}`); setInvite(data); setForm((f) => ({ ...f, name: f.name || `${data.nome || ""} ${data.cognome || ""}`.trim(), telefono: f.telefono || data.telefono || "" })); }
      catch (e) { setError(formatApiError(e.response?.data?.detail) || "Invito non valido"); }
      try { const { data } = await api.get("/auth/me"); setMe(data); } catch { setMe(null); }
    })();
  }, [token, setUser]);

  const emailMatches = me && invite && me.email?.toLowerCase() === invite.email?.toLowerCase();

  const acceptLoggedIn = async () => {
    setBusy(true);
    try { await api.post(`/invites/${token}/accept`); const { data } = await api.get("/auth/me"); setUser(data); toast.success("Invito accettato"); window.location.href = "/app"; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const registerAndAccept = async () => {
    if (form.password.length < 8) { toast.error("La password deve avere almeno 8 caratteri"); return; }
    if (!form.telefono || !isValidPhoneNumber(form.telefono)) { toast.error("Inserisci un numero di cellulare valido."); return; }
    setBusy(true);
    try { const { data } = await api.post(`/invites/${token}/register`, form); setUser(data); toast.success("Account creato e invito accettato"); window.location.href = "/app"; }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const loginAndAccept = async () => {
    setBusy(true);
    try {
      localStorage.removeItem("acting_org_id");
      await api.post("/auth/login", { email: invite.email, password: login.password });
      await api.post(`/invites/${token}/accept`);
      const { data } = await api.get("/auth/me"); setUser(data);
      toast.success("Invito accettato"); window.location.href = "/app";
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const googleAccept = () => {
    const redirectUrl = `${window.location.origin}/invito?token=${token}`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  if (error && !invite) return <Card><div className="text-center"><AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-3" /><h1 className="text-xl font-bold text-slate-900">Invito non valido</h1><p className="text-sm text-slate-500 mt-2" data-testid="invite-error">{error}</p><Button className="mt-6" variant="outline" onClick={() => nav("/login")}>Vai al login</Button></div></Card>;
  if (!invite) return <Card><div className="text-center text-slate-400">Caricamento invito…</div></Card>;

  if (invite.status !== "pending") return <Card><div className="text-center"><AlertTriangle className="w-10 h-10 text-amber-500 mx-auto mb-3" /><h1 className="text-xl font-bold text-slate-900">Invito non disponibile</h1><p className="text-sm text-slate-500 mt-2" data-testid="invite-status">Stato invito: {invite.status}.</p><Button className="mt-6" variant="outline" onClick={() => nav("/login")}>Vai al login</Button></div></Card>;

  return (
    <Card>
      <img src="/logo-crmevent.png?v=5" alt="CRMEvent" className="h-9 w-auto mb-4" />
      <h1 className="text-2xl font-bold text-slate-900">Invito a {invite.org_name}</h1>
      <p className="text-sm text-slate-500 mt-1">Sei stato invitato con il ruolo <span className="font-semibold text-slate-700">{invite.role_label}</span> per l'indirizzo <span className="font-semibold text-slate-700">{invite.email}</span>.</p>

      {me && !emailMatches && (
        <div className="mt-5 p-3 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800" data-testid="invite-email-mismatch">
          Sei connesso come <b>{me.email}</b>, ma l'invito è per <b>{invite.email}</b>. Esci e accedi con l'indirizzo corretto per accettarlo.
        </div>
      )}

      {emailMatches && (
        <div className="mt-6"><Button onClick={acceptLoggedIn} disabled={busy} data-testid="invite-accept-btn" className="w-full h-11 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold"><ShieldCheck className="w-4 h-4 mr-1.5" />Accetta l'invito</Button></div>
      )}

      {!me && (
        <div className="mt-6 space-y-4">
          <button onClick={googleAccept} data-testid="invite-google-btn" className="w-full h-11 rounded-lg border border-slate-300 hover:bg-slate-50 flex items-center justify-center gap-2 font-medium text-slate-700">
            <img src="https://www.google.com/favicon.ico" alt="" className="w-4 h-4" />Continua con Google
          </button>
          <div className="flex items-center gap-3"><div className="flex-1 h-px bg-slate-200" /><span className="text-xs text-slate-400">oppure</span><div className="flex-1 h-px bg-slate-200" /></div>
          {invite.account_exists ? (
            <div className="space-y-3">
              <p className="text-xs text-slate-500">Hai già un account CRMEvent con questa email. Inserisci la password per accettare.</p>
              <PwField placeholder="Password" value={login.password} onChange={(e) => setLogin({ password: e.target.value })} testid="invite-login-password" />
              <Button onClick={loginAndAccept} disabled={busy} data-testid="invite-login-btn" className="w-full h-11 bg-slate-900 hover:bg-slate-800 text-white font-semibold">Accedi e accetta</Button>
            </div>
          ) : (
            <div className="space-y-3">
              <Input placeholder="Nome e cognome" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} onBlur={() => setForm((f) => ({ ...f, name: personName(f.name) }))} data-testid="invite-reg-name" />
              <PhoneInput international defaultCountry="IT" placeholder="Cellulare" value={form.telefono} onChange={(v) => setForm((f) => ({ ...f, telefono: v || "" }))} className="phone-input" data-testid="invite-reg-telefono" />
              <PwField placeholder="Crea una password (min 8)" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} testid="invite-reg-password" />
              <Button onClick={registerAndAccept} disabled={busy} data-testid="invite-reg-btn" className="w-full h-11 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">Crea account e accetta</Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
