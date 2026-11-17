import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { LayoutGrid, List, Download, Send, CheckCheck, Check } from "lucide-react";
import api from "@/lib/api";
import { CLOSED, ITV_STATES, PRIORITY, Pill, fmtDT, fmtTime, nameOf } from "./meta";

const RANK = { critica: 0, alta: 1, media: 2, bassa: 3 };
const Sel = ({ value, onChange, children, testid }) => <select value={value} onChange={(e) => onChange(e.target.value)} className="h-9 rounded-md border border-slate-200 bg-white px-2 text-xs" data-testid={testid}>{children}</select>;

export function ItvList({ d, open }) {
  const [f, setF] = useState({ sector: "", type: "", state: "aperti", team: "", q: "", sort: "prio" });
  const [cards, setCards] = useState(() => window.innerWidth < 640);
  const set = (k) => (v) => setF((o) => ({ ...o, [k]: v }));
  const types = Object.fromEntries(d.itv_types.map((t) => [t.key, t]));
  const rows = useMemo(() => d.interventions.filter((i) => (!f.sector || i.sector_id === f.sector) && (!f.type || i.tipologia === f.type)
    && (f.state === "" || (f.state === "aperti" ? !CLOSED.includes(i.stato) : i.stato === f.state)) && (!f.team || (i.assignments || []).some((a) => a.resource_id === f.team && a.stato !== "revocata"))
    && (!f.q || i.codice.toLowerCase().includes(f.q.toLowerCase()))).sort((a, b) => (f.sort === "prio" ? RANK[a.priorita] - RANK[b.priorita] || b.numero - a.numero : b.numero - a.numero)), [d.interventions, f]);
  const k = d.kpi;
  const team = (i) => (i.assignments || []).filter((a) => ["non_confermata", "confermata"].includes(a.stato)).map((a) => a.label).join(", ");
  return (
    <div className="space-y-3" data-testid="cr-itv-list">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {[["interventi_aperti", "Aperti"], ["interventi_critici", "Critici"], ["interventi_senza_squadra", "Senza squadra"], ["interventi_attesa_conferma", "Attesa conferma"], ["interventi_in_corso", "In corso"], ["interventi_risolti", "Risolti"]].map(([key, l]) =>
          <div key={key} className={`rounded-xl border px-3 py-2 ${key === "interventi_critici" && k[key] ? "border-red-300 bg-red-50 text-red-700" : "border-slate-100 bg-white"}`} data-testid={`cr-itvkpi-${key}`}><div className="text-[11px] text-slate-500">{l}</div><div className="text-xl font-bold">{k[key]}</div></div>)}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <Input value={f.q} onChange={(e) => set("q")(e.target.value)} placeholder="Codice INT-…" className="h-9 w-32 text-xs" data-testid="cr-itv-search" />
        <Sel value={f.state} onChange={set("state")} testid="cr-itv-filter-state"><option value="aperti">Aperti</option><option value="">Tutti gli stati</option>{Object.entries(ITV_STATES).map(([s, [l]]) => <option key={s} value={s}>{l}</option>)}</Sel>
        <Sel value={f.type} onChange={set("type")} testid="cr-itv-filter-type"><option value="">Tutte le tipologie</option>{d.itv_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</Sel>
        <Sel value={f.sector} onChange={set("sector")} testid="cr-itv-filter-sector"><option value="">Tutti i settori</option>{d.sectors.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}</Sel>
        <Sel value={f.team} onChange={set("team")} testid="cr-itv-filter-team"><option value="">Tutte le squadre</option>{d.resources.filter((r) => r.kind !== "persona").concat(d.resources.filter((r) => r.kind === "persona")).map((r) => <option key={r.id} value={r.id}>{nameOf(r)}</option>)}</Sel>
        <Sel value={f.sort} onChange={set("sort")} testid="cr-itv-sort"><option value="prio">Ordina per priorità</option><option value="time">Ordina per orario</option></Sel>
        <Button size="icon" variant="outline" className="ml-auto h-9 w-9" onClick={() => setCards(!cards)} title={cards ? "Vista tabella" : "Vista schede"} data-testid="cr-itv-view-toggle">{cards ? <List className="h-4 w-4" /> : <LayoutGrid className="h-4 w-4" />}</Button>
      </div>
      {cards ? (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{rows.map((i) => (
          <button key={i.id} type="button" onClick={() => open(i.id)} className={`rounded-xl border bg-white p-3 text-left transition-shadow hover:shadow ${i.priorita === "critica" && !CLOSED.includes(i.stato) ? "border-red-400 ring-2 ring-red-200" : "border-slate-200"}`} data-testid={`cr-itv-card-${i.codice}`}>
            <div className="flex items-center gap-1.5"><b>{i.codice}</b><Pill c={PRIORITY[i.priorita][2]}>{PRIORITY[i.priorita][0]}</Pill><Pill c={ITV_STATES[i.stato][1]}>{ITV_STATES[i.stato][0]}</Pill>{i.origine === "campo" && i.stato === "segnalato" && <Pill c="bg-sky-600 text-white">DAL CAMPO</Pill>}</div>
            <div className="mt-1 text-xs font-semibold text-slate-600">{types[i.tipologia]?.label} · {fmtTime(i.created_at)}</div>
            <div className="mt-1 line-clamp-2 text-sm">{i.descrizione}</div>
            <div className="mt-1 text-[11px] text-slate-500">{team(i) || <span className="font-semibold text-orange-600">Senza squadra</span>}{i.attesa_conferma && <span className="ml-1 font-semibold text-red-600">· NON CONFERMATA</span>}</div>
          </button>))}</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full min-w-[640px] text-left text-xs"><thead className="bg-slate-50 text-slate-500"><tr>{["Codice", "Ora", "Tipologia", "Priorità", "Stato", "Squadre", "Posizione"].map((h) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{rows.map((i) => (
              <tr key={i.id} onClick={() => open(i.id)} className={`cursor-pointer border-t border-slate-100 hover:bg-[#0ABAB5]/5 ${i.priorita === "critica" && !CLOSED.includes(i.stato) ? "bg-red-50" : ""}`} data-testid={`cr-itv-row-${i.codice}`}>
                <td className="px-3 py-2 font-bold">{i.codice}{i.origine === "campo" && i.stato === "segnalato" && <Pill c="ml-1 bg-sky-600 text-white">CAMPO</Pill>}</td><td className="px-3 py-2 font-mono">{fmtTime(i.created_at)}</td><td className="px-3 py-2">{types[i.tipologia]?.label}</td>
                <td className="px-3 py-2"><Pill c={PRIORITY[i.priorita][2]}>{PRIORITY[i.priorita][0]}</Pill></td><td className="px-3 py-2"><Pill c={ITV_STATES[i.stato][1]}>{ITV_STATES[i.stato][0]}</Pill></td>
                <td className="px-3 py-2">{team(i) || <span className="font-semibold text-orange-600">—</span>}{i.attesa_conferma && <span className="ml-1 font-semibold text-red-600">NON CONF.</span>}</td>
                <td className="px-3 py-2">{[i.km != null && `km ${i.km}`, d.posts.find((p) => p.id === (i.post_id || i.post_vicina_id))?.nome, i.riferimento].filter(Boolean).join(" · ")}{i.da_confermare && <span className="ml-1 text-amber-600">(da confermare)</span>}</td>
              </tr>))}</tbody></table>
          {!rows.length && <div className="p-6 text-center text-xs text-slate-400">Nessun intervento</div>}
        </div>
      )}
    </div>
  );
}

export function Comms({ d, call, preset }) {
  const [v, setV] = useState({ to_type: preset?.to_id ? "operatore" : "tutti", to_id: preset?.to_id || "", text: "", intervention_id: preset?.intervention_id || null });
  const can = ["responsabile", "coordinatore"].includes(d.perms.role);
  const send = async () => { if (await call("post", "/messages", { ...v, to_id: v.to_id || null }, "Messaggio registrato")) setV({ ...v, text: "" }); };
  const opts = v.to_type === "settore" ? d.sectors : d.resources.filter((r) => (v.to_type === "squadra" ? r.kind !== "persona" : r.kind === "persona"));
  return (
    <div className="grid gap-3 lg:grid-cols-[360px_1fr]" data-testid="cr-comms">
      {can && <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-3">
        <div className="text-sm font-semibold">Nuova comunicazione</div>
        <select className="h-10 w-full rounded-md border border-slate-200 px-2 text-sm" value={v.to_type} onChange={(e) => setV({ ...v, to_type: e.target.value, to_id: "" })} data-testid="cr-msg-to-type">
          {[["operatore", "Un operatore"], ["squadra", "Una squadra / mezzo"], ["settore", "Un settore"], ["coordinatori", "Tutti i coordinatori"], ["tutti", "Tutti gli operatori autorizzati"]].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        {["operatore", "squadra", "settore"].includes(v.to_type) && <select className="h-10 w-full rounded-md border border-slate-200 px-2 text-sm" value={v.to_id} onChange={(e) => setV({ ...v, to_id: e.target.value })} data-testid="cr-msg-to-id"><option value="">Destinatario…</option>{opts.map((o) => <option key={o.id} value={o.id}>{o.nome || o.codice}</option>)}</select>}
        <Textarea value={v.text} onChange={(e) => setV({ ...v, text: e.target.value })} placeholder="Testo del messaggio" className="min-h-[80px]" data-testid="cr-msg-text" />
        <Button disabled={!v.text.trim()} onClick={send} className="w-full bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-msg-send"><Send className="mr-1 h-4 w-4" />INVIA MESSAGGIO</Button>
        <p className="text-[11px] text-slate-400">I messaggi arrivano nella pagina mobile degli operatori con invito attivo. Nessun SMS o WhatsApp viene inviato. Per le emergenze usa telefono o radio.</p>
      </div>}
      <div className="space-y-1.5" data-testid="cr-msg-list">
        {d.unread_inbound > 0 && <Button size="sm" variant="outline" onClick={() => call("post", "/messages/read")} data-testid="cr-msg-mark-read">Segna come letti i messaggi ricevuti ({d.unread_inbound})</Button>}
        {d.messages.map((m) => (
          <div key={m.id} className={`rounded-lg border px-3 py-2 text-sm ${m.to_type === "centrale" ? (m.read_at ? "border-slate-100 bg-white" : "border-sky-300 bg-sky-50") : "border-slate-100 bg-white"}`} data-testid={`cr-msg-${m.id}`}>
            <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-slate-500"><b className="text-slate-700">{m.from_name}</b>→ {m.to_label}<span className="font-mono">{fmtDT(m.at)}</span>
              {m.to_type === "centrale" ? <span>{m.read_at ? "letto dalla centrale" : "da leggere"}</span>
                : m.n_recipients ? <span className="flex items-center gap-1" data-testid="cr-msg-status"><Check className="h-3 w-3" />consegnato {m.n_delivered}/{m.n_recipients}<CheckCheck className="ml-1 h-3 w-3 text-sky-600" />letto {m.n_read}/{m.n_recipients}</span>
                  : <span className="font-semibold text-amber-700" data-testid="cr-msg-status">nessun destinatario con accesso mobile: contatta via telefono/radio</span>}</div>
            <div className="mt-0.5 whitespace-pre-wrap">{m.text}</div>
          </div>))}
        {!d.messages.length && <div className="p-6 text-center text-xs text-slate-400">Nessuna comunicazione</div>}
      </div>
    </div>
  );
}

const DTYPES = ["segnalazione", "apertura", "cambio_priorita", "assegnazione", "conferma", "rifiuto", "partenza", "arrivo", "aggiornamento", "risoluzione", "chiusura", "annullamento", "riapertura", "comunicazione", "presenza", "allegato", "presa_in_carico", "stato"];

export function Diary({ d, base, open }) {
  const [type, setType] = useState("");
  const [rows, setRows] = useState(null);
  const load = (t) => api.get(`${base}/diary`, { params: { type: t || undefined } }).then((r) => setRows(r.data.rows)).catch(() => setRows([]));
  if (rows === null) load(type);
  const exp = async () => {
    const r = await api.get(`${base}/diary/export`, { responseType: "blob" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(r.data); a.download = "diario-operativo.csv"; a.click();
  };
  return (
    <div className="space-y-2" data-testid="cr-diary">
      <div className="flex flex-wrap items-center gap-2">
        <Sel value={type} onChange={(t) => { setType(t); load(t); }} testid="cr-diary-filter"><option value="">Tutte le registrazioni</option>{DTYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}</Sel>
        <Button size="sm" variant="outline" onClick={() => load(type)} data-testid="cr-diary-refresh">Aggiorna</Button>
        {d.perms.role === "responsabile" && <Button size="sm" variant="outline" onClick={exp} data-testid="cr-diary-export"><Download className="mr-1 h-4 w-4" />Esporta CSV</Button>}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full min-w-[560px] text-left text-xs"><thead className="bg-slate-50 text-slate-500"><tr>{["Data e ora", "Tipo", "Intervento", "Utente", "Registrazione"].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
          <tbody>{(rows || []).map((x) => <tr key={x.id} className="border-t border-slate-100" data-testid="cr-diary-row"><td className="whitespace-nowrap px-3 py-1.5 font-mono">{fmtDT(x.at)}:{new Date(x.at).getSeconds().toString().padStart(2, "0")}</td><td className="px-3 py-1.5">{x.type.replace("_", " ")}</td>
            <td className="px-3 py-1.5">{x.codice ? <button type="button" className="font-semibold text-[#088F8A] underline" onClick={() => open(x.intervention_id)}>{x.codice}</button> : "—"}</td><td className="px-3 py-1.5">{x.by_name}</td><td className="px-3 py-1.5">{x.text}</td></tr>)}</tbody></table>
      </div>
    </div>
  );
}
