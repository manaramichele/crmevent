import { useState, useEffect } from "react";
import api, { formatApiError } from "@/lib/api";
import { useSettings, toOptions } from "@/components/crm";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import SettingSelect from "@/components/SettingSelect";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

const emptyRef = { nome: "", cognome: "", ruolo: "", email: "", cellulare: "", referente_principale: false };

export default function CompanyDialog({ open, onOpenChange, initial, onSaved }) {
  const settings = useSettings();
  const editing = !!initial?.id;
  const [f, setF] = useState({});
  const [refs, setRefs] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setF(initial || { nazione: "Italia", tipo: "Azienda" }); setRefs([]); }, [initial, open]);
  const ch = (k, v) => setF((s) => ({ ...s, [k]: v }));

  const save = async () => {
    if (!f.nome) { toast.error("Ragione sociale obbligatoria"); return; }
    setSaving(true);
    try {
      let company;
      if (editing) { const { data } = await api.put(`/companies/${initial.id}`, f); company = data; }
      else { const { data } = await api.post("/companies", f); company = data; }
      // inline referenti (only on create)
      for (const r of refs) {
        if (!r.nome) continue;
        try {
          const { data: m } = await api.post("/persons-match", { email: r.email, cellulare: r.cellulare, nome: r.nome, cognome: r.cognome });
          if (m.matches.length > 0) {
            await api.post(`/companies/${company.id}/contacts`, { person_id: m.matches[0].id, ruolo: r.ruolo, referente_principale: r.referente_principale });
            toast.info(`${r.nome}: collegato a persona esistente`);
          } else {
            await api.post(`/companies/${company.id}/contacts`, r);
          }
        } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
      }
      toast.success(editing ? "Azienda aggiornata" : "Azienda creata");
      onSaved && onSaved(company);
      onOpenChange(false);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const settoreOpts = toOptions(settings?.settori);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="company-dialog">
        <DialogHeader><DialogTitle className="font-display">{editing ? "Modifica azienda" : "Nuova azienda"}</DialogTitle>
          <DialogDescription className="sr-only">Anagrafica azienda e referenti</DialogDescription></DialogHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-2">
          <div className="sm:col-span-2 space-y-1.5"><Label className="text-xs">Ragione sociale*</Label><Input value={f.nome || ""} onChange={(e) => ch("nome", e.target.value)} data-testid="field-nome" /></div>
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
          <div className="space-y-1.5"><Label className="text-xs">Città</Label><Input value={f.citta || ""} onChange={(e) => ch("citta", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Provincia</Label><Input value={f.provincia || ""} onChange={(e) => ch("provincia", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Regione</Label><Input value={f.regione || ""} onChange={(e) => ch("regione", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Nazione</Label><Input value={f.nazione || ""} onChange={(e) => ch("nazione", e.target.value)} /></div>
          <div className="space-y-1.5"><Label className="text-xs">Responsabile interno</Label><Input value={f.responsabile_interno || ""} onChange={(e) => ch("responsabile_interno", e.target.value)} /></div>
          <div className="sm:col-span-2 space-y-1.5"><Label className="text-xs">Note</Label><Textarea value={f.note || ""} onChange={(e) => ch("note", e.target.value)} /></div>
        </div>

        {!editing && (
          <div className="border-t border-slate-100 pt-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold text-slate-700">Referenti</span>
              <Button size="sm" variant="outline" onClick={() => setRefs((r) => [...r, { ...emptyRef }])} data-testid="company-add-referente"><Plus className="w-4 h-4 mr-1" />Aggiungi referente</Button>
            </div>
            {refs.length === 0 && <p className="text-xs text-slate-400">Puoi aggiungere uno o più referenti; verranno creati o collegati automaticamente in anagrafica Persone.</p>}
            <div className="space-y-3">
              {refs.map((r, i) => (
                <div key={i} className="border border-slate-200 rounded-lg p-3 relative" data-testid={`company-ref-${i}`}>
                  <button className="absolute top-2 right-2 text-slate-400 hover:text-red-500" onClick={() => setRefs((x) => x.filter((_, j) => j !== i))}><Trash2 className="w-4 h-4" /></button>
                  <div className="grid grid-cols-2 gap-2">
                    <Input placeholder="Nome*" value={r.nome} onChange={(e) => setRefs((x) => x.map((y, j) => j === i ? { ...y, nome: e.target.value } : y))} data-testid={`company-ref-nome-${i}`} />
                    <Input placeholder="Cognome" value={r.cognome} onChange={(e) => setRefs((x) => x.map((y, j) => j === i ? { ...y, cognome: e.target.value } : y))} />
                    <Input placeholder="Ruolo" value={r.ruolo} onChange={(e) => setRefs((x) => x.map((y, j) => j === i ? { ...y, ruolo: e.target.value } : y))} />
                    <Input placeholder="Email" value={r.email} onChange={(e) => setRefs((x) => x.map((y, j) => j === i ? { ...y, email: e.target.value } : y))} data-testid={`company-ref-email-${i}`} />
                    <Input placeholder="Cellulare" value={r.cellulare} onChange={(e) => setRefs((x) => x.map((y, j) => j === i ? { ...y, cellulare: e.target.value } : y))} />
                    <label className="flex items-center gap-2 text-sm text-slate-600"><Checkbox checked={r.referente_principale} onCheckedChange={(v) => setRefs((x) => x.map((y, j) => j === i ? { ...y, referente_principale: !!v } : y))} />Principale</label>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annulla</Button>
          <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={save} disabled={saving} data-testid="company-save">{saving ? "Salvataggio..." : "Salva"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
