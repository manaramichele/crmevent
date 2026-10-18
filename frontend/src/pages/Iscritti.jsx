import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Contact, Upload, Plus, RefreshCw, Download, ListPlus } from "lucide-react";
import { ImportWizard } from "@/components/iscritti/ImportWizard";
import { IscrittoDialog } from "@/components/iscritti/IscrittoDialog";
import { EdizioniPanel, ImportsPanel } from "@/components/iscritti/EdizioniPanel";
import { StatsPanel } from "@/components/iscritti/StatsPanel";

const SEL = "h-10 rounded-md border border-slate-200 px-3 text-sm bg-white min-w-0";
const err = (e) => toast.error(formatApiError(e.response?.data?.detail));
const COLS = [["cognome", "Cognome"], ["nome", "Nome"], ["email", "Email"], ["cellulare", "Cellulare"], ["societa", "Società"], ["last_year", "Ultimo anno"], ["partecipazioni", "Partecipazioni"], ["consenso_marketing", "Consenso"], ["brevo_status", "Brevo"]];
const SYNC = { ok: "Sincronizzato", parziale: "Parziale", errore: "Errore", rate_limit: "In attesa (limite Brevo)", non_configurato: "Brevo non configurato" };
const BREVO = { sincronizzato: "Sincronizzato", da_sincronizzare: "In coda", escluso_consenso: "Senza consenso", disiscritto: "Disiscritto", errore: "Errore", rate_limit: "In coda", da_rimuovere: "In rimozione", anonimizzato: "Anonimizzato", demo_escluso: "DEMO (escluso)" };

function Kpi({ label, v, id }) {
  return <div className="bg-white border border-slate-200 rounded-xl p-3" data-testid={`iscritti-kpi-${id}`}><div className="text-xs text-slate-500">{label}</div><div className="text-xl font-bold text-slate-900">{v}</div></div>;
}

function Filters({ f, setF, eds }) {
  const events = [...new Map(eds.map((e) => [e.event_id, e.event_nome])).entries()];
  const anni = [...new Set(eds.map((e) => e.anno))].sort((a, b) => b - a);
  const gare = [...new Set(eds.flatMap((e) => e.gare || []))];
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value, page: 1 });
  return (
    <div className="grid grid-cols-2 lg:grid-cols-7 gap-2" data-testid="iscritti-filters">
      <select className={SEL} value={f.event_id} onChange={set("event_id")} data-testid="filter-event"><option value="">Tutti gli eventi</option>{events.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>
      <select className={SEL} value={f.anno} onChange={set("anno")} data-testid="filter-anno"><option value="">Tutti gli anni</option>{anni.map((a) => <option key={a}>{a}</option>)}</select>
      <select className={SEL} value={f.edizione_id} onChange={set("edizione_id")} data-testid="filter-edizione"><option value="">Tutte le edizioni</option>{eds.filter((e) => (!f.event_id || e.event_id === f.event_id) && (!f.anno || String(e.anno) === f.anno)).map((e) => <option key={e.id} value={e.id}>{e.event_nome} {e.anno} {e.edizione}</option>)}</select>
      <Input list="gare-filter" placeholder="Gara/distanza" value={f.gara} onChange={set("gara")} data-testid="filter-gara" /><datalist id="gare-filter">{gare.map((g) => <option key={g} value={g} />)}</datalist>
      <select className={SEL} value={f.stato} onChange={set("stato")} data-testid="filter-stato"><option value="">Tutti gli stati</option>{["confermata", "in_attesa", "annullata", "ritirato"].map((s) => <option key={s}>{s}</option>)}</select>
      <select className={SEL} value={f.consenso} onChange={set("consenso")} data-testid="filter-consenso"><option value="">Consenso: tutti</option><option value="si">Con consenso</option><option value="no">Senza consenso</option></select>
      <Input placeholder="Cerca nome, email, società" value={f.q} onChange={set("q")} data-testid="filter-search" />
    </div>
  );
}

export default function Iscritti() {
  const [meta, setMeta] = useState(null);
  const [eds, setEds] = useState({ edizioni: [], events: [] });
  const [f, setF] = useState({ event_id: "", anno: "", edizione_id: "", gara: "", stato: "", consenso: "", q: "", sort: "cognome", dir: 1, page: 1 });
  const [list, setList] = useState(null);
  const [kpi, setKpi] = useState(null);
  const [imports, setImports] = useState([]);
  const [cols, setCols] = useState(COLS.map((c) => c[0]));
  const [wiz, setWiz] = useState(false);
  const [open, setOpen] = useState(undefined);
  const loadMeta = useCallback(() => {
    api.get("/iscritti/status").then(({ data }) => setMeta(data)).catch(() => setMeta({ active: false }));
    api.get("/iscritti/edizioni").then(({ data }) => setEds(data)).catch(() => {});
    api.get("/iscritti/imports").then(({ data }) => setImports(data.imports)).catch(() => {});
  }, []);
  const params = useMemo(() => Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "")), [f]);
  const load = useCallback(() => {
    api.get("/iscritti", { params }).then(({ data }) => setList(data)).catch(err);
    const { q, consenso, sort, dir, page, ...kf } = params; // eslint-disable-line no-unused-vars
    api.get("/iscritti/kpi", { params: kf }).then(({ data }) => setKpi(data)).catch(() => {});
  }, [params]);
  useEffect(() => { loadMeta(); }, [loadMeta]);
  useEffect(() => { if (meta?.active) { const t = setTimeout(load, 250); return () => clearTimeout(t); } return undefined; }, [meta, load]);
  const refresh = useCallback(() => { loadMeta(); load(); }, [loadMeta, load]);
  if (!meta) return <p className="text-slate-500">Caricamento...</p>;
  if (!meta.active) return (
    <div className="max-w-xl bg-white border border-slate-200 rounded-xl p-6 space-y-3" data-testid="iscritti-inactive">
      <h1 className="text-2xl font-bold flex items-center gap-2"><Contact className="w-6 h-6 text-[#0ABAB5]" />Elenco Iscritti</h1>
      <p className="text-slate-600">Il modulo non è attivo per la tua organizzazione. Puoi attivarlo dal Marketplace.</p>
      <Link to="/marketplace" className="inline-flex h-10 px-4 items-center rounded-full bg-[#0ABAB5] text-slate-900 font-semibold">Vai al Marketplace</Link>
    </div>
  );
  const sync = async () => { try { const { data } = await api.post("/iscritti/brevo/sync"); toast.success(SYNC[data.status] || data.status); loadMeta(); load(); } catch (e) { err(e); } };
  const segment = async () => { try { const { data } = await api.post("/iscritti/brevo/segment", { filters: { event_id: f.event_id, anno: f.anno, edizione_id: f.edizione_id, gara: f.gara, stato: f.stato } }); toast.success(`Lista Brevo «${data.name}»: ${data.count} contatti`); } catch (e) { err(e); } };
  const exportFile = async (format) => {
    try {
      const { data } = await api.get("/iscritti/export", { params: { ...params, format }, responseType: "blob" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(data); a.download = `iscritti.${format}`; a.click();
    } catch (e) { err(e); }
  };
  const ls = meta.brevo?.brevo_last_sync;
  const sortBy = (k) => setF({ ...f, sort: k, dir: f.sort === k ? -f.dir : 1 });
  return (
    <div className="space-y-5 max-w-full min-w-0" data-testid="iscritti-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2"><Contact className="w-6 h-6 text-[#0ABAB5]" />Elenco Iscritti</h1>
          <p className="text-sm text-slate-500" data-testid="iscritti-brevo-status">Brevo: {ls ? `${SYNC[ls.status] || ls.status} · ${new Date(ls.at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" })}${ls.error && ls.status !== "non_configurato" ? ` · ${ls.error}` : ""}` : "mai sincronizzato"}{meta.brevo?.brevo_list_name ? ` · lista «${meta.brevo.brevo_list_name}»` : ""} · solo iscritti con consenso marketing</p>
        </div>
        {meta.can_edit && (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setWiz(true)} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="iscritti-import-btn"><Upload className="w-4 h-4 mr-1" />+ Importa iscritti</Button>
            <Button variant="outline" onClick={() => setOpen(null)} data-testid="iscritti-add-btn"><Plus className="w-4 h-4 mr-1" />Aggiungi iscritto</Button>
            <Button variant="outline" onClick={sync} data-testid="iscritti-sync-btn"><RefreshCw className="w-4 h-4 mr-1" />Sincronizza Brevo</Button>
          </div>
        )}
      </div>
      <Tabs defaultValue="list">
        <TabsList className="flex-wrap h-auto"><TabsTrigger value="list" data-testid="iscritti-tab-list">Iscritti</TabsTrigger><TabsTrigger value="stats" data-testid="iscritti-tab-stats">Statistiche</TabsTrigger><TabsTrigger value="edizioni" data-testid="iscritti-tab-edizioni">Edizioni</TabsTrigger><TabsTrigger value="imports" data-testid="iscritti-tab-imports">Storico importazioni</TabsTrigger></TabsList>
        <TabsContent value="list" className="space-y-4">
          <Filters f={f} setF={setF} eds={eds.edizioni} />
          {kpi && (
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
              <Kpi id="total" label="Iscritti (selezione)" v={kpi.total} /><Kpi id="new" label="Nuovi (30 giorni)" v={kpi.new_30d} /><Kpi id="recurring" label="Ricorrenti" v={kpi.recurring} />
              <Kpi id="consent" label="Con consenso" v={kpi.with_consent} /><Kpi id="events" label="Eventi / edizioni" v={`${kpi.by_event.length} / ${kpi.by_edition.length}`} />
            </div>
          )}
          {kpi?.by_edition.length > 0 && <div className="flex flex-wrap gap-2 text-xs" data-testid="iscritti-by-edition">{kpi.by_edition.map((e) => <span key={e.edizione_id} className="rounded-full bg-[#0ABAB5]/10 px-2 py-1">{e.label}: <strong>{e.n}</strong></span>)}</div>}
          <div className="flex flex-wrap gap-2 items-center text-sm">
            <span className="text-slate-500">Colonne:</span>
            {COLS.map(([k, l]) => <label key={k} className="flex items-center gap-1"><input type="checkbox" checked={cols.includes(k)} onChange={(e) => setCols(e.target.checked ? [...cols, k] : cols.filter((x) => x !== k))} data-testid={`col-toggle-${k}`} />{l}</label>)}
            {meta.can_edit && <span className="ml-auto flex gap-2"><Button size="sm" variant="outline" onClick={() => exportFile("xlsx")} data-testid="iscritti-export-xlsx"><Download className="w-4 h-4 mr-1" />Excel</Button><Button size="sm" variant="outline" onClick={() => exportFile("csv")} data-testid="iscritti-export-csv">CSV</Button>
              <Button size="sm" variant="outline" onClick={segment} disabled={!(f.event_id || f.anno || f.edizione_id)} title="Crea una lista Brevo con gli iscritti con consenso della selezione" data-testid="iscritti-segment"><ListPlus className="w-4 h-4 mr-1" />Lista Brevo selezione</Button></span>}
          </div>
          <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm" data-testid="iscritti-table">
              <thead><tr className="text-left text-xs text-slate-500 border-b">{COLS.filter(([k]) => cols.includes(k)).map(([k, l]) => <th key={k} className="p-3 cursor-pointer select-none" onClick={() => sortBy(k)}>{l}{f.sort === k ? (f.dir > 0 ? " ▲" : " ▼") : ""}</th>)}</tr></thead>
              <tbody>
                {list?.items.length === 0 && <tr><td colSpan={9} className="p-4 text-slate-500">Nessun iscritto per questi filtri.</td></tr>}
                {list?.items.map((x) => (
                  <tr key={x.id} className="border-b last:border-0 hover:bg-slate-50 cursor-pointer" onClick={() => setOpen(x.id)} data-testid={`iscritto-row-${x.id}`}>
                    {COLS.filter(([k]) => cols.includes(k)).map(([k]) => <td key={k} className="p-3 break-all">{k === "consenso_marketing" ? (x[k] ? "Sì" : "No") : k === "brevo_status" ? (BREVO[x[k]] || "—") : (x[k] ?? "—") || "—"}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {list && (
            <div className="flex items-center gap-2 text-sm">
              <Button size="sm" variant="outline" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })} data-testid="iscritti-prev">Precedente</Button>
              <span data-testid="iscritti-total">Pagina {f.page} · {list.total} iscritti</span>
              <Button size="sm" variant="outline" disabled={f.page * list.limit >= list.total} onClick={() => setF({ ...f, page: f.page + 1 })} data-testid="iscritti-next">Successiva</Button>
            </div>
          )}
        </TabsContent>
        <TabsContent value="stats"><StatsPanel eds={eds.edizioni} /></TabsContent>
        <TabsContent value="edizioni"><EdizioniPanel data={eds} canEdit={meta.can_edit} onChanged={loadMeta} /></TabsContent>
        <TabsContent value="imports"><ImportsPanel rows={imports} /></TabsContent>
      </Tabs>
      <ImportWizard open={wiz} onClose={() => { setWiz(false); refresh(); }} meta={meta} edizioni={eds.edizioni} onDone={refresh} />
      <IscrittoDialog id={open} open={open !== undefined} onClose={() => setOpen(undefined)} meta={meta} edizioni={eds.edizioni} onChanged={refresh} />
    </div>
  );
}
