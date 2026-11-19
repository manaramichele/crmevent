import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Save, Trash2, Upload } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SEL, SearchSelect, Pill, ACTION } from "@/components/import/shared";

const err = (e) => toast.error(formatApiError(e.response?.data?.detail));

export function Dropzone({ onFile, busy }) {
  const [over, setOver] = useState(false);
  return (
    <label onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]); }}
      className={`flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${over ? "border-tiffany bg-tiffany-light" : "border-slate-200 hover:border-slate-300"}`} data-testid="import-dropzone">
      <Upload className="w-6 h-6 text-slate-400" />
      <span className="text-sm font-medium text-slate-700">{busy ? "Lettura del file…" : "Trascina qui il file oppure clicca per sceglierlo"}</span>
      <span className="text-xs text-slate-500">Excel (.xlsx, .xls) o CSV · massimo 8 MB · nulla viene importato prima della conferma</span>
      <input type="file" accept=".xlsx,.xls,.csv" className="hidden" disabled={busy} onChange={(e) => e.target.files[0] && onFile(e.target.files[0])} data-testid="import-file-input" />
    </label>
  );
}

export function MappingTable({ read, fields, mapping, setMapping }) {
  const opts = useMemo(() => [{ value: "", label: "Non importare" }, ...fields.map((f) => ({ value: f.key, label: f.label, hint: f.group === "persona" ? "anagrafica" : f.required ? "obbligatorio" : "" }))], [fields]);
  const used = Object.values(mapping).filter(Boolean);
  const missing = fields.filter((f) => f.required && !used.includes(f.key));
  return (
    <div className="space-y-2">
      {missing.length > 0 && <p className="text-xs text-red-600" data-testid="import-missing-required">Da abbinare: {missing.map((f) => f.label).join(", ")}</p>}
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-sm" data-testid="import-mapping-table">
          <thead className="bg-slate-50"><tr className="text-left text-xs text-slate-500">{["Colonna del file", "Campo CRMEvent", "Esempio", "Stato"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody>{read.columns.map((c, i) => {
            const ex = read.preview.map((r) => r[i]).find(Boolean) || "";
            const dup = mapping[c] && used.filter((u) => u === mapping[c]).length > 1;
            return (
              <tr key={c} className="border-t border-slate-100" data-testid={`import-map-row-${i}`}>
                <td className="px-3 py-1.5 font-medium text-slate-800">{c}</td>
                <td className="px-3 py-1.5"><SearchSelect value={mapping[c] || ""} onChange={(v) => setMapping({ ...mapping, [c]: v })} options={opts} testid={`import-map-field-${i}`} /></td>
                <td className="px-3 py-1.5 text-slate-500 max-w-[200px] truncate">{ex || "—"}</td>
                <td className="px-3 py-1.5 text-xs">{dup ? <span className="text-orange-700">Campo usato due volte</span> : mapping[c] ? <span className="text-emerald-700">Collegato</span> : <span className="text-slate-400">Escluso</span>}</td>
              </tr>);
          })}</tbody>
        </table>
      </div>
    </div>
  );
}

export function PipelineSetup({ read, events, cats, setCats, resp, setResp, evMap, setEvMap, sheets, setSheets, allSheets, people }) {
  const p = read.pipeline || { fasi: [], categorie_esistenti: [], responsabili: [], eventi: [], fogli: [] };
  const evOpts = [{ value: "", label: "Nessun evento" }, ...events.map((e) => ({ value: e.id, label: e.nome, hint: e.edizione || (e.data_inizio || "").slice(0, 10) }))];
  const catOpts = [...new Set([...p.categorie_esistenti, ...p.fasi])];
  return (
    <div className="space-y-5">
      {allSheets.length > 1 && (
        <section data-testid="import-pipeline-sheets"><h4 className="text-sm font-semibold mb-1">Fogli da importare</h4>
          <p className="text-xs text-slate-500 mb-2">Ogni foglio va nella pipeline di un evento. Il nome del foglio è usato come proposta.</p>
          {allSheets.map((s) => { const cur = sheets.find((x) => x.sheet === s.name); return (
            <div key={s.name} className="flex flex-col sm:flex-row sm:items-center gap-2 py-1">
              <label className="flex items-center gap-2 text-sm sm:w-56"><input type="checkbox" checked={!!cur} onChange={(e) => setSheets(e.target.checked ? [...sheets, { sheet: s.name, event_id: (p.fogli.find((f) => f.sheet === s.name) || {}).event_id || "" }] : sheets.filter((x) => x.sheet !== s.name))} data-testid={`import-sheet-${s.name}`} />{s.name} <span className="text-xs text-slate-400">{s.rows} righe</span></label>
              {cur && <div className="flex-1 min-w-0"><SearchSelect value={cur.event_id} onChange={(v) => setSheets(sheets.map((x) => (x.sheet === s.name ? { ...x, event_id: v } : x)))} options={evOpts} testid={`import-sheet-event-${s.name}`} /></div>}
            </div>); })}
        </section>)}
      {p.fasi.length > 0 && (
        <section data-testid="import-pipeline-fasi"><h4 className="text-sm font-semibold mb-1">Abbina fasi Pipeline</h4>
          <p className="text-xs text-slate-500 mb-2">Ogni fase del file diventa una Categoria della pipeline: collega una categoria esistente, scrivi un nuovo nome oppure escludila. Le nuove categorie vengono aggiunte in fondo, nell'ordine indicato.</p>
          {p.fasi.map((f, i) => { const m = cats[f] || { action: "use", name: f }; return (
            <div key={f} className="grid grid-cols-1 sm:grid-cols-[200px_140px_1fr] gap-2 py-1 items-center min-w-0" data-testid={`import-fase-row-${i}`}>
              <span className="text-sm font-medium truncate">{f}</span>
              <select className={SEL} value={m.action} onChange={(e) => setCats({ ...cats, [f]: { ...m, action: e.target.value } })} data-testid={`import-fase-action-${i}`}><option value="use">Importa in</option><option value="skip">Escludi</option></select>
              {m.action === "use" && <><Input list={`cats-${i}`} value={m.name} onChange={(e) => setCats({ ...cats, [f]: { ...m, name: e.target.value } })} className="h-9 w-full min-w-0" data-testid={`import-fase-name-${i}`} />
                <datalist id={`cats-${i}`}>{catOpts.map((c) => <option key={c} value={c} />)}</datalist></>}
            </div>); })}
        </section>)}
      {p.responsabili.length > 0 && (
        <section data-testid="import-pipeline-resp"><h4 className="text-sm font-semibold mb-1">Responsabili</h4>
          <p className="text-xs text-slate-500 mb-2">Cercati tra le persone dell'organizzazione. Nessun account o invito viene creato.</p>
          {p.responsabili.map((r, i) => (
            <div key={r.valore} className="grid grid-cols-1 sm:grid-cols-[200px_1fr] gap-2 py-1 items-center">
              <span className="text-sm">{r.valore} {!(resp[r.valore] ?? r.persona_id) && <span className="text-[11px] text-amber-700">non trovato</span>}</span>
              <SearchSelect value={resp[r.valore] ?? r.persona_id ?? ""} onChange={(v) => setResp({ ...resp, [r.valore]: v })} testid={`import-resp-${i}`}
                options={[{ value: "", label: "Nessun responsabile" }, ...people.map((x) => ({ value: x.id, label: `${x.cognome || ""} ${x.nome}`.trim(), hint: x.email }))]} />
            </div>))}
        </section>)}
      {p.eventi.length > 0 && (
        <section data-testid="import-pipeline-eventi"><h4 className="text-sm font-semibold mb-1">Eventi del file</h4>
          <p className="text-xs text-slate-500 mb-2">Collegati solo se il nome coincide esattamente: verifica gli eventi con nomi simili.</p>
          {p.eventi.map((r, i) => (
            <div key={r.valore} className="grid grid-cols-1 sm:grid-cols-[200px_1fr] gap-2 py-1 items-center"><span className="text-sm">{r.valore}</span>
              <SearchSelect value={evMap[r.valore] ?? r.event_id ?? ""} onChange={(v) => setEvMap({ ...evMap, [r.valore]: v })} options={evOpts} testid={`import-evmap-${i}`} /></div>))}
        </section>)}
    </div>
  );
}

export function ConfigBar({ target, mapping, options, onLoad, superadmin }) {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState("");
  const load = () => api.get("/imports/configs", { params: { target } }).then(({ data }) => setList(data)).catch(() => setList([]));
  useEffect(() => { load(); }, [target]); // eslint-disable-line react-hooks/exhaustive-deps
  const cur = list.find((c) => c.id === sel);
  const save = async (asNew) => {
    const name = window.prompt("Nome della configurazione", asNew ? "" : cur?.name || "");
    if (!name) return;
    const globale = asNew && superadmin && window.confirm("Renderla disponibile a tutte le organizzazioni? (i dati restano separati)");
    const body = { name, target, mapping, options, globale: asNew ? globale : cur?.org_id === null };
    try { if (asNew || !cur) { const { data } = await api.post("/imports/configs", body); setSel(data.id); } else await api.put(`/imports/configs/${cur.id}`, body); toast.success("Configurazione salvata"); load(); } catch (e) { err(e); }
  };
  const del = async () => { if (cur && window.confirm(`Eliminare "${cur.name}"?`)) { try { await api.delete(`/imports/configs/${cur.id}`); setSel(""); load(); } catch (e) { err(e); } } };
  return (
    <div className="flex flex-wrap items-center gap-2 min-w-0" data-testid="import-config-bar">
      <select className={`${SEL} max-w-full`} value={sel} onChange={(e) => { setSel(e.target.value); const c = list.find((x) => x.id === e.target.value); if (c) onLoad(c); }} data-testid="import-config-select">
        <option value="">Configurazioni salvate…</option>{list.map((c) => <option key={c.id} value={c.id}>{c.name}{c.org_id === null ? " (condivisa)" : ""}</option>)}
      </select>
      <Button size="sm" variant="outline" onClick={() => save(true)} data-testid="import-config-save"><Save className="w-4 h-4 mr-1" />Salva abbinamenti</Button>
      {cur && <Button size="sm" variant="ghost" onClick={() => save(false)} data-testid="import-config-update">Rinomina / aggiorna</Button>}
      {cur && <Button size="sm" variant="ghost" onClick={del} data-testid="import-config-delete"><Trash2 className="w-4 h-4" /></Button>}
    </div>
  );
}

export function PreviewPanel({ prev, ctx }) {
  const c = prev.counts, a = prev.actions, p = prev.pipeline;
  return (
    <div className="space-y-4" data-testid="import-preview">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
        {[["Organizzazione", ctx.org], ["Modulo", ctx.module], ["Stato modulo", ctx.active ? "Attivo" : "Non attivo"], ["File", `${ctx.file}${ctx.sheet ? ` · ${ctx.sheet}` : ""}`]].map(([k, v]) => (
          <div key={k} className="rounded-lg bg-slate-50 px-3 py-2"><div className="text-[11px] text-slate-500">{k}</div><div className="font-medium truncate" title={v}>{v}</div></div>))}
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-center" data-testid="import-preview-counts">
        {[["Righe", prev.rows], ["Da creare", a.crea + (prev.items.filter((x) => x.action === "collega").length)], ["Da aggiornare", a.aggiorna], ["Duplicati", c.possibile_duplicato + c.duplicato_file], ["Conflitti", c.conflitto], ["Errori", c.errore]].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-slate-200 py-2"><div className="text-lg font-bold" data-testid={`import-count-${k}`}>{v}</div><div className="text-[11px] text-slate-500">{k}</div></div>))}
      </div>
      {c.escluso > 0 && <p className="text-xs text-slate-500" data-testid="import-excluded-rows">Righe escluse (fasi non importate): {c.escluso}</p>}
      {prev.excluded.length > 0 && <p className="text-xs text-slate-500">Colonne escluse: {prev.excluded.join(", ")}</p>}
      {p && (
        <div className="rounded-lg border border-slate-200 p-3 text-sm space-y-1" data-testid="import-preview-pipeline">
          <div><b>Schede per fase:</b> {Object.entries(p.schede_per_fase).map(([k, v]) => `${k} (${v})`).join(" · ") || "—"}</div>
          <div><b>Eventi:</b> {Object.entries(p.schede_per_evento).map(([k, v]) => `${k} (${v})`).join(" · ") || "—"}</div>
          <div><b>Fasi da creare:</b> {p.fasi_da_creare.join(", ") || "nessuna"}</div>
          <div><b>Responsabili collegati:</b> {p.responsabili_collegati}{p.responsabili_non_trovati.length > 0 && <span className="text-amber-700"> · non trovati: {p.responsabili_non_trovati.join(", ")}</span>}</div>
          {p.eventi_senza_pipeline_attiva.length > 0 && <div className="text-amber-700">Pipeline non attiva su: {p.eventi_senza_pipeline_attiva.join(", ")}. I dati saranno visibili all'organizzazione solo dopo l'attivazione.</div>}
        </div>)}
      <div className="overflow-x-auto max-h-[380px] rounded-lg border border-slate-200">
        <table className="w-full text-sm"><thead className="bg-slate-50 sticky top-0"><tr className="text-left text-xs text-slate-500">{["Riga", "Dati", "Stato", "Azione", "Note"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
          <tbody>{prev.items.map((x, i) => (
            <tr key={i} className="border-t border-slate-100" data-testid={`import-preview-row-${i}`}>
              <td className="px-3 py-1.5 text-xs text-slate-500 whitespace-nowrap">{x.sheet !== "CSV" ? `${x.sheet} · ` : ""}{x.row}</td>
              <td className="px-3 py-1.5 max-w-[260px] truncate">{Object.values(x.data).slice(0, 4).join(" · ")}</td>
              <td className="px-3 py-1.5"><Pill s={x.status} /></td><td className="px-3 py-1.5 text-xs">{ACTION[x.action] || "Ignora"}</td>
              <td className="px-3 py-1.5 text-xs text-slate-600">{[x.message, x.avviso].filter(Boolean).join(" · ")}</td>
            </tr>))}</tbody></table>
      </div>
    </div>
  );
}
