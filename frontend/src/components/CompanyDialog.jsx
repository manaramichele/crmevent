import { useState, useEffect } from "react";
import api, { formatApiError } from "@/lib/api";
import { useSettings, toOptions } from "@/components/crm";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import SettingSelect from "@/components/SettingSelect";
import ReferentiFields, { emptyReferente } from "@/components/ReferentiFields";
import { toast } from "sonner";
import { CASE_FN, COMPANY_RULES } from "@/lib/textCase";

export default function CompanyDialog({ open, onOpenChange, initial, onSaved }) {
  const settings = useSettings();
  const editing = !!initial?.id;
  const [f, setF] = useState({});
  const [refs, setRefs] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setF(initial || { nazione: "Italia", tipo: "Azienda" });
    setRefs(initial?.id ? [] : [emptyReferente()]);
    if (initial?.id) api.get(`/companies/${initial.id}/referenti`).then(({ data }) => setRefs(data.length ? data : [emptyReferente()])).catch(() => {});
  }, [initial, open]);
  const ch = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const fix = (k) => () => setF((s) => (typeof s[k] === "string" ? { ...s, [k]: CASE_FN[COMPANY_RULES[k]](s[k]) } : s));

  const save = async () => {
    if (!f.nome) { toast.error("Ragione sociale obbligatoria"); return; }
    setSaving(true);
    try {
      if (!editing) {
        try {
          const { data: existing } = await api.get("/companies");
          const nn = (s) => (s || "").trim().toLowerCase();
          const dup = (existing || []).find((c) => nn(c.nome) === nn(f.nome));
          if (dup && !window.confirm(`Esiste già un'azienda "${dup.nome}". Vuoi crearla comunque?`)) { setSaving(false); return; }
        } catch {}
      }
      let company;
      if (editing) { const { data } = await api.put(`/companies/${initial.id}`, f); company = data; }
      else { const { data } = await api.post("/companies", f); company = data; }
      try { await api.put(`/companies/${company.id}/referenti`, { referenti: refs }); }
      catch (e) { toast.error(`Referenti non salvati: ${formatApiError(e.response?.data?.detail)}`); }
      toast.success(editing ? "Azienda aggiornata" : "Azienda creata");
      onSaved && onSaved(company);
      onOpenChange(false);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const settoreOpts = toOptions(settings?.settori);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="company-dialog">
        <DialogHeader><DialogTitle className="font-display">{editing ? "Modifica azienda" : "Nuova azienda"}</DialogTitle>
          <DialogDescription className="sr-only">Anagrafica azienda e referenti</DialogDescription></DialogHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-2">
          <div className="sm:col-span-2 space-y-1.5"><Label className="text-xs">Ragione sociale*</Label><Input value={f.nome || ""} onChange={(e) => ch("nome", e.target.value)} onBlur={fix("nome")} data-testid="field-nome" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Settore</Label>
            <SettingSelect settingKey="settori" value={f.settore} onChange={(v) => ch("settore", v)} options={settings?.settori || []} addLabel="Aggiungi nuovo settore" testid="field-settore" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Tipo</Label>
            <SettingSelect settingKey="tipi_azienda" value={f.tipo} onChange={(v) => ch("tipo", v)} options={settings?.tipi_azienda || []} addLabel="Aggiungi nuova tipologia" placeholder="Seleziona tipo..." testid="field-tipo" /></div>
          <div className="space-y-1.5"><Label className="text-xs">Partita IVA</Label><Input value={f.partita_iva || ""} onChange={(e) => ch("partita_iva", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Sito web</Label><Input value={f.sito_web || ""} onChange={(e) => ch("sito_web", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Email</Label><Input value={f.email || ""} onChange={(e) => ch("email", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Telefono</Label><Input value={f.telefono || ""} onChange={(e) => ch("telefono", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Indirizzo</Label><Input value={f.indirizzo || ""} onChange={(e) => ch("indirizzo", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">CAP</Label><Input value={f.cap || ""} onChange={(e) => ch("cap", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Città</Label><Input value={f.citta || ""} onChange={(e) => ch("citta", e.target.value)} onBlur={fix("citta")} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Provincia</Label><Input value={f.provincia || ""} onChange={(e) => ch("provincia", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Regione</Label><Input value={f.regione || ""} onChange={(e) => ch("regione", e.target.value)} onBlur={fix("regione")} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Nazione</Label><Input value={f.nazione || ""} onChange={(e) => ch("nazione", e.target.value)} onBlur={fix("nazione")} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Responsabile interno</Label><Input value={f.responsabile_interno || ""} onChange={(e) => ch("responsabile_interno", e.target.value)} /></div>
          <div className="sm:col-span-2 space-y-1.5"><Label className="text-xs">Note</Label><Textarea value={f.note || ""} onChange={(e) => ch("note", e.target.value)} /></div>
        </div>

        <ReferentiFields refs={refs} setRefs={setRefs} />

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={save} disabled={saving} data-testid="company-save">{saving ? "Salvataggio..." : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
