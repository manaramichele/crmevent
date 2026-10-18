import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");

// Super Admin: organizzazioni con Elenco Iscritti, stato Brevo, riavvio sincronizzazioni, attivazione manuale.
export function IscrittiAdminPanel() {
  const [d, setD] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [pick, setPick] = useState("");
  const load = useCallback(() => api.get("/platform/iscritti/orgs").then(({ data }) => setD(data)).catch(err), []);
  useEffect(() => { load(); api.get("/platform/organizations").then(({ data }) => setOrgs(Array.isArray(data) ? data : data.organizations || [])).catch(() => {}); }, [load]);
  const act = async (url, body, msg) => { try { const { data } = await api.post(url, body); toast.success(msg + (data?.counts ? ` · ${data.counts.sincronizzati} sincronizzati` : "")); load(); } catch (e) { err(e); } };
  if (!d) return <p className="text-sm text-slate-500">Caricamento...</p>;
  return (
    <div className="space-y-4" data-testid="iscritti-admin">
      <p className="text-sm text-slate-600">Prezzo Marketplace: {d.service?.price ? `${d.service.price} € / ${d.service.price_type === "yearly" ? "anno" : "mese"}` : "non configurato"} · si modifica nel tab Catalogo (servizio «Elenco Iscritti»).</p>
      <div className="flex flex-wrap gap-2">
        <select className="h-10 rounded-md border border-slate-200 px-3 text-sm bg-white min-w-0 max-w-full" value={pick} onChange={(e) => setPick(e.target.value)} data-testid="iscritti-admin-org"><option value="">Attiva gratuitamente per un'organizzazione...</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}</select>
        <Button disabled={!pick} onClick={() => act(`/platform/iscritti/orgs/${pick}/activate`, { active: true }, "Modulo attivato")} data-testid="iscritti-admin-activate">Attiva</Button>
        <Button variant="outline" onClick={async () => { try { const { data } = await api.post("/platform/iscritti/demo-seed"); toast.success(`Demo popolata: ${data.iscritti} iscritti · ${data.totale_partecipazioni} partecipazioni`); load(); } catch (e) { err(e); } }} data-testid="iscritti-admin-demo-seed">Popola organizzazione Demo</Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm" data-testid="iscritti-admin-table">
          <thead><tr className="text-left text-xs text-slate-500 border-b"><th className="py-2 pr-3">Organizzazione</th><th>Attivazione</th><th>Iscritti</th><th>Ultima importazione</th><th>Brevo</th><th>Errori</th><th>Azioni</th></tr></thead>
          <tbody>
            {d.orgs.length === 0 && <tr><td colSpan={7} className="py-4 text-slate-400">Nessuna organizzazione ha attivato il modulo.</td></tr>}
            {d.orgs.map((o) => {
              const ls = o.brevo?.brevo_last_sync;
              return (
                <tr key={o.org_id} className="border-b last:border-0 align-top" data-testid={`iscritti-admin-row-${o.org_id}`}>
                  <td className="py-2 pr-3 font-semibold">{o.nome}</td>
                  <td>{o.active ? (o.via === "acquisto" ? "Acquisto" : "Super Admin") : "Disattivato"}</td>
                  <td>{o.iscritti}</td>
                  <td className="text-xs">{o.last_import ? `${dt(o.last_import.created_at)} · ${o.last_import.status}` : "—"}</td>
                  <td className="text-xs">{ls ? `${ls.status} · ${dt(ls.at)}${ls.error ? ` · ${ls.error}` : ""}` : "—"}</td>
                  <td>{o.brevo_errors}</td>
                  <td className="space-x-1 whitespace-nowrap">
                    <Button size="sm" variant="outline" onClick={() => act(`/platform/iscritti/orgs/${o.org_id}/sync`, {}, "Sincronizzazione riavviata")} data-testid={`iscritti-admin-resync-${o.org_id}`}>Riavvia sync</Button>
                    {o.not_consented > 0 && <Button size="sm" variant="outline" onClick={() => window.confirm(`Inviare a Brevo ${o.not_consented} iscritti SENZA consenso marketing registrato? L'azione viene registrata nell'Audit Log.`) && act(`/platform/iscritti/orgs/${o.org_id}/force-sync`, {}, "Sincronizzazione forzata")} data-testid={`iscritti-admin-force-${o.org_id}`}>Sincronizza senza consenso ({o.not_consented})</Button>}
                    {o.via !== "acquisto" && <Button size="sm" variant="ghost" onClick={() => act(`/platform/iscritti/orgs/${o.org_id}/activate`, { active: !o.active }, o.active ? "Disattivato" : "Attivato")} data-testid={`iscritti-admin-toggle-${o.org_id}`}>{o.active ? "Disattiva" : "Riattiva"}</Button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
