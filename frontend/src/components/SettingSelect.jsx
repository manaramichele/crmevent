import { useState, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const ADD = "__add_new__";
const norm = (s) => (s || "").trim().toLowerCase();

// Dropdown collegato a una lista di impostazioni dell'Organizzazione (persistenza org-level,
// isolamento multi-tenant). Caratteristiche: ordinamento A→Z (case-insensitive, "altro" in fondo),
// ricerca per elenchi lunghi (ricerca fissa in alto), "+ Aggiungi nuova voce" fisso in basso,
// deduplica case-insensitive, selezione automatica della nuova voce, form mantenuto aperto.
export default function SettingSelect({ settingKey, value, onChange, options = [], onAdded, placeholder = "Seleziona...", addLabel = "Aggiungi nuovo", testid = "field", specials = [] }) {
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");

  const opts = useMemo(() => {
    const seen = new Set(); const out = [];
    (options || []).forEach((o) => { const v = typeof o === "string" ? o : o?.value; if (v && !seen.has(norm(v))) { seen.add(norm(v)); out.push(v); } });
    return out;
  }, [options]);
  // include il valore corrente anche se non ancora nella lista configurata (stale o appena aggiunto)
  const allOpts = value && !opts.some((o) => norm(o) === norm(value)) ? [...opts, value] : opts;
  const sorted = useMemo(() => [...allOpts].sort((a, b) => {
    const al = norm(a), bl = norm(b);
    if (al === "altro" && bl !== "altro") return 1;
    if (bl === "altro" && al !== "altro") return -1;
    return String(a).localeCompare(String(b), "it", { sensitivity: "base" });
  }), [allOpts]);
  const filtered = q.trim() ? sorted.filter((o) => norm(o).includes(norm(q))) : sorted;
  const showSearch = sorted.length >= 8;

  const doAdd = async () => {
    const name = text.trim();
    if (!name) return;
    const existing = opts.find((o) => norm(o) === norm(name));
    if (existing) { onChange(existing); setAdding(false); setText(""); toast.info("Voce già presente: selezionata."); return; }
    setSaving(true);
    try {
      const { data: current } = await api.get("/settings");
      const list = Array.isArray(current[settingKey]) ? current[settingKey] : [];
      const dup = list.find((o) => norm(o) === norm(name));
      if (dup) { onChange(dup); }
      else {
        const updated = [...list, name];
        await api.put("/settings", { ...current, [settingKey]: updated });
        onChange(name);
        onAdded && onAdded(updated);
        toast.success("Voce aggiunta");
      }
      setAdding(false); setText("");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  if (adding) {
    return (
      <div className="flex gap-2" data-testid={`${testid}-add-row`}>
        <Input autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Nome nuova voce"
          data-testid={`${testid}-add-input`}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); doAdd(); } if (e.key === "Escape") { setAdding(false); setText(""); } }} />
        <Button type="button" size="sm" onClick={doAdd} disabled={saving} data-testid={`${testid}-add-confirm`} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shrink-0">Aggiungi</Button>
        <Button type="button" size="sm" variant="outline" onClick={() => { setAdding(false); setText(""); }} data-testid={`${testid}-add-cancel`} className="shrink-0">Annulla</Button>
      </div>
    );
  }
  return (
    <Select value={value || ""} onValueChange={(v) => { if (v === ADD) { setAdding(true); setText(q.trim()); } else onChange(v); }} onOpenChange={(o) => { if (!o) setQ(""); }}>
      <SelectTrigger data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        {showSearch && (
          <div className="p-1.5 sticky top-0 bg-white z-10 border-b border-slate-100">
            <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.stopPropagation()} placeholder="Cerca..." className="h-8" data-testid={`${testid}-search`} />
          </div>
        )}
        {specials.map((s) => <SelectItem key={s.value} value={s.value} data-testid={`${testid}-opt-${s.value}`}>{s.label}</SelectItem>)}
        {filtered.map((o) => <SelectItem key={o} value={o} data-testid={`${testid}-opt-${o}`}>{o}</SelectItem>)}
        {filtered.length === 0 && <div className="px-2 py-2 text-xs text-slate-400" data-testid={`${testid}-empty`}>Nessuna voce trovata</div>}
        <div className="sticky bottom-0 bg-white border-t border-slate-100">
          <SelectItem value={ADD} data-testid={`${testid}-add-option`} className="text-tiffany-active font-semibold">+ {addLabel}</SelectItem>
        </div>
      </SelectContent>
    </Select>
  );
}
