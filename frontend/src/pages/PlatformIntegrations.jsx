import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ReceiptText, Link2, Unlink, Users, Mail, SlidersHorizontal } from "lucide-react";
import { FicVatPanel } from "@/components/saas/FicVatPanel";

function FicCard() {
  const [fic, setFic] = useState(null);
  const [params, setParams] = useSearchParams();
  const loadFic = () => api.get("/fic/status").then(({ data }) => setFic(data)).catch(() => {});
  useEffect(() => { loadFic(); }, []);
  useEffect(() => {
    const f = params.get("fic");
    if (!f) return;
    if (f === "connected") toast.success("Fatture in Cloud collegato"); else toast.error("Collegamento Fatture in Cloud non riuscito");
    params.delete("fic"); setParams(params, { replace: true }); loadFic();
  }, [params, setParams]);
  const connectFic = async () => { try { const { data } = await api.get("/fic/oauth/start"); window.location.href = data.authorize_url; } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const disconnectFic = async () => { if (!window.confirm("Scollegare Fatture in Cloud? La creazione automatica delle fatture in bozza si interrompe fino al nuovo collegamento.")) return; try { await api.post("/fic/disconnect"); toast.success("Fatture in Cloud scollegato"); loadFic(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5" data-testid="fic-card">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><ReceiptText className="w-5 h-5" /></div>
        <div className="min-w-0">
          <div className="font-semibold text-slate-800">Fatturazione elettronica · Fatture in Cloud</div>
          <div className="text-xs text-slate-500 mt-0.5" data-testid="fic-status">
            {!fic ? "…" : !fic.configured ? "Non configurato: imposta FIC_CLIENT_ID / SECRET / REDIRECT_URI nei Secrets" : fic.connected ? <>Collegato · company_id {fic.company_id || "—"}</> : "Configurato — non ancora collegato"}
          </div>
        </div>
        <div className="ml-auto">
          {fic && fic.configured && (fic.connected
            ? <Button variant="outline" size="sm" onClick={disconnectFic} data-testid="fic-disconnect"><Unlink className="w-4 h-4 mr-1.5" />Scollega</Button>
            : <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={connectFic} data-testid="fic-connect"><Link2 className="w-4 h-4 mr-1.5" />Collega Fatture in Cloud</Button>)}
        </div>
      </div>
      {fic?.connected && <FicVatPanel />}
    </div>
  );
}

function SendersTable({ senders }) {
  if (!senders.length) return <div className="text-xs text-slate-500">Nessun mittente trovato. Configura e verifica un mittente <span className="font-medium">CRMEvent</span> con casella <span className="font-medium">@crmevent.it</span> nel pannello Brevo (Mittenti, domini e IP dedicati).</div>;
  return (
    <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="brevo-senders-table">
      <thead><tr className="border-b border-slate-200 text-left text-slate-500"><th className="py-2 px-3 font-semibold">Nome</th><th className="py-2 px-3 font-semibold">Email</th><th className="py-2 px-3 font-semibold">Dominio</th><th className="py-2 px-3 font-semibold">Stato</th></tr></thead>
      <tbody>{senders.map((s) => (
        <tr key={s.id} className="border-b border-slate-100" data-testid={`brevo-sender-row-${s.id}`}>
          <td className="py-2 px-3 text-slate-800">{s.name || "—"}</td><td className="py-2 px-3 text-slate-600">{s.email}</td><td className="py-2 px-3 text-slate-600">{s.domain || "—"}</td>
          <td className="py-2 px-3">{s.active ? <span className="text-emerald-600 font-medium">Verificato</span> : <span className="text-amber-600 font-medium">Non verificato</span>}</td>
        </tr>))}</tbody>
    </table></div>
  );
}

function BrevoTest({ senders }) {
  const [testTo, setTestTo] = useState(""); const [testSender, setTestSender] = useState(senders.find((s) => s.active)?.email || "");
  const [busy, setBusy] = useState(false); const [res, setRes] = useState(null);
  const send = async () => {
    if (!testTo.trim()) { toast.error("Inserisci l'indirizzo destinatario"); return; }
    if (!testSender) { toast.error("Seleziona un mittente verificato"); return; }
    setBusy(true); setRes(null);
    try { const { data } = await api.post("/integrations/brevo/send-test", { to: testTo.trim(), sender_email: testSender }); setRes(data); toast[data.success ? "success" : "error"](data.message); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <div className="mt-5 border-t border-slate-100 pt-4" data-testid="brevo-test-section">
      <div className="text-sm font-semibold text-slate-800 mb-2">Invia email di test</div>
      <div className="text-xs text-slate-500 mb-3">Oggetto: <span className="font-medium">CRMEvent · Test collegamento Brevo</span>. Nessuna CTA commerciale, nessuna automazione.</div>
      <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <div className="sm:w-64"><label className="text-xs text-slate-500">Mittente verificato</label>
          <select className="w-full mt-1 border border-slate-200 rounded-md px-2 py-2 text-sm bg-white" value={testSender} onChange={(e) => setTestSender(e.target.value)} data-testid="brevo-test-sender-select">
            {senders.filter((s) => s.active).map((s) => <option key={s.id} value={s.email}>{s.name ? `${s.name} — ${s.email}` : s.email}</option>)}
          </select></div>
        <div className="flex-1"><label className="text-xs text-slate-500">Destinatario</label><Input type="email" placeholder="destinatario@esempio.it" value={testTo} onChange={(e) => setTestTo(e.target.value)} className="mt-1" data-testid="brevo-test-to-input" /></div>
        <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={send} disabled={busy} data-testid="brevo-send-test-btn"><Mail className="w-4 h-4 mr-1.5" />{busy ? "Invio…" : "Invia email di test"}</Button>
      </div>
      {res && (
        <div className={`mt-3 rounded-lg border p-3 text-xs ${res.success ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`} data-testid="brevo-test-result">
          <div className={`font-semibold ${res.success ? "text-emerald-700" : "text-red-700"}`}>{res.success ? "Invio riuscito" : "Invio fallito"}</div>
          <div className="text-slate-600 mt-1 space-y-0.5"><div>Esito: {res.message}</div>{res.status != null && <div>HTTP status: {res.status}</div>}{res.messageId && <div>messageId: <span className="font-mono">{res.messageId}</span></div>}<div>Timestamp: {res.timestamp}</div></div>
        </div>
      )}
    </div>
  );
}

function BrevoCard() {
  const [brevo, setBrevo] = useState(null); const [busy, setBusy] = useState(false);
  const [senders, setSenders] = useState(null); const [sBusy, setSBusy] = useState(false);
  const check = async () => { setBusy(true); try { const { data } = await api.get("/integrations/brevo/check"); setBrevo(data); toast[data.valid ? "success" : "warning"](data.message); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); } };
  const loadSenders = async () => { setSBusy(true); try { const { data } = await api.get("/integrations/brevo/senders"); setSenders(data.senders || []); if (!data.configured || data.message !== "OK") toast.warning(data.message); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setSBusy(false); } };
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5" data-testid="brevo-card">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><Mail className="w-5 h-5" /></div>
        <div className="min-w-0">
          <div className="font-semibold text-slate-800">Email marketing · Brevo</div>
          <div className="text-xs text-slate-500 mt-0.5" data-testid="brevo-status">
            {!brevo ? "Verifica la connessione API a Brevo (nessuna email viene inviata)." : brevo.valid ? <span className="text-emerald-600 font-medium">Connesso · chiave API valida (HTTP {brevo.status})</span> : <span className="text-amber-600 font-medium">{brevo.message}{brevo.status ? ` (HTTP ${brevo.status})` : ""}</span>}
          </div>
        </div>
        <div className="ml-auto flex gap-2 flex-wrap">
          <Button size="sm" variant="outline" onClick={check} disabled={busy} data-testid="brevo-check-btn"><Link2 className="w-4 h-4 mr-1.5" />{busy ? "Verifica…" : "Verifica connessione Brevo"}</Button>
          <Button size="sm" variant="outline" onClick={loadSenders} disabled={sBusy} data-testid="brevo-senders-btn"><Users className="w-4 h-4 mr-1.5" />{sBusy ? "Carico…" : "Carica mittenti"}</Button>
        </div>
      </div>
      {senders !== null && (
        <div className="mt-4 border-t border-slate-100 pt-4" data-testid="brevo-senders-section">
          <div className="text-sm font-semibold text-slate-800 mb-2">Mittenti configurati su Brevo</div>
          <SendersTable senders={senders} />
          {senders.some((s) => s.active) && <BrevoTest senders={senders} />}
        </div>
      )}
    </div>
  );
}

export default function PlatformIntegrations() {
  return (
    <div className="max-w-6xl space-y-6 animate-fade-up" data-testid="platform-integrations-page">
      <div>
        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-slate-900 bg-tiffany rounded-full px-2.5 py-1 mb-1">Marketing &amp; Admin</span>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><SlidersHorizontal className="w-6 h-6 text-tiffany-active" />Admin · Integrazioni</h1>
        <p className="text-slate-500 text-sm mt-1">Fatturazione elettronica e collegamenti amministrativi di CRMEvent. Credenziali e collegamenti esistenti restano invariati.</p>
      </div>
      <FicCard />
      <BrevoCard />
    </div>
  );
}
