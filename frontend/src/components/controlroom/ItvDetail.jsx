import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Phone, Send, MapPin, Crosshair, Paperclip, ShieldAlert, AlertTriangle, Radio } from "lucide-react";
import api from "@/lib/api";
import { ASG, CLOSED, FLOW, ITV_STATES, PRIORITY, RES_STATES, Pill, fmtDT, fmtTime, label, nameOf } from "./meta";
import { PriorityPicker } from "./ItvNew";

const TIMES = [["created_at", "Apertura"], ["t_presa", "Presa in carico"], ["t_invio", "Invio squadra"], ["t_arrivo", "Arrivo sul posto"], ["t_risoluzione", "Risoluzione"], ["t_chiusura", "Chiusura"]];

function Assign({ d, it, call }) {
  const [sel, setSel] = useState([]);
  const [ext, setExt] = useState(false);
  const taken = new Set((it.assignments || []).filter((a) => ["non_confermata", "confermata"].includes(a.stato)).map((a) => a.resource_id));
  const list = d.resources.filter((r) => !taken.has(r.id)).sort((a, b) => (a.stato === "disponibile" ? -1 : 1) - (b.stato === "disponibile" ? -1 : 1));
  const needExt = sel.some((id) => { const r = d.resources.find((x) => x.id === id); return r?.kind === "mezzo" && d.external_vehicles.includes(r.tipologia); });
  const posts = Object.fromEntries(d.posts.map((p) => [p.id, p])), secs = Object.fromEntries(d.sectors.map((s) => [s.id, s.nome]));
  const go = async () => { if (await call("post", `/interventions/${it.id}/assign`, { resource_ids: sel, conferma_esterni: ext }, "Incarico inviato: in attesa di conferma")) { setSel([]); setExt(false); } };
  return (
    <div className="space-y-2" data-testid="cr-itv-assign">
      <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-slate-100 p-1">
        {list.map((r) => {
          const st = label(RES_STATES, r.stato), p = posts[r.post_id];
          return (
            <label key={r.id} className="flex cursor-pointer items-start gap-2 rounded px-2 py-1.5 text-xs hover:bg-slate-50" data-testid={`cr-assign-row-${r.id}`}>
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[#0ABAB5]" checked={sel.includes(r.id)} onChange={() => setSel((s) => (s.includes(r.id) ? s.filter((x) => x !== r.id) : [...s, r.id]))} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1"><b className="text-sm">{nameOf(r)}</b><Pill c={st[2]}>{st[1]}</Pill>{d.overlaps[r.id] && <Pill c="bg-orange-100 text-orange-700">GIÀ SU {d.overlaps[r.id].join(", ")}</Pill>}</div>
                <div className="text-slate-500">{[r.kind === "mezzo" ? d.vehicles.find((v) => v.key === r.tipologia)?.label : r.tipologia, r.responsabile, r.telefono, secs[r.sector_id || p?.sector_id], p?.nome].filter(Boolean).join(" · ")}</div>
                <div className="text-slate-400">{r.gps?.last_at ? `Ultima posizione GPS ${fmtDT(r.gps.last_at)}` : "Nessuna posizione GPS rilevata"}</div>
              </div>
            </label>
          );
        })}
        {!list.length && <div className="p-2 text-xs text-slate-400">Nessuna risorsa disponibile da assegnare.</div>}
      </div>
      {needExt && <label className="flex items-start gap-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-900"><input type="checkbox" checked={ext} onChange={(e) => setExt(e.target.checked)} className="mt-0.5 h-4 w-4" data-testid="cr-assign-external" />Confermo che esiste un accordo operativo con l'ente esterno per questo incarico.</label>}
      <Button disabled={!sel.length} onClick={go} className="h-10 w-full bg-[#0ABAB5] font-bold text-slate-900 hover:bg-[#09A8A3]" data-testid="cr-assign-submit">ASSEGNA INTERVENTO{sel.length ? ` (${sel.length})` : ""}</Button>
    </div>
  );
}

function Status({ d, it, call }) {
  const resp = d.perms.role === "responsabile";
  const [force, setForce] = useState("");
  const ask = (msg) => window.prompt(msg)?.trim();
  const move = (to, extra = {}) => call("post", `/interventions/${it.id}/status`, { to, version: it.version, ...extra }, `Stato: ${ITV_STATES[to][0]}`);
  const go = (to) => {
    if (to === "annullato") { const m = ask("Motivazione dell'annullamento (obbligatoria)"); if (m) move(to, { motivo: m }); return; }
    move(to);
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {FLOW[it.stato].filter((s) => s !== "chiuso" || resp).map((s) => <Button key={s} size="sm" variant={s === "annullato" ? "outline" : "default"} onClick={() => go(s)} className={s === "annullato" ? "text-red-600" : "bg-slate-900 text-white"} data-testid={`cr-itv-to-${s}`}>{ITV_STATES[s][0]}</Button>)}
        {CLOSED.includes(it.stato) && resp && <Button size="sm" variant="outline" onClick={() => { const m = ask("Motivo della riapertura (obbligatorio)"); if (m) move("preso_in_carico", { motivo: m }); }} data-testid="cr-itv-reopen">RIAPRI</Button>}
      </div>
      {resp && !CLOSED.includes(it.stato) && (
        <div className="flex gap-1.5">
          <select value={force} onChange={(e) => setForce(e.target.value)} className="h-8 flex-1 rounded-md border border-slate-200 px-2 text-xs" data-testid="cr-itv-force-select"><option value="">Cambio fuori flusso (responsabile)…</option>
            {Object.keys(ITV_STATES).filter((s) => s !== it.stato && !FLOW[it.stato].includes(s)).map((s) => <option key={s} value={s}>{ITV_STATES[s][0]}</option>)}</select>
          <Button size="sm" variant="outline" disabled={!force} onClick={() => { const n = ask("Nota obbligatoria per il cambio fuori flusso"); if (n) move(force, { force: true, note: n, ...(force === "annullato" ? { motivo: n } : {}) }); setForce(""); }} data-testid="cr-itv-force">Applica</Button>
        </div>
      )}
    </div>
  );
}

function Attachments({ it, base, call, canAdd }) {
  const [urls, setUrls] = useState({});
  useEffect(() => {
    let alive = true;
    (it.attachments || []).forEach((a) => { if (!urls[a.id]) api.get(`${base}/interventions/${it.id}/attachments/${a.id}`, { responseType: "blob" }).then((r) => alive && setUrls((u) => ({ ...u, [a.id]: URL.createObjectURL(r.data) }))).catch(() => {}); });
    return () => { alive = false; };
  }, [it.attachments]); // eslint-disable-line react-hooks/exhaustive-deps
  const up = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    await call("post", `/interventions/${it.id}/attachments`, fd, "Fotografia allegata");
  };
  return (
    <div className="space-y-2" data-testid="cr-itv-attachments">
      <div className="flex flex-wrap gap-2">{(it.attachments || []).map((a) => <a key={a.id} href={urls[a.id]} target="_blank" rel="noreferrer" className="block h-16 w-16 overflow-hidden rounded-lg bg-slate-100" title={`${a.by_name} · ${fmtDT(a.at)}`}>{urls[a.id] && <img src={urls[a.id]} alt="allegato" className="h-full w-full object-cover" />}</a>)}</div>
      {canAdd && <label className="inline-flex cursor-pointer items-center gap-1 text-xs font-semibold text-[#088F8A]"><Paperclip className="h-3.5 w-3.5" />Allega fotografia (JPG, PNG, WEBP, HEIC · max 8 MB)<input type="file" accept="image/jpeg,image/png,image/webp,image/heic" className="hidden" onChange={up} data-testid="cr-itv-attach-input" /></label>}
    </div>
  );
}

function Health({ it, base }) {
  const [notes, setNotes] = useState(null);
  const [t, setT] = useState("");
  const load = () => api.get(`${base}/interventions/${it.id}/health`).then((r) => setNotes(r.data.notes)).catch(() => setNotes([]));
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-2.5" data-testid="cr-itv-health">
      <div className="flex items-center gap-1 text-xs font-semibold text-rose-800"><ShieldAlert className="h-3.5 w-3.5" />Note sanitarie riservate (solo Responsabile)</div>
      {notes === null ? <button type="button" className="mt-1 text-xs underline" onClick={load} data-testid="cr-itv-health-open">Mostra</button> : (
        <div className="mt-1 space-y-1">{notes.map((n) => <div key={n.id} className="text-xs"><span className="text-slate-400">{fmtTime(n.at)}</span> {n.text}</div>)}
          <div className="flex gap-1"><Textarea value={t} onChange={(e) => setT(e.target.value)} className="min-h-[40px] text-xs" data-testid="cr-itv-health-input" />
            <Button size="sm" disabled={!t.trim()} onClick={async () => { await api.post(`${base}/interventions/${it.id}/health`, { text: t }); setT(""); load(); }} data-testid="cr-itv-health-save">Salva</Button></div></div>)}
    </div>
  );
}

function Edit({ d, it, call }) {
  const [v, setV] = useState(null);
  if (!v) return <button type="button" className="text-xs font-semibold text-[#088F8A] underline" onClick={() => setV({ ...it })} data-testid="cr-itv-edit">Modifica dati</button>;
  const save = async () => { if (await call("put", `/interventions/${it.id}`, { ...v, version: it.version }, "Intervento aggiornato")) setV(null); };
  return (
    <div className="space-y-2 rounded-lg border border-slate-200 p-2.5" data-testid="cr-itv-edit-form">
      <PriorityPicker value={v.priorita} onPick={(p) => setV({ ...v, priorita: p })} prefix="cr-itv-edit-prio" />
      <select className="h-9 w-full rounded-md border border-slate-200 px-2 text-sm" value={v.tipologia} onChange={(e) => setV({ ...v, tipologia: e.target.value })}>{d.itv_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select>
      <Textarea value={v.descrizione} onChange={(e) => setV({ ...v, descrizione: e.target.value })} className="min-h-[50px]" />
      <input className="h-9 w-full rounded-md border border-slate-200 px-2 text-sm" placeholder="Responsabile incaricato" value={v.responsabile_incaricato || ""} onChange={(e) => setV({ ...v, responsabile_incaricato: e.target.value })} />
      <Textarea placeholder="Note operative" value={v.note || ""} onChange={(e) => setV({ ...v, note: e.target.value })} className="min-h-[50px]" data-testid="cr-itv-edit-note" />
      <div className="flex gap-2"><Button size="sm" onClick={save} data-testid="cr-itv-edit-save">Salva</Button><Button size="sm" variant="ghost" onClick={() => setV(null)}>Annulla</Button></div>
    </div>
  );
}

export function ItvDetail({ d, it, onClose, call, base, focus, openPost, message }) {
  const [hist, setHist] = useState([]);
  useEffect(() => { api.get(`${base}/diary`, { params: { intervention_id: it.id } }).then((r) => setHist(r.data.rows)).catch(() => {}); }, [it.id, it.version, base]);
  const t = d.itv_types.find((x) => x.key === it.tipologia), pr = PRIORITY[it.priorita], st = ITV_STATES[it.stato];
  const post = d.posts.find((p) => p.id === (it.post_id || it.post_vicina_id)), sec = d.sectors.find((s) => s.id === it.sector_id);
  const asg = it.assignments || [], m = it.can_manage;
  const tel = asg.map((a) => d.resources.find((r) => r.id === a.resource_id)).find((r) => r?.telefono)?.telefono || post?.telefono;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className={`max-h-[92vh] w-[96vw] max-w-3xl space-y-3 overflow-y-auto ${it.priorita === "critica" && !CLOSED.includes(it.stato) ? "border-2 border-red-500" : ""}`} data-testid="cr-itv-detail">
        <DialogHeader><DialogTitle className="flex flex-wrap items-center gap-2 font-display"><span data-testid="cr-itv-code">{it.codice}</span><span className="text-base font-medium text-slate-600">{t?.label || it.tipologia}</span>
          <Pill c={pr[2]} testid="cr-itv-priority">{pr[0]}</Pill><Pill c={st[1]} testid="cr-itv-state">{st[0]}</Pill>{it.origine === "campo" && <Pill c="bg-sky-600 text-white">DAL CAMPO</Pill>}</DialogTitle></DialogHeader>
        <p className="whitespace-pre-wrap text-sm text-slate-800">{it.descrizione}</p>
        <div className="flex flex-wrap gap-2">
          {tel && <a href={`tel:${tel}`} className="inline-flex h-9 items-center gap-1.5 rounded-full bg-emerald-600 px-4 text-xs font-bold text-white" data-testid="cr-itv-call"><Phone className="h-4 w-4" />CHIAMA</a>}
          {asg.some((a) => a.stato !== "revocata") && <Button size="sm" variant="outline" onClick={() => message(asg.find((a) => a.stato !== "revocata").resource_id, it.id)} data-testid="cr-itv-message"><Send className="mr-1 h-4 w-4" />INVIA MESSAGGIO</Button>}
          {post && <Button size="sm" variant="outline" onClick={() => openPost(post.id)} data-testid="cr-itv-open-post"><MapPin className="mr-1 h-4 w-4" />APRI POSTAZIONE</Button>}
          {it.lng != null && <Button size="sm" variant="outline" onClick={() => focus([it.lng, it.lat])} data-testid="cr-itv-focus"><Crosshair className="mr-1 h-4 w-4" />VISUALIZZA SULLA MAPPA</Button>}
        </div>
        <div className="grid gap-3 rounded-lg bg-slate-50 p-3 text-xs sm:grid-cols-2">
          <div><b>Posizione:</b> {[it.lng != null && `${it.lat.toFixed(5)}, ${it.lng.toFixed(5)}`, it.km != null && `km ${it.km}`, sec && `settore ${sec.nome}`, it.riferimento].filter(Boolean).join(" · ") || "—"}
            {it.da_confermare && <div className="mt-1 flex items-center gap-1 font-semibold text-amber-700" data-testid="cr-itv-pos-unconfirmed"><AlertTriangle className="h-3.5 w-3.5" />Posizione da confermare</div>}</div>
          <div><b>Postazione {it.post_id ? "" : "più vicina"}:</b> {post?.nome || "non determinabile"}</div>
          <div><b>Registrato da:</b> {it.created_by_name} · {it.origine}</div><div><b>Responsabile incaricato:</b> {it.responsabile_incaricato || "—"}</div>
          {it.note && <div className="sm:col-span-2"><b>Note operative:</b> {it.note}</div>}
        </div>
        <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-6" data-testid="cr-itv-times">{TIMES.map(([k, l]) => <div key={k} className="rounded bg-white p-1.5 text-center ring-1 ring-slate-100"><div className="text-[10px] text-slate-400">{l}</div><div className="font-mono text-xs font-semibold">{fmtTime(it[k])}</div></div>)}</div>
        {m && <Status d={d} it={it} call={call} />}
        <div><div className="mb-1 text-xs font-semibold text-slate-600">Squadre e mezzi assegnati</div>
          <div className="space-y-1">{asg.map((a) => (
            <div key={`${a.resource_id}${a.assigned_at}`} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-100 px-3 py-2 text-sm" data-testid={`cr-itv-asg-${a.resource_id}`}>
              <span className="flex-1">{a.label}</span><Pill c={ASG[a.stato][1]}>{ASG[a.stato][0]}</Pill>
              <span className="text-[11px] text-slate-400">{fmtTime(a.assigned_at)}{a.confirmed_at ? ` · conf. ${fmtTime(a.confirmed_at)} (${a.confirmed_via})` : ""}{a.motivo ? ` · ${a.motivo}` : ""}</span>
              {m && a.stato === "non_confermata" && <Button size="sm" variant="outline" className="h-7 text-[11px]" onClick={() => call("post", `/interventions/${it.id}/assignments/${a.resource_id}/confirm`, { via: "radio" }, "Conferma registrata")} data-testid={`cr-itv-asg-confirm-${a.resource_id}`}><Radio className="mr-1 h-3 w-3" />Confermata via radio</Button>}
              {m && ["non_confermata", "confermata"].includes(a.stato) && <Button size="sm" variant="ghost" className="h-7 text-[11px] text-red-600" onClick={() => call("delete", `/interventions/${it.id}/assignments/${a.resource_id}`, undefined, "Assegnazione revocata")} data-testid={`cr-itv-asg-revoke-${a.resource_id}`}>Revoca</Button>}
            </div>))}
            {!asg.length && <div className="text-xs font-semibold text-orange-600">Nessuna squadra assegnata</div>}</div></div>
        {m && !CLOSED.includes(it.stato) && <Assign d={d} it={it} call={call} />}
        {m && <Edit d={d} it={it} call={call} />}
        <Attachments it={it} base={base} call={call} canAdd={m} />
        {d.perms.role === "responsabile" && <Health it={it} base={base} />}
        <div><div className="mb-1 text-xs font-semibold text-slate-600">Cronologia</div>
          <div className="max-h-40 space-y-0.5 overflow-y-auto text-[11px] text-slate-600" data-testid="cr-itv-history">{hist.map((h) => <div key={h.id}><span className="font-mono text-slate-400">{fmtTime(h.at)}</span> · {h.by_name} · {h.text}</div>)}</div></div>
      </DialogContent>
    </Dialog>
  );
}
