import { useState } from "react";
import { toast } from "sonner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
export const NO_GROUP = "__no_group__";
const ADD = "__add_group__";

// Gruppo di appartenenza nel modulo pubblico: i nuovi gruppi finiscono sempre nell'organizzazione del link.
export default function PublicGroupSelect({ code, value, onChange, options, onOptions, t }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!name.trim()) { toast.error(t("groupNameReq")); return; }
    setBusy(true);
    try {
      const res = await fetch(`${BACKEND}/api/public/availability/${code}/groups`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nome: name }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { toast.error(typeof data.detail === "string" ? data.detail : t("errSend")); return; }
      if (!options.includes(data.value)) onOptions([...options, data.value]);
      onChange(data.value);
      if (!data.created) toast.info(t("groupExists"));
      setOpen(false); setName("");
    } catch { toast.error(t("errNet")); } finally { setBusy(false); }
  };
  return (
    <>
      <Select value={value} onValueChange={(v) => (v === ADD ? setOpen(true) : onChange(v))}>
        <SelectTrigger data-testid="pf-gruppo"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value={NO_GROUP} className="italic" data-testid="pf-gruppo-none"><span className="italic">{t("groupNone")}</span></SelectItem>
          {options.map((g) => <SelectItem key={g} value={g} data-testid={`pf-gruppo-opt-${g}`}>{g}</SelectItem>)}
          <SelectItem value={ADD} className="font-medium text-tiffany-fg" data-testid="pf-gruppo-add">{t("groupAdd")}</SelectItem>
        </SelectContent>
      </Select>
      <Dialog open={open} onOpenChange={(o) => { if (!o) { setOpen(false); setName(""); } }}>
        <DialogContent className="w-[95vw] max-w-sm" data-testid="pf-gruppo-dialog">
          <DialogHeader><DialogTitle>{t("groupAddTitle")}</DialogTitle><DialogDescription>{t("groupAddDesc")}</DialogDescription></DialogHeader>
          <label className="text-sm text-slate-600">{t("groupName")} <span className="text-red-500">*</span>
            <Input autoFocus value={name} maxLength={80} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && save()} className="mt-1" data-testid="pf-gruppo-name" /></label>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => { setOpen(false); setName(""); }} data-testid="pf-gruppo-cancel">{t("cancel")}</Button>
            <Button disabled={busy} onClick={save} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" data-testid="pf-gruppo-save">{t("save")}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
