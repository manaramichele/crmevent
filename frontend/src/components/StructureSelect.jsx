import { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import SettingSelect from "@/components/SettingSelect";
import { useSettings } from "@/components/crm";
import { toast } from "sonner";

const ADD = "__add_structure__";

// Reusable Structure picker with inline "+ Nuova struttura" quick-create.
export default function StructureSelect({ value, onChange, testid = "struct" }) {
  const [list, setList] = useState([]);
  const [adding, setAdding] = useState(false);
  const [nf, setNf] = useState({ nome: "", tipologia: "", indirizzo: "", citta: "", provincia: "", telefono: "", google_maps_url: "" });
  const settings = useSettings();
  const load = useCallback(() => api.get("/structures").then(({ data }) => setList(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const setF = (k, v) => setNf((f) => ({ ...f, [k]: v }));
  const save = async () => {
    if (!nf.nome.trim()) return toast.error("Nome struttura obbligatorio");
    try {
      const { data } = await api.post("/structures", nf);
      await load();
      onChange(data.id, data);
      setAdding(false);
      setNf({ nome: "", tipologia: "", indirizzo: "", citta: "", provincia: "", telefono: "", google_maps_url: "" });
      toast.success("Struttura creata");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  if (adding) {
    return (
      <div className="border border-tiffany-border rounded-lg p-3 space-y-2 bg-tiffany-light/30" data-testid={`${testid}-new-form`}>
        <div className="text-xs font-semibold text-slate-600">Nuova struttura</div>
        <Input placeholder="Nome struttura*" value={nf.nome} onChange={(e) => setF("nome", e.target.value)} data-testid={`${testid}-new-nome`} />
        <div className="space-y-1"><Label className="text-[11px] text-slate-500">Tipologia</Label>
          <SettingSelect settingKey="tipologie_struttura" value={nf.tipologia} onChange={(v) => setF("tipologia", v)} options={settings?.tipologie_struttura || ["Hotel", "B&B", "Residence", "Agriturismo", "Ristorante", "Pizzeria", "Bar", "Catering", "Mensa", "Altro"]} addLabel="Aggiungi tipologia" testid={`${testid}-new-tipologia`} /></div>
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder="Indirizzo" value={nf.indirizzo} onChange={(e) => setF("indirizzo", e.target.value)} data-testid={`${testid}-new-indirizzo`} />
          <Input placeholder="Città" value={nf.citta} onChange={(e) => setF("citta", e.target.value)} />
        </div>
        <Input placeholder="Link Google Maps" value={nf.google_maps_url} onChange={(e) => setF("google_maps_url", e.target.value)} data-testid={`${testid}-new-maps`} />
        <div className="flex gap-2">
          <Button type="button" size="sm" onClick={save} data-testid={`${testid}-new-save`} className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold">Salva struttura</Button>
          <Button type="button" size="sm" variant="outline" onClick={() => setAdding(false)}>Annulla</Button>
        </div>
      </div>
    );
  }
  return (
    <Select value={value || ""} onValueChange={(v) => { if (v === ADD) setAdding(true); else onChange(v, list.find((s) => s.id === v)); }}>
      <SelectTrigger data-testid={`${testid}-select`}><SelectValue placeholder="Seleziona struttura..." /></SelectTrigger>
      <SelectContent>
        {list.map((s) => <SelectItem key={s.id} value={s.id} data-testid={`${testid}-opt-${s.id}`}>{s.nome}{s.tipologia ? ` · ${s.tipologia}` : ""}</SelectItem>)}
        <SelectItem value={ADD} className="text-tiffany-active font-semibold" data-testid={`${testid}-add`}>+ Nuova struttura</SelectItem>
      </SelectContent>
    </Select>
  );
}
