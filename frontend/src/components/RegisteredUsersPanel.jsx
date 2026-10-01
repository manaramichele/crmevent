import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Users, RefreshCw, CheckCircle2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

const fmt = (s) => (s ? new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

export function RegisteredUsersPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try { const { data } = await api.get("/platform/brevo/registered-users"); setData(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6" data-testid="brevo-registered-panel">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2"><Users className="w-5 h-5 text-tiffany-active" /><h2 className="font-semibold text-slate-800">CRMEvent · Utenti registrati</h2></div>
        <Button size="sm" variant="outline" onClick={load} disabled={loading} data-testid="brevo-registered-refresh"><RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? "animate-spin" : ""}`} />Aggiorna</Button>
      </div>
      <p className="text-sm text-slate-500 mb-4">Lista Brevo dedicata agli utenti che hanno completato la registrazione a CRMEvent. Separata dai Lead e dalle email di disponibilità. CRMEvent resta la fonte di verità per crediti, eventi e attivazioni.</p>
      {!data ? <p className="text-sm text-slate-400">Caricamento…</p> : !data.configured ? (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800" data-testid="brevo-registered-unconfigured"><AlertTriangle className="w-4 h-4" />BREVO_API_KEY non configurata nei Secrets.</div>
      ) : (
        <div className="space-y-3">
          <div className="grid sm:grid-cols-3 gap-3">
            <div className="rounded-lg border border-slate-200 p-3"><div className="text-xs text-slate-400 uppercase tracking-wide">List ID</div><div className="font-semibold text-slate-900" data-testid="brevo-registered-listid">{data.list_id ?? "—"}</div></div>
            <div className="rounded-lg border border-slate-200 p-3"><div className="text-xs text-slate-400 uppercase tracking-wide">Contatti</div><div className="font-semibold text-slate-900" data-testid="brevo-registered-count">{data.contacts ?? "—"}</div></div>
            <div className="rounded-lg border border-slate-200 p-3"><div className="text-xs text-slate-400 uppercase tracking-wide">Ultima sincronizzazione</div><div className="font-semibold text-slate-900 text-sm">{fmt(data.last_sync)}</div></div>
          </div>
          <div className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 className="w-4 h-4" />{data.name}</div>
          <div className="text-xs text-slate-500">Attributi sincronizzati: {(data.attributes || []).join(", ")}</div>
        </div>
      )}
    </div>
  );
}
