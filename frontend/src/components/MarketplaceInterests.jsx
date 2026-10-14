import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Download } from "lucide-react";

const d = (s) => (s ? new Date(s).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
const BS = { sincronizzato: "Sincronizzato", errore: "Errore" };
const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

export function MarketplaceInterests() {
  const [services, setServices] = useState([]);
  const [sid, setSid] = useState("");
  const [rows, setRows] = useState(null);
  useEffect(() => { api.get("/platform/marketplace/services").then(({ data }) => setServices(data.services || [])).catch(() => {}); }, []);
  useEffect(() => {
    setRows(null);
    api.get("/platform/marketplace/interests", { params: sid ? { service_id: sid } : {} }).then(({ data }) => setRows(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [sid]);
  const csv = () => {
    const head = ["Servizio", "Codice servizio", "ID organizzazione", "Organizzazione", "ID utente", "Nome", "Cognome", "Email", "Data richiesta", "Brevo", "Errore Brevo"];
    const lines = [head, ...rows.map((r) => [r.service_name, r.service_code, r.org_id, r.org_name, r.user_id, r.nome, r.cognome, r.email, d(r.created_at), BS[r.brevo_status] || "In attesa", r.brevo_error])];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["\ufeff" + lines.map((l) => l.map(cell).join(";")).join("\n")], { type: "text/csv;charset=utf-8" }));
    a.download = "interessi-marketplace.csv"; a.click();
  };
  const orgs = new Set((rows || []).map((r) => r.org_id)).size;
  return (
    <div className="space-y-3" data-testid="mkt-admin-interests-all">
      <div className="flex flex-wrap items-center gap-2">
        <select value={sid} onChange={(e) => setSid(e.target.value)} className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" data-testid="mkt-admin-interests-filter">
          <option value="">Tutti i servizi</option>{services.filter((s) => s.status === "coming_soon" || s.interest_count).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <Button variant="outline" disabled={!rows?.length} onClick={csv} data-testid="mkt-admin-interests-all-csv"><Download className="w-4 h-4 mr-1" />Esporta CSV</Button>
        <span className="text-sm text-slate-600" data-testid="mkt-admin-interests-summary">{rows ? `${rows.length} richieste · ${orgs} organizzazioni` : ""}</span>
      </div>
      <div className="rounded-xl border border-slate-200 overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm" data-testid="mkt-admin-interests-all-table">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Servizio", "Organizzazione", "Nome", "Cognome", "Email", "Data richiesta", "Brevo"].map((h) => <th key={h} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
          <tbody>{!rows ? <tr><td colSpan={7} className="p-4 text-slate-400">Caricamento...</td></tr> : !rows.length ? <tr><td colSpan={7} className="p-6 text-center text-slate-500">Nessuna richiesta.</td></tr> : rows.map((r) => (
            <tr key={r.id} className="border-t border-slate-100"><td className="px-3 py-2">{r.service_name}</td><td className="px-3 py-2">{r.org_name}</td><td className="px-3 py-2">{r.nome || r.name}</td><td className="px-3 py-2">{r.cognome}</td><td className="px-3 py-2">{r.email}</td><td className="px-3 py-2 whitespace-nowrap">{d(r.created_at)}</td><td className="px-3 py-2" title={r.brevo_error || ""}>{BS[r.brevo_status] || "In attesa"}</td></tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}
