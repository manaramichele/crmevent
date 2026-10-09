import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { dt, Card, pname } from "@/components/partners/shared";

function Attribution({ partners, onDone }) {
  const [orgs, setOrgs] = useState([]);
  const [f, setF] = useState({ org_id: "", partner_id: "", note: "" });
  useEffect(() => { api.get("/platform/organizations").then(({ data }) => setOrgs(data || [])).catch(() => {}); }, []);
  const save = async () => {
    try { await api.put(`/platform/partner-referrals/${f.org_id}`, { partner_id: f.partner_id || null, note: f.note }); toast.success("Attribuzione aggiornata e registrata"); setF({ org_id: "", partner_id: "", note: "" }); onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const sel = "h-10 rounded-md border border-slate-200 px-2 text-sm w-full";
  return (
    <Card title="Modifica attribuzione manuale" testid="partner-attribution">
      <div className="p-4 grid sm:grid-cols-4 gap-2">
        <select className={sel} value={f.org_id} onChange={(e) => setF({ ...f, org_id: e.target.value })} data-testid="attr-org"><option value="">Organizzazione…</option>{orgs.map((o) => <option key={o.id} value={o.id}>{o.nome}</option>)}</select>
        <select className={sel} value={f.partner_id} onChange={(e) => setF({ ...f, partner_id: e.target.value })} data-testid="attr-partner"><option value="">Nessun partner (rimuovi)</option>{partners.map((p) => <option key={p.id} value={p.id}>{pname(p)} · {p.code}</option>)}</select>
        <Input value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Motivo della modifica (obbligatorio)" data-testid="attr-note" />
        <Button disabled={!f.org_id || f.note.trim().length < 3} onClick={save} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="attr-save">Salva attribuzione</Button>
      </div>
    </Card>
  );
}

export default function PartnerOrgs() {
  const [rows, setRows] = useState(null);
  const [partners, setPartners] = useState([]);
  const [logRows, setLog] = useState([]);
  const load = () => Promise.all([api.get("/platform/partner-referrals"), api.get("/platform/partners"), api.get("/platform/partner-attribution-log")])
    .then(([a, b, c]) => { setRows(a.data); setPartners(b.data); setLog(c.data); }).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  const name = Object.fromEntries(partners.map((p) => [p.id, pname(p)]));
  return (
    <div className="space-y-5">
      <Card title={`Organizzazioni attribuite (${rows?.length ?? "…"})`} testid="partner-orgs">
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-xs text-slate-500 bg-slate-50"><tr>{["Organizzazione", "Partner", "Campagna", "Registrata", "Piano", "Stato abbonamento", "Pagamenti", "Rinnovi", "Commissioni fino al", "Origine"].map((h) => <th key={h} className="text-left p-2 first:pl-4">{h}</th>)}</tr></thead>
          <tbody>{(rows || []).map((r) => (
            <tr key={r.id} className="border-t border-slate-100" data-testid={`partner-org-${r.org_id}`}>
              <td className="p-2 pl-4 font-medium">{r.org_name}</td><td className="p-2">{r.partner_name}</td><td className="p-2">{r.campaign || "principale"}</td><td className="p-2">{dt(r.created_at)}</td>
              <td className="p-2">{(r.plan || "—").toUpperCase()} {r.billing_cycle ? `· ${r.billing_cycle === "yearly" ? "12 mesi" : "6 mesi"}` : ""}</td>
              <td className="p-2">{r.stripe_status || (r.saas_mode === "trial" ? "prova" : r.saas_mode) || "—"}</td><td className="p-2">{r.payments}</td><td className="p-2">{r.renewals}</td>
              <td className="p-2">{dt(r.commission_until)}</td><td className="p-2">{r.source === "manuale" ? "Manuale" : "Referral"}</td>
            </tr>))}</tbody></table></div>
        {rows && !rows.length && <p className="p-4 text-sm text-slate-500" data-testid="partner-orgs-empty">Nessuna organizzazione attribuita.</p>}
      </Card>
      <Attribution partners={partners} onDone={load} />
      <Card title="Registro modifiche attribuzione" testid="partner-attr-log">
        {!logRows.length ? <p className="p-4 text-sm text-slate-500">Nessuna modifica manuale.</p> : logRows.map((l) => (
          <div key={l.id} className="px-4 py-2 border-t border-slate-100 text-sm">{dt(l.at)} · <b>{l.org_name}</b>: {name[l.from_partner_id] || "nessuno"} → {name[l.to_partner_id] || "nessuno"} · {l.note} <span className="text-xs text-slate-400">({l.by})</span></div>))}
      </Card>
    </div>
  );
}
