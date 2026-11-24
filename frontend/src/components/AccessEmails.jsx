import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/crm";
import { fmtInvite } from "@/components/PersonInvites";
import { toast } from "sonner";

export const CONF = { confermato: ["Confermato", "green"], da_confermare: ["Da confermare", "orange"], non_confermato: ["Non confermato", "red"] };
export const confGroup = (s) => (s === "confermato" ? "confermato" : ["non_disponibile", "rinunciato"].includes(s) ? "non_confermato" : "da_confermare");
export const confOf = (links) => {
  const g = new Set((links || []).map((l) => confGroup(l.stato)));
  return g.has("confermato") ? "confermato" : g.has("da_confermare") || !g.size ? "da_confermare" : "non_confermato";
};
export const ACCESS = { email_da_inviare: ["Email da inviare", "gray"], email_inviata: ["Email inviata", "blue"], accesso_effettuato: ["Accesso effettuato", "green"] };

export function AccessCell({ person }) {
  const [label, color] = ACCESS[person.access_status] || ACCESS.email_da_inviare;
  return (
    <div data-testid={`access-status-${person.id}`}>
      <StatusBadge color={color}>{label}</StatusBadge>
      {person.last_invite_at && <div className="mt-1 text-xs text-slate-500 whitespace-nowrap" data-testid={`access-last-sent-${person.id}`}>Ultimo invio: {fmtInvite(person.last_invite_at)}</div>}
    </div>
  );
}

const TONES = {
  all: "border-slate-200 text-slate-800", confermato: "border-emerald-200 bg-emerald-50 text-emerald-800",
  da_confermare: "border-orange-200 bg-orange-50 text-orange-800", non_confermato: "border-red-200 bg-red-50 text-red-800",
};

export function ConfSummary({ groups, value, onChange }) {
  const n = (k) => groups.filter((g) => g === k).length;
  const items = [["all", "Totale persone", groups.length], ["confermato", "Confermati", n("confermato")], ["da_confermare", "Da confermare", n("da_confermare")], ["non_confermato", "Non confermati", n("non_confermato")]];
  return (
    <div className="mb-4 grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="conf-summary">
      {items.map(([k, label, count]) => (
        <button key={k} type="button" onClick={() => onChange(k)} aria-pressed={value === k} data-testid={`conf-counter-${k}`}
          className={`rounded-xl border px-4 py-3 text-left transition-shadow hover:shadow-md ${TONES[k]} ${k === "all" ? "bg-white" : ""} ${value === k ? "ring-2 ring-slate-900 shadow-md" : ""}`}>
          <div className="text-[11px] font-bold uppercase tracking-wider">{label}</div>
          <div className="mt-1 font-display text-3xl font-bold" data-testid={`conf-count-${k}`}>{count}</div>
        </button>
      ))}
    </div>
  );
}

export function AccessEmailDialog({ request, eventoId, onClose, onDone }) {
  const [resend, setResend] = useState(!!request.single);
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const body = { person_ids: request.all ? null : request.ids, all_unsent: !!request.all, evento_id: eventoId || null, resend, force: !!request.single };
  useEffect(() => {
    setD(null);
    api.post("/person-invites/access-preview", { person_ids: request.all ? null : request.ids, all_unsent: !!request.all, evento_id: eventoId || null, resend, force: !!request.single })
      .then((r) => setD(r.data)).catch((e) => { toast.error(formatApiError(e.response?.data?.detail)); onClose(); });
  }, [request, eventoId, resend]); // eslint-disable-line react-hooks/exhaustive-deps
  const send = async () => {
    setBusy(true);
    try { const { data } = await api.post("/person-invites/access-send", body); setResult(data); onDone(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const ok = (d?.recipients || []).filter((r) => !r.reason);
  const ko = (d?.recipients || []).filter((r) => r.reason);
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[92dvh] overflow-y-auto" data-testid="access-email-dialog">
        <DialogHeader><DialogTitle className="font-display">Invia email di accesso</DialogTitle>
          <DialogDescription>{request.all ? "Confermati che non hanno ancora ricevuto l'email di accesso." : "L'email viene inviata solo alle persone con partecipazione confermata."}</DialogDescription></DialogHeader>
        {result ? (
          <div className="space-y-2" data-testid="access-email-result">
            <p className="text-sm text-slate-700"><b>{result.sent.length}</b> email inviate · <b>{result.skipped.length}</b> non inviate{result.remaining ? ` · ${result.remaining} ancora da inviare (ripeti l'invio)` : ""}</p>
            {result.skipped.map((s) => <div key={s.id} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm"><b className="font-semibold">{s.name}</b><div className="text-xs text-amber-800">{s.reason}</div></div>)}
            <DialogFooter><Button onClick={onClose} data-testid="access-email-close">Chiudi</Button></DialogFooter>
          </div>
        ) : !d ? <p className="py-8 text-center text-sm text-slate-400">Caricamento…</p> : (
          <>
            <div className="text-sm text-slate-700" data-testid="access-email-summary"><b data-testid="access-email-count">{ok.length}</b> destinatari{ko.length ? ` · ${ko.length} esclusi` : ""}</div>
            <div className="max-h-44 overflow-y-auto rounded-lg border border-slate-200 divide-y text-sm" data-testid="access-email-recipients">
              {ok.map((r) => <div key={r.id} className="px-3 py-1.5" data-testid={`access-rcpt-${r.id}`}><b className="font-semibold">{r.name}</b> <span className="text-slate-500 break-all">{r.email}</span>
                {r.last_invite_at && <div className="text-xs text-amber-700">Reinvio · ultimo invio {fmtInvite(r.last_invite_at)}: il link precedente non sarà più valido</div>}</div>)}
              {ko.map((r) => <div key={r.id} className="px-3 py-1.5 bg-slate-50 text-slate-500" data-testid={`access-skip-${r.id}`}>{r.name} <span className="text-xs text-amber-700">· {r.reason}</span></div>)}
              {!d.recipients.length && <div className="px-3 py-4 text-center text-slate-400">Nessun destinatario.</div>}
            </div>
            {!request.all && !request.single && (
              <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={resend} onChange={(e) => setResend(e.target.checked)} data-testid="access-email-resend" />Reinvia anche a chi ha già ricevuto l'email</label>
            )}
            <div>
              <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-500">Anteprima</div>
              <div className="text-sm text-slate-700" data-testid="access-email-subject">Oggetto: <b className="font-semibold">{d.subject}</b></div>
              <iframe title="Anteprima email" srcDoc={d.html} sandbox="" className="mt-2 h-72 w-full rounded-lg border border-slate-200 bg-white" data-testid="access-email-preview" />
            </div>
            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={onClose} data-testid="access-email-cancel">Annulla</Button>
              <Button onClick={send} disabled={busy || !ok.length} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="access-email-confirm">{busy ? "Invio…" : `Conferma invio a ${ok.length}`}</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
