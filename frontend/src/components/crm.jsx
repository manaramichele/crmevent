import { useEffect, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import SettingSelect from "@/components/SettingSelect";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Plus, Pencil, Trash2, Search } from "lucide-react";

export const eurFmt = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
export const formatEUR = (n) => eurFmt.format(Number(n || 0));

export const BACKEND = process.env.REACT_APP_BACKEND_URL;
export const fileUrl = (u) => (u ? (u.startsWith("http") ? u : `${BACKEND}${u}`) : "");
export const toOptions = (arr) => (arr || []).map((v) => ({ value: v, label: v }));

// Età calcolata dinamicamente dalla data di nascita (YYYY-MM-DD). Resta sempre corretta nel tempo.
export const calcAge = (dn) => {
  if (!dn) return null;
  const b = new Date(String(dn).slice(0, 10));
  if (isNaN(b.getTime())) return null;
  const t = new Date();
  let a = t.getFullYear() - b.getFullYear();
  const m = t.getMonth() - b.getMonth();
  if (m < 0 || (m === 0 && t.getDate() < b.getDate())) a--;
  return a >= 0 && a < 120 ? a : null;
};

export function useSettings() {
  const [settings, setSettings] = useState(null);
  useEffect(() => { api.get("/settings").then(({ data }) => setSettings(data)).catch(() => {}); }, []);
  return settings;
}

export function FileUpload({ label, value, onChange, accept, testid = "file" }) {
  const [busy, setBusy] = useState(false);
  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      onChange(data.url);
      toast.success("File caricato");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-1.5">
      {label && <Label className="text-xs font-medium text-slate-600">{label}</Label>}
      <div className="flex items-center gap-2">
        <input type="file" accept={accept} onChange={upload} data-testid={`${testid}-input`}
          className="text-xs file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-tiffany-light file:text-tiffany-fg file:font-medium file:cursor-pointer" />
        {busy && <span className="text-xs text-slate-400">Caricamento...</span>}
      </div>
      {value && <a href={fileUrl(value)} target="_blank" rel="noreferrer" className="text-xs text-tiffany-active hover:underline break-all">{value}</a>}
    </div>
  );
}

export function ImageUpload({ value, onChange, testid = "image" }) {
  const [busy, setBusy] = useState(false);
  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!/\.(png|jpe?g)$/i.test(f.name)) { toast.error("Formato non supportato: usa PNG o JPG/JPEG"); e.target.value = ""; return; }
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const { data } = await api.post("/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      onChange(data.url);
      toast.success("Logo caricato");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setBusy(false); e.target.value = ""; }
  };
  return (
    <div className="flex items-center gap-3">
      {value ? (
        <div className="h-16 w-28 rounded-lg border border-slate-200 bg-white flex items-center justify-center overflow-hidden shrink-0">
          <img src={fileUrl(value)} alt="Logo evento" className="max-h-full max-w-full object-contain" data-testid={`${testid}-preview`} />
        </div>
      ) : (
        <div className="h-16 w-28 rounded-lg border border-dashed border-slate-300 bg-slate-50 flex items-center justify-center text-[11px] text-slate-400 shrink-0">Nessun logo</div>
      )}
      <div className="space-y-1.5">
        <input type="file" accept="image/png,image/jpeg" onChange={upload} data-testid={`${testid}-input`}
          className="text-xs file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-tiffany-light file:text-tiffany-fg file:font-medium file:cursor-pointer" />
        {busy && <span className="text-xs text-slate-400">Caricamento...</span>}
        {value && <button type="button" onClick={() => onChange("")} className="block text-xs text-red-500 hover:underline" data-testid={`${testid}-remove`}>Elimina logo</button>}
      </div>
    </div>
  );
}

export function useCollection(endpoint) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async (params) => {
    setLoading(true);
    try {
      const { data } = await api.get(endpoint, { params });
      setItems(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => { reload(); }, [reload]);

  const create = async (payload) => {
    const { data } = await api.post(endpoint, payload);
    setItems((p) => [data, ...p]);
    return data;
  };
  const update = async (id, payload) => {
    const { data } = await api.put(`${endpoint}/${id}`, payload);
    setItems((p) => p.map((i) => (i.id === id ? data : i)));
    return data;
  };
  const remove = async (id) => {
    await api.delete(`${endpoint}/${id}`);
    setItems((p) => p.filter((i) => i.id !== id));
  };
  return { items, loading, reload, create, update, remove, setItems };
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-900 font-display">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500 mt-1">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function SectionCard({ title, children, className = "", action }) {
  return (
    <div className={`bg-white border border-slate-200 rounded-xl shadow-sm p-5 ${className}`}>
      {title && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold text-slate-800 font-display">{title}</h3>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

const STATUS_STYLES = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  orange: "bg-amber-50 text-amber-700 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  tiffany: "bg-tiffany-light text-tiffany-fg ring-tiffany-border",
  gray: "bg-slate-100 text-slate-600 ring-slate-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
};

export function StatusBadge({ children, color = "gray", ...props }) {
  return (
    <span {...props} className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${STATUS_STYLES[color] || STATUS_STYLES.gray}`}>
      {children}
    </span>
  );
}

export function PrimaryButton({ children, ...props }) {
  return (
    <Button
      className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold shadow-sm transition-all active:scale-[0.98]"
      {...props}
    >
      {children}
    </Button>
  );
}

function Field({ field, value, onChange, options }) {
  const common = { id: field.name, "data-testid": `field-${field.name}` };
  if (field.type === "image") {
    return <ImageUpload value={value} onChange={(u) => onChange(field.name, u)} testid={`field-${field.name}`} />;
  }
  if (field.type === "textarea") {
    return <Textarea {...common} value={value || ""} onChange={(e) => onChange(field.name, e.target.value)} placeholder={field.placeholder} />;
  }
  if (field.type === "select" && field.settingKey) {
    return <SettingSelect settingKey={field.settingKey} value={value} onChange={(v) => onChange(field.name, v)}
      options={options?.[field.source] || field.options || []} placeholder={field.placeholder}
      addLabel={field.addLabel || "Aggiungi nuovo"} testid={`field-${field.name}`} />;
  }
  if (field.type === "select") {
    const opts = field.options || options?.[field.source] || [];
    return (
      <Select value={value || ""} onValueChange={(v) => onChange(field.name, v)}>
        <SelectTrigger data-testid={`field-${field.name}`}><SelectValue placeholder={field.placeholder || "Seleziona..."} /></SelectTrigger>
        <SelectContent>
          {opts.map((o) => (
            <SelectItem key={o.value} value={o.value} data-testid={`option-${field.name}-${o.value}`}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  return (
    <Input
      {...common}
      type={field.type === "number" ? "number" : field.type === "date" ? "date" : field.type || "text"}
      value={value ?? ""}
      onChange={(e) => onChange(field.name, field.type === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)}
      placeholder={field.placeholder}
    />
  );
}

export function EntityDialog({ open, onOpenChange, title, fields, initial, onSubmit, options, testid = "entity" }) {
  const [form, setForm] = useState(initial || {});
  const [saving, setSaving] = useState(false);
  useEffect(() => { setForm(initial || {}); }, [initial, open]);

  const change = (name, val) => setForm((f) => ({ ...f, [name]: val }));

  const submit = async () => {
    for (const f of fields) {
      if (f.required && !form[f.name]) { toast.error(`Campo obbligatorio: ${f.label}`); return; }
    }
    setSaving(true);
    try {
      await onSubmit(form);
      onOpenChange(false);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid={`${testid}-dialog`}>
        <DialogHeader><DialogTitle className="font-display">{title}</DialogTitle><DialogDescription className="sr-only">Compila i campi e salva.</DialogDescription></DialogHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-2">
          {fields.map((f) => (
            <div key={f.name} className={f.full ? "sm:col-span-2 space-y-1.5" : "space-y-1.5"}>
              <Label htmlFor={f.name} className="text-xs font-medium text-slate-600">
                {f.label}{f.required && <span className="text-red-500 ml-0.5">*</span>}
              </Label>
              <Field field={f} value={form[f.name]} onChange={change} options={options} />
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid={`${testid}-cancel`}>Annulla</Button>
          <PrimaryButton onClick={submit} disabled={saving} data-testid={`${testid}-save`}>{saving ? "Salvataggio..." : "Salva"}</PrimaryButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EntityManager({ title, subtitle, endpoint, fields, columns, options = {}, entityLabel = "elemento", testid = "entity", searchKeys = ["nome"], filters = [], rowActions }) {
  const { items, loading, create, update, remove } = useCollection(endpoint);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [query, setQuery] = useState("");
  const [filterVals, setFilterVals] = useState({});

  const openNew = () => { setEditing(null); setDialogOpen(true); };
  const openEdit = (row) => { setEditing(row); setDialogOpen(true); };

  const onSubmit = async (form) => {
    if (editing) { await update(editing.id, form); toast.success(`${entityLabel} aggiornato`); }
    else { await create(form); toast.success(`${entityLabel} creato`); }
  };

  const onDelete = async (row) => {
    try { await remove(row.id); toast.success(`${entityLabel} eliminato`); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const filtered = items.filter((i) =>
    (!query || searchKeys.some((k) => String(i[k] || "").toLowerCase().includes(query.toLowerCase()))) &&
    filters.every((f) => !filterVals[f.name] || filterVals[f.name] === "all" || i[f.name] === filterVals[f.name])
  );

  return (
    <div className="animate-fade-up">
      <PageHeader
        title={title}
        subtitle={subtitle}
        action={<PrimaryButton onClick={openNew} data-testid={`add-${testid}-button`}><Plus className="w-4 h-4 mr-1.5" />Aggiungi</PrimaryButton>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <Input className="pl-9" placeholder="Cerca..." value={query} onChange={(e) => setQuery(e.target.value)} data-testid={`search-${testid}-input`} />
        </div>
        {filters.map((f) => (
          <Select key={f.name} value={filterVals[f.name] || "all"} onValueChange={(v) => setFilterVals((p) => ({ ...p, [f.name]: v }))}>
            <SelectTrigger className="w-full sm:w-44" data-testid={`filter-${testid}-${f.name}`}><SelectValue placeholder={f.label} /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{f.label}: tutti</SelectItem>
              {f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        ))}
      </div>
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70">
                {columns.map((c) => (
                  <th key={c.key} className="text-left font-semibold text-slate-600 px-4 py-3 whitespace-nowrap">{c.label}</th>
                ))}
                <th className="px-4 py-3 text-right font-semibold text-slate-600">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={columns.length + 1} className="px-4 py-10 text-center text-slate-400">Caricamento...</td></tr>
              ) : filtered.length === 0 ? (
                <tr><td colSpan={columns.length + 1} className="px-4 py-10 text-center text-slate-400">Nessun {entityLabel} trovato.</td></tr>
              ) : filtered.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50/80 transition-colors" data-testid={`${testid}-row-${row.id}`}>
                  {columns.map((c) => (
                    <td key={c.key} className="px-4 py-3 text-slate-700">{c.render ? c.render(row) : (row[c.key] || "—")}</td>
                  ))}
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      {rowActions && rowActions(row)}
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" onClick={() => openEdit(row)} data-testid={`edit-${testid}-${row.id}`}><Pencil className="w-4 h-4" /></Button>
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" data-testid={`delete-${testid}-${row.id}`}><Trash2 className="w-4 h-4" /></Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Confermi l'eliminazione?</AlertDialogTitle>
                            <AlertDialogDescription>Questa azione non può essere annullata.</AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Annulla</AlertDialogCancel>
                            <AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={() => onDelete(row)} data-testid={`confirm-delete-${testid}-${row.id}`}>Elimina</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <EntityDialog
        open={dialogOpen} onOpenChange={setDialogOpen}
        title={editing ? `Modifica ${entityLabel}` : `Nuovo ${entityLabel}`}
        fields={fields} initial={editing} onSubmit={onSubmit} options={options} testid={testid}
      />
    </div>
  );
}
