import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Trash2, RotateCcw, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";

export function DeleteRequestButton({ person, eventIds, events, onDone, testid }) {
  const [open, setOpen] = useState(false);
  const [ev, setEv] = useState(eventIds[0] || "");
  const [busy, setBusy] = useState(false);
  const name = `${person.nome || ""} ${person.cognome || ""}`.trim();
  const evName = (id) => events.find((e) => e.id === id)?.nome || "evento";
  const go = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/da-classificare/delete", { persona_id: person.id, evento_id: ev });
      toast.success(data.person_deleted ? "Richiesta e anagrafica eliminate" : "Richiesta eliminata");
      setOpen(false); onDone();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setBusy(false);
  };
  if (!eventIds.length) return null;
  return (
    <>
      <Button variant="ghost" size="sm" className="h-8 px-2 text-slate-500 hover:text-red-600" onClick={() => { setEv(eventIds[0]); setOpen(true); }} data-testid={testid || `delete-request-${person.id}`}>
        <Trash2 className="w-4 h-4 mr-1" />Elimina richiesta
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent onClick={(e) => e.stopPropagation()} data-testid={`delete-request-dialog-${person.id}`}>
          <DialogHeader>
            <DialogTitle>Elimina richiesta</DialogTitle>
            <DialogDescription>Vuoi eliminare la richiesta di <b>{name}</b> per l'evento <b>{evName(ev)}</b>? La richiesta non comparirà più nella sezione Da classificare.</DialogDescription>
          </DialogHeader>
          {eventIds.length > 1 && (
            <label className="text-sm text-slate-600 space-y-1">Evento
              <select className="h-9 w-full rounded-md border border-slate-200 px-2" value={ev} onChange={(e) => setEv(e.target.value)} data-testid="delete-request-event">
                {eventIds.map((id) => <option key={id} value={id}>{evName(id)}</option>)}
              </select>
            </label>)}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} data-testid="delete-request-cancel">Annulla</Button>
            <Button className="bg-red-500 hover:bg-red-600" disabled={busy} onClick={go} data-testid="delete-request-confirm"><Trash2 className="w-4 h-4 mr-1" />Elimina richiesta</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function DeletedRequestsButton({ onRestored }) {
  const [open, setOpen] = useState(false);
  const [list, setList] = useState(null);
  const load = () => api.get("/admin/deleted-requests").then(({ data }) => setList(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  useEffect(() => { if (open) { load(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const restore = async (b) => {
    try { await api.post(`/admin/deleted-requests/${b}/restore`); toast.success("Richiesta ripristinata"); load(); onRestored(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} data-testid="deleted-requests-open"><Archive className="w-4 h-4 mr-1" />Richieste eliminate</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="deleted-requests-dialog">
          <DialogHeader><DialogTitle>Richieste Da classificare eliminate</DialogTitle><DialogDescription>Visibile solo al Super Admin. Il ripristino riporta richiesta, disponibilità e anagrafica.</DialogDescription></DialogHeader>
          {!list ? <p className="text-sm text-slate-400">Caricamento…</p> : !list.length ? <p className="text-sm text-slate-400" data-testid="deleted-requests-empty">Nessuna richiesta eliminata.</p> : (
            <div className="divide-y divide-slate-100">
              {list.map((b) => (
                <div key={b.batch_id} className="py-2 flex flex-col sm:flex-row sm:items-center gap-2" data-testid={`deleted-request-${b.batch_id}`}>
                  <div className="flex-1 text-sm"><div className="font-medium text-slate-800">{b.persona_nome} · {b.evento_nome}</div>
                    <div className="text-xs text-slate-500">Eliminata il {new Date(b.deleted_at).toLocaleString("it-IT")} da {b.deleted_by}{b.items.includes("persons") ? " · anagrafica inclusa" : ""}</div></div>
                  <Button size="sm" variant="outline" onClick={() => restore(b.batch_id)} data-testid={`restore-request-${b.batch_id}`}><RotateCcw className="w-4 h-4 mr-1" />Ripristina</Button>
                </div>))}
            </div>)}
        </DialogContent>
      </Dialog>
    </>
  );
}
