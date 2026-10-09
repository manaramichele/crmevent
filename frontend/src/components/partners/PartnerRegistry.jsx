import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { StatusBadge } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Check, Ban, X, Search } from "lucide-react";
import { P_ST, CAT, SOG, pname, dt, eur, Card } from "@/components/partners/shared";

function Detail({ id, onClose }) {
  const [d, setD] = useState(null);
  useEffect(() => { api.get(`/platform/partners/${id}`).then(({ data }) => setD(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))); }, [id]);
  if (!d) return <p className="p-4 text-sm text-slate-400">Caricamento...</p>;
  const p = d.partner, a = p.indirizzo || {};
  const row = (l, v) => <div className="min-w-0"><div className="text-xs text-slate-500">{l}</div><div className="text-sm text-slate-900 break-words">{v || "—"}</div></div>;
  return (
    <div className="p-4 bg-slate-50 border-t border-slate-100 space-y-3" data-testid={`partner-detail-${id}`}>
      <div className="flex justify-between"><b className="text-slate-900">Scheda partner</b><button onClick={onClose} aria-label="Chiudi" data-testid="partner-detail-close"><X className="w-4 h-4" /></button></div>
      <div className="grid sm:grid-cols-3 gap-3">
        {row("Email", p.email)}{row("Cellulare", p.telefono)}{row("Categoria", CAT[p.categoria])}{row("Soggetto fiscale", SOG[p.soggetto])}{row("Ragione sociale", p.ragione_sociale)}
        {row("Codice fiscale", p.codice_fiscale)}{row("Partita IVA", p.partita_iva)}{row("Regime fiscale partner", p.regime_fiscale)}
        {row("Indirizzo fiscale", [a.via, a.cap, a.citta, a.provincia, a.paese].filter(Boolean).join(", "))}{row("IBAN", p.iban)}{row("Sito web", p.sito_web)}{row("Social", p.social)}
        {row("Codice referral", p.code)}{row("Registrato", dt(p.created_at))}{row("Accesso", p.auth_provider === "google" ? "Google" : "Email e password")}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 text-sm">
        {[["Click", d.stats.clicks], ["Visitatori", d.stats.visitors], ["Registrazioni", d.stats.registrations], ["Abbonati", d.stats.active], ["Maturate", eur(d.stats.maturate_cents + d.stats.liquidabili_cents)], ["Pagate", eur(d.stats.pagate_cents)]].map(([l, v]) => (
          <div key={l} className="rounded-lg bg-white border border-slate-200 p-2"><div className="text-xs text-slate-500">{l}</div><b>{v}</b></div>))}
      </div>
    </div>
  );
}

export default function PartnerRegistry() {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState("");
  const [st, setSt] = useState("");
  const [open, setOpen] = useState(null);
  const load = () => api.get("/platform/partners", { params: { q, status: st } }).then(({ data }) => setRows(data)).catch(() => setRows([]));
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [q, st]); // eslint-disable-line react-hooks/exhaustive-deps
  const setStatus = async (p, status) => {
    let note = null;
    if (status !== "approved") { note = window.prompt(`Motivo (${P_ST[status][1]}), facoltativo:`) ; if (note === null) return; }
    try { await api.post(`/platform/partners/${p.id}/status`, { status, note }); toast.success(`${p.email}: ${P_ST[status][1]}`); load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Card testid="partner-registry" title={`Partner (${rows?.length ?? "…"})`} right={
      <div className="flex gap-2 font-normal">
        <div className="relative"><Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca nome, email, P.IVA, codice" className="pl-8 h-9 w-56" data-testid="partner-search" /></div>
        <select value={st} onChange={(e) => setSt(e.target.value)} className="h-9 rounded-md border border-slate-200 px-2 text-sm" data-testid="partner-status-filter">
          <option value="">Tutti</option>{Object.entries(P_ST).map(([k, [, l]]) => <option key={k} value={k}>{l}</option>)}
        </select>
      </div>}>
      {rows && !rows.length && <p className="p-4 text-sm text-slate-500" data-testid="partners-empty">Nessun partner trovato.</p>}
      <div className="divide-y divide-slate-100">
        {(rows || []).map((p) => (
          <div key={p.id} data-testid={`partner-row-${p.id}`}>
            <div className="p-4 flex flex-col lg:flex-row lg:items-center gap-3">
              <button type="button" className="flex-1 min-w-0 text-left" onClick={() => setOpen(open === p.id ? null : p.id)} data-testid={`partner-open-${p.id}`}>
                <div className="flex items-center gap-2 flex-wrap"><span className="font-semibold text-slate-900">{pname(p)}</span><StatusBadge color={P_ST[p.status]?.[0]}>{P_ST[p.status]?.[1]}</StatusBadge><span className="text-xs text-slate-500">{CAT[p.categoria] || "Profilo incompleto"} · {SOG[p.soggetto] || "—"}</span></div>
                <div className="text-xs text-slate-500 mt-0.5 truncate">{p.email} · codice {p.code} · {p.referrals} organizzazioni · registrato il {dt(p.created_at)}</div>
              </button>
              <div className="flex gap-2 flex-wrap">
                {p.status !== "approved" && <Button size="sm" onClick={() => setStatus(p, "approved")} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid={`partner-approve-${p.id}`}><Check className="w-4 h-4 mr-1" />Approva</Button>}
                {p.status === "pending" && <Button size="sm" variant="outline" onClick={() => setStatus(p, "rejected")} data-testid={`partner-reject-${p.id}`}>Rifiuta</Button>}
                {p.status === "approved" && <Button size="sm" variant="outline" className="text-red-600" onClick={() => setStatus(p, "suspended")} data-testid={`partner-suspend-${p.id}`}><Ban className="w-4 h-4 mr-1" />Sospendi</Button>}
              </div>
            </div>
            {open === p.id && <Detail id={p.id} onClose={() => setOpen(null)} />}
          </div>
        ))}
      </div>
    </Card>
  );
}
