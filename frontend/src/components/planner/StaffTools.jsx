import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { FileSpreadsheet, FileText, Users, User, MapPin } from "lucide-react";

export const KIND = { team: ["Team", "#0F766E"], staff: ["Staff", "#2563EB"], volontario: ["Volontario", "#16A34A"], generica: ["Senza assegnazione", "#94A3B8"] };
const TIPI = ["Ristoro", "Incrocio", "Partenza", "Arrivo", "Deposito borse", "Expo", "Area sponsor", "Sicurezza percorso", "Altro"];
const lbl = "space-y-1 text-xs text-slate-500";

function PersonPick({ list, sel, setSel }) {
  const [q, setQ] = useState("");
  const vis = list.filter((p) => p.nome.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="space-y-1">
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca per nome…" className="h-8 text-xs" data-testid="st-person-search" />
      <div className="max-h-44 overflow-y-auto rounded-md border border-slate-200 divide-y">
        {vis.map((p) => <label key={p.persona_id} className="flex items-start gap-2 p-2 text-xs" data-testid={`st-person-${p.persona_id}`}>
          <input type="checkbox" checked={sel.includes(p.persona_id)} onChange={(e) => setSel(e.target.checked ? [...sel, p.persona_id] : sel.filter((x) => x !== p.persona_id))} />
          <span className="flex-1"><b>{p.nome}</b> · {p.categoria === "volontario" ? "Volontario" : "Staff"}{p.ruolo ? ` · ${p.ruolo}` : ""}{p.team_nome ? ` · Team ${p.team_nome}` : ""}
            {p.disponibilita && <span className="block text-slate-500">Disponibilità: {p.disponibilita}{p.stato ? ` (${p.stato.replace(/_/g, " ")})` : ""}</span>}
            {p.turni.length > 0 && <span className="block text-amber-700">Già assegnato: {p.turni.map((t) => `${t.luogo || "turno"} ${t.data || ""} ${t.ora_inizio || ""}-${t.ora_fine || ""}`).join("; ")}</span>}</span>
        </label>)}
        {!vis.length && <p className="p-2 text-xs text-slate-400">Nessuna persona trovata tra lo staff e i volontari dell'evento.</p>}
      </div>
    </div>
  );
}

export function StationDialog({ open, feature, eid, pid, onClose, onSaved }) {
  const [ppl, setPpl] = useState(null);
  const [f, setF] = useState({});
  const [sel, setSel] = useState([]);
  const [conf, setConf] = useState(null);
  useEffect(() => {
    if (!open || !feature) return;
    const st = feature.properties.station || {};
    setF({ kind: "generica", nome: feature.properties.nome || "Postazione", tipologia: "", ruolo: "", data: "", ora_inizio: "", ora_fine: "", note: "", team_id: "", ...st });
    setConf(null);
    api.get(`/planner/events/${eid}/people`).then(({ data }) => setPpl(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail)));
    api.get(`/planner/projects/${pid}/stations`).then(({ data }) => setSel((data.stations[feature.properties.id] || []).map((s) => s.persona_id)));
  }, [open, feature, eid, pid]);
  if (!open || !feature) return null;
  const team = ppl?.teams.find((t) => t.id === f.team_id);
  const list = (ppl?.people || []).filter((p) => (f.kind === "team" ? p.team_id === f.team_id : p.categoria === f.kind));
  const save = async (force) => {
    const body = { ...f, persona_ids: f.kind === "generica" ? [] : sel, team_id: f.kind === "team" ? f.team_id || null : null, force };
    ["tipologia", "ruolo", "data", "ora_inizio", "ora_fine", "note"].forEach((k) => { if (!body[k]) body[k] = null; });
    try {
      const { data } = await api.post(`/planner/projects/${pid}/stations/${feature.properties.id}`, body);
      const station = { kind: f.kind, nome: f.nome, tipologia: body.tipologia, ruolo: body.ruolo, data: body.data, ora_inizio: body.ora_inizio, ora_fine: body.ora_fine, note: body.note, team_id: body.team_id };
      onSaved(station, data.shifts.length); toast.success(data.shifts.length ? `${data.shifts.length} persone assegnate: turni aggiornati in Staff e Volontari` : "Postazione salvata");
    } catch (e) {
      const d = e.response?.data?.detail;
      if (d?.code === "staff_conflict") setConf(d.conflicts); else toast.error(formatApiError(d));
    }
  };
  const set = (p) => setF({ ...f, ...p });
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto" data-testid="station-dialog">
        <DialogHeader><DialogTitle>Assegna staff / volontari</DialogTitle><DialogDescription>I turni vengono registrati in Staff e Volontari dell'evento. Una disponibilità non diventa una conferma di partecipazione.</DialogDescription></DialogHeader>
        <div className="flex flex-wrap gap-1">{Object.entries(KIND).map(([k, [l, c]]) => <button key={k} type="button" onClick={() => { set({ kind: k }); setSel([]); }} className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${f.kind === k ? "text-white" : "text-slate-700"}`} style={f.kind === k ? { background: c, borderColor: c } : {}} data-testid={`station-kind-${k}`}>{k === "generica" ? "Postazione generica" : l}</button>)}</div>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className={lbl}>Nome postazione<Input value={f.nome} onChange={(e) => set({ nome: e.target.value })} className="h-8 text-sm" data-testid="station-nome" /></label>
          <label className={lbl}>Tipologia<select value={f.tipologia || ""} onChange={(e) => set({ tipologia: e.target.value })} className="h-8 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="station-tipologia"><option value="">–</option>{TIPI.map((t) => <option key={t}>{t}</option>)}</select></label>
          <label className={lbl}>Ruolo operativo<Input value={f.ruolo || ""} onChange={(e) => set({ ruolo: e.target.value })} className="h-8 text-sm" data-testid="station-ruolo" /></label>
          <label className={lbl}>Data<Input type="date" value={f.data || ""} onChange={(e) => set({ data: e.target.value })} className="h-8 text-sm" data-testid="station-data" /></label>
          <label className={lbl}>Inizio<Input type="time" value={f.ora_inizio || ""} onChange={(e) => set({ ora_inizio: e.target.value })} className="h-8 text-sm" data-testid="station-inizio" /></label>
          <label className={lbl}>Fine<Input type="time" value={f.ora_fine || ""} onChange={(e) => set({ ora_fine: e.target.value })} className="h-8 text-sm" data-testid="station-fine" /></label>
        </div>
        <label className={lbl}>Note<Input value={f.note || ""} onChange={(e) => set({ note: e.target.value })} className="h-8 text-sm" data-testid="station-note" /></label>
        {f.kind === "team" && <label className={lbl}>Team<select value={f.team_id || ""} onChange={(e) => { const t = ppl?.teams.find((x) => x.id === e.target.value); set({ team_id: e.target.value }); setSel((t?.membri || []).map((m) => m.persona_id)); }} className="h-8 w-full rounded-md border border-slate-200 px-2 text-sm" data-testid="station-team">
          <option value="">Scegli il team…</option>{(ppl?.teams || []).map((t) => <option key={t.id} value={t.id}>{t.nome} · {t.membri.length} persone</option>)}</select></label>}
        {team && <p className="text-xs text-slate-600" data-testid="station-team-info">Responsabile: <b>{team.responsabile || "–"}</b> · componenti: {team.membri.length}. Deseleziona chi non è assegnato a questa postazione.</p>}
        {f.kind !== "generica" && (f.kind !== "team" || team) && <PersonPick list={list} sel={sel} setSel={setSel} />}
        {conf && <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900" data-testid="station-conflicts"><b>Turni sovrapposti:</b>{conf.map((c, i) => <div key={i}>{c.nome}: {c.luogo || "turno"} {c.data} {c.ora_inizio || ""}-{c.ora_fine || ""}</div>)}</div>}
        <DialogFooter className="gap-2"><Button variant="outline" onClick={onClose} data-testid="station-cancel">Annulla</Button>
          {conf ? <Button onClick={() => save(true)} className="bg-amber-500 text-slate-900 hover:bg-amber-400" data-testid="station-force">Assegna comunque</Button>
            : <Button disabled={!f.nome?.trim() || (f.kind === "team" && !f.team_id)} onClick={() => save(false)} className="bg-tiffany text-slate-900 hover:bg-tiffany-hover" data-testid="station-save">Salva postazione</Button>}</DialogFooter>
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
        <DialogHeader><DialogTitle>Riepilogo assegnazioni</DialogTitle></DialogHeader>
        <div className="flex flex-wrap items-center gap-2">
          <select value={scope} onChange={(e) => setScope(e.target.value)} className="h-8 rounded-md border border-slate-200 px-2 text-xs" data-testid="assign-scope"><option value="project">Progetto corrente</option><option value="event">Tutti i progetti dell'evento</option></select>
          <div className="ml-auto flex gap-2"><Button size="sm" variant="outline" onClick={() => get(`/planner/events/${eid}/assignments/export.xlsx${q}`, "assegnazioni.xlsx")} data-testid="assign-xlsx"><FileSpreadsheet className="mr-1 h-4 w-4" />Excel</Button>
            <Button size="sm" variant="outline" onClick={() => get(`/planner/events/${eid}/assignments/export.pdf${q}`, "assegnazioni.pdf")} data-testid="assign-pdf"><FileText className="mr-1 h-4 w-4" />PDF</Button></div>
        </div>
        {d && <>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-6" data-testid="assign-counts">{[["Postazioni", c.postazioni], ["Coperte", c.coperte], ["Senza personale", c.scoperte], ["Team", c.team], ["Staff", c.staff], ["Volontari", c.volontari]].map(([l, v]) =>
            <div key={l} className="rounded-lg bg-slate-50 p-2 text-center"><div className="text-lg font-bold">{v}</div><div className="text-[11px] text-slate-500">{l}</div></div>)}</div>
          {d.conflicts.length > 0 && <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900" data-testid="assign-conflicts"><b>Conflitti di orario ({d.conflicts.length})</b>{d.conflicts.map((x, i) => <div key={i}>{x.nome} · {x.data}: {x.a} / {x.b}</div>)}</div>}
          <div className="divide-y rounded-md border border-slate-200 text-sm">{d.rows.map((r) => <div key={r.station_id} className="flex flex-wrap items-start gap-2 p-2" data-testid={`assign-row-${r.station_id}`}>
            <span className="mt-1 h-3 w-3 rounded-full" style={{ background: (KIND[r.kind] || KIND.generica)[1] }} />
            <span className="flex-1"><b>{r.nome}</b>{r.tipologia ? ` · ${r.tipologia}` : ""}{scope === "event" ? ` · ${r.progetto}` : ""}
              <span className="block text-xs text-slate-500">{r.team ? <><Users className="inline h-3 w-3" /> Team {r.team} · </> : null}{r.persone.length ? r.persone.map((p) => p.nome).join(", ") : "Senza personale"}{r.ruolo ? ` · ${r.ruolo}` : ""}{r.data ? ` · ${r.data} ${r.ora_inizio || ""}-${r.ora_fine || ""}` : ""}{r.note ? ` · ${r.note}` : ""}</span></span></div>)}
            {!d.rows.length && <p className="p-3 text-sm text-slate-500"><User className="inline h-4 w-4" /> Nessuna postazione: usa lo strumento Staff e volontari e clicca sulla mappa.</p>}</div>
        </>}
      </DialogContent>
    </Dialog>
  );
}

export const stationMatch = (f, flt) => {
  const st = f.properties.station;
  if (!flt.kind && !flt.ruolo && !flt.data) return true;
  if (!st) return f.properties.layer_id !== "staff";
  return (!flt.kind || (flt.kind === "assegnate" ? st.kind !== "generica" : st.kind === flt.kind)) && (!flt.ruolo || (st.ruolo || "").toLowerCase().includes(flt.ruolo.toLowerCase())) && (!flt.data || st.data === flt.data);
};

export function StaffFilter({ flt, setFlt }) {
  const s = "h-8 rounded-md border border-slate-200 px-1 text-xs";
  return (
    <div className="flex flex-wrap gap-1" data-testid="staff-filter">
      <select value={flt.kind} onChange={(e) => setFlt({ ...flt, kind: e.target.value })} className={s} data-testid="staff-filter-kind"><option value="">Tutte le postazioni</option><option value="team">Team</option><option value="staff">Staff</option><option value="volontario">Volontari</option><option value="assegnate">Assegnate</option><option value="generica">Senza assegnazione</option></select>
      <Input value={flt.ruolo} onChange={(e) => setFlt({ ...flt, ruolo: e.target.value })} placeholder="Ruolo" className="h-8 w-24 text-xs" data-testid="staff-filter-ruolo" />
      <Input type="date" value={flt.data} onChange={(e) => setFlt({ ...flt, data: e.target.value })} className="h-8 w-36 text-xs" data-testid="staff-filter-data" />
    </div>
  );
}
