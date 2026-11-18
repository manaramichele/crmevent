import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Pencil, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { StatusBadge } from "@/components/crm";

export const STATO = {
  valido: ["Valido", "green"], in_scadenza: ["In scadenza", "orange"], scaduto: ["Scaduto", "red"], mancante: ["Mancante", "gray"],
  senza_scadenza: ["Senza scadenza", "gray"], annullato: ["Annullato", "gray"], pagata: ["Pagata", "green"], parziale: ["Pagata in parte", "orange"],
  da_pagare: ["Da pagare", "blue"], scaduta: ["Scaduta", "red"], attivo: ["Attivo", "green"], sospeso: ["Sospeso", "orange"], cessato: ["Cessato", "gray"],
};
export const StatoBadge = ({ s, testid }) => <StatusBadge color={(STATO[s] || [])[1]} data-testid={testid}>{(STATO[s] || [s])[0]}</StatusBadge>;
export const toOpts = (o) => Object.entries(o || {}).map(([value, label]) => ({ value, label }));
export const fmtDate = (d) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString("it-IT") : "—");
export const fmtEur = (n) => `${Number(n || 0).toLocaleString("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
export const apiErr = (e) => toast.error(formatApiError(e.response?.data?.detail));
export const SEL = "h-10 rounded-md border border-slate-200 px-3 text-sm bg-white min-w-0";

export function useAsd(path, params) {
  const key = JSON.stringify(params || {});
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(() => {
    setLoading(true);
    return api.get(path, { params: JSON.parse(key) }).then(({ data }) => setRows(data)).catch(apiErr).finally(() => setLoading(false));
  }, [path, key]);
  useEffect(() => { reload(); }, [reload]);
  return { rows, loading, reload };
}

// Tabella responsive con azioni modifica/elimina (eliminazione solo Admin).
export function AsdTable({ cols, rows, loading, testid, onEdit, onDelete, canDelete, empty, extra }) {
  if (loading) return <p className="text-sm text-slate-500 py-6" data-testid={`${testid}-loading`}>Caricamento…</p>;
  if (!rows.length) return <p className="text-sm text-slate-500 py-6" data-testid={`${testid}-empty`}>{empty}</p>;
  return (
    <div className="overflow-x-auto -mx-5 px-5" data-testid={testid}>
      <table className="w-full text-sm min-w-[720px]">
        <thead><tr className="text-left text-xs text-slate-500 border-b border-slate-200">{cols.map(([k, l]) => <th key={k} className="py-2 pr-3 font-medium">{l}</th>)}<th className="py-2 w-24" /></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors" data-testid={`${testid}-row-${r.id}`}>
            {cols.map(([k, , render]) => <td key={k} className="py-2 pr-3 align-top">{render ? render(r) : (r[k] ?? "—")}</td>)}
            <td className="py-2 text-right whitespace-nowrap">
              {extra && extra(r)}
              <button type="button" onClick={() => onEdit(r)} className="p-1.5 text-slate-500 hover:text-slate-900" title="Modifica" data-testid={`${testid}-edit-${r.id}`}><Pencil className="w-4 h-4" /></button>
              {canDelete && <button type="button" onClick={() => onDelete(r)} className="p-1.5 text-slate-400 hover:text-red-600" title="Elimina" data-testid={`${testid}-delete-${r.id}`}><Trash2 className="w-4 h-4" /></button>}
            </td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

export async function saveItem(path, item, form) {
  const body = { ...form };
  ["id", "org_id", "created_at", "updated_at", "created_by", "updated_by", "socio_nome", "stato_calc", "certificato_scadenza", "certificato_stato", "quote_da_pagare", "file_name", "file_type", "file_size"].forEach((k) => delete body[k]);
  if (path !== "/asd/soci") delete body.stato;
  if (item?.id) await api.put(`${path}/${item.id}`, body); else await api.post(path, body);
  toast.success("Salvato");
}

export async function deleteItem(path, item, label, reload) {
  if (!window.confirm(`Eliminare definitivamente ${label}?`)) return;
  try { await api.delete(`${path}/${item.id}`); toast.success("Eliminato"); reload(); } catch (e) { apiErr(e); }
}

export const socioField = (soci) => ({ name: "socio_id", label: "Socio / tesserato", type: "select", required: true, keepOrder: true, full: true,
  options: soci.map((s) => ({ value: s.id, label: `${s.cognome} ${s.nome}${s.codice_fiscale ? ` · ${s.codice_fiscale}` : ""}` })) });

export function SocioFilter({ soci, value, onChange, testid }) {
  return (
    <select className={SEL} value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid}>
      <option value="">Tutti i soci</option>{soci.map((s) => <option key={s.id} value={s.id}>{s.cognome} {s.nome}</option>)}
    </select>
  );
}
