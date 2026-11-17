import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Plus, UserPlus, Crosshair, Phone } from "lucide-react";
import { PRESIDIO, RES_STATES, KINDS, label, resourceIcon, nameOf } from "./meta";

const TABS = [["resources", "Risorse"], ["posts", "Postazioni"], ["sectors", "Settori"], ["interventions", "Interventi"], ["alerts", "Avvisi"]];
const Sel = ({ value, onChange, children, testid }) => <select value={value} onChange={(e) => onChange(e.target.value)} className="h-9 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs" data-testid={testid}>{children}</select>;
const Badge = ({ c, children }) => <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${c}`}>{children}</span>;
const Row = ({ onClick, children, testid }) => <button type="button" onClick={onClick} className="flex w-full items-center gap-3 rounded-lg border border-slate-100 bg-white px-3 py-2.5 text-left transition-colors hover:border-[#0ABAB5]/50 hover:bg-[#0ABAB5]/5" data-testid={testid}>{children}</button>;

function Resources({ d, q, open, onAdd, onImport }) {
  const [f, setF] = useState({ kind: "", stato: "", sector: "", post: "" });
  const set = (k) => (v) => setF((o) => ({ ...o, [k]: v }));
  const posts = Object.fromEntries(d.posts.map((p) => [p.id, p]));
  const rows = d.resources.filter((r) => (!f.kind || r.kind === f.kind) && (!f.stato || r.stato === f.stato) && (!f.sector || r.sector_id === f.sector || posts[r.post_id]?.sector_id === f.sector)
    && (!f.post || r.post_id === f.post) && (!q || [r.nome, r.codice, r.telefono, r.targa].some((x) => x && x.toLowerCase().includes(q))));
  return (
    <>
      <div className="grid grid-cols-2 gap-1.5">
        <Sel value={f.kind} onChange={set("kind")} testid="cr-filter-kind"><option value="">Tutti i tipi</option>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Sel>
        <Sel value={f.stato} onChange={set("stato")} testid="cr-filter-stato"><option value="">Tutti gli stati</option>{RES_STATES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Sel>
        <Sel value={f.sector} onChange={set("sector")} testid="cr-filter-sector"><option value="">Tutti i settori</option>{d.sectors.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}</Sel>
        <Sel value={f.post} onChange={set("post")} testid="cr-filter-post"><option value="">Tutte le postazioni</option>{d.posts.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</Sel>
      </div>
      {d.perms.edit && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={onImport} className="flex-1" data-testid="cr-import-staff-btn"><UserPlus className="mr-1 h-4 w-4" />Da Staff / Volontari</Button>
        <Button size="sm" onClick={onAdd} className="flex-1 bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-add-resource-btn"><Plus className="mr-1 h-4 w-4" />Risorsa o mezzo</Button></div>}
      {rows.map((r) => {
        const I = resourceIcon(r), s = label(RES_STATES, r.stato);
        return (
          <Row key={r.id} onClick={() => open("resources", r.id)} testid={`cr-resource-${r.id}`}>
            <I className="h-4 w-4 shrink-0 text-[#088F8A]" />
            <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{nameOf(r)}{r.caposquadra && <span className="ml-1 text-[10px] text-[#088F8A]">CAPOSQUADRA</span>}</div>
              <div className="truncate text-[11px] text-slate-500">{[r.codice, posts[r.post_id]?.nome, r.turno_label].filter(Boolean).join(" · ") || "Non assegnata"}</div></div>
            {r.kind === "persona" && <span className={`h-2 w-2 shrink-0 rounded-full ${r.presente ? "bg-emerald-500" : "bg-slate-300"}`} title={r.presente ? "Presente" : "Presenza non confermata"} />}
            <Badge c={s[2]}>{s[1]}</Badge>
          </Row>
        );
      })}
      {!rows.length && <div className="py-6 text-center text-xs text-slate-400" data-testid="cr-resources-empty">Nessuna risorsa</div>}
    </>
  );
}

function Posts({ d, q, open, onPlace, placing }) {
  const rows = d.posts.filter((p) => !q || [p.nome, p.codice, p.telefono, p.responsabile].some((x) => x && x.toLowerCase().includes(q)));
  const cats = Object.fromEntries(d.settings.categories.map((c) => [c.key, c.label]));
  return (
    <>
      {d.perms.edit && <Button size="sm" onClick={onPlace} className={`w-full ${placing ? "bg-amber-500 hover:bg-amber-600" : "bg-[#0ABAB5] hover:bg-[#09A8A3]"} text-slate-900`} data-testid="cr-place-post-btn">
        <Crosshair className="mr-1 h-4 w-4" />{placing ? "Clicca sulla mappa… (annulla)" : "Nuova postazione sulla mappa"}</Button>}
      {rows.map((p) => {
        const s = PRESIDIO[p.presidio];
        return (
          <Row key={p.id} onClick={() => open("posts", p.id)} testid={`cr-post-${p.id}`}>
            <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{p.codice ? `${p.codice} · ` : ""}{p.nome}</div>
              <div className="truncate text-[11px] text-slate-500">{[cats[p.categoria], p.km != null && `km ${p.km}`, `${p.presenti}/${p.previsti} operatori`].filter(Boolean).join(" · ")}</div></div>
            <Badge c={s[1]}>{s[0]}</Badge>
          </Row>
        );
      })}
      {!rows.length && <div className="py-6 text-center text-xs text-slate-400">Nessuna postazione</div>}
    </>
  );
}

function Sectors({ d, open, highlight, setHighlight, onAdd }) {
  return (
    <>
      {d.perms.edit && <Button size="sm" onClick={onAdd} className="w-full bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-add-sector-btn"><Plus className="mr-1 h-4 w-4" />Nuovo settore</Button>}
      {d.sectors.map((s) => (
        <div key={s.id} className={`rounded-lg border p-3 ${highlight === s.id ? "border-[#0ABAB5] bg-[#0ABAB5]/5" : "border-slate-100"}`} data-testid={`cr-sector-${s.id}`}>
          <div className="flex items-center gap-2"><span className="h-3 w-3 rounded-full" style={{ background: s.colore || "#7C3AED" }} />
            <button type="button" onClick={() => open("sectors", s.id)} className="min-w-0 flex-1 truncate text-left text-sm font-semibold hover:underline" data-testid={`cr-sector-open-${s.id}`}>{s.codice ? `${s.codice} · ` : ""}{s.nome}</button>
            <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setHighlight(highlight === s.id ? null : s.id)} data-testid={`cr-sector-highlight-${s.id}`}>{highlight === s.id ? "Normale" : "Evidenzia"}</Button></div>
          <div className="mt-1 text-[11px] text-slate-500">{s.km_inizio ?? "?"}–{s.km_fine ?? "?"} km{s.responsabile ? ` · ${s.responsabile}` : ""}{s.telefono && <a href={`tel:${s.telefono}`} className="ml-1 text-[#088F8A]"><Phone className="inline h-3 w-3" /> {s.telefono}</a>}</div>
          <div className="mt-2 grid grid-cols-4 gap-1 text-center text-[11px]" data-testid={`cr-sector-summary-${s.id}`}>
            {[["Postaz.", s.summary.postazioni], ["Volont.", s.summary.volontari], ["Presenti", s.summary.presenti], ["Mezzi disp.", `${s.summary.mezzi_disponibili}/${s.summary.mezzi}`]].map(([l, v]) =>
              <div key={l} className="rounded bg-slate-50 py-1"><div className="font-bold text-slate-800">{v}</div><div className="text-slate-400">{l}</div></div>)}
          </div>
        </div>
      ))}
      {!d.sectors.length && <div className="py-6 text-center text-xs text-slate-400">Dividi il percorso in settori operativi</div>}
    </>
  );
}

function Interventions({ d, open }) {
  return d.interventions.length ? d.interventions.map((i) => (
    <Row key={i.id} onClick={() => open("interventions", i.id)} testid={`cr-intervention-${i.id}`}>
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${i.stato === "chiuso" ? "bg-slate-300" : i.priorita === "urgente" ? "bg-red-600" : "bg-orange-400"}`} />
      <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{i.titolo}</div><div className="text-[11px] text-slate-500">{new Date(i.created_at).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })} · {i.created_by}</div></div>
      <Badge c={i.stato === "chiuso" ? "bg-slate-100 text-slate-500" : i.priorita === "urgente" ? "bg-red-100 text-red-700" : "bg-orange-100 text-orange-700"}>{i.stato === "chiuso" ? "CHIUSO" : i.priorita === "urgente" ? "URGENTE" : "APERTO"}</Badge>
    </Row>
  )) : <div className="py-6 text-center text-xs text-slate-400">Nessun intervento. La gestione completa arriva con la Fase 3.</div>;
}

function Alerts({ d, open }) {
  return (
    <>
      {d.alerts.map((a, i) => <Row key={i} onClick={() => open(...a.ref)} testid={`cr-alert-${i}`}><span className={`h-2.5 w-2.5 shrink-0 rounded-full ${a.level === "high" ? "bg-red-600" : "bg-amber-400"}`} /><span className="text-sm">{a.text}</span></Row>)}
      {!d.alerts.length && <div className="py-4 text-center text-xs text-slate-400">Nessun avviso</div>}
      <div className="pt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Ultime modifiche</div>
      {d.log.slice(0, 15).map((l) => <div key={l.id} className="text-[11px] text-slate-500" data-testid="cr-log-row"><span className="font-mono">{new Date(l.at).toLocaleTimeString("it-IT")}</span> · {l.by} · {l.action} {l.entity} {l.label}</div>)}
    </>
  );
}

export function SidePanel(props) {
  const { d, tab, setTab } = props;
  const [q, setQ] = useState("");
  const ql = useMemo(() => q.trim().toLowerCase(), [q]);
  const P = { resources: Resources, posts: Posts, sectors: Sectors, interventions: Interventions, alerts: Alerts }[tab];
  return (
    <div className="flex h-full flex-col" data-testid="cr-side-panel">
      <div className="flex flex-wrap gap-1 border-b border-slate-100 p-2">
        {TABS.map(([k, l]) => <button key={k} type="button" onClick={() => setTab(k)} className={`shrink-0 rounded-full px-2.5 py-1.5 text-xs font-semibold transition-colors ${tab === k ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"}`} data-testid={`cr-tab-${k}`}>
          {l}{k === "alerts" && d.alerts.length > 0 && <span className="ml-1 rounded-full bg-red-600 px-1.5 text-[10px] text-white">{d.alerts.length}</span>}</button>)}
      </div>
      {(tab === "resources" || tab === "posts") && <div className="relative px-2 pt-2"><Search className="absolute left-4 top-1/2 mt-1 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca nome, codice, telefono…" className="h-9 pl-8 text-sm" data-testid="cr-search" /></div>}
      <div className="flex-1 space-y-2 overflow-y-auto p-2">{<P {...props} q={ql} />}</div>
    </div>
  );
}
