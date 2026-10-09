import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { CaseSensitive } from "lucide-react";

const COLL = { persons: "Persone", companies: "Aziende/Sponsor", structures: "Strutture", teams: "Team", organizations: "Organizzazioni", users: "Utenti", leads: "Lead", demo_requests: "Richieste demo" };
const key = (i) => `${i.coll}|${i.id}|${i.field}`;

export default function NormalizePreview() {
  const [items, setItems] = useState(null);
  const [sel, setSel] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const analyze = async () => {
    setBusy(true);
    try { const { data } = await api.get("/platform/normalize/preview"); setItems(data.items); setSel(new Set()); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const apply = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/platform/normalize/apply", { items: items.filter((i) => sel.has(key(i))) });
      toast.success(`${data.updated} campi corretti`); await analyze();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); setBusy(false); }
  };
  const toggle = (k) => setSel((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 mb-8" data-testid="normalize-card">
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-tiffany-light text-tiffany-fg flex items-center justify-center"><CaseSensitive className="w-5 h-5" /></div>
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-slate-800">Formattazione anagrafiche esistenti</div>
          <div className="text-xs text-slate-500 mt-0.5">Anteprima delle correzioni di maiuscole proposte. Nessuna modifica senza conferma.</div>
        </div>
        <Button size="sm" variant="outline" onClick={analyze} disabled={busy} data-testid="normalize-analyze">{busy && !items ? "Analisi…" : "Analizza"}</Button>
        {items?.length > 0 && <Button size="sm" onClick={apply} disabled={busy || !sel.size} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="normalize-apply">Applica selezionate ({sel.size})</Button>}
      </div>
      {items && (items.length === 0 ? <p className="mt-4 text-sm text-slate-500" data-testid="normalize-empty">Nessuna correzione necessaria.</p> : (
        <div className="mt-4 max-h-80 overflow-auto border-t border-slate-100" data-testid="normalize-table">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="py-2 px-2"><input type="checkbox" checked={sel.size === items.length} onChange={(e) => setSel(e.target.checked ? new Set(items.map(key)) : new Set())} aria-label="Seleziona tutte" data-testid="normalize-all" /></th>
              <th className="py-2 px-2 font-semibold">Anagrafica</th><th className="py-2 px-2 font-semibold">Campo</th><th className="py-2 px-2 font-semibold">Attuale</th><th className="py-2 px-2 font-semibold">Proposta</th>
            </tr></thead>
            <tbody>{items.map((i) => (
              <tr key={key(i)} className="border-b border-slate-100">
                <td className="py-1.5 px-2"><input type="checkbox" checked={sel.has(key(i))} onChange={() => toggle(key(i))} aria-label="Seleziona" data-testid={`normalize-row-${i.coll}-${i.id}-${i.field}`} /></td>
                <td className="py-1.5 px-2 text-slate-600">{COLL[i.coll] || i.coll}</td><td className="py-1.5 px-2 text-slate-500">{i.field}</td>
                <td className="py-1.5 px-2 text-slate-500">{i.old}</td><td className="py-1.5 px-2 font-medium text-slate-900">{i.new}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
