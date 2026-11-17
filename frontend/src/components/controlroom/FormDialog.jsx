import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ADD_OPTION, promptAdd } from "@/lib/optionLists";

const NUM = new Set(["number"]);

function Field({ f, v, set, all }) {
  const id = `crf-${f.k}`;
  const common = { id, "data-testid": id, disabled: f.disabled?.(all), className: "h-10" };
  if (f.type === "select") {
    return (
      <select {...common} value={v ?? ""} onChange={async (e) => { if (f.addKey && e.target.value === ADD_OPTION) { const nv = await promptAdd(f.addKey); if (nv) set(nv); } else set(e.target.value || null); }} className="h-10 w-full rounded-md border border-slate-200 bg-white px-2 text-sm">
        {!f.required && <option value="">—</option>}
        {(typeof f.options === "function" ? f.options(all) : f.options).map(([val, l]) => <option key={val} value={val}>{l}</option>)}
        {f.addKey && v && !(typeof f.options === "function" ? f.options(all) : f.options).some(([val]) => val === v) && <option value={v}>{v}</option>}
        {f.addKey && <option value={ADD_OPTION}>+ Aggiungi</option>}
      </select>
    );
  }
  if (f.type === "checkbox") return <label className="flex h-10 items-center gap-2 text-sm"><input type="checkbox" {...common} className="h-4 w-4 accent-[#0ABAB5]" checked={!!v} onChange={(e) => set(e.target.checked)} />{f.hint}</label>;
  if (f.type === "textarea") return <Textarea {...common} className="min-h-[72px]" value={v ?? ""} onChange={(e) => set(e.target.value)} />;
  return <Input {...common} type={f.type || "text"} step="any" value={v ?? ""} onChange={(e) => set(NUM.has(f.type) ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)} placeholder={f.placeholder} />;
}

// Modulo generico Control Room: campi dichiarativi, visibilità condizionale, nessuna finestra oltre lo schermo.
export function FormDialog({ open, onOpenChange, title, fields, initial, onSubmit, testid = "cr-form", submitLabel = "Salva", note }) {
  const [v, setV] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setV(initial || {}); }, [open, initial]);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const ok = await onSubmit(v);
    setBusy(false);
    if (ok) onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[95vw] max-w-2xl overflow-y-auto" data-testid={testid}>
        <DialogHeader><DialogTitle className="font-display">{title}</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          {note}
          <div className="grid gap-3 sm:grid-cols-2">
            {fields.filter((f) => !f.show || f.show(v)).map((f) => (
              <div key={f.k} className={f.wide || f.type === "textarea" ? "sm:col-span-2" : ""}>
                <label htmlFor={`crf-${f.k}`} className="mb-1 block text-xs font-medium text-slate-600">{f.label}{f.required ? " *" : ""}</label>
                <Field f={f} v={v[f.k]} all={v} set={(x) => setV((o) => ({ ...o, [f.k]: x }))} />
              </div>
            ))}
          </div>
          <DialogFooter><Button type="submit" disabled={busy} className="bg-[#0ABAB5] text-slate-900 hover:bg-[#09A8A3]" data-testid={`${testid}-submit`}>{busy ? "Salvataggio…" : submitLabel}</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
