import { useEffect, useState } from "react";
import { sortIt } from "@/lib/sortOptions";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { MapPin, AlertTriangle } from "lucide-react";
import { ICONS, PRIORITY } from "./meta";

const S = "h-10 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";

export function TypeGrid({ types, value, onPick, prefix = "cr-itv-type" }) {
  return (
    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
      {types.map((t) => {
        const I = ICONS[t.icon] || MapPin;
        return (
          <button key={t.key} type="button" onClick={() => onPick(t)} className={`flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-xs font-semibold transition-colors ${value === t.key ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white hover:border-slate-400"}`} data-testid={`${prefix}-${t.key}`}>
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full" style={{ background: t.color }}><I className="h-3.5 w-3.5 text-white" /></span>{t.label}
          </button>
        );
      })}
    </div>
  );
}

export function PriorityPicker({ value, onPick, prefix = "cr-itv-prio" }) {
  return (
    <div className="grid grid-cols-4 gap-1.5">
      {Object.entries(PRIORITY).map(([k, [l, col]]) => (
        <button key={k} type="button" onClick={() => onPick(k)} className={`h-10 rounded-lg text-xs font-bold transition-transform ${value === k ? "scale-105 text-white ring-2 ring-slate-900 ring-offset-1" : "text-slate-800 opacity-60 hover:opacity-100"}`} style={{ background: value === k ? col : `${col}33` }} data-testid={`${prefix}-${k}`}>{l}</button>
      ))}
    </div>
  );
}

// Apertura rapida: tipologia, priorità, posizione/riferimento, descrizione. Il resto si completa dopo.
export function ItvNew({ open, onOpenChange, d, initial, onSubmit }) {
  const [v, setV] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setV({ origine: "telefono", ...initial }); }, [open, initial]);
  const set = (k, x) => setV((o) => ({ ...o, [k]: x }));
  const hasPos = v.lng != null || v.post_id || v.sector_id || v.km != null || (v.riferimento || "").trim();
  const ok = v.tipologia && v.priorita && (v.descrizione || "").trim() && hasPos;
  const submit = async (e) => {
    e.preventDefault();
    if (!ok || busy) return;
    setBusy(true);
    const r = await onSubmit({ ...v, km: v.km === "" ? null : v.km });
    setBusy(false);
    if (r) onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] w-[96vw] max-w-xl overflow-y-auto" data-testid="cr-itv-new">
        <DialogHeader><DialogTitle className="font-display">Nuovo intervento</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div><div className="mb-1 text-xs font-semibold text-slate-600">Tipologia *</div><TypeGrid types={d.itv_types} value={v.tipologia} onPick={(t) => setV((o) => ({ ...o, tipologia: t.key, priorita: o.prioritaTouched ? o.priorita : t.priorita }))} /></div>
          <div><div className="mb-1 text-xs font-semibold text-slate-600">Priorità *</div><PriorityPicker value={v.priorita} onPick={(p) => setV((o) => ({ ...o, priorita: p, prioritaTouched: true }))} /></div>
          <div className="space-y-2 rounded-lg bg-slate-50 p-2.5">
            <div className="text-xs font-semibold text-slate-600">Posizione o riferimento operativo *</div>
            {v.lng != null && <div className="flex items-center gap-2 text-xs text-emerald-700" data-testid="cr-itv-new-coords"><MapPin className="h-3.5 w-3.5" />{v.lat.toFixed(5)}, {v.lng.toFixed(5)}<button type="button" className="text-slate-400 underline" onClick={() => setV((o) => ({ ...o, lng: null, lat: null }))}>rimuovi</button></div>}
            <div className="grid gap-2 sm:grid-cols-3">
              <select className={S} value={v.post_id || ""} onChange={(e) => set("post_id", e.target.value || null)} data-testid="cr-itv-new-post"><option value="">Postazione…</option>{sortIt(d.posts, (p) => p.nome).map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</select>
              <select className={S} value={v.sector_id || ""} onChange={(e) => set("sector_id", e.target.value || null)} data-testid="cr-itv-new-sector"><option value="">Settore…</option>{sortIt(d.sectors, (s) => s.nome).map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}</select>
              <Input type="number" step="0.1" min="0" placeholder="Km" value={v.km ?? ""} onChange={(e) => set("km", e.target.value === "" ? null : Number(e.target.value))} data-testid="cr-itv-new-km" />
            </div>
            <Input placeholder="Indirizzo o riferimento (es. curva dopo il ponte)" value={v.riferimento || ""} onChange={(e) => set("riferimento", e.target.value)} data-testid="cr-itv-new-ref" />
            {hasPos && v.lng == null && !v.post_id && <div className="flex items-center gap-1 text-[11px] text-amber-700"><AlertTriangle className="h-3.5 w-3.5" />Senza coordinate: la posizione risulterà da confermare.</div>}
          </div>
          <Textarea placeholder="Descrizione sintetica *" value={v.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} className="min-h-[64px]" data-testid="cr-itv-new-desc" />
          <select className={S} value={v.origine} onChange={(e) => set("origine", e.target.value)} data-testid="cr-itv-new-origin">
            {[["telefono", "Segnalazione telefonica"], ["radio", "Comunicazione radio"], ["centrale", "Rilevato dalla Control Room"], ["mappa", "Dalla mappa"]].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <Button type="submit" disabled={!ok || busy} className="h-11 w-full bg-red-600 font-bold text-white hover:bg-red-700" data-testid="cr-itv-new-submit">{busy ? "Registrazione…" : "APRI INTERVENTO"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
