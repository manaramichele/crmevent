import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Trash2 } from "lucide-react";
import { Card } from "@/components/partners/shared";

const FIELDS = [["commission_pct", "Commissione (%)", "number"], ["duration_months", "Durata dal primo pagamento (mesi)", "number"], ["attribution_days", "Finestra di attribuzione referral (giorni)", "number"],
  ["hold_days", "Giorni minimi dal pagamento prima della liquidazione", "number"], ["min_payout_cents", "Soglia minima liquidazione (centesimi)", "number"]];

function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/platform/partner-settings").then(({ data }) => setS(data)).catch(() => {}); }, []);
  if (!s) return null;
  const save = async () => {
    try { const b = Object.fromEntries(FIELDS.map(([k]) => [k, Number(s[k])])); const { data } = await api.put("/platform/partner-settings", { ...b, payout_frequency: s.payout_frequency, crmevent_tax_regime: s.crmevent_tax_regime, payout_notes: s.payout_notes }); setS(data); toast.success("Configurazione salvata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const sel = "w-full h-10 rounded-md border border-slate-200 bg-white px-3 text-sm";
  return (
    <Card title="Regole del programma" testid="partner-settings">
      <div className="p-4 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {FIELDS.map(([k, l]) => <label key={k} className="text-sm">{l}<Input type="number" value={s[k]} onChange={(e) => setS({ ...s, [k]: e.target.value })} data-testid={`partner-settings-${k}`} /></label>)}
        <label className="text-sm">Frequenza liquidazioni<select className={sel} value={s.payout_frequency} onChange={(e) => setS({ ...s, payout_frequency: e.target.value })} data-testid="partner-settings-frequency"><option value="trimestrale">Trimestrale</option><option value="semestrale">Semestrale</option><option value="mensile">Mensile</option></select></label>
        <label className="text-sm">Regime fiscale CRMEvent<select className={sel} value={s.crmevent_tax_regime} onChange={(e) => setS({ ...s, crmevent_tax_regime: e.target.value })} data-testid="partner-settings-regime"><option value="forfettario">Forfettario</option><option value="ordinario">Ordinario</option></select></label>
        <label className="text-sm sm:col-span-2 lg:col-span-3">Note amministrative liquidazioni<textarea className="w-full rounded-md border border-slate-200 p-2 text-sm" rows={2} value={s.payout_notes || ""} onChange={(e) => setS({ ...s, payout_notes: e.target.value })} data-testid="partner-settings-notes" /></label>
      </div>
      <div className="px-4 pb-4 text-xs text-slate-500 space-y-1">
        <p>Base di calcolo: importo dell'abbonamento BRONZE, SILVER o GOLD effettivamente incassato e confermato da Stripe, imposte escluse, al netto di rimborsi e storni. Marketplace e crediti esclusi. Nessuna IVA presunta.</p>
        <p>Il regime di CRMEvent è indipendente da quello dei partner e viene registrato su ogni commissione e liquidazione. Liquidazione manuale (nessun pagamento automatico).</p>
      </div>
      <div className="px-4 pb-4"><Button onClick={save} className="bg-[#0ABAB5] hover:bg-[#09A8A3] text-slate-900 font-semibold" data-testid="partner-settings-save">Salva configurazione</Button></div>
    </Card>
  );
}

function Materials() {
  const [rows, setRows] = useState([]);
  const [f, setF] = useState({ title: "", description: "", url: "" });
  const [file, setFile] = useState(null);
  const load = () => api.get("/platform/partner-materials").then(({ data }) => setRows(data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const add = async () => {
    const fd = new FormData(); Object.entries(f).forEach(([k, v]) => fd.append(k, v)); if (file) fd.append("file", file);
    try { await api.post("/platform/partner-materials", fd); toast.success("Materiale aggiunto"); setF({ title: "", description: "", url: "" }); setFile(null); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const del = async (m) => { if (!window.confirm(`Eliminare "${m.title}"?`)) return; await api.delete(`/platform/partner-materials/${m.id}`); load(); };
  return (
    <Card title="Materiali promozionali" testid="partner-materials-admin">
      <div className="p-4 grid sm:grid-cols-2 gap-2">
        <Input placeholder="Titolo" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="material-title" />
        <Input placeholder="Link (https://...) facoltativo se carichi un file" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} data-testid="material-url" />
        <Input placeholder="Descrizione" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} data-testid="material-description" />
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} className="text-sm" data-testid="material-file" />
        <Button disabled={!f.title.trim() || (!f.url.trim() && !file)} onClick={add} className="bg-[#0ABAB5] text-slate-900 sm:w-fit" data-testid="material-add">Aggiungi materiale</Button>
      </div>
      {rows.map((m) => <div key={m.id} className="px-4 py-2 border-t border-slate-100 flex items-center justify-between text-sm" data-testid={`material-${m.id}`}><span><b>{m.title}</b> {m.description && `· ${m.description}`} {m.has_file ? "· file" : m.url ? "· link" : ""}</span><button onClick={() => del(m)} aria-label="Elimina" data-testid={`material-del-${m.id}`}><Trash2 className="w-4 h-4 text-red-500" /></button></div>)}
    </Card>
  );
}

export default function PartnerConfig() {
  return <div className="space-y-5"><Settings /><Materials /></div>;
}
