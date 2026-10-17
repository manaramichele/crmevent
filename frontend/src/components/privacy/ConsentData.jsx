import { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

const CARD = "bg-white border border-slate-200 rounded-xl p-4 sm:p-6";
const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");
const pct = (a, b) => (b ? `${Math.round((a / b) * 100)}%` : "—");
const ACTION = { accept_all: "Accetta tutti", reject_all: "Rifiuta", custom: "Personalizzato" };

function Kpi({ label, value, sub, id }) {
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-200 p-3" data-testid={`privacy-kpi-${id}`}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-bold text-slate-900">{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export function ConsentStats() {
  const [days, setDays] = useState(30);
  const [d, setD] = useState(null);
  useEffect(() => { api.get(`/platform/privacy/stats?days=${days}`).then(({ data }) => setD(data)).catch(() => {}); }, [days]);
  return (
    <div className={`${CARD} space-y-4`} data-testid="privacy-stats">
      <div className="flex flex-wrap gap-2">
        {[7, 30, 90, 365].map((n) => <Button key={n} size="sm" variant={n === days ? "default" : "outline"} onClick={() => setDays(n)} data-testid={`privacy-stats-days-${n}`}>{n} giorni</Button>)}
      </div>
      {d && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          <Kpi id="records" label="Scelte registrate" value={d.records} />
          <Kpi id="accept" label="Accetta tutti" value={d.actions.accept_all} sub={pct(d.actions.accept_all, d.records)} />
          <Kpi id="reject" label="Rifiuta non necessari" value={d.actions.reject_all} sub={pct(d.actions.reject_all, d.records)} />
          <Kpi id="custom" label="Personalizzati" value={d.actions.custom} sub={pct(d.actions.custom, d.records)} />
          <Kpi id="devices" label="Dispositivi (ultima scelta)" value={d.devices} />
          <Kpi id="analytics" label="Analitici attivi" value={d.analytics_granted} sub={pct(d.analytics_granted, d.devices)} />
          <Kpi id="marketing" label="Marketing attivi" value={d.marketing_granted} sub={pct(d.marketing_granted, d.devices)} />
          <Kpi id="revocations" label="Revoche" value={d.revocations} />
        </div>
      )}
      <p className="text-xs text-slate-500">Dati aggregati, senza indirizzi IP né informazioni sul dispositivo.</p>
    </div>
  );
}

export function ConsentRegistry() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [d, setD] = useState(null);
  const load = useCallback((p = 1) => api.get("/platform/privacy/consents", { params: { q: q || undefined, page: p, limit: 50 } })
    .then(({ data }) => { setD(data); setPage(p); }).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), [q]);
  return (
    <div className={`${CARD} space-y-4 min-w-0 max-w-full overflow-hidden`} data-testid="privacy-registry">
      <p className="text-sm text-slate-600">Accesso riservato al Super Admin; ogni consultazione viene registrata nell'Audit Log. I record vengono cancellati automaticamente dopo 24 mesi.</p>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); load(1); }}>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID consenso o ID utente (vuoto = tutti)" className="max-w-sm" data-testid="privacy-registry-search" />
        <Button type="submit" data-testid="privacy-registry-load">{d ? "Cerca" : "Consulta registro"}</Button>
      </form>
      {d && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm" data-testid="privacy-registry-table">
              <thead><tr className="text-left text-xs text-slate-500 border-b"><th className="py-2 pr-3">Data</th><th className="pr-3">ID consenso</th><th className="pr-3">Utente</th><th className="pr-3">Scelta</th><th className="pr-3">Analitici</th><th className="pr-3">Marketing</th><th className="pr-3">Evento</th><th className="pr-3">Origine</th><th>Versioni P/C/B</th></tr></thead>
              <tbody>
                {d.items.length === 0 && <tr><td colSpan={9} className="py-4 text-slate-400">Nessun record.</td></tr>}
                {d.items.map((r) => (
                  <tr key={r.id} className="border-b last:border-0 align-top">
                    <td className="py-2 pr-3 whitespace-nowrap">{dt(r.created_at)}</td>
                    <td className="pr-3 font-mono text-xs break-all">{r.consent_id}</td>
                    <td className="pr-3 font-mono text-xs">{r.user_id || "—"}</td>
                    <td className="pr-3">{ACTION[r.action]}</td>
                    <td className="pr-3">{r.choices.analytics ? "Sì" : "No"}</td>
                    <td className="pr-3">{r.choices.marketing ? "Sì" : "No"}</td>
                    <td className="pr-3">{r.event === "revoke" ? `Revoca (${r.revoked.join(", ")})` : r.event === "first" ? "Primo" : "Modifica"}</td>
                    <td className="pr-3">{r.source} · {r.lang}</td>
                    <td className="text-xs whitespace-nowrap">{r.versions.privacy} / {r.versions.cookie} / {r.versions.banner}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => load(page - 1)} data-testid="privacy-registry-prev">Precedente</Button>
            <span>Pagina {page} · {d.total} record</span>
            <Button size="sm" variant="outline" disabled={page * d.limit >= d.total} onClick={() => load(page + 1)} data-testid="privacy-registry-next">Successiva</Button>
          </div>
        </>
      )}
    </div>
  );
}
