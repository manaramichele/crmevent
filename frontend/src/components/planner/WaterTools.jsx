import { useState } from "react";
import { toast } from "sonner";
import { Waves, Download, Plus, Trash2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { distance, fmtM } from "@/lib/geo";
import { DISCIPLINE, measures, waterShape } from "./features";

const SEL = "mt-0.5 h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";
const BUOY_COLORS = [["#F97316", "Arancione"], ["#EAB308", "Giallo"], ["#DC2626", "Rosso"], ["#16A34A", "Verde"]];
const DISTANZE = [400, 750, 1500, 1900, 3800];
const T = ({ label, value, onChange, testid, type = "text" }) => (
  <label className="block text-[11px] text-slate-500">{label}<Input type={type} value={value ?? ""} onChange={(e) => onChange(type === "number" ? (e.target.value === "" ? null : +e.target.value) : e.target.value)} className="h-8" data-testid={testid} /></label>
);

function CoordsEditor({ coords, onGeom }) {
  const set = (i, k, v) => { const cs = coords.map((c) => [...c]); cs[i][k] = +v; onGeom(cs); };
  return (
    <div className="space-y-1" data-testid="water-coords">
      <div className="text-[11px] font-semibold text-slate-600">Punti del percorso (lat, lng)</div>
      {coords.map((c, i) => (
        <div key={i} className="flex items-center gap-1 text-[11px]" data-testid={`water-pt-${i}`}>
          <span className="w-5 text-slate-400">{i + 1}</span>
          <input className="h-7 w-[5.6rem] rounded border border-slate-200 px-1" value={c[1]} onChange={(e) => set(i, 1, e.target.value)} data-testid={`water-pt-lat-${i}`} />
          <input className="h-7 w-[5.6rem] rounded border border-slate-200 px-1" value={c[0]} onChange={(e) => set(i, 0, e.target.value)} data-testid={`water-pt-lng-${i}`} />
          <span className="w-12 text-right text-slate-500">{i > 0 ? fmtM(distance(coords[i - 1], c)) : ""}</span>
          {coords.length > 2 && <button type="button" onClick={() => onGeom(coords.filter((_, j) => j !== i), (j) => (j === i ? null : j > i ? j - 1 : j))} className="p-1 text-slate-400 hover:text-red-600" aria-label="Elimina punto" data-testid={`water-pt-del-${i}`}><Trash2 className="h-3 w-3" /></button>}
        </div>))}
      <button type="button" onClick={() => { const l = coords[coords.length - 1]; onGeom([...coords, [l[0] + 0.0003, l[1]]]); }} className="text-[11px] text-tiffany-active" data-testid="water-pt-add"><Plus className="inline h-3 w-3" /> Aggiungi punto</button>
    </div>
  );
}

// Campi aggiuntivi per percorsi con disciplina, boe e mezzi nautici (stesso pannello Proprietà).
export function WaterProps({ f, features, onPatch, onGeom }) {
  const p = f.properties, set = (k) => (v) => onPatch({ [k]: v });
  const routes = features.filter((x) => x.geometry?.type === "LineString" && x.properties.disciplina);
  const linked = routes.find((x) => x.properties.id === p.link_route);
  return (
    <div className="space-y-2 rounded-md border border-sky-200 bg-sky-50/50 p-2" data-testid="water-props">
      {f.geometry?.type === "LineString" && <>
        <label className="block text-[11px] text-slate-500">Disciplina<select className={SEL} value={p.disciplina || ""} onChange={(e) => onPatch({ disciplina: e.target.value || null, ...(e.target.value && !p.disciplina ? { colore: DISCIPLINE[e.target.value][1] } : {}) })} data-testid="water-disciplina">
          <option value="">Nessuna (linea generica)</option>{Object.entries(DISCIPLINE).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select></label>
        {p.disciplina && <>
          <div className="grid grid-cols-2 gap-2"><T label="Giri" type="number" value={p.giri || 1} onChange={(v) => onPatch({ giri: Math.max(1, Math.round(v || 1)) })} testid="water-giri" />
            <label className="flex items-end gap-1.5 pb-2 text-xs"><input type="checkbox" checked={!!p.frecce} onChange={(e) => onPatch({ frecce: e.target.checked })} data-testid="water-frecce" />Frecce direzionali</label></div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { const cs = f.geometry.coordinates; if (cs.length > 2) onGeom([...cs, cs[0]]); }} data-testid="water-close">Chiudi circuito</Button>
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => { const n = f.geometry.coordinates.length; onGeom([...f.geometry.coordinates].reverse(), (i) => n - 1 - i); }} data-testid="water-reverse">Inverti direzione</Button></div>
          <CoordsEditor coords={f.geometry.coordinates} onGeom={onGeom} /></>}
      </>}
      {p.categoria === "Boe" && <>
        <div className="grid grid-cols-2 gap-2"><T label="Numero" type="number" value={p.numero} onChange={set("numero")} testid="buoy-numero" /><T label="Dimensione grafica" type="number" value={p.dimensione} onChange={set("dimensione")} testid="buoy-size" /></div>
        <div className="flex gap-1">{BUOY_COLORS.map(([c, l]) => <button key={c} type="button" title={l} onClick={() => onPatch({ colore: c })} className={`h-6 w-6 rounded-full border-2 ${p.colore === c ? "border-slate-900" : "border-white"}`} style={{ background: c }} data-testid={`buoy-color-${l.toLowerCase()}`} />)}</div>
        <T label="Responsabile posizionamento" value={p.responsabile} onChange={set("responsabile")} testid="buoy-resp" />
        <label className="block text-[11px] text-slate-500">Collegamento al percorso<select className={SEL} value={p.link_route ? `${p.link_route}|${p.link_idx}` : ""} data-testid="buoy-link"
          onChange={(e) => { const [r, i] = e.target.value.split("|"); onPatch(r ? { link_route: r, link_idx: +i } : { link_route: null, link_idx: null }); }}>
          <option value="">Indipendente dal tracciato</option>
          {routes.map((r) => r.geometry.coordinates.map((_, i) => <option key={`${r.properties.id}${i}`} value={`${r.properties.id}|${i}`}>{r.properties.nome} · punto {i + 1}</option>))}</select></label>
        {linked && <p className="text-[11px] text-sky-800">Spostando la boa si sposta il punto {+p.link_idx + 1} di «{linked.properties.nome}» e le distanze si ricalcolano.</p>}
      </>}
      {p.categoria === "Mezzi nautici" && <>
        <div className="grid grid-cols-2 gap-2"><T label="Responsabile" value={p.responsabile} onChange={set("responsabile")} testid="boat-resp" /><T label="Cellulare" value={p.cellulare} onChange={set("cellulare")} testid="boat-phone" /></div>
        <div className="grid grid-cols-2 gap-2"><T label="Funzione" value={p.funzione} onChange={set("funzione")} testid="boat-role" /><T label="Area di competenza" value={p.area_competenza} onChange={set("area_competenza")} testid="boat-area" /></div>
        <T label="Dispositivo GPS (ID, facoltativo)" value={p.gps_device} onChange={set("gps_device")} testid="boat-gps" />
        <p className="text-[11px] text-slate-500" data-testid="boat-gps-state">{p.gps_device ? "Dispositivo indicato: nessuna posizione reale ricevuta finché non sarà collegato un servizio GPS." : "Nessun GPS: elemento statico, posizione pianificata."}</p>
      </>}
      {f.geometry?.type === "Point" && <div className="grid grid-cols-2 gap-2">
        <T label="Latitudine" type="number" value={f.geometry.coordinates[1]} onChange={(v) => v != null && onGeom([f.geometry.coordinates[0], v])} testid="pt-lat" />
        <T label="Longitudine" type="number" value={f.geometry.coordinates[0]} onChange={(v) => v != null && onGeom([v, f.geometry.coordinates[1]])} testid="pt-lng" /></div>}
      <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={!!p.riservato} onChange={(e) => onPatch({ riservato: e.target.checked })} data-testid="prop-riservato" />Riservato alla sicurezza (escluso dalla versione pubblica)</label>
    </div>
  );
}

const download = async (pid, fmt, pubblico) => {
  try {
    const { data, headers } = await api.get(`/planner/projects/${pid}/export/${fmt}`, { params: { pubblico }, responseType: "blob" });
    const name = /filename="([^"]+)"/.exec(headers["content-disposition"] || "")?.[1] || `export.${fmt}`;
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(data), download: name }); a.click();
  } catch (e) { const t = await e.response?.data?.text?.().catch(() => ""); toast.error(t ? formatApiError(JSON.parse(t).detail) : "Esportazione non riuscita"); }
};

// Sezione della barra laterale: percorso in acqua, riepilogo multidisciplina ed esportazioni.
export function WaterPanel({ pid, features, center, onAdd, onDraw }) {
  const [dist, setDist] = useState(750), [shape, setShape] = useState("triangolo"), [giri, setGiri] = useState(1), [pub, setPub] = useState(false);
  const routes = features.filter((f) => f.geometry?.type === "LineString" && f.properties.disciplina);
  const tot = Object.fromEntries(Object.keys(DISCIPLINE).map((k) => [k, routes.filter((r) => r.properties.disciplina === k).reduce((s, r) => s + measures(r).totale, 0)]));
  const png = () => { const u = window.__plannerExportPng?.(); if (u) Object.assign(document.createElement("a"), { href: u, download: "planimetria.png" }).click(); };
  return (
    <div className="space-y-2 rounded-md border border-sky-200 bg-white p-2 text-xs" data-testid="water-panel">
      <div className="flex items-center gap-1 font-semibold text-slate-700"><Waves className="h-4 w-4 text-sky-600" />Percorso in acqua</div>
      <div className="grid grid-cols-2 gap-1">
        <label className="text-[11px] text-slate-500">Distanza totale (m)<Input type="number" value={dist} onChange={(e) => setDist(+e.target.value)} className="h-8" list="water-dist" data-testid="water-dist" /></label>
        <datalist id="water-dist">{DISTANZE.map((d) => <option key={d} value={d} />)}</datalist>
        <label className="text-[11px] text-slate-500">Giri<Input type="number" min={1} value={giri} onChange={(e) => setGiri(Math.max(1, +e.target.value || 1))} className="h-8" data-testid="water-new-giri" /></label>
      </div>
      <div className="flex flex-wrap gap-1">{DISTANZE.map((d) => <button key={d} type="button" onClick={() => setDist(d)} className={`rounded-full border px-2 py-0.5 ${dist === d ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200"}`} data-testid={`water-dist-${d}`}>{d} m</button>)}</div>
      <select className={SEL} value={shape} onChange={(e) => setShape(e.target.value)} data-testid="water-shape"><option value="lineare">Lineare</option><option value="triangolo">Triangolare</option><option value="rettangolo">Rettangolare</option><option value="anello">Ad anello</option></select>
      <div className="flex flex-wrap gap-1">
        <Button size="sm" className="h-8 bg-tiffany text-xs text-slate-900 hover:bg-tiffany-hover" onClick={() => onAdd(waterShape(center(), shape, dist / giri), { giri, nome: `Nuoto ${dist} m` })} data-testid="water-create">Crea al centro mappa</Button>
        <Button size="sm" variant="outline" className="h-8 text-xs" onClick={onDraw} data-testid="water-draw">Disegna con clic</Button></div>
      <p className="text-[10px] text-slate-400">I valori sono suggerimenti. Distanze geodetiche tra i punti, senza seguire strade o sentieri: stima cartografica, non sostituisce la misurazione in acqua. Un percorso tracciato non è per questo sicuro.</p>
      {routes.length > 0 && <div className="rounded bg-slate-50 p-2" data-testid="water-summary">
        {routes.map((r) => <div key={r.properties.id} className="flex justify-between gap-2"><span className="truncate" style={{ color: r.properties.colore }}>{DISCIPLINE[r.properties.disciplina][0]} · {r.properties.nome}</span><b>{measures(r).testo}</b></div>)}
        <div className="mt-1 border-t border-slate-200 pt-1 text-slate-600" data-testid="water-summary-totals">{["nuoto", "ciclismo", "corsa"].map((k) => `${DISCIPLINE[k][0]} ${fmtM(tot[k])}`).join(" · ")}{tot.transizione ? ` · Transizioni ${fmtM(tot.transizione)} (separate)` : ""}</div></div>}
      <div className="font-semibold text-slate-700 pt-1">Esporta</div>
      <div className="flex flex-wrap gap-1">{[["gpx", "GPX"], ["kml", "KML"], ["boe.pdf", "Elenco boe PDF"], ["boe.xlsx", "Elenco boe Excel"]].map(([k, l]) =>
        <Button key={k} size="sm" variant="outline" className="h-7 text-xs" onClick={() => download(pid, k, pub)} data-testid={`water-export-${k.replace(".", "-")}`}><Download className="mr-1 h-3 w-3" />{l}</Button>)}
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={png} data-testid="water-export-png"><Download className="mr-1 h-3 w-3" />PNG mappa</Button></div>
      <label className="flex items-center gap-1.5"><input type="checkbox" checked={pub} onChange={(e) => setPub(e.target.checked)} data-testid="water-export-public" />Versione pubblica (senza elementi riservati e livelli nascosti)</label>
    </div>
  );
}
