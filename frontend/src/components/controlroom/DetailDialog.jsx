import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Phone, Pencil, Copy, Trash2, Crosshair, CheckCircle2, Circle } from "lucide-react";
import { PRESIDIO, RES_STATES, label, nameOf, posOf } from "./meta";

const Info = ({ l, v }) => (v || v === 0 ? <div><div className="text-[11px] text-slate-400">{l}</div><div className="text-sm font-medium text-slate-800">{v}</div></div> : null);
const Call = ({ tel, testid }) => (tel ? <a href={`tel:${tel}`} className="inline-flex h-9 items-center gap-1.5 rounded-full bg-emerald-600 px-4 text-sm font-semibold text-white hover:bg-emerald-700" data-testid={testid}><Phone className="h-4 w-4" />Chiama {tel}</a> : null);

function Actions({ d, onEdit, onDelete, onDuplicate, onFocus, kind }) {
  return (
    <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
      {onFocus && <Button size="sm" variant="outline" onClick={onFocus} data-testid={`cr-${kind}-focus`}><Crosshair className="mr-1 h-4 w-4" />Mostra sulla mappa</Button>}
      {d.perms.edit && <Button size="sm" variant="outline" onClick={onEdit} data-testid={`cr-${kind}-edit`}><Pencil className="mr-1 h-4 w-4" />Modifica</Button>}
      {d.perms.edit && onDuplicate && <Button size="sm" variant="outline" onClick={onDuplicate} data-testid={`cr-${kind}-duplicate`}><Copy className="mr-1 h-4 w-4" />Duplica</Button>}
      {d.perms.edit && <Button size="sm" variant="outline" className="text-red-600" onClick={() => window.confirm("Eliminare definitivamente?") && onDelete()} data-testid={`cr-${kind}-delete`}><Trash2 className="mr-1 h-4 w-4" />Elimina</Button>}
    </div>
  );
}

function Presence({ d, r, act }) {
  const on = r.presente;
  return (
    <button type="button" disabled={!d.perms.edit} onClick={() => act.presence(r, !on)} className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${on ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-500"}`} data-testid={`cr-presence-${r.id}`}>
      {on ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Circle className="h-3.5 w-3.5" />}{on ? "Presente" : "Conferma presenza"}
    </button>
  );
}

function PostBody({ d, p, act }) {
  const s = PRESIDIO[p.presidio], cat = d.settings.categories.find((c) => c.key === p.categoria);
  const ppl = d.resources.filter((r) => r.post_id === p.id);
  return (
    <>
      <div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-3 py-1 text-xs font-bold ${s[1]}`} data-testid="cr-post-presidio">{s[0]}</span><span className="text-xs text-slate-500">{cat?.label}</span></div>
      <div className="grid grid-cols-3 gap-2 text-center" data-testid="cr-post-presence">
        {[["Previsti", p.previsti], ["Presenti", p.presenti], ["Mancanti", p.mancanti]].map(([l, v]) => <div key={l} className="rounded-lg bg-slate-50 py-2"><div className="text-xl font-bold">{v}</div><div className="text-[11px] text-slate-500">{l}</div></div>)}
      </div>
      <div className="grid grid-cols-2 gap-3"><Info l="Codice" v={p.codice} /><Info l="Settore" v={d.sectors.find((x) => x.id === p.sector_id)?.nome} /><Info l="Chilometro" v={p.km} />
        <Info l="Orario" v={[p.apertura, p.chiusura].filter(Boolean).join(" – ")} /><Info l="Responsabile" v={p.responsabile} /><Info l="Coordinate" v={p.lat != null ? `${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}` : null} /></div>
      {p.contatti_nascosti && <div className="text-xs text-slate-400">Contatti riservati</div>}
      <Call tel={p.telefono} testid="cr-post-call" />
      <div><div className="mb-1 text-xs font-semibold text-slate-600">Personale e mezzi assegnati ({ppl.length})</div>
        <div className="space-y-1">{ppl.map((r) => (
          <div key={r.id} className="flex items-center gap-2 rounded-lg border border-slate-100 px-3 py-2"><div className="min-w-0 flex-1 truncate text-sm">{nameOf(r)}{r.caposquadra && <span className="ml-1 text-[10px] font-bold text-[#088F8A]">CAPOSQUADRA</span>}</div>
            {r.kind === "persona" ? <Presence d={d} r={r} act={act} /> : <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${label(RES_STATES, r.stato)[2]}`}>{label(RES_STATES, r.stato)[1]}</span>}</div>))}
          {!ppl.length && <div className="text-xs text-slate-400">Nessuno assegnato: usa Risorse › Da Staff / Volontari.</div>}</div>
        <div className="mt-2 text-[11px] text-slate-400">Il check-in autonomo degli operatori da smartphone sarà disponibile con l'accesso mobile.</div></div>
      {p.note && <div className="whitespace-pre-wrap text-sm text-slate-600">{p.note}</div>}
    </>
  );
}

function ResourceBody({ d, r, act }) {
  const p = d.posts.find((x) => x.id === r.post_id), g = r.gps;
  return (
    <>
      <div className="flex flex-wrap gap-1.5" data-testid="cr-resource-states">
        {RES_STATES.map(([k, l, c]) => <button key={k} type="button" disabled={!d.perms.edit} onClick={() => act.status(r, k)} className={`rounded-full px-3 py-1.5 text-[11px] font-bold ${r.stato === k ? c + " ring-2 ring-offset-1 ring-slate-400" : "bg-white text-slate-500 border border-slate-200"}`} data-testid={`cr-set-status-${k}`}>{l}</button>)}
      </div>
      {r.kind === "persona" && <Presence d={d} r={r} act={act} />}
      <div className="grid grid-cols-2 gap-3"><Info l="Identificativo" v={r.codice} /><Info l="Tipologia" v={r.kind === "mezzo" ? d.vehicles.find((v) => v.key === r.tipologia)?.label : r.tipologia} />
        <Info l="Targa" v={r.targa} /><Info l="Equipaggio" v={r.equipaggio} /><Info l="Responsabile" v={r.responsabile} /><Info l="Postazione" v={p?.nome} />
        <Info l="Settore" v={d.sectors.find((x) => x.id === (r.sector_id || p?.sector_id))?.nome} /><Info l="Turno" v={r.turno_label} /></div>
      {r.contatti_nascosti && <div className="text-xs text-slate-400">Contatti riservati</div>}
      <Call tel={r.telefono} testid="cr-resource-call" />
      <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600" data-testid="cr-resource-gps">
        <div><b>Posizione assegnata:</b> {posOf(r, d.posts) ? (r.lat != null ? "posizione fissa" : `postazione ${p?.nome}`) : "non definita"}</div>
        <div><b>Posizione GPS rilevata:</b> {g?.last_at ? `${g.last_lat}, ${g.last_lng} · ${new Date(g.last_at).toLocaleString("it-IT")}` : "nessun dato"}</div>
        <div><b>Dispositivo:</b> {g?.device_id ? `${g.device_id} (${g.device_type || "n.d."}) · ${g.status === "non_collegato" ? "non ancora collegato" : g.status}` : "nessuno associato"}</div>
      </div>
      {r.note && <div className="whitespace-pre-wrap text-sm text-slate-600">{r.note}</div>}
    </>
  );
}

// Scheda dell'elemento selezionato (postazione, risorsa, settore, intervento).
export function DetailDialog({ d, sel, onClose, act }) {
  const coll = sel ? { posts: d.posts, resources: d.resources, sectors: d.sectors }[sel[0]] : null;
  const it = coll?.find((x) => x.id === sel[1]);
  if (!sel || !it) return null;
  const [kind] = sel;
  const pos = kind === "posts" ? (it.lng != null ? [it.lng, it.lat] : null) : kind === "resources" ? posOf(it, d.posts) : null;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] w-[95vw] max-w-lg space-y-3 overflow-y-auto" data-testid={`cr-detail-${kind}`}>
        <DialogHeader><DialogTitle className="font-display">{nameOf(it)}</DialogTitle></DialogHeader>
        {kind === "posts" && <PostBody d={d} p={it} act={act} />}
        {kind === "resources" && <ResourceBody d={d} r={it} act={act} />}
        {kind === "sectors" && <div className="grid grid-cols-2 gap-3"><Info l="Codice" v={it.codice} /><Info l="Km" v={`${it.km_inizio ?? "?"} – ${it.km_fine ?? "?"}`} /><Info l="Responsabile" v={it.responsabile} /><Info l="Note" v={it.note} /><Call tel={it.telefono} testid="cr-sector-call" /></div>}
        {kind === "interventions" && <div className="space-y-2 text-sm"><div className="text-slate-600">{it.descrizione || "Nessuna descrizione"}</div><div className="text-xs text-slate-400">{it.priorita.toUpperCase()} · {it.stato.toUpperCase()} · creato da {it.created_by}</div>
          {d.perms.edit && it.stato !== "chiuso" && <Button size="sm" onClick={() => act.closeIntervention(it)} data-testid="cr-intervention-close">Chiudi intervento</Button>}</div>}
        <Actions d={d} kind={kind} onEdit={() => act.edit(kind, it)} onDelete={() => act.remove(kind, it)} onDuplicate={kind === "posts" ? () => act.duplicate(it) : null}
          onFocus={pos ? () => act.focus(pos) : null} />
      </DialogContent>
    </Dialog>
  );
}
