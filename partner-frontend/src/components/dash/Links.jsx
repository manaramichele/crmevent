import { useState } from "react";
import { toast } from "sonner";
import { Copy, Plus, Share2, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button, Input } from "@/components/ui";

export function CopyBtn({ text, testid }) {
  const copy = async () => { try { await navigator.clipboard.writeText(text); toast.success("Link copiato"); } catch { toast.error("Copia non riuscita"); } };
  return <Button onClick={copy} data-testid={testid} className="shrink-0"><Copy className="w-4 h-4" />Copia</Button>;
}

export function ShareBtn({ text, testid }) {
  const share = async () => {
    if (navigator.share) { try { await navigator.share({ title: "CRMEvent", text: "Organizza i tuoi eventi con CRMEvent: prova gratuita di 14 giorni.", url: text }); } catch {} return; }
    try { await navigator.clipboard.writeText(text); toast.success("Link copiato: incollalo dove vuoi condividerlo"); } catch { toast.error("Condivisione non disponibile"); }
  };
  return <Button variant="outline" onClick={share} data-testid={testid} className="shrink-0"><Share2 className="w-4 h-4" />Condividi</Button>;
}

const Mini = ({ s }) => <div className="flex gap-3 text-xs text-slate-500"><span>{s.clicks} click</span><span>{s.visitors} visitatori</span><span>{s.registrations} registrazioni</span><span>{s.converted} abbonati</span></div>;

export default function Links({ d, reload }) {
  const [name, setName] = useState("");
  const add = async (e) => {
    e.preventDefault();
    try { await api.post("/partner/campaigns", { name }); setName(""); reload(); toast.success("Link campagna creato"); } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };
  const del = async (c) => { if (!window.confirm(`Eliminare il link "${c.name}"? I dati raccolti restano nelle statistiche.`)) return; await api.delete(`/partner/campaigns/${c.id}`); reload(); };
  return (
    <div className="space-y-5">
      <div className="rounded-3xl bg-ink text-white p-5 sm:p-6" data-testid="referral-card">
        <div className="text-sm text-slate-300">Il tuo link referral · codice <b className="text-tiffany" data-testid="referral-code">{d.partner.code}</b></div>
        <div className="mt-3 flex flex-col sm:flex-row gap-2">
          <code className="flex-1 min-w-0 truncate rounded-xl bg-white/10 px-4 h-11 flex items-center text-sm" data-testid="referral-link">{d.partner.referral_link}</code>
          <div className="flex gap-2"><CopyBtn text={d.partner.referral_link} testid="referral-copy" /><ShareBtn text={d.partner.referral_link} testid="referral-share" /></div>
        </div>
        <div className="mt-3 [&_span]:text-slate-400"><Mini s={d.main_stats} /></div>
        <p className="mt-2 text-xs text-slate-400">Il cliente viene attribuito a te se si registra entro {d.settings.attribution_days} giorni dalla visita e ha accettato i cookie di misurazione.</p>
      </div>
      <div className="rounded-3xl border border-slate-200 bg-white p-5" data-testid="campaigns">
        <h3 className="font-bold">Link per campagne</h3>
        <form onSubmit={add} className="mt-3 flex gap-2"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Es. Newsletter ottobre, Instagram, Fiera" maxLength={60} required data-testid="campaign-name" /><Button type="submit" data-testid="campaign-add"><Plus className="w-4 h-4" />Crea</Button></form>
        <div className="mt-4 space-y-3">
          {!d.campaigns.length && <p className="text-sm text-slate-500" data-testid="campaigns-empty">Crea link diversi per capire quale canale funziona meglio.</p>}
          {d.campaigns.map((c) => (
            <div key={c.id} className="rounded-2xl border border-slate-200 p-3" data-testid={`campaign-${c.slug}`}>
              <div className="flex items-center justify-between gap-2"><b className="text-sm">{c.name}</b><button onClick={() => del(c)} aria-label="Elimina" data-testid={`campaign-del-${c.slug}`}><Trash2 className="w-4 h-4 text-slate-400 hover:text-red-500" /></button></div>
              <div className="mt-2 flex flex-col sm:flex-row gap-2"><code className="flex-1 min-w-0 truncate rounded-xl bg-slate-50 px-3 h-11 flex items-center text-xs" data-testid={`campaign-link-${c.slug}`}>{c.link}</code><CopyBtn text={c.link} testid={`campaign-copy-${c.slug}`} /></div>
              <div className="mt-2"><Mini s={c.stats} /></div>
            </div>))}
        </div>
      </div>
    </div>
  );
}
