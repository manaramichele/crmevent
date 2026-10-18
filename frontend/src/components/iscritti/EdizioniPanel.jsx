import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Trash2 } from "lucide-react";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const SEL = "h-10 rounded-md border border-slate-200 px-3 text-sm bg-white w-full min-w-0";

// Edizioni (anche storiche) collegate agli eventi CRMEvent.
export function EdizioniPanel({ data, canEdit, onChanged }) {
  const [f, setF] = useState({ event_id: "", anno: new Date().getFullYear(), edizione: "", gare: "" });
  const add = async () => {
    try { await api.post("/iscritti/edizioni", { ...f, anno: Number(f.anno), gare: f.gare.split(",").map((g) => g.trim()).filter(Boolean) }); toast.success("Edizione creata"); setF({ ...f, edizione: "", gare: "" }); onChanged(); } catch (e) { err(e); }
  };
  const del = async (id) => { try { await api.delete(`/iscritti/edizioni/${id}`); onChanged(); } catch (e) { err(e); } };
  return (
    <div className="space-y-4" data-testid="edizioni-panel">
      {canEdit && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 grid sm:grid-cols-5 gap-2">
          <select className={`${SEL} sm:col-span-2`} value={f.event_id} onChange={(e) => setF({ ...f, event_id: e.target.value })} data-testid="edizione-event"><option value="">Evento CRMEvent...</option>{data.events.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</select>
          <Input type="number" value={f.anno} onChange={(e) => setF({ ...f, anno: e.target.value })} aria-label="Anno" data-testid="edizione-anno" />
          <Input placeholder="Edizione (es. 26ª)" value={f.edizione} onChange={(e) => setF({ ...f, edizione: e.target.value })} data-testid="edizione-label" />
          <Input placeholder="Gare (virgola)" value={f.gare} onChange={(e) => setF({ ...f, gare: e.target.value })} data-testid="edizione-gare" />
          <Button className="sm:col-span-5 sm:justify-self-end bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" disabled={!f.event_id} onClick={add} data-testid="edizione-add">+ Crea edizione</Button>
          <p className="sm:col-span-5 text-xs text-slate-500">Puoi creare anche edizioni di anni passati per importare lo storico, collegandole all'evento già presente in CRMEvent.</p>
        </div>
      )}
      <div className="bg-white border border-slate-200 rounded-xl divide-y" data-testid="edizioni-list">
        {data.edizioni.length === 0 && <p className="p-4 text-sm text-slate-500">Nessuna edizione.</p>}
        {data.edizioni.map((e) => (
          <div key={e.id} className="p-3 flex flex-wrap items-center gap-2 text-sm" data-testid={`edizione-${e.id}`}>
            <strong>{e.event_nome}</strong><span>{e.anno} {e.edizione}</span><span className="text-slate-500">{(e.gare || []).join(", ")}</span>
            <span className="ml-auto text-slate-600">{e.iscritti} iscrizioni</span>
            {canEdit && e.iscritti === 0 && <Button size="icon" variant="ghost" onClick={() => del(e.id)} aria-label="Elimina edizione"><Trash2 className="w-4 h-4" /></Button>}
          </div>
        ))}
      </div>
    </div>
  );
}

const dt = (s) => (s ? new Date(s).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—");
export function ImportsPanel({ rows }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto" data-testid="imports-history">
      <table className="w-full min-w-[720px] text-sm">
        <thead><tr className="text-left text-xs text-slate-500 border-b"><th className="p-3">Data</th><th>File</th><th>Edizione</th><th>Stato</th><th>Risultato</th><th>Utente</th></tr></thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={6} className="p-4 text-slate-500">Nessuna importazione.</td></tr>}
          {rows.map((r) => (
            <tr key={r.id} className="border-b last:border-0">
              <td className="p-3 whitespace-nowrap">{dt(r.created_at)}</td><td className="break-all">{r.filename}</td><td>{r.anno} {r.edizione} {r.gara}</td><td>{r.status}</td>
              <td className="text-xs">{r.result ? `+${r.result.created} nuovi · ${r.result.updated} agg. · ${r.result.participations} partecipazioni · ${r.result.errors} errori` : "—"}</td><td>{r.created_by?.name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
