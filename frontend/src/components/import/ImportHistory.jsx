import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Undo2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { download } from "@/components/import/shared";

const fmt = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

export function ImportHistory({ reloadKey }) {
  const [rows, setRows] = useState(null);
  const load = () => api.get("/imports/history").then(({ data }) => setRows(data)).catch(() => setRows([]));
  useEffect(() => { load(); }, [reloadKey]);
  const undo = async (j) => {
    if (!window.confirm(`Annullare l'importazione di "${j.filename}"? Verranno rimossi solo i record creati e non modificati dopo; gli aggiornamenti restano.`)) return;
    try { const { data } = await api.post(`/imports/jobs/${j.id}/undo`); toast.success(`Annullata: ${data.rimossi} record rimossi, ${data.mantenuti} mantenuti perché modificati o collegati`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  if (!rows) return <p className="text-sm text-slate-500">Caricamento…</p>;
  if (!rows.length) return <p className="text-sm text-slate-500" data-testid="import-history-empty">Nessuna importazione eseguita.</p>;
  return (
    <div className="overflow-x-auto" data-testid="import-history">
      <table className="w-full text-sm">
        <thead><tr className="text-left text-xs text-slate-500 border-b">{["Data", "Utente", "Modulo", "File", "Configurazione", "Creati", "Aggiornati", "Ignorati", "Errori", ""].map((h) => <th key={h} className="py-2 pr-3 font-medium">{h}</th>)}</tr></thead>
        <tbody>{rows.map((j) => { const r = j.result || {}; const p = r.pipeline; return (
          <tr key={j.id} className="border-b border-slate-100 align-top" data-testid={`import-history-row-${j.id}`}>
            <td className="py-2 pr-3 whitespace-nowrap">{fmt(j.ran_at)}</td><td className="py-2 pr-3">{j.ran_by}{j.superadmin && <span className="ml-1 text-[11px] text-amber-700">(Super Admin)</span>}</td>
            <td className="py-2 pr-3">{j.label}{j.module_active === false && <div className="text-[11px] text-amber-700">modulo non attivo</div>}</td>
            <td className="py-2 pr-3 max-w-[180px] truncate" title={j.filename}>{j.filename}</td><td className="py-2 pr-3">{j.config_name || "—"}</td>
            <td className="py-2 pr-3">{r.creati}</td><td className="py-2 pr-3">{r.aggiornati}</td><td className="py-2 pr-3">{r.ignorati}</td>
            <td className="py-2 pr-3">{(r.errori || []).length}{p && <div className="text-[11px] text-slate-500 whitespace-nowrap">{p.schede} schede · {p.fasi_create} fasi create · {p.collegamenti} collegamenti</div>}</td>
            <td className="py-2 whitespace-nowrap">
              {(r.errori || []).length > 0 && <Button size="sm" variant="ghost" onClick={() => download(`/imports/jobs/${j.id}/errors.csv`, `errori-${j.filename}.csv`)} data-testid={`import-errors-${j.id}`}><Download className="w-4 h-4" /></Button>}
              {j.status === "importato" ? <Button size="sm" variant="ghost" onClick={() => undo(j)} title="Annulla importazione" data-testid={`import-undo-${j.id}`}><Undo2 className="w-4 h-4" /></Button>
                : <span className="text-[11px] text-slate-500">Annullata</span>}
            </td>
          </tr>); })}</tbody>
      </table>
    </div>
  );
}
