import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, SectionCard, PrimaryButton } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { X, Plus, Check, Pencil, AlertTriangle } from "lucide-react";

const LISTS = [
  { key: "tipologie_evento", label: "Tipologie evento" },
  { key: "settori", label: "Settori aziende" },
  { key: "tipi_azienda", label: "Tipi di azienda" },
  { key: "ruoli_staff", label: "Ruoli staff" },
  { key: "aree_operative", label: "Aree operative" },
  { key: "livelli_sponsorship", label: "Livelli sponsorship" },
];

function ListEditor({ lkey, label, settings, save }) {
  const [val, setVal] = useState("");
  const [edit, setEdit] = useState(null); // {idx, value}
  const items = settings[lkey] || [];

  const add = () => {
    const v = val.trim();
    if (!v || items.includes(v)) return;
    save({ ...settings, [lkey]: [...items, v] });
    setVal(""); toast.success("Aggiunto");
  };
  const remove = async (v) => {
    try {
      const { data } = await api.get("/settings/usage", { params: { list: lkey, value: v } });
      if (data.count > 0 && !window.confirm(`"${v}" è utilizzata in ${data.count} record. Eliminare comunque? I record esistenti manterranno il valore.`)) return;
    } catch {}
    save({ ...settings, [lkey]: items.filter((x) => x !== v) });
    toast.success("Rimosso");
  };
  const saveEdit = () => {
    const nv = (edit.value || "").trim();
    if (!nv) return setEdit(null);
    const arr = [...items]; arr[edit.idx] = nv;
    save({ ...settings, [lkey]: arr }); setEdit(null); toast.success("Aggiornato");
  };

  return (
    <SectionCard title={label}>
      <div className="flex flex-wrap gap-2 mb-3">
        {items.map((item, idx) => (
          edit && edit.idx === idx ? (
            <span key={idx} className="inline-flex items-center gap-1 rounded-full bg-white ring-1 ring-tiffany-border px-2 py-0.5">
              <input autoFocus value={edit.value} onChange={(e) => setEdit({ idx, value: e.target.value })} onKeyDown={(e) => e.key === "Enter" && saveEdit()}
                className="text-xs w-24 outline-none" data-testid={`edit-input-${lkey}`} />
              <button onClick={saveEdit} data-testid={`save-edit-${lkey}`}><Check className="w-3.5 h-3.5 text-emerald-600" /></button>
            </span>
          ) : (
            <span key={idx} className="inline-flex items-center gap-1.5 rounded-full bg-tiffany-light text-tiffany-fg ring-1 ring-tiffany-border px-3 py-1 text-xs font-medium" data-testid={`setting-${lkey}-${item}`}>
              {item}
              <button onClick={() => setEdit({ idx, value: item })} className="hover:text-slate-800" data-testid={`rename-${lkey}-${item}`}><Pencil className="w-3 h-3" /></button>
              <button onClick={() => remove(item)} className="hover:text-red-500" data-testid={`remove-${lkey}-${item}`}><X className="w-3 h-3" /></button>
            </span>
          )
        ))}
      </div>
      <div className="flex gap-2">
        <Input value={val} onChange={(e) => setVal(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Aggiungi..." data-testid={`add-input-${lkey}`} />
        <Button variant="outline" size="icon" onClick={add} data-testid={`add-button-${lkey}`}><Plus className="w-4 h-4" /></Button>
      </div>
    </SectionCard>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  const [settings, setSettings] = useState(null);
  useEffect(() => { api.get("/settings").then(({ data }) => setSettings(data)); }, []);
  const save = async (next) => { setSettings(next); try { await api.put("/settings", next); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  const doReset = async () => {
    try { const { data } = await api.post("/admin/reset-data"); toast.success("Database operativo azzerato"); setTimeout(() => window.location.reload(), 800); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  if (!settings) return <div className="text-slate-400">Caricamento...</div>;

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeader title="Impostazioni" subtitle="Liste configurabili, profilo e manutenzione dati" />

      <SectionCard title="Profilo">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div><div className="text-xs uppercase text-slate-400 font-medium">Nome</div><div className="text-slate-800 font-medium">{user?.name}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Email</div><div className="text-slate-800 font-medium">{user?.email}</div></div>
        </div>
      </SectionCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {LISTS.map((l) => <ListEditor key={l.key} lkey={l.key} label={l.label} settings={settings} save={save} />)}
      </div>

      <SectionCard title="Google Calendar">
        <p className="text-sm text-slate-600">La sincronizzazione Google Calendar richiede la configurazione di <b>GOOGLE_CLIENT_ID</b> e <b>GOOGLE_CLIENT_SECRET</b> nei Secrets di produzione. Ogni utente collega poi il proprio calendario da <b>Profilo → Integrazioni</b>.</p>
      </SectionCard>

      <div className="bg-white border border-red-200 rounded-xl shadow-sm p-5">
        <div className="flex items-center gap-2 mb-2"><AlertTriangle className="w-5 h-5 text-red-500" /><h3 className="text-base font-semibold text-slate-800 font-display">Reset database operativo</h3></div>
        <p className="text-sm text-slate-600 mb-4">Elimina definitivamente tutti i dati operativi (eventi, aziende, persone, trattative, staff, team, turni, mappe, attività, follow-up e account staff/volontari) e disabilita il seed demo. L'account amministratore e le configurazioni restano. Usalo solo quando sei pronto a partire con i dati reali.</p>
        <AlertDialog>
          <AlertDialogTrigger asChild><Button className="bg-red-500 hover:bg-red-600 text-white" data-testid="reset-data-button">Azzera database operativo</Button></AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader><AlertDialogTitle>Confermi l'azzeramento?</AlertDialogTitle>
              <AlertDialogDescription>Tutti i dati operativi saranno eliminati in modo irreversibile. Questa azione non può essere annullata.</AlertDialogDescription></AlertDialogHeader>
            <AlertDialogFooter><AlertDialogCancel>Annulla</AlertDialogCancel>
              <AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={doReset} data-testid="confirm-reset">Sì, azzera tutto</AlertDialogAction></AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
