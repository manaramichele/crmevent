import { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { calApi, err, fmtD } from "./shared";

const Row = ({ x, why }) => (
  <tr className="border-t border-slate-100">
    <td className="px-2 py-1">{x.organizzatore || "—"}<div className="text-[11px] text-slate-400">{x.email || "senza email"}</div></td>
    <td className="px-2 py-1">{x.evento}<div className="text-[11px] text-slate-400">{fmtD(x.data_evento)} · {x.comune || "—"}</div></td>
    <td className="px-2 py-1">{fmtD(x.data_comunicazione)}</td>
    {why && <td className="px-2 py-1 text-amber-700">{x.motivo}</td>}
  </tr>
);

const Table = ({ rows, why, testid }) => (
  <div className="overflow-x-auto max-h-72 overflow-y-auto border border-slate-200 rounded-lg"><table className="w-full min-w-[560px] text-xs" data-testid={testid}>
    <thead className="bg-slate-50 text-slate-500 sticky top-0"><tr><th className="px-2 py-1 text-left">Organizzatore</th><th className="px-2 py-1 text-left">Evento</th><th className="px-2 py-1 text-left">Data comunicazione</th>{why && <th className="px-2 py-1 text-left">Motivo</th>}</tr></thead>
    <tbody>{rows.map((x) => <Row key={`${x.event_id}`} x={x} why={why} />)}</tbody>
  </table></div>
);

export function RecipientsPreview({ prev, filters, onDone }) {
  const [conf, setConf] = useState("");
  const [busy, setBusy] = useState(false);
  const ready = prev.template.su_brevo && prev.mittente;
  const send = async (simulazione) => {
    setBusy(true);
    try {
      const { data } = await api.post(calApi("/campaigns/send"), { ...filters, dal: prev.dal, al: prev.al, firma: prev.firma, conferma: conf, simulazione });
      toast.success(simulazione ? `Simulazione avviata su ${data.destinatari} destinatari (nessuna email inviata)` : `Invio avviato a ${data.destinatari} destinatari`);
      onDone();
    } catch (e) { err(e); }
    setBusy(false);
  };
  return (
    <div className="space-y-3 border-t border-slate-100 pt-3" data-testid="cal-recipients-preview">
      <div className="text-xs text-slate-600">Template <b>{prev.template.nome}</b> · oggetto "{prev.template.oggetto}" · periodo {fmtD(prev.dal)} – {fmtD(prev.al)} · mittente {prev.mittente ? `${prev.mittente.name} <${prev.mittente.email}>` : "non scelto"}</div>
      <div className="font-semibold text-sm">Riceveranno l'email: <span data-testid="cal-preview-included-count">{prev.inclusi.length}</span></div>
      {prev.inclusi.length ? <Table rows={prev.inclusi} testid="cal-preview-included" /> : <p className="text-xs text-slate-500">Nessun destinatario idoneo nel periodo scelto.</p>}
      <div className="font-semibold text-sm">Esclusi: <span data-testid="cal-preview-excluded-count">{prev.esclusi.length}</span></div>
      {!!prev.esclusi.length && <Table rows={prev.esclusi} why testid="cal-preview-excluded" />}
      {!!prev.inclusi.length && <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 space-y-2">
        {!ready && <p className="text-xs text-amber-800">Per l'invio reale servono il mittente (Impostazioni) e il template salvato su Brevo. Puoi comunque fare una simulazione.</p>}
        <p className="text-xs text-amber-800">Scrivi <b>INVIA</b> per confermare. Se i destinatari cambiano prima dell'invio, ti verrà chiesto di rifare l'anteprima.</p>
        <div className="flex flex-wrap gap-2"><Input value={conf} onChange={(e) => setConf(e.target.value)} placeholder="INVIA" className="h-9 w-32" data-testid="cal-send-confirm" />
          <Button variant="outline" disabled={busy || conf.trim().toUpperCase() !== "INVIA"} onClick={() => send(true)} data-testid="cal-send-simulate">Simula invio</Button>
          <Button disabled={busy || !ready || conf.trim().toUpperCase() !== "INVIA"} onClick={() => send(false)} className="bg-red-600 hover:bg-red-700 text-white" data-testid="cal-send-real">Invia {prev.inclusi.length} email</Button></div>
      </div>}
    </div>
  );
}
