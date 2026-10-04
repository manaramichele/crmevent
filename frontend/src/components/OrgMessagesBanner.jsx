import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { X, Info, Sparkles, AlertTriangle, Wrench, CheckCircle2, Eye } from "lucide-react";
import { toast } from "sonner";

const TYPE = {
  informazione: { label: "Informazione", icon: Info, cls: "border-sky-200 bg-sky-50", badge: "bg-sky-100 text-sky-700", ic: "text-sky-600" },
  novita: { label: "Novità", icon: Sparkles, cls: "border-emerald-200 bg-emerald-50", badge: "bg-emerald-100 text-emerald-700", ic: "text-emerald-600" },
  importante: { label: "Importante", icon: AlertTriangle, cls: "border-amber-300 bg-amber-50", badge: "bg-amber-100 text-amber-800", ic: "text-amber-600" },
  manutenzione: { label: "Manutenzione", icon: Wrench, cls: "border-slate-300 bg-slate-50", badge: "bg-slate-200 text-slate-700", ic: "text-slate-600" },
};

export default function OrgMessagesBanner() {
  const { actingOrgId } = useAuth();
  const [msgs, setMsgs] = useState([]);
  const [preview, setPreview] = useState(false);
  const [orgName, setOrgName] = useState(null);
  const load = async () => {
    try {
      const { data } = await api.get("/my/messages");
      const list = Array.isArray(data) ? data : (data.messages || []);
      setMsgs(list);
      setPreview(!Array.isArray(data) && !!data.preview);
      setOrgName(!Array.isArray(data) ? data.org_name : null);
    } catch { /* banner silenzioso in caso di errore */ }
  };
  useEffect(() => { load(); }, [actingOrgId]);
  if (!msgs.length) return null;

  const markRead = async (m) => {
    try { await api.post(`/my/messages/${m.id}/read`); setMsgs((s) => s.map((x) => x.id === m.id ? { ...x, read: true } : x)); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const hide = async (m) => {
    try { await api.post(`/my/messages/${m.id}/hide`); setMsgs((s) => s.filter((x) => x.id !== m.id)); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const ack = async (m) => {
    try { await api.post(`/my/messages/${m.id}/ack`); setMsgs((s) => s.filter((x) => x.id !== m.id)); toast.success("Conferma di lettura registrata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div className="space-y-2" data-testid="org-messages-banner">
      {preview && (
        <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg px-3 py-1.5 w-fit" data-testid="org-messages-preview-badge">
          <Eye className="w-3.5 h-3.5" />Anteprima come {orgName || "Organizzazione"}
        </div>
      )}
      {msgs.map((m) => {
        const t = TYPE[m.tipologia] || TYPE.informazione; const Icon = t.icon;
        return (
          <div key={m.id} className={`relative rounded-xl border ${t.cls} px-4 py-3 ${!m.read ? "ring-1 ring-slate-300 shadow-sm" : ""}`} data-testid={`org-message-${m.id}`}>
            <div className="flex items-start gap-3">
              <span className={`mt-0.5 ${t.ic}`}><Icon className="w-5 h-5" /></span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-[11px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${t.badge}`}>{t.label}</span>
                  {!m.read && <span className="text-[11px] font-bold uppercase tracking-wide text-rose-600 bg-rose-100 px-1.5 py-0.5 rounded-full" data-testid={`org-message-new-${m.id}`}>Nuovo</span>}
                  <span className="text-xs text-slate-400">{m.publish_at ? new Date(m.publish_at).toLocaleDateString("it-IT") : ""}</span>
                </div>
                <h3 className="font-semibold text-slate-900 mt-1" data-testid={`org-message-title-${m.id}`}>{m.titolo}</h3>
                <p className="text-sm text-slate-700 whitespace-pre-line mt-0.5">{m.messaggio}</p>
                <div className="flex items-center gap-2 mt-2">
                  {m.require_ack ? (
                    <Button size="sm" onClick={() => ack(m)} className="bg-amber-500 hover:bg-amber-600 text-white" data-testid={`org-message-ack-${m.id}`}><CheckCircle2 className="w-4 h-4 mr-1" />Ho letto</Button>
                  ) : (
                    <>
                      {!m.read && <Button size="sm" variant="outline" onClick={() => markRead(m)} data-testid={`org-message-read-${m.id}`}>Segna come letto</Button>}
                      <Button size="sm" variant="ghost" onClick={() => hide(m)} className="text-slate-500" data-testid={`org-message-hide-${m.id}`}><X className="w-4 h-4 mr-1" />Nascondi</Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
