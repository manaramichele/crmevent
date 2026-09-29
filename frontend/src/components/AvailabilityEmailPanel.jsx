import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MailCheck, RefreshCw, Plus, Send, ShieldCheck } from "lucide-react";

const fmtDate = (iso) => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
};

export function AvailabilityEmailPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [events, setEvents] = useState([]);
  const [eventId, setEventId] = useState("");
  const [to, setTo] = useState("");
  const [sendingKind, setSendingKind] = useState(null);
  const [result, setResult] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [t, e] = await Promise.allSettled([
        api.get("/brevo/availability-templates"),
        api.get("/brevo/availability-test-events"),
      ]);
      if (t.status === "fulfilled") setData(t.value.data);
      else toast.error(formatApiError(t.reason?.response?.data?.detail) || "Errore nel caricamento dei template Brevo");
      if (e.status === "fulfilled") {
        const evs = e.value.data.events || [];
        setEvents(evs);
        if (evs.length && !eventId) setEventId(evs[0].id);
      }
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []); // eslint-disable-line

  const createTemplates = async () => {
    setCreating(true);
    try {
      const { data: r } = await api.post("/brevo/create-availability-templates");
      const created = (r.templates || []).filter((x) => x.created).length;
      toast.success(created ? `Creati ${created} template su Brevo` : "I due template master esistono già: riuso dei Template ID esistenti");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setCreating(false); }
  };

  const sendTest = async (kind) => {
    if (!eventId) { toast.error("Seleziona un Evento di tipo Test"); return; }
    if (!to.trim()) { toast.error("Inserisci l'indirizzo destinatario"); return; }
    setSendingKind(kind); setResult(null);
    try {
      const { data: r } = await api.post("/brevo/availability-test-email", { event_id: eventId, kind, to_email: to.trim() });
      setResult({ kind, ...r });
      if (r.ok) toast.success(r.message);
      else toast.warning(r.message);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSendingKind(null); }
  };

  const enabled = data?.enabled;
  const configured = data?.configured;
  const templates = data?.templates || [];
  const list = data?.list;
  const missing = templates.some((t) => !t.template_id);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 mb-8" data-testid="availability-email-panel">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><MailCheck className="w-5 h-5" /></div>
        <div className="min-w-0">
          <div className="font-semibold text-slate-800">Email disponibilità eventi</div>
          <div className="text-xs text-slate-500 mt-0.5">
            Template master universali per la raccolta disponibilità (guidati da parametri dinamici dell'Evento). Gestione riservata al Super Admin.
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span
            className={`text-xs font-semibold px-2.5 py-1 rounded-full ${enabled ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-slate-100 text-slate-600 border border-slate-200"}`}
            data-testid="availability-auto-status"
          >
            Invii automatici: {enabled ? "ATTIVI" : "DISATTIVATI"}
          </span>
          <Button size="sm" variant="outline" onClick={load} disabled={loading} data-testid="availability-refresh-btn">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />{loading ? "Aggiorno…" : "Aggiorna stato"}
          </Button>
        </div>
      </div>

      {!configured && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800" data-testid="availability-not-configured">
          Brevo non configurato in questo ambiente. La creazione dei template e l'invio reale sono disponibili in produzione.
        </div>
      )}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm" data-testid="availability-templates-table">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 px-3 font-semibold">Nome template</th>
              <th className="py-2 px-3 font-semibold">Tipo</th>
              <th className="py-2 px-3 font-semibold">Template ID</th>
              <th className="py-2 px-3 font-semibold">Stato</th>
              <th className="py-2 px-3 font-semibold">Ultimo aggiornamento</th>
              <th className="py-2 px-3 font-semibold text-right">Test</th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.kind} className="border-b border-slate-100" data-testid={`availability-template-row-${t.kind}`}>
                <td className="py-2.5 px-3 text-slate-800 font-medium">{t.name}</td>
                <td className="py-2.5 px-3 text-slate-600">{t.type_label}</td>
                <td className="py-2.5 px-3 text-slate-600 font-mono">{t.template_id ?? "—"}</td>
                <td className="py-2.5 px-3">
                  {t.template_id == null
                    ? <span className="text-slate-400">Non creato</span>
                    : t.is_active
                      ? <span className="text-emerald-600 font-medium">Attivo</span>
                      : <span className="text-amber-600 font-medium">Bozza</span>}
                </td>
                <td className="py-2.5 px-3 text-slate-500">{fmtDate(t.updated_at)}</td>
                <td className="py-2.5 px-3 text-right">
                  <Button
                    size="sm" variant="outline"
                    onClick={() => sendTest(t.kind)}
                    disabled={sendingKind === t.kind}
                    data-testid={`availability-send-test-${t.kind}`}
                  >
                    <Send className="w-3.5 h-3.5 mr-1.5" />{sendingKind === t.kind ? "Invio…" : "Invia test"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4">
        <Button size="sm" variant="outline" onClick={createTemplates} disabled={creating || !configured || !missing} data-testid="availability-create-templates-btn">
          <Plus className="w-4 h-4 mr-1.5" />{creating ? "Creo…" : missing ? "Crea template in Brevo" : "Template già presenti"}
        </Button>
      </div>

      <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid="availability-list-info">
        <div className="text-xs font-semibold text-slate-700 mb-2">Lista Brevo unica · {list?.name || "CRMEvent · Disponibilità eventi"}</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <div className="text-slate-400">List ID</div>
            <div className="font-mono text-slate-700" data-testid="availability-list-id">{list?.id ?? "—"}</div>
          </div>
          <div>
            <div className="text-slate-400">Contatti totali (Brevo)</div>
            <div className="font-semibold text-slate-800" data-testid="availability-list-contacts">{list?.contacts ?? "—"}</div>
          </div>
          <div>
            <div className="text-slate-400">Ultima sincronizzazione</div>
            <div className="text-slate-700" data-testid="availability-list-lastsync">{fmtDate(list?.last_sync)}</div>
          </div>
          <div>
            <div className="text-slate-400">Stato sincronizzazione</div>
            <div data-testid="availability-list-syncstatus">
              {list?.last_error
                ? <span className="text-red-600 font-medium">Errore</span>
                : list?.last_sync ? <span className="text-emerald-600 font-medium">OK</span> : <span className="text-slate-400">—</span>}
            </div>
          </div>
        </div>
        {list?.last_error && (
          <div className="mt-2 text-[11px] text-red-600" data-testid="availability-list-error">
            Errore sincronizzazione: {list.last_error.error}{list.last_error.at ? ` (${fmtDate(list.last_error.at)})` : ""}
          </div>
        )}
        {!list?.id && (
          <div className="mt-2 text-[11px] text-slate-400">
            La lista verrà creata automaticamente via API al primo utilizzo (o con «Crea template in Brevo») e il List ID sarà salvato qui.
          </div>
        )}
      </div>

      <div className="mt-5 border-t border-slate-100 pt-4" data-testid="availability-test-section">
        <div className="text-sm font-semibold text-slate-800 mb-1">Invia email di test</div>
        <div className="text-xs text-slate-500 mb-3">
          Scegli un Evento di un'Organizzazione di tipo <span className="font-medium">Test</span> e un indirizzo destinatario. L'email usa i dati reali dell'Evento (logo, nome, data, località), così vedi esattamente cosa riceverà una persona. L'invio manuale non attiva gli automatismi e non dipende da <span className="font-mono">BREVO_AVAILABILITY_ENABLED</span>.
        </div>
        <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
          <div className="sm:w-80">
            <label className="text-xs text-slate-500">Evento (tipo Test)</label>
            <select
              className="w-full mt-1 border border-slate-200 rounded-md px-2 py-2 text-sm bg-white"
              value={eventId} onChange={(e) => setEventId(e.target.value)}
              data-testid="availability-test-event-select"
            >
              {events.length === 0 && <option value="">Nessun evento Test disponibile</option>}
              {events.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nome}{e.org_nome ? ` — ${e.org_nome}` : ""}{e.has_logo ? " (con logo)" : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="text-xs text-slate-500">Destinatario</label>
            <Input type="email" placeholder="destinatario@esempio.it" value={to} onChange={(e) => setTo(e.target.value)} className="mt-1" data-testid="availability-test-to-input" />
          </div>
        </div>
        <div className="text-[11px] text-slate-400 mt-2 flex items-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5" /> Il Codice Fiscale non viene mai inviato a Brevo. La chiave API non è mai esposta.
        </div>

        {result && (
          <div className={`mt-3 rounded-lg border p-3 text-xs ${result.ok ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`} data-testid="availability-test-result">
            <div className={`font-semibold ${result.ok ? "text-emerald-700" : "text-amber-700"}`}>
              {result.ok ? "Invio riuscito" : "Invio non eseguito"} · {result.kind === "conferma" ? "Partecipazione confermata" : "Disponibilità ricevuta"}
            </div>
            <div className="text-slate-600 mt-1 space-y-0.5">
              <div>{result.message}</div>
              {result.sender && <div>Mittente: <span className="font-mono">{result.sender}</span></div>}
              {result.event && <div>Evento: {result.event}{result.logo ? " · logo evento" : " · logo CRMEvent (fallback)"}</div>}
              {result.messageId && <div>messageId: <span className="font-mono">{result.messageId}</span></div>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
