import { useEffect, useState } from "react";
import api from "@/lib/platformApi";
import { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Building2, Users, CalendarRange, Search, ShieldCheck, ExternalLink, GitMerge, Send, Instagram, Linkedin, Mail, Globe } from "lucide-react";

const FIELD = "w-full h-10 px-3 rounded-lg border border-slate-200 bg-white focus:border-tiffany focus:ring-2 focus:ring-tiffany/30 outline-none text-sm";
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: ShieldCheck },
  { id: "organizers", label: "Organizzatori", icon: Building2 },
  { id: "events", label: "Eventi trovati", icon: CalendarRange },
  { id: "finder", label: "Lead Finder", icon: Search },
  { id: "review", label: "Da verificare", icon: Users },
];
const STATE_LABEL = { da_verificare: "Da verificare", verificato: "Verificato", interessante: "Interessante", contattato: "Contattato", demo_richiesta: "Demo richiesta", trial: "Trial", cliente: "Cliente", non_interessato: "Non interessato", non_contattare: "Non contattare" };
const SCAN_STAT = [
  ["events_analyzed", "Eventi analizzati"], ["endu_reachable", "ENDU raggiungibili"],
  ["endu_with_site", "Siti ufficiali su ENDU"],
  ["endu_with_social", "Social su ENDU"], ["sites_visited", "Siti visitati"],
  ["organizers_identified", "Organizzatori identificati"], ["emails_found", "Email trovate"],
  ["instagram_found", "Instagram"], ["facebook_found", "Facebook"], ["linkedin_found", "LinkedIn"],
  ["duplicates_found", "Duplicati rilevati"], ["complete", "Record completi"],
  ["partial", "Record parziali"], ["to_verify", "Da verificare"],
];
const SCAN_BADGE = { Completo: "bg-emerald-100 text-emerald-700", Parziale: "bg-amber-100 text-amber-700", "Da verificare": "bg-slate-100 text-slate-600", Errore: "bg-red-100 text-red-700" };
const yesNo = (v) => (v ? "Sì" : "—");

function Stat({ label, value }) {
  return <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`lf-stat-${label}`}><div className="text-2xl font-bold text-slate-800">{value}</div><div className="text-xs text-slate-500 mt-1">{label}</div></div>;
}
function Dist({ title, data }) {
  const entries = Object.entries(data || {}).slice(0, 10);
  return <div className="rounded-xl border border-slate-200 bg-white p-4"><div className="text-sm font-semibold text-slate-700 mb-2">{title}</div>{entries.length === 0 ? <div className="text-xs text-slate-400">Nessun dato</div> : entries.map(([k, v]) => <div key={k} className="flex justify-between text-sm py-0.5"><span className="text-slate-600 truncate">{k}</span><span className="font-semibold text-slate-800">{v}</span></div>)}</div>;
}

export default function LeadFinder() {
  const [tab, setTab] = useState("dashboard");
  const [dash, setDash] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [events, setEvents] = useState([]);
  const [q, setQ] = useState("");
  const [fRegion, setFRegion] = useState(""); const [fSport, setFSport] = useState(""); const [fStatus, setFStatus] = useState("");
  const [fEmail, setFEmail] = useState(false); const [fIg, setFIg] = useState(false); const [fLi, setFLi] = useState(false);
  const [detail, setDetail] = useState(null);
  const [mergeSel, setMergeSel] = useState([]);
  const [scan, setScan] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [diag, setDiag] = useState(null);
  const [diagUrl, setDiagUrl] = useState("");
  const [diagBusy, setDiagBusy] = useState(false);

  const load = async () => {
    try {
      const [d, o, e] = await Promise.all([api.get("/leadfinder/dashboard"), api.get("/leadfinder/organizers"), api.get("/leadfinder/events")]);
      setDash(d.data); setOrgs(o.data); setEvents(e.data);
    } catch (err) { toast.error(formatApiError(err?.response?.data?.detail)); }
  };
  const loadLastScan = async () => {
    try {
      const { data } = await api.get("/leadfinder/scans");
      const last = (data || [])[0];
      if (last && last.status === "done") { const { data: full } = await api.get(`/leadfinder/scan/${last.id}`); setScan(full); }
    } catch { /* no scans yet */ }
  };
  useEffect(() => { load(); loadLastScan(); }, []);

  const regions = [...new Set(orgs.map((o) => o.region).filter(Boolean))].sort();
  const sports = [...new Set(events.map((e) => e.sport).filter(Boolean))].sort();

  const filtered = orgs.filter((o) => {
    if (fRegion && o.region !== fRegion) return false;
    if (fStatus && o.status !== fStatus) return false;
    if (fSport && !(o.sports || []).includes(fSport)) return false;
    if (fEmail && !(o.emails || []).length) return false;
    if (fIg && !o.instagram_url) return false;
    if (fLi && !o.linkedin_url) return false;
    if (q) { const s = q.toLowerCase(); if (!(`${o.name} ${o.city} ${o.region} ${(o.emails || []).join(" ")} ${(o.events || []).map((e) => e.name).join(" ")}`.toLowerCase().includes(s))) return false; }
    return true;
  });
  const toReview = orgs.filter((o) => o.status === "da_verificare" || o.socials_status === "da_verificare");

  const doMerge = async () => {
    if (mergeSel.length < 2) { toast.error("Seleziona almeno 2 organizzatori"); return; }
    try { await api.post("/leadfinder/organizers/merge", { primary_id: mergeSel[0], duplicate_ids: mergeSel.slice(1) }); toast.success("Duplicati uniti nel primo selezionato"); setMergeSel([]); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const setStatus = async (o, status) => {
    try { const { data } = await api.put(`/leadfinder/organizers/${o.id}`, { status, _manual: true, _verified: status === "verificato" }); setDetail(data); load(); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
  };
  const brevo = async () => { try { await api.post("/leadfinder/brevo-export", {}); } catch (e) { toast.info(formatApiError(e?.response?.data?.detail)); } };

  const startScan = async () => {
    setScanning(true); setScan(null);
    try {
      const { data } = await api.post("/leadfinder/scan-endu", {});
      const sid = data.scan_id;
      const poll = async () => {
        try {
          const { data: s } = await api.get(`/leadfinder/scan/${sid}`);
          setScan(s);
          if (s.status === "done" || s.status === "empty") {
            setScanning(false); load();
            if (s.status === "empty") toast.error(s.message || "Nessun evento acquisito"); else toast.success("Scansione ENDU completata");
            return;
          }
        } catch { /* keep polling */ }
        setTimeout(poll, 2500);
      };
      poll();
    } catch (e) { setScanning(false); toast.error(formatApiError(e?.response?.data?.detail)); }
  };

  const runDiagnose = async () => {
    setDiagBusy(true); setDiag(null);
    try { const { data } = await api.get("/leadfinder/diagnose", { params: diagUrl.trim() ? { url: diagUrl.trim() } : {} }); setDiag(data); }
    catch (e) { toast.error(formatApiError(e?.response?.data?.detail)); }
    finally { setDiagBusy(false); }
  };

  const Link = ({ url, icon: Icon, label }) => url ? <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-tiffany-fg hover:underline text-sm" data-testid={`lf-link-${label}`}><Icon className="w-4 h-4" />{label}<ExternalLink className="w-3 h-3" /></a> : <span className="inline-flex items-center gap-1 text-slate-400 text-sm"><Icon className="w-4 h-4" />Da verificare</span>;

  return (
    <div className="space-y-6" data-testid="leadfinder-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Organizzatori — Lead Finder</h1>
        <p className="text-sm text-slate-500">Database proprietario degli organizzatori di eventi sportivi italiani. Fonte iniziale: ENDU. Nessun invio a Brevo in questa fase.</p>
      </div>
      <div className="flex gap-1 border-b border-slate-200 overflow-x-auto">
        {TABS.map((t) => <button key={t.id} onClick={() => setTab(t.id)} data-testid={`lf-tab-${t.id}`} className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 -mb-px transition-colors ${tab === t.id ? "border-tiffany text-tiffany-fg" : "border-transparent text-slate-500 hover:text-slate-800"}`}><t.icon className="w-4 h-4" />{t.label}{t.id === "review" && toReview.length > 0 ? ` (${toReview.length})` : ""}</button>)}
      </div>

      {tab === "dashboard" && dash && (
        <div className="space-y-4" data-testid="lf-dashboard">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Organizzatori" value={dash.organizers_total} />
            <Stat label="Verificati" value={dash.organizers_verified} />
            <Stat label="Eventi censiti" value={dash.events_total} />
            <Stat label="Da verificare" value={dash.organizers_to_verify} />
            <Stat label="Con email" value={dash.with_email} />
            <Stat label="Con Instagram" value={dash.with_instagram} />
            <Stat label="Con LinkedIn" value={dash.with_linkedin} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Dist title="Per sport" data={dash.by_sport} />
            <Dist title="Per regione" data={dash.by_region} />
            <Dist title="Per fonte" data={dash.by_source} />
          </div>
        </div>
      )}

      {(tab === "organizers" || tab === "review") && (
        <div className="space-y-3" data-testid="lf-organizers">
          {tab === "organizers" && (
            <div className="flex flex-wrap gap-2 items-center">
              <div className="relative"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ricerca libera…" className={`${FIELD} pl-9 w-64`} data-testid="lf-search" /></div>
              <select value={fRegion} onChange={(e) => setFRegion(e.target.value)} className={`${FIELD} w-auto`} data-testid="lf-filter-region"><option value="">Regione</option>{regions.map((r) => <option key={r}>{r}</option>)}</select>
              <select value={fSport} onChange={(e) => setFSport(e.target.value)} className={`${FIELD} w-auto`} data-testid="lf-filter-sport"><option value="">Sport</option>{sports.map((s) => <option key={s}>{s}</option>)}</select>
              <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} className={`${FIELD} w-auto`} data-testid="lf-filter-status"><option value="">Stato</option>{Object.entries(STATE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              <label className="text-sm flex items-center gap-1"><input type="checkbox" checked={fEmail} onChange={(e) => setFEmail(e.target.checked)} data-testid="lf-filter-email" />Email</label>
              <label className="text-sm flex items-center gap-1"><input type="checkbox" checked={fIg} onChange={(e) => setFIg(e.target.checked)} />Instagram</label>
              <label className="text-sm flex items-center gap-1"><input type="checkbox" checked={fLi} onChange={(e) => setFLi(e.target.checked)} />LinkedIn</label>
              {mergeSel.length >= 2 && <Button size="sm" onClick={doMerge} data-testid="lf-merge-btn" className="bg-amber-500 hover:bg-amber-600 text-white"><GitMerge className="w-4 h-4 mr-1" />Unisci {mergeSel.length}</Button>}
            </div>
          )}
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr>
                {tab === "organizers" && <th className="p-2"></th>}
                <th className="p-2 text-left">Organizzazione</th><th className="p-2">Eventi</th><th className="p-2">Email</th><th className="p-2">Instagram</th><th className="p-2">LinkedIn</th><th className="p-2">Regione</th><th className="p-2">Fonte</th><th className="p-2">Stato</th><th className="p-2">Ultima verifica</th>
              </tr></thead>
              <tbody>
                {(tab === "organizers" ? filtered : toReview).map((o) => (
                  <tr key={o.id} className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" data-testid={`lf-org-row-${o.id}`}>
                    {tab === "organizers" && <td className="p-2 text-center"><input type="checkbox" checked={mergeSel.includes(o.id)} onChange={(e) => setMergeSel((s) => e.target.checked ? [...s, o.id] : s.filter((x) => x !== o.id))} onClick={(ev) => ev.stopPropagation()} data-testid={`lf-merge-check-${o.id}`} /></td>}
                    <td className="p-2 font-medium text-slate-800" onClick={() => setDetail(o)}>{o.name}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{o.events_count}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{yesNo((o.emails || []).length)}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{yesNo(o.instagram_url)}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{yesNo(o.linkedin_url)}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{o.region || "—"}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}>{o.source_main}</td>
                    <td className="p-2 text-center" onClick={() => setDetail(o)}><span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">{STATE_LABEL[o.status] || o.status}</span></td>
                    <td className="p-2 text-center text-xs text-slate-400" onClick={() => setDetail(o)}>{o.last_verified_at ? o.last_verified_at.slice(0, 10) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(tab === "organizers" ? filtered : toReview).length === 0 && <div className="p-6 text-center text-slate-400 text-sm">Nessun organizzatore</div>}
          </div>
        </div>
      )}

      {tab === "events" && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white" data-testid="lf-events">
          <table className="w-full text-sm"><thead className="bg-slate-50 text-slate-500 text-xs uppercase"><tr><th className="p-2 text-left">Evento</th><th className="p-2">Sport</th><th className="p-2">Data</th><th className="p-2">Città</th><th className="p-2">Regione</th><th className="p-2">Organizzatore</th><th className="p-2">Fonte ENDU</th></tr></thead>
            <tbody>{events.map((e) => (<tr key={e.id} className="border-t border-slate-100"><td className="p-2 font-medium text-slate-800">{e.name}</td><td className="p-2 text-center">{e.sport}</td><td className="p-2 text-center">{e.date}</td><td className="p-2 text-center">{e.city} {e.province ? `(${e.province})` : ""}</td><td className="p-2 text-center">{e.region}</td><td className="p-2 text-center">{e.organizer_name || "—"}</td><td className="p-2 text-center">{e.endu_url ? <a href={e.endu_url} target="_blank" rel="noreferrer" className="text-tiffany-fg hover:underline"><ExternalLink className="w-4 h-4 inline" /></a> : "—"}</td></tr>))}</tbody>
          </table>
          {events.length === 0 && <div className="p-6 text-center text-slate-400 text-sm">Nessun evento</div>}
        </div>
      )}

      {tab === "finder" && (
        <div className="space-y-4" data-testid="lf-finder">
          <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
            <div className="text-sm text-slate-700">Il Lead Finder ricerca organizzatori ed eventi da fonti pubbliche. <strong>Fonte attiva: ENDU.</strong></div>
            <div className="text-sm text-slate-600">Catena di scansione: <strong>ENDU → sito ufficiale → pagine rilevanti → organizzatore → contatti → social → deduplicazione → CRMEvent.</strong> I risultati vengono salvati in stato <em>Da verificare</em>: nessun dato è inventato, ogni informazione conserva la propria fonte. LinkedIn è associato solo se presente esplicitamente su ENDU o sui siti ufficiali.</div>
            <div className="flex flex-wrap gap-2 pt-1">
              <Button onClick={startScan} disabled={scanning} data-testid="lf-scan-btn" className="bg-tiffany hover:bg-tiffany/90 text-slate-900">
                <Search className="w-4 h-4 mr-1" />{scanning ? "Scansione in corso…" : "Scansiona ENDU + Arricchisci"}
              </Button>
              <Button disabled variant="outline" className="opacity-60 cursor-not-allowed" data-testid="lf-brevo-btn-disabled" onClick={brevo}><Send className="w-4 h-4 mr-1" />Esporta/Sincronizza con Brevo (non attivo)</Button>
            </div>
            {scan && (
              scan.status === "empty" ? (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2" data-testid="lf-scan-empty">
                  <strong>Nessun evento acquisito — scansione da verificare.</strong>{scan.reason ? <div className="text-xs mt-1">{scan.reason}</div> : null}
                </div>
              ) : (
                <div className="text-xs text-slate-500" data-testid="lf-scan-progress">
                  Stato: <strong>{scan.status === "done" ? "Completata" : "In corso"}</strong> — {scan.done || 0}/{scan.total || 0} eventi analizzati{scan.seeded ? ` · ${scan.seeded} eventi ENDU importati` : ""}
                </div>
              )
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3" data-testid="lf-diagnose">
            <div className="text-sm font-semibold text-slate-700">Diagnostica su 1 evento ENDU</div>
            <div className="text-xs text-slate-500">Verifica end-to-end del primo passaggio della pipeline su un singolo evento (nessun dato salvato). Lascia vuoto per usare un evento ENDU noto.</div>
            <div className="flex flex-wrap gap-2">
              <input value={diagUrl} onChange={(e) => setDiagUrl(e.target.value)} placeholder="https://www.endu.net/events/…" className={`${FIELD} flex-1 min-w-[260px]`} data-testid="lf-diagnose-url" />
              <Button variant="outline" onClick={runDiagnose} disabled={diagBusy} data-testid="lf-diagnose-btn"><ShieldCheck className="w-4 h-4 mr-1" />{diagBusy ? "Verifica…" : "Diagnostica"}</Button>
            </div>
            {diag && (
              <div className="text-xs bg-slate-50 rounded-lg border border-slate-200 p-3 space-y-1" data-testid="lf-diagnose-result">
                <div><span className="text-slate-400">URL ENDU:</span> <a href={diag.endu_url} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.endu_url}</a></div>
                <div><span className="text-slate-400">HTTP:</span> <strong className={diag.http_status === 200 ? "text-emerald-600" : "text-red-600"}>{diag.http_status ?? "—"}</strong> · {diag.bytes || 0} byte {diag.final_url && diag.final_url !== diag.endu_url ? `→ ${diag.final_url}` : ""}</div>
                <div><span className="text-slate-400">Evento:</span> {diag.name || "—"} · <span className="text-slate-400">data</span> {diag.date || "—"} · <span className="text-slate-400">città</span> {diag.city || "—"} {diag.province ? `(${diag.province})` : ""}</div>
                <div><span className="text-slate-400">Sito ufficiale:</span> {diag.official_site ? <a href={diag.official_site} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.official_site}</a> : "—"} {diag.official_reachable === false ? <span className="text-red-600">(non raggiungibile)</span> : diag.official_reachable ? <span className="text-emerald-600">(raggiungibile)</span> : null}</div>
                <hr className="my-1 border-slate-200" />
                <div><span className="text-slate-400">Organizzatore:</span> {diag.organizer || "—"} {diag.org_site ? <a href={diag.org_site} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">· sito org.</a> : ""}</div>
                <div><span className="text-slate-400">Email:</span> {diag.email_main ? <strong>{diag.email_main}</strong> : "—"}{(diag.emails || []).length > 1 ? ` (+${diag.emails.length - 1})` : ""}</div>
                <div><span className="text-slate-400">Telefono:</span> {diag.phone || "—"}</div>
                <div><span className="text-slate-400">Instagram evento (ENDU):</span> {diag.instagram_event ? <a href={diag.instagram_event} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.instagram_event}</a> : "—"}</div>
                <div><span className="text-slate-400">Instagram organizzatore (sito):</span> {diag.instagram_org ? <a href={diag.instagram_org} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.instagram_org}</a> : "—"}</div>
                <div><span className="text-slate-400">Facebook:</span> {diag.facebook ? <a href={diag.facebook} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.facebook}</a> : "—"}</div>
                <div><span className="text-slate-400">LinkedIn:</span> {diag.linkedin ? <a href={diag.linkedin} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{diag.linkedin}</a> : "—"}</div>
                <div><span className="text-slate-400">Pagine sito analizzate ({(diag.pages_analyzed || []).length}):</span>
                  <ul className="list-disc pl-5 mt-0.5">{(diag.pages_analyzed || []).map((u, i) => <li key={i}><a href={u} target="_blank" rel="noreferrer" className="text-tiffany-fg break-all">{u}</a></li>)}{(diag.pages_analyzed || []).length === 0 ? <li className="text-slate-400 list-none">—</li> : null}</ul>
                </div>
                {(diag.not_found || []).length > 0 && (
                  <div><span className="text-amber-600 font-medium">Dati non trovati:</span>
                    <ul className="list-disc pl-5 mt-0.5 text-amber-700">{diag.not_found.map((n, i) => <li key={i}>{n}</li>)}</ul>
                  </div>
                )}
                {diag.error ? <div className="text-red-600"><span className="text-slate-400">Errore:</span> {diag.error}</div> : <div className="text-emerald-600 font-medium">Pipeline ENDU → sito ufficiale → contatti OK</div>}
              </div>
            )}
          </div>

          {scan && scan.stats && Object.keys(scan.stats).length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3" data-testid="lf-scan-stats">
              {SCAN_STAT.map(([k, label]) => <Stat key={k} label={label} value={scan.stats[k] ?? 0} />)}
            </div>
          )}

          {scan && (scan.rows || []).length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white" data-testid="lf-scan-table">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-slate-500 uppercase"><tr>
                  <th className="p-2 text-left">Evento</th><th className="p-2 text-left">Organizzatore</th><th className="p-2">Sito evento</th><th className="p-2">Sito org.</th><th className="p-2">Email</th><th className="p-2">IG</th><th className="p-2">FB</th><th className="p-2">LinkedIn</th><th className="p-2">Stato</th><th className="p-2 text-left">Note</th>
                </tr></thead>
                <tbody>
                  {scan.rows.map((r, i) => (
                    <tr key={i} className="border-t border-slate-100 align-top" data-testid={`lf-scan-row-${i}`}>
                      <td className="p-2 font-medium text-slate-800">{r.endu_url ? <a href={r.endu_url} target="_blank" rel="noreferrer" className="hover:underline">{r.event}</a> : r.event}</td>
                      <td className="p-2 text-slate-700">{r.organizer_legal || r.organizer || "—"}</td>
                      <td className="p-2 text-center">{r.event_site ? <a href={r.event_site} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Globe className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center">{r.org_site ? <a href={r.org_site} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Globe className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-slate-600">{(r.emails || []).length ? (r.emails || []).join(", ") : "—"}</td>
                      <td className="p-2 text-center">{r.instagram ? <a href={r.instagram} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Instagram className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center">{r.facebook ? <a href={r.facebook} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Globe className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center">{r.linkedin ? <a href={r.linkedin} target="_blank" rel="noreferrer" className="text-tiffany-fg"><Linkedin className="w-4 h-4 inline" /></a> : "—"}</td>
                      <td className="p-2 text-center whitespace-nowrap"><span className={`px-2 py-0.5 rounded-full ${SCAN_BADGE[r.status] || "bg-slate-100 text-slate-600"}`}>{r.status}</span>{r.duplicate_of && <div className="text-[10px] text-amber-600 mt-0.5">dup? {r.duplicate_of.name}</div>}</td>
                      <td className="p-2 text-slate-400">{r.reason || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <ul className="text-xs text-slate-500 list-disc pl-5 space-y-1">
            <li>Dati a livello evento (nome, sport, città/provincia, data, URL) recuperati da ENDU.</li>
            <li>Email e social ufficiali provengono dai siti ufficiali; ogni dato conserva l'URL della pagina sorgente.</li>
            <li>La scansione massiva e i provider esterni a pagamento non sono attivi.</li>
          </ul>
        </div>
      )}

      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="lf-org-detail">
          {detail && (<>
            <DialogHeader><DialogTitle>{detail.name}</DialogTitle></DialogHeader>
            <div className="space-y-4 text-sm">
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Anagrafica</div>
                <div className="grid grid-cols-2 gap-1 text-slate-700"><div>Ragione sociale: {detail.legal_name || "—"}</div><div>Tipologia: {detail.org_type || "—"}</div><div>Città: {detail.city || "—"} {detail.province ? `(${detail.province})` : ""}</div><div>Regione: {detail.region || "—"}</div><div className="col-span-2"><Link url={detail.website} icon={Globe} label="Sito web" /></div></div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Contatti</div>
                <div className="text-slate-700">{(detail.emails || []).length ? detail.emails.map((e) => <span key={e} className="inline-flex items-center gap-1 mr-3"><Mail className="w-4 h-4" />{e}</span>) : <span className="text-slate-400 inline-flex items-center gap-1"><Mail className="w-4 h-4" />Da verificare</span>}{detail.phone ? <div>Tel: {detail.phone}</div> : null}</div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Social</div>
                <div className="flex gap-4 flex-wrap"><Link url={detail.instagram_url} icon={Instagram} label="Instagram" /><Link url={detail.linkedin_url} icon={Linkedin} label="LinkedIn" /><Link url={detail.facebook_url} icon={Globe} label="Facebook" /></div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Eventi organizzati ({(detail.events || []).length})</div>
                <ul className="space-y-1">{(detail.events || []).map((e) => <li key={e.id} className="flex items-center justify-between"><span>{e.name} · <span className="text-slate-500">{e.sport} · {e.city} · {e.date}</span></span>{e.endu_url && <a href={e.endu_url} target="_blank" rel="noreferrer" className="text-tiffany-fg"><ExternalLink className="w-3.5 h-3.5" /></a>}</li>)}</ul>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Fonti</div>
                <div className="text-slate-600">Principale: {detail.source_main} {detail.source_url && <a href={detail.source_url} target="_blank" rel="noreferrer" className="text-tiffany-fg ml-1"><ExternalLink className="w-3.5 h-3.5 inline" /></a>}</div>
                <div className="text-xs text-slate-400">Acquisito: {(detail.acquired_at || "").slice(0, 10) || "—"} · Ultima verifica: {(detail.last_verified_at || "").slice(0, 10) || "—"}</div>
              </section>
              <section><div className="text-xs font-semibold uppercase text-slate-400 mb-1">Stato</div>
                {detail.possibile_duplicato && <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1 mb-2" data-testid="lf-detail-dup">Possibile duplicato di: <strong>{detail.possibile_duplicato.name}</strong> — verifica e usa "Unisci duplicati" se confermato.</div>}
                <select value={detail.status} onChange={(e) => setStatus(detail, e.target.value)} className={FIELD} data-testid="lf-detail-status">{Object.entries(STATE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                {detail.status === "non_contattare" && <div className="text-xs text-red-600 mt-1">"Non contattare" ha priorità e non viene sovrascritto dalle ricerche automatiche.</div>}
              </section>
            </div>
          </>)}
        </DialogContent>
      </Dialog>
    </div>
  );
}
