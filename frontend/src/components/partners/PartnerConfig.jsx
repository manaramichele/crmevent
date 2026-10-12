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

export const MAT_CATS = [["generale", "Generale"], ["instagram", "Instagram"], ["facebook", "Facebook"], ["linkedin", "LinkedIn"], ["whatsapp", "WhatsApp"], ["email", "Email"]];
const EMPTY = { kind: "file", category: "generale", title: "", description: "", url: "", text: "" };
const PH = "[LINK PERSONALE DEL PARTNER]";
const MAX_MB = 20;
const mb = (n) => `${(n / 1048576).toFixed(1)} MB`;

export function uploadError(e, file) {
  const r = e.response;
  if (!r) return "Connessione al server non riuscita o interrotta durante il caricamento. Controlla la rete e riprova.";
  const d = typeof r.data === "object" ? r.data?.detail : null;
  if (r.status === 413 && !d) return `Il server web ha rifiutato il file${file ? ` (${mb(file.size)})` : ""} perché supera il limite di caricamento configurato su api.crmevent.it. Serve aumentare client_max_body_size in nginx.`;
  if (r.status === 401) return "Sessione scaduta: accedi di nuovo.";
  if (r.status === 403) return "Permesso negato: serve un account Super Admin.";
  if (d) return formatApiError(d);
  return `Errore del server (HTTP ${r.status}). Riprova tra poco.`;
}

function Materials() {
  const [rows, setRows] = useState([]);
  const [f, setF] = useState(EMPTY);
  const [file, setFile] = useState(null);
  const load = () => api.get("/platform/partner-materials").then(({ data }) => setRows(data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const [busy, setBusy] = useState(false);
  const add = async () => {
    if (f.kind === "file" && file) {
      if (!file.size) return toast.error("Il file selezionato è vuoto");
      if (file.size > MAX_MB * 1048576) return toast.error(`File troppo grande (${mb(file.size)}): il massimo consentito è ${MAX_MB} MB`);
      if (!/^(image|video)\//.test(file.type) && file.type !== "application/pdf") return toast.error("Formato non supportato: carica un'immagine, un video o un PDF");
    }
    const fd = new FormData(); Object.entries(f).forEach(([k, v]) => fd.append(k, v)); if (file && f.kind === "file") fd.append("file", file);
    setBusy(true);
    try { await api.post("/platform/partner-materials", fd); toast.success("Materiale aggiunto"); setF({ ...EMPTY, kind: f.kind, category: f.category }); setFile(null); load(); } catch (e) { toast.error(uploadError(e, file), { duration: 10000 }); } finally { setBusy(false); }
  };
  const del = async (m) => { if (!window.confirm(`Eliminare "${m.title}"?`)) return; await api.delete(`/platform/partner-materials/${m.id}`); load(); };
  return (
    <Card title="Materiali promozionali" testid="partner-materials-admin">
      <div className="p-4 grid sm:grid-cols-2 gap-2">
        <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} data-testid="material-kind"><option value="file">Immagine, video, PDF o link</option><option value="text">Testo promozionale</option></select>
        <select className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} data-testid="material-category">{MAT_CATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <Input placeholder="Titolo" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="material-title" />
        <Input placeholder="Descrizione (facoltativa)" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} data-testid="material-description" />
        {f.kind === "text" ? (
          <div className="sm:col-span-2 space-y-1">
            <textarea rows={10} maxLength={10000} className="w-full rounded-md border border-slate-200 p-3 text-sm leading-relaxed" placeholder={`Scrivi il messaggio completo (emoji e paragrafi inclusi). Usa ${PH} dove deve comparire il link del partner.`} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} data-testid="material-text" />
            <div className="flex justify-between text-xs text-slate-500"><button type="button" className="underline" onClick={() => setF({ ...f, text: `${f.text}${f.text && !f.text.endsWith("\n") ? " " : ""}${PH}` })} data-testid="material-insert-placeholder">Inserisci {PH}</button><span>{f.text.length}/10000</span></div>
          </div>
        ) : (<>
          <Input placeholder="Link (https://...) facoltativo se carichi un file" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} data-testid="material-url" />
          <input type="file" accept="image/*,video/*,application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} className="text-sm" data-testid="material-file" />
        </>)}
        <Button disabled={busy || !f.title.trim() || (f.kind === "text" ? !f.text.trim() : !f.url.trim() && !file)} onClick={add} className="bg-[#0ABAB5] text-slate-900 sm:w-fit" data-testid="material-add">{busy ? "Caricamento..." : "Aggiungi materiale"}</Button>
      </div>
      {rows.map((m) => <div key={m.id} className="px-4 py-2 border-t border-slate-100 flex items-center justify-between gap-3 text-sm" data-testid={`material-${m.id}`}><span className="min-w-0"><b>{m.title}</b> · {(MAT_CATS.find((c) => c[0] === m.category) || MAT_CATS[0])[1]} {m.kind === "text" ? "· testo" : m.has_file ? "· file" : m.url ? "· link" : ""}{m.kind === "text" && <span className="block text-xs text-slate-500 truncate">{m.text}</span>}</span><button onClick={() => del(m)} aria-label="Elimina" data-testid={`material-del-${m.id}`}><Trash2 className="w-4 h-4 text-red-500" /></button></div>)}
    </Card>
  );
}

export default function PartnerConfig() {
  return <div className="space-y-5"><Settings /><Materials /></div>;
}
