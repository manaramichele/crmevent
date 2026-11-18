import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/crm";
import PersonDetailDialog from "@/components/PersonDetailDialog";
import { apiErr, fmtDate } from "@/components/asd/asdShared";

const CLS = { staff: ["Staff", "blue"], volontario: ["Volontario", "green"], da_classificare: ["Da classificare", "orange"], collaboratore: ["Staff", "blue"] };

// Sezione "Staff e Volontari" della scheda socio: dati operativi in sola lettura + apertura della scheda generale (stessa anagrafica).
export function AsdSocioStaff({ socio, onClose, onChanged }) {
  const [d, setD] = useState(null);
  const [events, setEvents] = useState([]);
  const [open, setOpen] = useState(false);
  const load = () => api.get(`/asd/soci/${socio.id}/staff`).then(({ data }) => setD(data)).catch(apiErr);
  useEffect(() => { load(); api.get("/events").then(({ data }) => setEvents(data)).catch(() => setEvents([])); }, [socio.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      <Dialog open={!open} onOpenChange={(v) => !v && onClose()}>
        <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="asd-socio-staff-dialog">
          <DialogHeader><DialogTitle className="font-display">Staff e Volontari — {socio.cognome} {socio.nome}</DialogTitle>
            <DialogDescription>Dati operativi della stessa persona. Eventi, team e disponibilità restano separati dai dati associativi.</DialogDescription></DialogHeader>
          {!d ? <p className="text-sm text-slate-500">Caricamento…</p> : (
            <div className="space-y-4 text-sm">
              <div className="flex flex-wrap gap-1.5" data-testid="asd-socio-staff-cls">
                {d.classificazione.length ? d.classificazione.map((c) => <StatusBadge key={c} color={CLS[c][1]}>{CLS[c][0]}</StatusBadge>) : <span className="text-slate-500">Non presente in Staff / Volontari</span>}
              </div>
              <div><div className="text-xs font-semibold text-slate-500 mb-1">Eventi, team e mansioni</div>
                {d.eventi.length ? <ul className="space-y-1" data-testid="asd-socio-staff-events">{d.eventi.map((e, i) => (
                  <li key={i} className="rounded border border-slate-100 px-3 py-1.5"><b className="font-medium">{e.evento_nome}</b> · {(CLS[e.categoria] || [e.categoria])[0]}{e.team ? ` · Team ${e.team}` : ""}{e.mansione ? ` · ${e.mansione}` : ""}</li>))}</ul>
                  : <p className="text-slate-500">Nessun evento collegato.</p>}</div>
              <div><div className="text-xs font-semibold text-slate-500 mb-1">Disponibilità</div>
                {d.disponibilita.length ? d.disponibilita.map((x, i) => <p key={i} data-testid={`asd-socio-staff-avail-${i}`}><b className="font-medium">{x.evento_nome || "Evento"}</b>: {x.preferenza || "preferenza non indicata"}{x.giorni.length ? ` · ${x.giorni.map(fmtDate).join(", ")}` : ""}</p>)
                  : <p className="text-slate-500">Nessuna disponibilità indicata.</p>}</div>
              <div className="flex flex-col sm:flex-row gap-2 pt-1">
                <Button variant="outline" onClick={() => setOpen(true)} data-testid="asd-socio-open-person">Apri scheda generale della persona</Button>
                <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={() => setOpen(true)} data-testid="asd-socio-add-staff">Aggiungi a Staff / Volontari</Button>
              </div>
              <p className="text-xs text-slate-500">Nella scheda generale premi «Modifica» e, nel tab Eventi, associa la persona a un evento come Staff o Volontario: l'anagrafica non viene ricreata.</p>
            </div>
          )}
        </DialogContent>
      </Dialog>
      {open && d && <PersonDetailDialog personId={d.persona_id} open onOpenChange={(v) => { if (!v) { setOpen(false); load(); onChanged(); } }} events={events} onChanged={load} />}
    </>
  );
}
