import { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

const ADD = "__add_new__";
const norm = (s) => (s || "").trim().toLowerCase();

// Dropdown backed by an Organization settings list (e.g. "settori") with an inline
// "+ Aggiungi nuovo" action: creates the option, selects it, keeps the form open.
export default function SettingSelect({ settingKey, value, onChange, options = [], onAdded, placeholder = "Seleziona...", addLabel = "Aggiungi nuovo", testid = "field" }) {
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const opts = (options || []).map((o) => (typeof o === "string" ? o : o.value)).filter(Boolean);
  // Always render the current value as an option (covers a just-added value before the
  // parent's options list refreshes, and legacy values not in the configured list).
  const allOpts = value && !opts.some((o) => norm(o) === norm(value)) ? [...opts, value] : opts;
  const sortedOpts = [...allOpts].sort((a, b) => {
    const al = String(a).trim().toLowerCase(), bl = String(b).trim().toLowerCase();
    if (al === "altro" && bl !== "altro") return 1;
    if (bl === "altro" && al !== "altro") return -1;
    return String(a).localeCompare(String(b), "it", { sensitivity: "base" });
  });

  const doAdd = async () => {
    const name = text.trim();
    if (!name) return;
    const existing = opts.find((o) => norm(o) === norm(name));
    if (existing) { onChange(existing); setAdding(false); setText(""); toast.info("Voce già presente: selezionata."); return; }
    setSaving(true);
    try {
      const { data: current } = await api.get("/settings");
      const list = Array.isArray(current[settingKey]) ? current[settingKey] : [];
      if (list.some((o) => norm(o) === norm(name))) { onChange(list.find((o) => norm(o) === norm(name))); }
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
    <Select value={value || ""} onValueChange={(v) => { if (v === ADD) setAdding(true); else onChange(v); }}>
      <SelectTrigger data-testid={testid}><SelectValue placeholder={placeholder} /></SelectTrigger>
      <SelectContent>
        {sortedOpts.map((o) => <SelectItem key={o} value={o} data-testid={`${testid}-opt-${o}`}>{o}</SelectItem>)}
        <SelectItem value={ADD} data-testid={`${testid}-add-option`} className="text-tiffany-active font-semibold">+ {addLabel}</SelectItem>
      </SelectContent>
    </Select>
  );
}
