import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { calApi, err, fmtD, SEL, Pill, PRIVACY, STATO_COMM } from "./shared";

const FIELDS = [["nome", "Nome società/organizzazione"], ["ragione_sociale", "Ragione sociale"], ["regione", "Regione"], ["provincia", "Provincia"], ["comune", "Comune"],
  ["sito_web", "Sito web"], ["email_generale", "Email generale"], ["email_organizzativa", "Email organizzativa"], ["telefono", "Telefono"], ["cellulare", "Cellulare aziendale pubblico"],
  ["referente", "Referente (solo se utilizzabile lecitamente)"], ["note_commerciali", "Note commerciali"]];
const PCOL = { da_verificare: "#D97706", idoneo: "#16A34A", non_idoneo: "#DC2626", disiscritto: "#64748B", opposizione: "#DC2626" };

function PrivacyBox({ o, onSaved }) {
  const [p, setP] = useState({ status: "da_verificare", ...(o.privacy || {}) });
  const save = async () => { try { await api.put(calApi(`/organizers/${o.id}/privacy`), p); toast.success("Stato privacy aggiornato"); onSaved(); } catch (e) { err(e); } };
  const s = (k) => (e) => setP({ ...p, [k]: e.target.value });
  return (
    <div className="rounded-lg border border-slate-200 p-3 text-xs space-y-2" data-testid="cal-org-privacy">
      <div className="font-semibold">Contattabilità e privacy</div>
      <p className="text-slate-500">Un indirizzo pubblicato online non equivale al consenso. "Idoneo" richiede fonte, finalità e base giuridica documentata, decise dal Super Admin.</p>
      <div className="grid sm:grid-cols-2 gap-2">
        <label>Stato<select className={`${SEL} w-full`} value={p.status} onChange={s("status")} data-testid="cal-privacy-status">{Object.entries(PRIVACY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        {[["fonte", "Fonte del contatto"], ["data_acquisizione", "Data acquisizione"], ["tipo_indirizzo", "Tipologia indirizzo"], ["finalita", "Finalità del trattamento"],
          ["base_giuridica", "Base giuridica documentata"], ["consenso_data", "Data consenso"], ["consenso_prova", "Prova del consenso"], ["note", "Note"]].map(([k, l]) => (
          <label key={k}>{l}<Input value={p[k] || ""} onChange={s(k)} className="h-8" data-testid={`cal-privacy-${k}`} /></label>))}
      </div>
      <Button size="sm" onClick={save} data-testid="cal-privacy-save">Salva privacy</Button>
    </div>
  );
}

function OrgDialog({ id, onClose, onSaved }) {
  const [o, setO] = useState(id ? null : { tipologia: "altro", stato_commerciale: "da_qualificare", escluso_campagne: false });
  const load = useCallback(() => { if (id) api.get(calApi(`/organizers/${id}`)).then(({ data }) => setO(data)).catch(err); }, [id]);
  useEffect(() => { load(); }, [load]);
  const save = async () => {
    const body = Object.fromEntries(Object.entries(o).filter(([k]) => [...FIELDS.map((x) => x[0]), "tipologia", "stato_commerciale", "escluso_campagne"].includes(k)));
    try { await (id ? api.put(calApi(`/organizers/${id}`), body) : api.post(calApi("/organizers"), body)); toast.success("Organizzatore salvato"); onSaved(); } catch (e) { err(e); }
  };
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl w-[calc(100vw-1.5rem)] max-h-[90dvh] overflow-y-auto" data-testid="cal-org-dialog">
        <DialogTitle>{id ? "Organizzatore" : "Nuovo organizzatore"}</DialogTitle>
        {!o ? <p className="text-sm">Caricamento...</p> : <div className="space-y-3 text-xs">
          <div className="grid sm:grid-cols-3 gap-2">
            <label>Tipologia<select className={`${SEL} w-full`} value={o.tipologia} onChange={(e) => setO({ ...o, tipologia: e.target.value })} data-testid="cal-org-tipologia">{["ASD", "SSD", "societa", "ente", "agenzia", "altro"].map((t) => <option key={t}>{t}</option>)}</select></label>
            <label>Stato commerciale<select className={`${SEL} w-full`} value={o.stato_commerciale} onChange={(e) => setO({ ...o, stato_commerciale: e.target.value })} data-testid="cal-org-comm">{Object.entries(STATO_COMM).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <label className="flex items-center gap-2 mt-5"><input type="checkbox" checked={!!o.escluso_campagne} onChange={(e) => setO({ ...o, escluso_campagne: e.target.checked })} data-testid="cal-org-excluded" />Escluso dalle campagne</label>
            {FIELDS.map(([k, l]) => <label key={k} className={k === "nome" || k === "note_commerciali" ? "sm:col-span-3" : ""}>{l}<Input value={o[k] || ""} onChange={(e) => setO({ ...o, [k]: e.target.value })} className="h-9" data-testid={`cal-org-${k}`} /></label>)}
          </div>
          <Button onClick={save} disabled={!o.nome} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="cal-org-save">Salva</Button>
          {id && <>
            <PrivacyBox o={o} onSaved={load} />
            <div className="rounded-lg border border-slate-200 p-3" data-testid="cal-org-events"><div className="font-semibold mb-1">Eventi collegati ({o.events.length})</div>
              {o.events.map((e) => <div key={e.id}>{fmtD(e.data_inizio)} · {e.nome} · {e.comune || ""}</div>)}</div>
            <div className="rounded-lg border border-slate-200 p-3 text-slate-500" data-testid="cal-org-comms">Storico comunicazioni: nessuna (le comunicazioni Brevo arrivano con la Fase 3).</div>
          </>}
        </div>}
      </DialogContent>
    </Dialog>
  );
}

export function OrganizersPanel() {
  const [q, setQ] = useState("");
  const [pf, setPf] = useState("");
  const [d, setD] = useState({ total: 0, rows: [] });
  const [open, setOpen] = useState(undefined);
  const [sel, setSel] = useState([]);
  const load = useCallback(() => api.get(calApi("/organizers"), { params: { q, privacy: pf, limit: 200 } }).then(({ data }) => setD(data)).catch(err), [q, pf]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  const merge = async () => {
    if (!window.confirm(`Unire ${sel.length} organizzatori nel primo selezionato? Gli eventi verranno spostati.`)) return;
    try { await api.post(calApi("/organizers/merge"), { keep_id: sel[0], merge_ids: sel.slice(1) }); toast.success("Organizzatori uniti"); setSel([]); load(); } catch (e) { err(e); }
  };
  return (
    <div className="space-y-3" data-testid="cal-organizers">
      <div className="flex flex-wrap gap-2">
        <Input placeholder="Cerca organizzatore" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 w-64" data-testid="cal-org-search" />
        <select className={SEL} value={pf} onChange={(e) => setPf(e.target.value)} data-testid="cal-org-filter-privacy"><option value="">Privacy: tutti</option>{Object.entries(PRIVACY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        {sel.length > 1 && <Button size="sm" variant="outline" onClick={merge} data-testid="cal-org-merge">Unisci {sel.length} selezionati</Button>}
        <Button size="sm" onClick={() => setOpen(null)} className="ml-auto bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900" data-testid="cal-org-new"><Plus className="w-4 h-4 mr-1" />Nuovo organizzatore</Button>
      </div>
      <div className="text-xs text-slate-500">{d.total} organizzatori</div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full min-w-[820px] text-sm" data-testid="cal-org-table">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr>{["", "Organizzatore", "Località", "Email", "Eventi", "Privacy", "Stato commerciale", ""].map((h, i) => <th key={i} className="px-3 py-2 text-left">{h}</th>)}</tr></thead>
        <tbody>{d.rows.map((o) => (
          <tr key={o.id} className="border-t border-slate-100" data-testid={`cal-org-row-${o.id}`}>
            <td className="px-3 py-2"><input type="checkbox" checked={sel.includes(o.id)} onChange={(e) => setSel(e.target.checked ? [...sel, o.id] : sel.filter((x) => x !== o.id))} data-testid={`cal-org-sel-${o.id}`} /></td>
            <td className="px-3 py-2 font-medium">{o.nome}<div className="text-[11px] text-slate-400">{o.tipologia}{o.escluso_campagne ? " · escluso campagne" : ""}</div></td>
            <td className="px-3 py-2 text-xs">{[o.comune, o.provincia, o.regione].filter(Boolean).join(" · ") || "—"}</td>
            <td className="px-3 py-2 text-xs">{o.email_generale || o.email_organizzativa || "—"}</td>
            <td className="px-3 py-2">{o.eventi}</td>
            <td className="px-3 py-2"><Pill color={PCOL[o.privacy?.status || "da_verificare"]}>{PRIVACY[o.privacy?.status || "da_verificare"]}</Pill></td>
            <td className="px-3 py-2 text-xs">{STATO_COMM[o.stato_commerciale]}</td>
            <td className="px-3 py-2"><Button size="sm" variant="outline" onClick={() => setOpen(o.id)} data-testid={`cal-org-open-${o.id}`}>Apri</Button></td>
          </tr>))}</tbody>
      </table></div>
      {open !== undefined && <OrgDialog id={open} onClose={() => setOpen(undefined)} onSaved={() => { setOpen(undefined); load(); }} />}
    </div>
  );
}
