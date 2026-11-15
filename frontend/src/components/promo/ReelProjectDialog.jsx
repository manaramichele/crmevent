import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";

const sel = "h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm";
const total = (t) => (Number(t.hook.dur) + t.sections.reduce((a, s) => a + s.scenes.reduce((b, c) => b + Number(c.dur || 0), 0), 0) + Number(t.outro.dur)).toFixed(1);

function SceneRow({ sc, assets, onChange, onRemove, testid }) {
  const src = sc.clip || sc.asset || "";
  const setSrc = (v) => onChange(v.startsWith("clips/") ? { ...sc, clip: v, asset: null, crop: null } : { ...sc, asset: v, clip: null });
  return (
    <div className="grid grid-cols-12 gap-2 rounded-lg bg-slate-50 p-2" data-testid={testid}>
      <select className={`${sel} col-span-12 sm:col-span-4`} value={src} onChange={(e) => setSrc(e.target.value)} data-testid={`${testid}-src`}>{assets.map((a) => <option key={a} value={a}>{a}</option>)}</select>
      <Input className="col-span-6 sm:col-span-3" value={sc.label || ""} placeholder="Etichetta" onChange={(e) => onChange({ ...sc, label: e.target.value })} data-testid={`${testid}-label`} />
      <Input className="col-span-3 sm:col-span-1" type="number" step="0.1" value={sc.dur} onChange={(e) => onChange({ ...sc, dur: Number(e.target.value) })} title="Durata (s)" data-testid={`${testid}-dur`} />
      {sc.clip
        ? <Input className="col-span-10 sm:col-span-3" type="number" step="0.5" value={sc.start || 0} onChange={(e) => onChange({ ...sc, start: Number(e.target.value) })} title="Inizio clip (s)" data-testid={`${testid}-start`} />
        : <Input className="col-span-10 sm:col-span-3" value={(sc.crop || []).join(",")} placeholder="Ritaglio x,y,l,a" onChange={(e) => onChange({ ...sc, crop: e.target.value ? e.target.value.split(",").map((n) => parseInt(n, 10) || 0) : null })} data-testid={`${testid}-crop`} />}
      <Button size="sm" variant="ghost" className="col-span-2 sm:col-span-1" onClick={onRemove} data-testid={`${testid}-remove`}><Trash2 className="h-4 w-4" /></Button>
    </div>
  );
}

export function ReelProjectDialog({ r, assets, music, onClose, onSaved }) {
  const [t, setT] = useState(() => JSON.parse(JSON.stringify(r.timeline)));
  const [busy, setBusy] = useState(false);
  const media = assets.filter((a) => /\.(png|jpg|mp4)$/.test(a) && a !== "logo.png");
  const setSec = (i, sec) => setT({ ...t, sections: t.sections.map((s, k) => (k === i ? sec : s)) });
  const save = async () => {
    setBusy(true);
    try { await api.put(`/promo-reels/${r.slug}/timeline`, t); toast.success("Progetto salvato. Premi Rigenera per creare una nuova versione."); onSaved(); onClose(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Salvataggio non riuscito"); }
    setBusy(false);
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid={`reel-project-dialog-${r.slug}`}>
        <DialogHeader><DialogTitle>Progetto di montaggio · {r.title}</DialogTitle></DialogHeader>
        <p className="text-xs text-slate-500">Schermate reali, clip, testi, musica e durate. Durata totale: <strong data-testid="reel-project-total">{total(t)} s</strong>. Il ritaglio è in pixel sulla schermata 1920×1080.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2"><Label>Testo iniziale (0–3 s)</Label><Input value={t.hook.text} onChange={(e) => setT({ ...t, hook: { ...t.hook, text: e.target.value } })} data-testid="reel-project-hook" /></div>
          <div><Label>Durata (s)</Label><Input type="number" step="0.1" value={t.hook.dur} onChange={(e) => setT({ ...t, hook: { ...t.hook, dur: Number(e.target.value) } })} /></div>
        </div>
        {t.sections.map((sec, i) => (
          <div key={i} className="space-y-2 rounded-lg border border-slate-200 p-3" data-testid={`reel-project-section-${i}`}>
            <div className="flex gap-2">
              <Input value={sec.text} onChange={(e) => setSec(i, { ...sec, text: e.target.value })} className="font-semibold" data-testid={`reel-project-section-text-${i}`} />
              {t.sections.length > 1 && <Button size="sm" variant="ghost" onClick={() => setT({ ...t, sections: t.sections.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></Button>}
            </div>
            {sec.scenes.map((sc, j) => <SceneRow key={j} sc={sc} assets={media} testid={`reel-scene-${i}-${j}`} onChange={(n) => setSec(i, { ...sec, scenes: sec.scenes.map((x, k) => (k === j ? n : x)) })} onRemove={() => sec.scenes.length > 1 && setSec(i, { ...sec, scenes: sec.scenes.filter((_, k) => k !== j) })} />)}
            <Button size="sm" variant="outline" onClick={() => setSec(i, { ...sec, scenes: [...sec.scenes, { asset: media[0], dur: 2, label: "" }] })} data-testid={`reel-project-add-scene-${i}`}><Plus className="h-4 w-4 mr-1" />Inquadratura</Button>
          </div>
        ))}
        <Button size="sm" variant="outline" onClick={() => setT({ ...t, sections: [...t.sections, { text: "NUOVO TESTO", scenes: [{ asset: media[0], dur: 2, label: "" }] }] })} data-testid="reel-project-add-section"><Plus className="h-4 w-4 mr-1" />Sezione</Button>
        <div className="grid gap-3 sm:grid-cols-3">
          <div><Label>Testo finale</Label><Input value={t.outro.text} onChange={(e) => setT({ ...t, outro: { ...t.outro, text: e.target.value } })} data-testid="reel-project-outro" /></div>
          <div><Label>Durata finale (s)</Label><Input type="number" step="0.1" value={t.outro.dur} onChange={(e) => setT({ ...t, outro: { ...t.outro, dur: Number(e.target.value) } })} /></div>
          <div><Label>Musica</Label><select className={sel} value={t.music || ""} onChange={(e) => setT({ ...t, music: e.target.value || null })} data-testid="reel-project-music"><option value="">Nessuna</option>{music.map((m) => <option key={m} value={m}>{m}</option>)}</select></div>
          <div className="sm:col-span-2"><Label>Titolo copertina</Label><Input value={t.cover_text || ""} onChange={(e) => setT({ ...t, cover_text: e.target.value })} data-testid="reel-project-cover" /></div>
          <div><Label>Transizione (s)</Label><Input type="number" step="0.05" value={t.transition ?? 0.35} onChange={(e) => setT({ ...t, transition: Number(e.target.value) })} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annulla</Button>
          <Button onClick={save} disabled={busy} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid="reel-project-save">Salva progetto</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
