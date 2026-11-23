import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const fmt = (iso) => (iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");

function Scope({ acc }) {
  const act = acc.memberships.filter((m) => m.active && !m.org_disabled);
  if (!act.length) return <p className="text-sm text-slate-500">Nessuna organizzazione con accesso attivo.</p>;
  return (
    <ul className="space-y-1.5 text-sm" data-testid="account-state-scope">
      {act.map((m) => (
        <li key={m.org_id} className="rounded-lg border border-slate-200 px-3 py-2">
          <span className="font-medium text-slate-800">{m.org_nome}</span><span className="text-slate-500"> · {m.role_label}</span>
          {m.role === "collaboratore" && <div className="text-xs text-slate-500 mt-0.5">{m.all_events ? "Tutti gli eventi" : (m.events.filter((e) => e.status === "active").map((e) => e.nome).join(", ") || "Nessun evento attivo")}</div>}
        </li>
      ))}
    </ul>
  );
}

export default function AccountStateDialog({ user, onClose, onDone }) {
  const [acc, setAcc] = useState(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const activate = !user.active;
  useEffect(() => { api.get(`/platform/users/${user.user_id}/access`).then(({ data }) => setAcc(data)).catch(() => setAcc(false)); }, [user.user_id]);
  const go = async () => {
    setBusy(true);
    try { await api.post(`/platform/users/${user.user_id}/state`, { active: activate, reason }); toast.success(activate ? "Account riattivato" : "Account disattivato"); onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="account-state-dialog">
        <DialogHeader><DialogTitle>{activate ? "Riattivare l'account?" : "Disattivare l'account?"}</DialogTitle>
          <DialogDescription>{user.name || user.email} · {user.email}. {activate
            ? "Stesso account, stessa email e stesse associazioni: torneranno accessibili solo gli accessi ancora attivi qui sotto. Gli accessi revocati restano revocati."
            : "L'accesso viene bloccato subito, anche nelle sessioni aperte. Dati, storico e associazioni restano invariati."}</DialogDescription></DialogHeader>
        {acc && activate && acc.deactivated_at && <p className="text-xs text-slate-500" data-testid="account-state-prev">Disattivato il {fmt(acc.deactivated_at)}{acc.deactivation_reason ? ` · motivo: ${acc.deactivation_reason}` : ""}</p>}
        {acc ? <><div className="text-xs font-semibold uppercase text-slate-500">{activate ? "Torneranno accessibili" : "Accessi che verranno sospesi"}</div><Scope acc={acc} /></> : <p className="text-sm text-slate-400">Caricamento...</p>}
        {!activate && <Textarea placeholder="Motivo della disattivazione (facoltativo)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="account-state-reason" />}
        <DialogFooter><Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button disabled={busy || !acc} onClick={go} className={activate ? "bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" : "bg-red-500 hover:bg-red-600"} data-testid="account-state-confirm">{activate ? "Riattiva account" : "Disattiva account"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
