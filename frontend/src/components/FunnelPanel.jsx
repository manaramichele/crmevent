import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Workflow, RefreshCw, Send, CheckCircle2, XCircle, Clock, Mail, Link2 } from "lucide-react";

const STATUS = {
  draft: { label: "Bozza", cls: "bg-slate-100 text-slate-600" },
  active: { label: "Attivo", cls: "bg-emerald-100 text-emerald-700" },
  paused: { label: "In pausa", cls: "bg-amber-100 text-amber-700" },
};

function StatCell({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-lg px-3 py-2" data-testid={`funnel-stat-${label}`}>
      <div className="text-lg font-bold text-slate-900">{value ?? 0}</div>
      <div className="text-[11px] text-slate-500 leading-tight">{label}</div>
    </div>
  );
}

export const FunnelPanel = () => {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [webhookBusy, setWebhookBusy] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [testBusy, setTestBusy] = useState(false);
  const [testResults, setTestResults] = useState(null);

  const load = useCallback(() => api.get("/platform/funnels/demo").then(({ data }) => setF(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), []);
  useEffect(() => { load(); }, [load]);

  const changeStatus = async (status) => {
    if (status === f.status) return;
    if (status === "active" && !window.confirm("Attivare il Funnel Demo? Le email partiranno sui lead reali che richiedono la demo.")) return;
    setBusy(true);
    try { const { data } = await api.post("/platform/funnels/demo/status", { status }); toast.success(`Funnel: ${STATUS[data.status].label}`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const syncTemplates = async () => {
    setSyncing(true);
    try { const { data } = await api.post("/platform/funnels/demo/sync-templates"); toast[data.ok ? "success" : "warning"](data.ok ? "Template sincronizzati su Brevo" : "Sincronizzazione parziale: controlla i dettagli"); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSyncing(false); }
  };

  const registerWebhook = async () => {
    setWebhookBusy(true);
    try { const { data } = await api.post("/platform/funnels/demo/register-webhook"); toast[data.ok ? "success" : "warning"](data.ok ? `Webhook Brevo configurato${data.webhook_id ? ` (#${data.webhook_id})` : ""}` : `Webhook non configurato${data.error ? `: ${data.error}` : ""}`); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setWebhookBusy(false); }
  };

  const sendTest = async () => {
    if (!testEmail.trim()) { toast.error("Inserisci un'email di test"); return; }
    setTestBusy(true); setTestResults(null);
    try { const { data } = await api.post("/platform/funnels/demo/test", { email: testEmail.trim() }); setTestResults(data.results); toast[data.ok ? "success" : "warning"](data.ok ? `Tutte le 4 email inviate a ${data.sent_to}` : "Alcune email non sono state inviate"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setTestBusy(false); }
  };

  if (!f) return null;
  const st = f.stats || {};
  const badge = STATUS[f.status] || STATUS.draft;

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 mb-8" data-testid="funnel-panel">
      <div className="flex items-center gap-4 flex-wrap">
        <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><Workflow className="w-5 h-5" /></div>
        <div className="min-w-0">
          <div className="font-semibold text-slate-800 flex items-center gap-2">Automazioni email · {f.name}
            <span className={`text-[11px] px-2 py-0.5 rounded-full font-medium ${badge.cls}`} data-testid="funnel-status-badge">{badge.label}</span>
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            Mittente {f.sender?.name} — {f.sender?.email}. {f.brevo_configured ? "Brevo connesso" : <span className="text-amber-600">Brevo non configurato</span>}. {f.templates_synced ? "Template sincronizzati" : <span className="text-amber-600">Template da sincronizzare</span>}.
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <select className="h-9 px-3 rounded-lg border border-slate-200 bg-white text-sm outline-none focus:border-tiffany" value={f.status} disabled={busy} onChange={(e) => changeStatus(e.target.value)} data-testid="funnel-status-select">
            <option value="draft">Bozza</option>
            <option value="paused">In pausa</option>
            <option value="active">Attivo</option>
          </select>
          <Button size="sm" variant="outline" onClick={syncTemplates} disabled={syncing || !f.brevo_configured} data-testid="funnel-sync-btn"><RefreshCw className={`w-4 h-4 mr-1.5 ${syncing ? "animate-spin" : ""}`} />{syncing ? "Sincronizzo…" : "Sincronizza template"}</Button>
          <Button size="sm" variant="outline" onClick={registerWebhook} disabled={webhookBusy || !f.brevo_configured} data-testid="funnel-webhook-btn"><Link2 className="w-4 h-4 mr-1.5" />{webhookBusy ? "Configuro…" : "Configura webhook Brevo"}</Button>
        </div>
      </div>

      <div className="grid grid-cols-3 sm:grid-cols-6 lg:grid-cols-12 gap-2 mt-4" data-testid="funnel-dashboard">
        <StatCell label="Lead entrati" value={st.lead_entrati} />
        <StatCell label="Demo richieste" value={st.demo_richieste} />
        <StatCell label="Demo avviate" value={st.demo_avviate} />
        <StatCell label="Trial avviati" value={st.trial_avviati} />
        <StatCell label="Clienti" value={st.clienti} />
        <StatCell label="Email inviate" value={st.email_inviate} />
        <StatCell label="Consegnate" value={st.email_consegnate} />
        <StatCell label="Aperture" value={st.aperture} />
        <StatCell label="Click" value={st.click} />
        <StatCell label="Bounce" value={st.bounce} />
        <StatCell label="Unsubscribe" value={st.unsubscribe} />
        <StatCell label="Spam" value={st.spam} />
      </div>

      <div className="mt-5 grid md:grid-cols-2 gap-5">
        <div>
          <div className="text-sm font-semibold text-slate-800 mb-2">Sequenza email</div>
          <div className="space-y-2">
            {f.steps.map((s) => (
              <div key={s.step} className="flex items-start gap-3 border border-slate-100 rounded-lg p-3" data-testid={`funnel-step-${s.step}`}>
                <div className="w-7 h-7 rounded-full bg-tiffany-light text-tiffany-fg flex items-center justify-center text-xs font-bold shrink-0">{s.step}</div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-slate-800">{s.subject}</div>
                  <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5"><Clock className="w-3 h-3" />{s.timing}
                    {s.synced ? <span className="text-emerald-600 inline-flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Template #{s.brevo_template_id}</span> : <span className="text-amber-600">Non sincronizzato</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-sm font-semibold text-slate-800 mb-2">Condizioni di stop</div>
          <ul className="text-xs text-slate-600 space-y-1 mb-4">
            {f.stop_conditions.map((c) => <li key={c} className="flex items-center gap-2"><XCircle className="w-3.5 h-3.5 text-slate-400" />{c}</li>)}
          </ul>

          <div className="text-sm font-semibold text-slate-800 mb-2">Invia test funnel</div>
          <div className="text-xs text-slate-500 mb-2">Invia tutte le 4 email a un indirizzo di test, subito e senza toccare i lead reali.</div>
          <div className="flex gap-2">
            <Input type="email" placeholder="tua-email@crmevent.it" value={testEmail} onChange={(e) => setTestEmail(e.target.value)} data-testid="funnel-test-email" />
            <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shrink-0" onClick={sendTest} disabled={testBusy || !f.templates_synced} data-testid="funnel-test-btn"><Send className="w-4 h-4 mr-1.5" />{testBusy ? "Invio…" : "Invia test funnel"}</Button>
          </div>
          {testResults && (
            <div className="mt-3 space-y-1.5" data-testid="funnel-test-results">
              {testResults.map((r) => (
                <div key={r.step} className={`text-xs rounded-md border p-2 ${r.ok ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
                  <span className="font-medium">Email {r.step}</span> · {r.ok ? <span className="text-emerald-700">inviata{r.messageId ? ` · ${r.messageId}` : ""}</span> : <span className="text-red-700">errore: {r.error || `HTTP ${r.status}`}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
