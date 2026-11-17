import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Copy, Ban } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import { fmtDT, nameOf } from "./meta";

const S = "h-9 rounded-md border border-slate-200 bg-white px-2 text-xs";
const ROLES = [["", "Automatico (dai permessi)"], ["responsabile", "Responsabile Control Room"], ["coordinatore", "Coordinatore di settore"], ["visualizzatore", "Visualizzatore"]];

function Roles({ d, base, call }) {
  const [ms, setMs] = useState(null);
  const load = () => api.get(`${base}/members`).then((r) => setMs(r.data.members)).catch(() => setMs([]));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async (m, role, sector_ids) => { if (await call("put", "/roles", { user_id: m.user_id, role: role || null, sector_ids }, "Ruolo aggiornato")) load(); };
  return (
    <div className="space-y-1.5" data-testid="cr-roles">
      {(ms || []).map((m) => (
        <div key={m.user_id} className="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-100 px-2 py-1.5 text-xs" data-testid={`cr-role-${m.user_id}`}>
          <div className="min-w-0 flex-1"><b>{m.name || m.email}</b> <span className="text-slate-400">{m.org_role}</span></div>
          {m.org_role === "admin_org" ? <span className="text-slate-500">Responsabile (amministratore)</span> : <>
            <select className={S} value={m.cr_role || ""} onChange={(e) => save(m, e.target.value, m.sector_ids)} data-testid={`cr-role-select-${m.user_id}`}>{ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
            {m.cr_role === "coordinatore" && <select multiple className="h-16 rounded-md border border-slate-200 text-xs" value={m.sector_ids} onChange={(e) => save(m, "coordinatore", [...e.target.selectedOptions].map((o) => o.value))} data-testid={`cr-role-sectors-${m.user_id}`}>
              {d.sectors.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}</select>}</>}
        </div>))}
    </div>
  );
}

function Invites({ d, call }) {
  const [f, setF] = useState({ resource_id: "", role: "operatore", days: 3, can_set_priority: false });
  const [link, setLink] = useState(null);
  const [qr, setQr] = useState(null);
  useEffect(() => { if (link) QRCode.toDataURL(link, { width: 220, margin: 1 }).then(setQr); }, [link]);
  const create = async () => {
    const r = await call("post", "/invites", { ...f, days: Number(f.days) }, "Invito creato");
    if (r?.token) setLink(`${window.location.origin}/cr/op/${r.token}`);
  };
  const res = Object.fromEntries(d.resources.map((r) => [r.id, r]));
  return (
    <div className="space-y-3" data-testid="cr-invites">
      <div className="flex flex-wrap gap-1.5">
        <select className={`${S} flex-1`} value={f.resource_id} onChange={(e) => setF({ ...f, resource_id: e.target.value })} data-testid="cr-invite-resource"><option value="">Operatore o squadra…</option>{d.resources.map((r) => <option key={r.id} value={r.id}>{nameOf(r)}</option>)}</select>
        <select className={S} value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} data-testid="cr-invite-role"><option value="operatore">Operatore</option><option value="coordinatore">Coordinatore</option></select>
        <select className={S} value={f.days} onChange={(e) => setF({ ...f, days: e.target.value })} data-testid="cr-invite-days">{[1, 2, 3, 7, 14].map((x) => <option key={x} value={x}>Scade in {x} g</option>)}</select>
        <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={f.can_set_priority} onChange={(e) => setF({ ...f, can_set_priority: e.target.checked })} />può indicare la priorità</label>
        <Button size="sm" disabled={!f.resource_id} onClick={create} data-testid="cr-invite-create">Crea invito</Button>
      </div>
      {link && <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[#0ABAB5]/40 bg-[#0ABAB5]/5 p-3" data-testid="cr-invite-link">
        {qr && <img src={qr} alt="QR invito" className="h-36 w-36 rounded bg-white" data-testid="cr-invite-qr" />}
        <div className="min-w-0 flex-1 space-y-1 text-xs"><div className="font-semibold">Link personale (mostrato solo ora)</div><div className="break-all font-mono text-[11px]">{link}</div>
          <Button size="sm" variant="outline" onClick={() => { navigator.clipboard?.writeText(link); toast.success("Link copiato"); }} data-testid="cr-invite-copy"><Copy className="mr-1 h-3.5 w-3.5" />Copia</Button>
          <p className="text-slate-500">Consegnalo solo all'operatore indicato. Vale solo per questo evento, scade automaticamente e puoi revocarlo in qualsiasi momento. Creare un nuovo invito per la stessa risorsa revoca il precedente.</p></div></div>}
      <div className="space-y-1">{(d.invites || []).map((i) => (
        <div key={i.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-100 px-2 py-1.5 text-xs" data-testid={`cr-invite-${i.id}`}>
          <b className="flex-1">{res[i.resource_id] ? nameOf(res[i.resource_id]) : "Risorsa rimossa"}</b><span>{i.role}</span>
          <span className="text-slate-400">{i.revoked_at ? `revocato ${fmtDT(i.revoked_at)}` : i.expires_at < new Date().toISOString() ? "scaduto" : `scade ${fmtDT(i.expires_at)}`}{i.last_seen_at ? ` · ultimo accesso ${fmtDT(i.last_seen_at)}` : ""}</span>
          {!i.revoked_at && <Button size="sm" variant="ghost" className="h-7 text-red-600" onClick={() => call("delete", `/invites/${i.id}`, undefined, "Accesso revocato")} data-testid={`cr-invite-revoke-${i.id}`}><Ban className="mr-1 h-3.5 w-3.5" />Revoca</Button>}
        </div>))}</div>
    </div>
  );
}

// Ruoli Control Room (utenti CRMEvent) e inviti personali per gli operatori sul percorso.
export function AccessDialog({ open, onOpenChange, d, base, call }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[96vw] max-w-2xl space-y-4 overflow-y-auto" data-testid="cr-access">
        <DialogHeader><DialogTitle className="font-display">Ruoli e accessi operatori</DialogTitle></DialogHeader>
        <div><div className="mb-1 text-sm font-semibold">Utenti CRMEvent</div><Roles d={d} base={base} call={call} /></div>
        <div><div className="mb-1 text-sm font-semibold">Inviti mobile (operatori sul percorso)</div><Invites d={d} call={call} /></div>
      </DialogContent>
    </Dialog>
  );
}
