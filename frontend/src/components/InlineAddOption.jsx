import { useState } from "react";
import { addOption } from "@/lib/optionLists";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function InlineAddOption({ listKey, onDone, testid = "inline-add", small = false }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!text.trim()) return;
    setBusy(true);
    const v = await addOption(listKey, text);
    setBusy(false);
    if (v) onDone(v);
  };
  const h = small ? "h-8" : "h-10";
  return (
    <div className="flex gap-1.5 mt-1" data-testid={testid}>
      <Input autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Nome nuova voce" className={`${h} text-sm`} data-testid={`${testid}-input`}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); save(); } if (e.key === "Escape") onDone(null); }} />
      <Button type="button" size="sm" onClick={save} disabled={busy} className={`${h} shrink-0 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold`} data-testid={`${testid}-confirm`}>Aggiungi</Button>
      <Button type="button" size="sm" variant="outline" onClick={() => onDone(null)} className={`${h} shrink-0`} data-testid={`${testid}-cancel`}>Annulla</Button>
    </div>
  );
}
