import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/crm";
import { FolderTree, ShieldCheck, UploadCloud, Lock } from "lucide-react";

const fmt = (s) => (s ? new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

// Liste Brevo per organizzazione: affiancano le liste esistenti (mai modificate). Avvio solo dal Super Admin.
export function OrgListsPanel() {
  const [cfg, setCfg] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [orgId, setOrgId] = useState("");
  const [prev, setPrev] = useState(null);
  const [busy, setBusy] = useState(false);
  const loadCfg = () => api.get("/platform/brevo/org-lists/settings").then(({ data }) => setCfg(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => {
    loadCfg();
    api.get("/platform/organizations").then(({ data }) => setOrgs([...data].sort((a, b) => (a.nome || "").localeCompare(b.nome || "", "it", { sensitivity: "base" })))).catch(() => {});
  }, []);
  const loadPrev = (id) => { setPrev(null); if (id) api.get("/platform/brevo/org-lists/preview", { params: { org_id: id } }).then(({ data }) => setPrev(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))); };
  useEffect(() => { loadPrev(orgId); }, [orgId]);

  const toggle = async (v) => {
    try { await api.put("/platform/brevo/org-lists/settings", { enabled: v }); toast.success(v ? "Liste per organizzazione attivate" : "Liste per organizzazione disattivate"); loadCfg(); loadPrev(orgId); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const sync = async () => {
    setBusy(true);
    try { await api.post(`/platform/brevo/org-lists/sync/${orgId}`); toast.success("Sincronizzazione completata"); loadPrev(orgId); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 sm:p-6" data-testid="org-lists-panel">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h2 className="font-semibold text-slate-900 flex items-center gap-2"><FolderTree className="w-5 h-5 text-tiffany-active" />Liste per organizzazione</h2>
          <p className="text-sm text-slate-500 mt-1">Staff, Collaboratori, Utenti invitati, Volontari e Referenti Aziendali, separati per organizzazione nella cartella «{cfg?.folder || "CRMEvent · Organizzazioni"}». Nessun funnel commerciale collegato.</p>
        </div>
        <label className="flex items-center gap-2 text-sm font-medium text-slate-700 shrink-0">
          <Switch checked={!!cfg?.enabled} onCheckedChange={toggle} data-testid="org-lists-toggle" />{cfg?.enabled ? "Attive" : "Disattivate"}
        </label>
      </div>

      <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800" data-testid="org-lists-unchanged">
        <div className="flex items-center gap-1.5 font-semibold"><Lock className="w-3.5 h-3.5" />Liste esistenti invariate</div>
        <p className="mt-1">{(cfg?.unchanged_lists || []).join(" · ")}: nomi, ID, contatti, consensi, funnel e automazioni non vengono mai modificati. Chi si registra dal sito continua a seguire il percorso attuale.</p>
      </div>
      {cfg && !cfg.configured && <p className="mt-3 text-xs text-amber-700" data-testid="org-lists-no-key">Brevo non configurato in questo ambiente: puoi vedere l'anteprima ma non sincronizzare.</p>}

      <div className="mt-4 space-y-1.5">
        <label className="text-xs font-semibold text-slate-600">Organizzazione</label>
        <select className="h-11 w-full sm:w-80 px-3 rounded-lg border border-slate-200 text-sm bg-white" value={orgId} onChange={(e) => setOrgId(e.target.value)} data-testid="org-lists-org">
          <option value="">Seleziona un'organizzazione…</option>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}
        </select>
      </div>

      {orgId && !prev && <p className="mt-4 text-sm text-slate-400">Caricamento anteprima…</p>}
      {prev && (
        <div className="mt-4 space-y-2" data-testid="org-lists-preview">
          {prev.lists.map((l) => (
            <div key={l.category} className="rounded-lg border border-slate-200 p-3" data-testid={`org-list-${l.category}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-slate-900 break-all">{l.list_name}</span>
                {l.list_id ? <StatusBadge color="green">Collegata · ID {l.list_id}</StatusBadge> : l.contacts ? <StatusBadge color="orange">Da creare alla sincronizzazione</StatusBadge> : <StatusBadge color="gray">Nessun contatto: non verrà creata</StatusBadge>}
              </div>
              <div className="mt-1 text-sm text-slate-600" data-testid={`org-list-count-${l.category}`}>{l.contacts} contatti con email</div>
              {l.sample.length > 0 && <div className="mt-1 text-xs text-slate-400 break-words">{l.sample.map((s) => `${s.cognome} ${s.nome}`.trim() || s.email).join(", ")}{l.contacts > l.sample.length ? "…" : ""}</div>}
            </div>
          ))}
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 pt-2">
            <Button onClick={sync} disabled={busy || !prev.enabled || !prev.configured} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold w-full sm:w-auto" data-testid="org-lists-sync"><UploadCloud className="w-4 h-4 mr-1.5" />{busy ? "Sincronizzazione…" : "Approva e sincronizza"}</Button>
            <span className="text-xs text-slate-500 flex items-center gap-1"><ShieldCheck className="w-3.5 h-3.5" />Solo aggiunte: nessuna rimozione, nessuna riattivazione di disiscritti. Ultima: {fmt(prev.last_sync?.created_at)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
