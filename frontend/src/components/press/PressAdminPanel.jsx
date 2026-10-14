import { useState } from "react";
import api from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { pErr, dt, useLoad } from "@/components/press/pressShared";

export function PressAdminPanel() {
  const [rows, load] = useLoad("/platform/press/orgs");
  const [q, setQ] = useState("");
  const toggle = async (o, v) => {
    if (!window.confirm(`${v ? "Attivare" : "Disattivare"} Comunicati stampa per «${o.nome}»?`)) return;
    try { await api.post(`/platform/press/orgs/${o.org_id}/activate`, { active: v }); toast.success(v ? "Servizio attivato" : "Servizio disattivato"); load(); } catch (e) { pErr(e); }
  };
  const list = (rows || []).filter((o) => !q || (o.nome || "").toLowerCase().includes(q.toLowerCase())).sort((a, b) => b.active - a.active);
  return (
    <div className="space-y-3" data-testid="press-admin">
      <p className="text-sm text-slate-600">Attivazione gratuita per singola organizzazione (listino e Stripe non attivi). Il Super Admin non invia comunicati per conto delle organizzazioni.</p>
      <Input placeholder="Cerca organizzazione" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" data-testid="press-admin-search" />
      <div className="rounded-2xl border border-slate-200 bg-white overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["Organizzazione", "Attivo", "Comunicati", "Inviati", "Errori", "Contatti", "Lista Brevo", "Sync"].map((h) => <th key={h} className="px-3 py-2.5 text-left font-semibold">{h}</th>)}</tr></thead>
          <tbody>{!rows ? <tr><td colSpan={8} className="p-6 text-slate-400">Caricamento...</td></tr> : list.map((o) => (
            <tr key={o.org_id} className="border-t border-slate-100" data-testid={`press-admin-row-${o.org_id}`}>
              <td className="px-3 py-2">{o.nome}{o.activated_at && o.active && <div className="text-[11px] text-slate-400">dal {dt(o.activated_at)}</div>}</td>
              <td className="px-3 py-2"><Switch checked={o.active} onCheckedChange={(v) => toggle(o, v)} data-testid={`press-admin-toggle-${o.org_id}`} /></td>
              <td className="px-3 py-2">{o.releases}</td><td className="px-3 py-2">{o.sent}</td><td className="px-3 py-2">{o.errors + o.contact_errors}</td><td className="px-3 py-2">{o.contacts}</td>
              <td className="px-3 py-2 text-xs">{o.list?.list_name || "—"}</td>
              <td className="px-3 py-2 text-xs" title={o.list?.error || ""}>{o.list ? `${o.list.sync_status} · ${dt(o.list.last_sync)}` : "—"}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}
