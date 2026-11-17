import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Monitor, Smartphone } from "lucide-react";
import PlannerDemoAdmin from "@/pages/PlannerDemoAdmin";
import { LogoCarousel } from "@/components/landing/EventLogosCarousel";

const ST = { published: ["Pubblicato", "bg-emerald-50 text-emerald-700"], pending: ["Non pubblicato", "bg-slate-100 text-slate-600"], excluded: ["Escluso", "bg-red-50 text-red-700"] };
const TABS = [["sezioni", "Sezioni homepage"], ["carosello", "Carosello loghi eventi"]];

function Settings({ s, setS, onSave, busy }) {
  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5" data-testid="carousel-settings">
      <label className="block text-xs text-slate-500">Titolo della sezione
        <Input value={s.carousel_title} onChange={(e) => setS({ ...s, carousel_title: e.target.value })} maxLength={120} className="mt-1 text-sm text-slate-900" data-testid="carousel-title-input" /></label>
      <label className="flex items-center gap-3 text-sm font-medium"><Switch checked={s.carousel_enabled} onCheckedChange={(v) => setS({ ...s, carousel_enabled: v })} data-testid="carousel-enabled" />
        {s.carousel_enabled ? "Carosello visibile in homepage" : "Carosello nascosto in homepage"}</label>
      <label className="flex items-start gap-3 text-sm font-medium"><Switch checked={s.auto_new} onCheckedChange={(v) => setS({ ...s, auto_new: v })} data-testid="carousel-auto-new" />
        <span>Pubblica automaticamente i nuovi eventi con logo<span className="block text-xs font-normal text-slate-500">Vale solo per gli eventi creati da quando attivi l'opzione. Gli eventi già esistenti restano da approvare uno per uno; le esclusioni restano sempre salvate.</span></span></label>
      <Button onClick={onSave} disabled={busy || s.carousel_title.trim().length < 3} className="bg-tiffany text-slate-900 hover:bg-tiffany-hover" data-testid="carousel-save">{busy ? "Salvataggio..." : "Salva modifiche"}</Button>
    </div>
  );
}

function Preview({ title, logos }) {
  if (!logos.length) return <p className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-400" data-testid="carousel-preview-empty">Nessun logo pubblicato: in homepage la sezione non viene mostrata.</p>;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
      <div className="min-w-0 rounded-xl border border-slate-200 bg-white p-6" data-testid="carousel-preview-desktop"><div className="mb-4 flex items-center gap-1.5 text-xs font-semibold text-slate-400"><Monitor className="h-4 w-4" />Desktop</div><LogoCarousel title={title} logos={logos} testid="preview-desktop" /></div>
      <div className="mx-auto w-[300px] rounded-[2rem] border-[6px] border-slate-900 bg-white px-3 py-6" data-testid="carousel-preview-mobile"><div className="mb-3 flex items-center gap-1.5 text-xs font-semibold text-slate-400"><Smartphone className="h-4 w-4" />Smartphone</div><LogoCarousel title={title} logos={logos} compact testid="preview-mobile" /></div>
    </div>
  );
}

function LogoTable({ rows, onSet }) {
  const [q, setQ] = useState(""); const [org, setOrg] = useState(""); const [st, setSt] = useState("");
  const orgs = useMemo(() => [...new Map(rows.map((r) => [r.org_id, r.org_nome])).entries()].sort((a, b) => (a[1] || "").localeCompare(b[1] || "")), [rows]);
  const list = rows.filter((r) => (!q || (r.nome || "").toLowerCase().includes(q.toLowerCase())) && (!org || r.org_id === org) && (!st || r.status === st));
  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca evento" className="sm:max-w-xs" data-testid="logos-search" />
        <select value={org} onChange={(e) => setOrg(e.target.value)} className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" data-testid="logos-filter-org"><option value="">Tutte le organizzazioni</option>{orgs.map(([id, n]) => <option key={id} value={id}>{n}</option>)}</select>
        <select value={st} onChange={(e) => setSt(e.target.value)} className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" data-testid="logos-filter-status"><option value="">Tutti gli stati</option>{Object.entries(ST).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}</select>
        <span className="self-center text-xs text-slate-500" data-testid="logos-count">{list.length} eventi con logo</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[720px] text-sm" data-testid="logos-table">
          <thead className="bg-slate-50 text-left text-xs text-slate-500"><tr><th className="px-3 py-2">Logo</th><th className="px-3 py-2">Evento</th><th className="px-3 py-2">Organizzazione</th><th className="px-3 py-2">Stato</th><th className="px-3 py-2">Ultimo aggiornamento</th><th className="px-3 py-2" /></tr></thead>
          <tbody>{list.map((r) => (
            <tr key={r.id} className="border-t border-slate-100" data-testid={`logo-row-${r.id}`}>
              <td className="px-3 py-2"><div className="flex h-12 w-24 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 p-1.5">{r.valid ? <img src={`${process.env.REACT_APP_BACKEND_URL}${r.thumb}`} alt={r.nome} loading="lazy" className="max-h-full max-w-full object-contain" /> : <span className="text-[10px] text-center text-slate-400">Logo esterno non utilizzabile</span>}</div></td>
              <td className="px-3 py-2 font-medium">{r.nome}</td>
              <td className="px-3 py-2 text-slate-600">{r.org_nome}</td>
              <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${ST[r.status][1]}`} data-testid={`logo-status-${r.id}`}>{ST[r.status][0]}</span></td>
              <td className="px-3 py-2 text-slate-500">{r.updated_at ? new Date(r.updated_at).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "—"}</td>
              <td className="px-3 py-2 text-right whitespace-nowrap">
                {r.status !== "published" && <Button size="sm" variant="outline" disabled={!r.valid} title={r.valid ? undefined : "Il logo non è stato caricato su CRMEvent: l'organizzazione deve caricarlo nella scheda evento"} onClick={() => onSet(r, "approved")} data-testid={`logo-publish-${r.id}`}>Pubblica</Button>}
                {r.status !== "excluded" && <Button size="sm" variant="outline" onClick={() => onSet(r, "excluded")} className="ml-1.5 text-red-600" data-testid={`logo-exclude-${r.id}`}>Escludi</Button>}
              </td>
            </tr>))}
            {!list.length && <tr><td colSpan={6} className="px-3 py-8 text-center text-slate-400">Nessun evento con logo trovato.</td></tr>}</tbody>
        </table>
      </div>
    </div>
  );
}

function CarouselAdmin() {
  const [s, setS] = useState(null); const [rows, setRows] = useState(null); const [busy, setBusy] = useState(false);
  const loadRows = useCallback(() => api.get("/homepage/logos").then(({ data }) => setRows(data)).catch((e) => toast.error(formatApiError(e.response?.data?.detail))), []);
  useEffect(() => { api.get("/homepage/settings").then(({ data }) => setS(data)); loadRows(); }, [loadRows]);
  const save = async () => {
    setBusy(true);
    try { const { data } = await api.put("/homepage/settings", { carousel_enabled: s.carousel_enabled, carousel_title: s.carousel_title.trim(), auto_new: s.auto_new }); setS(data); toast.success("Impostazioni salvate"); loadRows(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } finally { setBusy(false); }
  };
  const setStatus = async (r, status) => {
    try { await api.post(`/homepage/logos/${r.id}`, { status }); toast.success(status === "approved" ? `${r.nome} pubblicato in homepage` : `${r.nome} escluso dalla homepage`); loadRows(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  if (!s || !rows) return <p className="text-sm text-slate-400">Caricamento...</p>;
  const logos = rows.filter((r) => r.status === "published").map((r) => ({ id: r.id, name: r.nome, src: r.thumb }));
  return (
    <div className="space-y-8" data-testid="carousel-admin">
      <Settings s={s} setS={setS} onSave={save} busy={busy} />
      <div><h2 className="mb-3 font-display text-lg font-bold">Anteprima</h2><Preview title={s.carousel_title} logos={logos} /></div>
      <div><h2 className="mb-1 font-display text-lg font-bold">Loghi degli eventi</h2>
        <p className="mb-3 text-xs text-slate-500">Elenco automatico degli eventi con logo di tutte le organizzazioni, in ordine alfabetico. Solo gli eventi pubblicati compaiono in homepage; il nome dell'organizzazione non viene mostrato al pubblico.</p>
        <LogoTable rows={rows} onSet={setStatus} /></div>
    </div>
  );
}

export default function HomePageAdmin() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : "sezioni";
  return (
    <div className="max-w-6xl space-y-6 animate-fade-up" data-testid="homepage-admin">
      <div>
        <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400" data-testid="homepage-admin-breadcrumb">Marketing · Home Page</div>
        <h1 className="font-display text-2xl font-bold">Home Page</h1>
        <p className="text-sm text-slate-500">Sezioni e contenuti della homepage pubblica di crmevent.it.</p>
      </div>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map(([k, l]) => <button key={k} type="button" onClick={() => setParams({ tab: k }, { replace: true })} className={`-mb-px shrink-0 border-b-2 px-4 py-2 text-sm font-semibold ${tab === k ? "border-[#0ABAB5] text-slate-900" : "border-transparent text-slate-500"}`} data-testid={`homepage-tab-${k}`}>{l}</button>)}
      </div>
      {tab === "sezioni" ? <PlannerDemoAdmin embedded /> : <CarouselAdmin />}
    </div>
  );
}
