import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));

// Diagnostica (sola lettura) e impostazione verificata dell'aliquota "Contribuenti forfettari"
export function FicVatPanel() {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [vid, setVid] = useState("");
  const run = async () => { setBusy(true); try { const { data } = await api.get("/fic/vat-diagnostics"); setD(data); } catch (e) { err(e); } setBusy(false); };
  const save = async (id) => {
    try { const { data } = await api.put("/fic/vat-forfettario", { vat_id: Number(id) }); toast.success(`Aliquota impostata: ${data.vat.description} (ID ${data.vat.id})`); run(); } catch (e) { err(e); }
  };
  const zero = (d?.rows || []).filter((r) => Math.abs(Number(r.value || 0)) < 0.01);
  return (
    <div className="mt-4 border-t border-slate-100 pt-4 text-xs text-slate-600 space-y-2" data-testid="fic-vat-panel">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" disabled={busy} onClick={run} data-testid="fic-vat-diagnostics">{busy ? "Lettura aliquote..." : "Diagnostica aliquote"}</Button>
        <Input value={vid} onChange={(e) => setVid(e.target.value.replace(/\D/g, ""))} placeholder="ID aliquota" className="h-8 w-32" data-testid="fic-vat-id-input" />
        <Button size="sm" variant="outline" disabled={!vid} onClick={() => save(vid)} data-testid="fic-vat-id-save">Verifica e imposta ID</Button>
      </div>
      {d && (
        <div className="space-y-1" data-testid="fic-vat-result">
          <div>Azienda FIC collegata: <b>{d.company_id || "—"}</b>{d.companies?.length ? ` · aziende dell'account: ${d.companies.map((c) => `${c.name} (${c.id})${c.selected ? " ✓" : ""}`).join(", ")}` : ""}</div>
          <div>Endpoint: {d.endpoint} · aliquote recuperate: <b data-testid="fic-vat-total">{d.total}</b> · pagine: {d.pages}{d.paginated ? " (paginata)" : ""}</div>
          <div>Configurata: {d.env_override ? `ID ${d.env_override} da variabile d'ambiente` : d.configured ? `ID ${d.configured.id} · ${d.configured.description || ""} (${d.configured.source === "manual" ? "manuale" : "trovata via API"})` : "nessuna"}</div>
          <div data-testid="fic-vat-match" className={d.match ? "text-emerald-700 font-semibold" : "text-red-600 font-semibold"}>
            {d.match ? `Trovata: ${d.match.description} · ID ${d.match.id} · ${d.match.value}% · ${d.match.ei_type || "natura non indicata"}` : "Aliquota 'Contribuenti forfettari' non trovata"}
          </div>
          {d.error && <div className="text-red-600" data-testid="fic-vat-error">Errore API: {d.error}</div>}
          {zero.length > 0 && (
            <div className="overflow-x-auto"><table className="min-w-[560px] w-full" data-testid="fic-vat-table">
              <thead><tr className="text-slate-400"><th className="text-left py-1">ID</th><th className="text-left">Descrizione</th><th className="text-left">IVA</th><th className="text-left">Natura</th><th className="text-left">Descr. e-fattura</th><th></th></tr></thead>
              <tbody>{zero.map((r) => <tr key={r.id} className="border-t border-slate-100"><td className="py-1">{r.id}</td><td>{r.description}{r.is_disabled ? " (disattivata)" : ""}</td><td>{r.value}%</td><td>{r.ei_type || "—"}</td><td>{r.ei_description || "—"}</td>
                <td>{d.match?.id !== r.id && <button type="button" className="text-[#088F8A] font-semibold" onClick={() => save(r.id)} data-testid={`fic-vat-use-${r.id}`}>Usa</button>}</td></tr>)}</tbody>
            </table></div>
          )}
        </div>
      )}
    </div>
  );
}
