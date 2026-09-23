import { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, SectionCard, PrimaryButton } from "@/components/crm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { X, Plus } from "lucide-react";

const LISTS = [
  { key: "tipologie_evento", label: "Tipologie evento" },
  { key: "settori", label: "Settori aziende" },
  { key: "ruoli_staff", label: "Ruoli staff" },
];

export default function SettingsPage() {
  const { user } = useAuth();
  const [settings, setSettings] = useState(null);
  const [newVal, setNewVal] = useState({});

  useEffect(() => { api.get("/settings").then(({ data }) => setSettings(data)); }, []);

  const save = async (next) => {
    setSettings(next);
    try { await api.put("/settings", next); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const addItem = (key) => {
    const v = (newVal[key] || "").trim();
    if (!v) return;
    save({ ...settings, [key]: [...(settings[key] || []), v] });
    setNewVal((p) => ({ ...p, [key]: "" }));
    toast.success("Aggiunto");
  };
  const removeItem = (key, val) => {
    save({ ...settings, [key]: settings[key].filter((x) => x !== val) });
  };

  if (!settings) return <div className="text-slate-400">Caricamento...</div>;

  return (
    <div className="animate-fade-up space-y-6">
      <PageHeader title="Impostazioni" subtitle="Configurazione liste e profilo" />

      <SectionCard title="Profilo utente">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
          <div><div className="text-xs uppercase text-slate-400 font-medium">Nome</div><div className="text-slate-800 font-medium">{user?.name}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Email</div><div className="text-slate-800 font-medium">{user?.email}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Ruolo</div><div className="text-slate-800 font-medium capitalize">{user?.role}</div></div>
          <div><div className="text-xs uppercase text-slate-400 font-medium">Accesso</div><div className="text-slate-800 font-medium capitalize">{user?.auth_provider === "google" ? "Google" : "Email / Password"}</div></div>
        </div>
      </SectionCard>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {LISTS.map((l) => (
          <SectionCard key={l.key} title={l.label}>
            <div className="flex flex-wrap gap-2 mb-3">
              {(settings[l.key] || []).map((item) => (
                <span key={item} className="inline-flex items-center gap-1 rounded-full bg-tiffany-light text-tiffany-fg ring-1 ring-tiffany-border px-3 py-1 text-xs font-medium" data-testid={`setting-${l.key}-${item}`}>
                  {item}
                  <button onClick={() => removeItem(l.key, item)} className="hover:text-red-500" data-testid={`remove-${l.key}-${item}`}><X className="w-3 h-3" /></button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <Input value={newVal[l.key] || ""} onChange={(e) => setNewVal((p) => ({ ...p, [l.key]: e.target.value }))}
                onKeyDown={(e) => e.key === "Enter" && addItem(l.key)} placeholder="Aggiungi..." data-testid={`add-input-${l.key}`} />
              <Button variant="outline" size="icon" onClick={() => addItem(l.key)} data-testid={`add-button-${l.key}`}><Plus className="w-4 h-4" /></Button>
            </div>
          </SectionCard>
        ))}
      </div>
    </div>
  );
}
