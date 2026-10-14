import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "@/components/crm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, CheckCircle2, RotateCcw, Lock } from "lucide-react";
import { CATEGORIES, STATUS_META, StatusBadge, Conversation, Composer, dt, err, usePoll } from "@/components/tickets/TicketShared";

const changed = () => window.dispatchEvent(new Event("tickets:changed"));
const sel = "h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 min-w-0";

function CloseDialog({ t, onClose, onDone }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try { await api.post(`/platform/tickets/${t.id}/status`, { status: "chiusa", message: msg }); toast.success(`Segnalazione #${t.number} chiusa`); onDone(); onClose(); } catch (e) { err(e); }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg w-[calc(100vw-1.5rem)]" data-testid="ticket-close-dialog">
        <DialogTitle>Chiudere la segnalazione #{t.number}?</DialogTitle>
        <DialogDescription>L'organizzatore vedrà subito lo stato Chiusa con data e ora. Puoi aggiungere una risposta finale.</DialogDescription>
        <Textarea rows={4} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Risposta finale (facoltativa)" data-testid="ticket-close-message" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="ticket-close-cancel">Annulla</Button>
          <Button disabled={busy} onClick={go} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="ticket-close-confirm"><CheckCircle2 className="w-4 h-4 mr-1" />Conferma chiusura</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Detail({ id, onClose, onChanged }) {
  const [t, setT] = useState(null);
  const [internal, setInternal] = useState(false);
  const [closing, setClosing] = useState(false);
  const load = useCallback(() => api.get(`/platform/tickets/${id}`).then(({ data }) => setT(data)).catch(err), [id]);
  usePoll(load, [load]);
  const refresh = () => { load(); onChanged(); changed(); };
  const setStatus = async (status) => {
    try { await api.post(`/platform/tickets/${t.id}/status`, { status }); toast.success(`Stato: ${STATUS_META[status].label}`); refresh(); } catch (e) { err(e); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl w-[calc(100vw-1rem)] max-h-[94dvh] overflow-y-auto p-4 sm:p-6" data-testid="sa-ticket-detail">
        {!t ? <p className="text-sm text-slate-400">Caricamento...</p> : (<>
          <div className="pr-6">
            <div className="text-xs text-slate-500">#{t.number} · {CATEGORIES[t.category]} · <b className="text-slate-700">{t.org_name}</b> · {t.created_by?.name} ({t.created_by?.email})</div>
            <DialogTitle className="mt-0.5 break-words">{t.subject}</DialogTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge t={t} testid="sa-ticket-detail-status" />
              {t.status === "chiusa" && <span className="text-xs text-slate-600" data-testid="sa-ticket-closed-info">Chiusa il {dt(t.closed_at)} da {t.closed_by?.name}</span>}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {t.status === "chiusa" ? (
                <Button size="sm" variant="outline" onClick={() => setStatus("in_lavorazione")} data-testid="sa-ticket-reopen"><RotateCcw className="w-4 h-4 mr-1" />Riapri richiesta</Button>
              ) : (<>
                {["aperta", "in_lavorazione", "in_attesa"].filter((s) => s !== t.status).map((s) => (
                  <Button key={s} size="sm" variant="outline" onClick={() => setStatus(s)} data-testid={`sa-ticket-status-${s}`}>{STATUS_META[s].label}</Button>
                ))}
                <Button size="sm" onClick={() => setClosing(true)} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="sa-ticket-close"><CheckCircle2 className="w-4 h-4 mr-1" />Chiudi segnalazione</Button>
              </>)}
            </div>
          </div>
          <Conversation t={t} base="/platform/tickets" viewer="admin" />
          <div className={`border-t pt-3 ${internal ? "border-amber-200" : "border-slate-100"}`}>
            <Composer testid="sa-ticket-reply" placeholder={internal ? "Nota interna: visibile solo al Super Admin" : "Rispondi all'organizzatore..."}
              onSend={async (fd) => { fd.append("internal", internal ? "true" : "false"); await api.post(`/platform/tickets/${t.id}/messages`, fd); setInternal(false); refresh(); }}
              extra={<label className="inline-flex items-center gap-2 text-xs text-slate-600"><Switch checked={internal} onCheckedChange={setInternal} data-testid="sa-ticket-internal-toggle" /><Lock className="w-3.5 h-3.5" />Nota interna</label>} />
          </div>
          {closing && <CloseDialog t={t} onClose={() => setClosing(false)} onDone={refresh} />}
        </>)}
      </DialogContent>
    </Dialog>
  );
}

function Counters({ counts, reopen, status, setStatus }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
      {Object.entries(STATUS_META).map(([k, m]) => (
        <button key={k} type="button" onClick={() => setStatus(status === k ? "" : k)} data-testid={`sa-tickets-counter-${k}`}
          className={`text-left rounded-2xl border bg-white p-4 transition-colors ${status === k ? "border-[#0ABAB5] ring-2 ring-[#0ABAB5]/20" : "border-slate-200 hover:border-[#0ABAB5]/60"}`}>
          <div className="text-xs font-medium text-slate-500">{m.label}</div>
          <div className="mt-1 text-2xl font-bold text-slate-900">{counts?.[k] ?? 0}</div>
          {k === "chiusa" && reopen > 0 && <div className="text-[11px] text-rose-600 font-semibold">{reopen} riapertura richiesta</div>}
        </button>
      ))}
    </div>
  );
}

export default function PlatformTickets() {
  const [data, setData] = useState(null);
  const [f, setF] = useState({ q: "", org_id: "", category: "", status: "", from: "", to: "" });
  const [open, setOpen] = useState(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    const h = setTimeout(() => setF((x) => (x.q === q ? x : { ...x, q })), 350);
    return () => clearTimeout(h);
  }, [q]);
  const seq = useRef(0);
  const params = useMemo(() => Object.fromEntries(Object.entries(f).filter(([, v]) => v)), [f]);
  const load = useCallback(() => {
    const n = ++seq.current;
    return api.get("/platform/tickets", { params }).then(({ data: d }) => { if (n === seq.current) setData(d); }).catch(err);
  }, [params]);
  usePoll(load, [load]);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target ? e.target.value : e }));
  return (
    <div data-testid="sa-tickets-page">
      <PageHeader title="Segnalazioni e richieste" subtitle="Ticket inviati dalle organizzazioni: gestione, risposte e chiusura" />
      <Counters counts={data?.counts} reopen={data?.reopen_requests} status={f.status} setStatus={set("status")} />
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="relative flex-1 min-w-[200px]"><Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca per ID, oggetto, organizzazione, utente" className="pl-9" data-testid="sa-tickets-search" /></div>
        <select value={f.org_id} onChange={set("org_id")} className={sel} data-testid="sa-tickets-filter-org"><option value="">Tutte le organizzazioni</option>{(data?.orgs || []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
        <select value={f.category} onChange={set("category")} className={sel} data-testid="sa-tickets-filter-category"><option value="">Tutte le categorie</option>{Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select value={f.status} onChange={set("status")} className={sel} data-testid="sa-tickets-filter-status"><option value="">Tutti gli stati</option>{Object.entries(STATUS_META).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}<option value="riapertura">Riapertura richiesta</option></select>
        <Input type="date" value={f.from} onChange={set("from")} className="w-auto" aria-label="Dal" data-testid="sa-tickets-filter-from" />
        <Input type="date" value={f.to} onChange={set("to")} className="w-auto" aria-label="Al" data-testid="sa-tickets-filter-to" />
      </div>
      <div className="rounded-2xl border border-slate-200 bg-white overflow-x-auto">
        <table className="w-full min-w-[980px] text-sm" data-testid="sa-tickets-table">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["ID", "Data e ora", "Organizzazione", "Utente", "Categoria", "Oggetto", "Stato", "Ultimo aggiornamento", "Azioni"].map((h) => <th key={h} className="px-3 py-2.5 text-left font-semibold">{h}</th>)}</tr></thead>
          <tbody>
            {!data ? <tr><td colSpan={9} className="p-6 text-slate-400">Caricamento...</td></tr> : !data.tickets.length ? <tr><td colSpan={9} className="p-8 text-center text-slate-500" data-testid="sa-tickets-empty">Nessuna richiesta trovata.</td></tr> : data.tickets.map((t) => (
              <tr key={t.id} className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={() => setOpen(t.id)} data-testid={`sa-ticket-row-${t.number}`}>
                <td className="px-3 py-2.5 font-semibold">#{t.number}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">{dt(t.created_at)}</td>
                <td className="px-3 py-2.5">{t.org_name}</td>
                <td className="px-3 py-2.5">{t.created_by?.name}</td>
                <td className="px-3 py-2.5 text-xs">{CATEGORIES[t.category]}</td>
                <td className="px-3 py-2.5 max-w-[260px] truncate" title={t.subject}>{t.subject}</td>
                <td className="px-3 py-2.5"><StatusBadge t={t} testid={`sa-ticket-status-${t.number}`} /></td>
                <td className="px-3 py-2.5 whitespace-nowrap text-xs text-slate-500">{dt(t.updated_at)}</td>
                <td className="px-3 py-2.5"><Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setOpen(t.id); }} data-testid={`sa-ticket-open-${t.number}`}>Gestisci</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && <Detail id={open} onClose={() => setOpen(null)} onChanged={load} />}
    </div>
  );
}
