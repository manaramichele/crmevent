import { useEffect, useState } from "react";
import { sortIt } from "@/lib/sortOptions";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { FileSpreadsheet, FileText, Users, User, MapPin } from "lucide-react";
import { useSettings } from "@/components/crm";
import { ADD_OPTION } from "@/lib/optionLists";
import InlineAddOption from "@/components/InlineAddOption";

export const KIND = { team: ["Team", "#0F766E"], staff: ["Staff", "#2563EB"], volontario: ["Volontario", "#16A34A"], generica: ["Senza assegnazione", "#94A3B8"] };
const TIPI = ["Ristoro", "Incrocio", "Partenza", "Arrivo", "Deposito borse", "Expo", "Area sponsor", "Sicurezza percorso", "Altro"];
const lbl = "space-y-1 text-xs text-slate-500";

export function StationDialog({ open, feature, eid, pid, onClose, onSaved }) {
  const [ppl, setPpl] = useState(null);
  const [f, setF] = useState({});
  const settings = useSettings();
  const [addT, setAddT] = useState(false);
  useEffect(() => {
    if (!open || !feature) return;
    const st = feature.properties.station || {};
    setF({ kind: "generica", nome: feature.properties.nome || "Postazione", tipologia: "", ruolo: "", data: "", ora_inizio: "", ora_fine: "", note: "", team_id: "", ...st });
    api.get(`/planner/events/${eid}/people`).then(({ data }) => setPpl(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
  }, [open, feature, eid, pid]);
  if (!open || !feature) return null;
  const team = ppl?.teams.find((t) => t.id === f.team_id);
  const save = async () => {
    const body = { ...f, persona_ids: [], team_id: f.kind === "team" ? f.team_id || null : null, force: false };
    ["tipologia", "ruolo", "data", "ora_inizio", "ora_fine", "note"].forEach((k) => { if (!body[k]) body[k] = null; });
    try {
      await api.post(`/planner/projects/${pid}/stations/${feature.properties.id}`, body);
      const station = { kind: f.kind, nome: f.nome, tipologia: body.tipologia, ruolo: body.ruolo, data: body.data, ora_inizio: body.ora_inizio, ora_fine: body.ora_fine, note: body.note, team_id: body.team_id };
      onSaved(station, 0); toast.success("Postazione salvata");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };
  const set = (p) => setF({ ...f, ...p });
  const tipi = (settings && settings.tipi_postazione) || TIPI;
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto" data-testid="station-dialog">
        <DialogHeader><DialogTitle>Postazione staff / volontari</DialogTitle><DialogDescription>Indica nome, tipologia, ruolo operativo ed eventuale Team della postazione.</DialogDescription></DialogHeader>
        <div className="flex flex-wrap gap-1">{Object.entries(KIND).map(([k, [l, c]]) => <button key={k} type="button" onClick={() => set({ kind: k })} className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${f.kind === k ? "text-white" : "text-slate-700"}`} style={f.kind === k ? { background: c, borderColor: c } : {}} data-testid={`station-kind-${k}`}>{k === "generica" ? "Postazione generica" : l}</button>)}</div>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className={lbl}>Nome postazione<Input value={f.nome} onChange={(e) => set({ nome: e.target.value })} className="h-8 text-sm" data-testid="station-nome" /></label>
          <label className={lbl}>Tipologia<select value={f.tipologia || ""} onChange={(e) => { if (e.target.value === ADD_OPTION) setAddT(true); else set({ tipologia: e.target.value }); }} className="h-8 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="station-tipologia"><option value="">–</option>{sortIt([...new Set([...tipi, ...(f.tipologia ? [f.tipologia] : [])])]).map((t) => <option key={t}>{t}</option>)}<option value={ADD_OPTION}>+ Aggiungi</option></select>{addT && <InlineAddOption listKey="tipi_postazione" small testid="station-tipologia-add" onDone={(v) => { setAddT(false); if (v) set({ tipologia: v }); }} />}</label>
          <label className={lbl}>Ruolo operativo<Input value={f.ruolo || ""} onChange={(e) => set({ ruolo: e.target.value })} className="h-8 text-sm" data-testid="station-ruolo" /></label>
        </div>
        <label className={lbl}>Note<Input value={f.note || ""} onChange={(e) => set({ note: e.target.value })} className="h-8 text-sm" data-testid="station-note" /></label>
        {f.kind === "team" && <label className={lbl}>Team<select value={f.team_id || ""} onChange={(e) => set({ team_id: e.target.value })} className="h-8 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="station-team">
          <option value="">Scegli il team…</option>{sortIt(ppl?.teams, (t) => t.nome).map((t) => <option key={t.id} value={t.id}>{t.nome} · {t.membri.length} persone</option>)}</select></label>}
        {team && <p className="text-xs text-slate-600" data-testid="station-team-info">Responsabile: <b>{team.responsabile || "–"}</b> · componenti: {team.membri.length}.</p>}
        <DialogFooter className="gap-2"><Button variant="outline" onClick={onClose} data-testid="station-cancel">Annulla</Button>
          <Button disabled={!f.nome?.trim() || (f.kind === "team" && !f.team_id)} onClick={save} className="bg-tiffany text-slate-900 hover:bg-tiffany-hover" data-testid="station-save">Salva postazione</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RoutesDialog({ open, eid, onClose, onImport }) {
  const [list, setList] = useState(null);
  useEffect(() => { if (open) api.get(`/planner/events/${eid}/routes`).then(({ data }) => setList(data.routes)).catch(() => setList([])); }, [open, eid]);
  const pick = async (r) => {
    try { const { data } = await api.get(`/planner/events/${eid}/routes/${r.map_id}`); onImport(data); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent data-testid="routes-dialog">
        <DialogHeader><DialogTitle>Importa percorso evento</DialogTitle><DialogDescription>Percorsi GPX, KML e KMZ già caricati in Percorsi Eventi: il tracciato resta collegato all'originale, senza copie del file.</DialogDescription></DialogHeader>
        {!list ? <p className="text-sm text-slate-400">Caricamento…</p> : !list.length ? <p className="text-sm text-slate-500" data-testid="routes-empty">Nessun percorso GPX/KML/KMZ in Percorsi Eventi per questo evento.</p>
          : <div className="divide-y rounded-md border border-slate-200">{list.map((r) => <button key={r.map_id} type="button" onClick={() => pick(r)} className="flex w-full items-center gap-2 p-2 text-left text-sm hover:bg-slate-50" data-testid={`routes-item-${r.map_id}`}>
            <MapPin className="h-4 w-4 text-tiffany" /><span className="flex-1"><b>{r.nome}</b><span className="block text-xs text-slate-500">{r.format}{r.distance ? ` · ${r.distance} km` : ""} · aggiornato il {new Date(r.updated_at).toLocaleDateString("it-IT")}</span></span></button>)}</div>}
      </DialogContent>
    </Dialog>
  );
}

const get = async (url, name) => {
  try { const { data } = await api.get(url, { responseType: "blob" }); const u = URL.createObjectURL(data); const a = document.createElement("a"); a.href = u; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(u), 60000); }
  catch { toast.error("Esportazione non riuscita"); }
};

export function AssignPanel({ open, eid, pid, onClose }) {
  const [d, setD] = useState(null);
  const [scope, setScope] = useState("project");
  const q = scope === "project" ? `?project=${pid}` : "";
  useEffect(() => { if (open) api.get(`/planner/events/${eid}/assignments${q}`).then(({ data }) => setD(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))); }, [open, eid, q]);
  const c = d?.counts || {};
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[92dvh] w-[96vw] max-w-4xl overflow-y-auto" data-testid="assign-panel">
        <DialogHeader><DialogTitle>Riepilogo postazioni</DialogTitle></DialogHeader>
        <div className="flex flex-wrap items-center gap-2">
          <select value={scope} onChange={(e) => setScope(e.target.value)} className="h-8 rounded-md border border-slate-200 px-2 text-xs" data-testid="assign-scope"><option value="project">Progetto corrente</option><option value="event">Tutti i progetti dell'evento</option></select>
          <div className="ml-auto flex gap-2"><Button size="sm" variant="outline" onClick={() => get(`/planner/events/${eid}/assignments/export.xlsx${q}`, "assegnazioni.xlsx")} data-testid="assign-xlsx"><FileSpreadsheet className="mr-1 h-4 w-4" />Excel</Button>
            <Button size="sm" variant="outline" onClick={() => get(`/planner/events/${eid}/assignments/export.pdf${q}`, "assegnazioni.pdf")} data-testid="assign-pdf"><FileText className="mr-1 h-4 w-4" />PDF</Button></div>
        </div>
        {d && <>
          <div className="grid grid-cols-2 gap-2" data-testid="assign-counts">{[["Postazioni", c.postazioni], ["Team", c.team]].map(([l, v]) =>
            <div key={l} className="rounded-lg bg-slate-50 p-2 text-center"><div className="text-lg font-bold">{v}</div><div className="text-[11px] text-slate-500">{l}</div></div>)}</div>
          <div className="divide-y rounded-md border border-slate-200 text-sm">{d.rows.map((r) => <div key={r.station_id} className="flex flex-wrap items-start gap-2 p-2" data-testid={`assign-row-${r.station_id}`}>
            <span className="mt-1 h-3 w-3 rounded-full" style={{ background: (KIND[r.kind] || KIND.generica)[1] }} />
            <span className="flex-1"><b>{r.nome}</b>{r.tipologia ? ` · ${r.tipologia}` : ""}{scope === "event" ? ` · ${r.progetto}` : ""}
              <span className="block text-xs text-slate-500">{r.team ? <><Users className="inline h-3 w-3" /> Team {r.team}</> : "Senza Team"}{r.ruolo ? ` · ${r.ruolo}` : ""}{r.note ? ` · ${r.note}` : ""}</span></span></div>)}
            {!d.rows.length && <p className="p-3 text-sm text-slate-500"><User className="inline h-4 w-4" /> Nessuna postazione: usa lo strumento Staff e volontari e clicca sulla mappa.</p>}</div>
        </>}
      </DialogContent>
    </Dialog>
  );
}

export const stationMatch = (f, flt, staffLayerId = "staff") => {
  const st = f.properties.station;
  if (!flt.kind && !flt.ruolo && !flt.data) return true;
  if (!st) return f.properties.layer_id !== staffLayerId;
  return (!flt.kind || (flt.kind === "assegnate" ? st.kind !== "generica" : st.kind === flt.kind)) && (!flt.ruolo || (st.ruolo || "").toLowerCase().includes(flt.ruolo.toLowerCase())) && (!flt.data || st.data === flt.data);
};

export function StaffFilter({ flt, setFlt }) {
  const s = "h-8 rounded-md border border-slate-200 px-1 text-xs";
  return (
    <div className="flex flex-wrap gap-1" data-testid="staff-filter">
      <select value={flt.kind} onChange={(e) => setFlt({ ...flt, kind: e.target.value })} className={s} data-testid="staff-filter-kind"><option value="">Tutte le postazioni</option><option value="team">Team</option><option value="staff">Staff</option><option value="volontario">Volontari</option><option value="assegnate">Assegnate</option><option value="generica">Senza assegnazione</option></select>
      <Input value={flt.ruolo} onChange={(e) => setFlt({ ...flt, ruolo: e.target.value })} placeholder="Ruolo" className="h-8 w-24 text-xs" data-testid="staff-filter-ruolo" />
    </div>
  );
}
