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
import { useSort, SortIcon, sortRows } from "@/lib/sortable";
import { MODAL, MODAL_SCROLL } from "@/lib/modal";
import { StaffAssignSelect } from "@/components/StaffAssignSelect";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/perms";
import TeamSelect from "@/components/TeamSelect";
import CalendarSyncField from "@/components/CalendarSyncField";

export const eurFmt = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
export const formatEUR = (n) => eurFmt.format(Number(n || 0));

export const BACKEND = process.env.REACT_APP_BACKEND_URL;
export const fileUrl = (u) => (u ? (u.startsWith("http") ? u : `${BACKEND}${u}`) : "");
export const toOptions = (arr) => (arr || []).map((v) => ({ value: v, label: v }));

const MESI_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
// "16 dicembre 2026" (singolo) o "16–20 dicembre 2026" (stesso mese) o "16 dic 2026 – 3 gen 2027".
export function formatDateRange(start, end) {
  if (!start) return "";
  const s = new Date(start);
  if (isNaN(s)) return start;
  const e = end && end !== start ? new Date(end) : null;
  const one = (dt) => `${dt.getDate()} ${MESI_IT[dt.getMonth()]} ${dt.getFullYear()}`;
  if (!e || isNaN(e)) return one(s);
  if (s.getFullYear() === e.getFullYear() && s.getMonth() === e.getMonth())
    return `${s.getDate()}–${e.getDate()} ${MESI_IT[s.getMonth()]} ${s.getFullYear()}`;
  if (s.getFullYear() === e.getFullYear())
    return `${s.getDate()} ${MESI_IT[s.getMonth()]} – ${e.getDate()} ${MESI_IT[e.getMonth()]} ${s.getFullYear()}`;
  return `${one(s)} – ${one(e)}`;
}

const _WD_IT = ["Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"];
const _MO_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"];
export const eventDayList = (start, end) => {
  if (!start) return [];
  const s = new Date(String(start).slice(0, 10) + "T00:00:00");
  const e = new Date(String(end || start).slice(0, 10) + "T00:00:00");
  if (isNaN(s.getTime()) || isNaN(e.getTime()) || e < s) return [];
  const out = [];
  const cur = new Date(s);
  while (cur <= e && out.length < 120) {
    const iso = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, "0")}-${String(cur.getDate()).padStart(2, "0")}`;
    out.push({ date: iso, label: `${_WD_IT[cur.getDay()]} ${cur.getDate()} ${_MO_IT[cur.getMonth()]} ${cur.getFullYear()}` });
    cur.setDate(cur.getDate() + 1);
  }
  return out;
};

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

// Ordina alfabeticamente (A-Z, case-insensitive, locale IT) le opzioni "a valori".
// Eccezioni: "Nessuna preferenza"/valore vuoto/"tutti" sempre in testa; "Altro"/"+ ..." sempre in coda.
// keepOrder=true preserva l'ordine originale (per elenchi con ordine logico: stati, priorità, fasi...).
export const sortOptions = (opts, keepOrder = false) => {
  if (keepOrder || !Array.isArray(opts)) return opts || [];
  const rank = (o) => {
    const l = String(o.label ?? o.value ?? "").trim().toLowerCase();
    if (o.value === "" || l === "nessuna preferenza" || l === "tutti" || l === "tutte") return -1;
    if (l === "altro" || l.startsWith("+ ")) return 1;
    return 0;
  };
  return [...opts].sort((a, b) => {
    const r = rank(a) - rank(b);
    if (r !== 0) return r;
    return String(a.label ?? a.value ?? "").localeCompare(String(b.label ?? b.value ?? ""), "it", { sensitivity: "base" });
  });
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

function Field({ field, value, onChange, options, onAddEntity, form }) {
  const common = { id: field.name, "data-testid": `field-${field.name}` };
  if (field.type === "image") {
    return <ImageUpload value={value} onChange={(u) => onChange(field.name, u)} testid={`field-${field.name}`} />;
  }
  if (field.type === "daydesc") {
    const list = eventDayList(form?.data_inizio, form?.data_fine);
    const val = value || {};
    const setDay = (iso, txt) => {
      const next = { ...val };
      if (txt && txt.trim()) next[iso] = txt; else delete next[iso];
      onChange(field.name, next);
    };
    if (!form?.data_inizio) {
      return <div className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg p-3" data-testid="daydesc-empty">Imposta <span className="font-medium">Data inizio</span> (ed eventuale Data fine) evento per descrivere le singole giornate.</div>;
    }
    return (
      <div className="space-y-2" data-testid="field-giorni_descrizioni">
        {list.map((d) => (
          <div key={d.date} className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3">
            <div className="text-xs font-medium text-slate-600 capitalize sm:w-56">{d.label}</div>
            <Input value={val[d.date] || ""} onChange={(e) => setDay(d.date, e.target.value)} placeholder="Descrizione giornata (es. Mezza Maratona)" maxLength={80} data-testid={`daydesc-${d.date}`} className="flex-1" />
          </div>
        ))}
      </div>
    );
  }
  if (field.type === "textarea") {
    return <Textarea {...common} value={value || ""} onChange={(e) => onChange(field.name, e.target.value)} placeholder={field.placeholder} />;
  }
  if (field.type === "staffselect") {
    const eventoId = form?.[field.eventFrom || "evento_id"] || "";
    const staffPersons = field.staffPersonsFor ? field.staffPersonsFor(form) : [];
    if (!eventoId) {
      return <div className="text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg px-3 py-2.5" data-testid={`field-${field.name}`}>{field.noEventHint || "Seleziona prima l'evento."}</div>;
    }
    return (
      <StaffAssignSelect eventoId={eventoId} staffPersons={staffPersons} allPersons={field.allPersons || []}
        value={value || null} onChange={(pid) => onChange(field.name, pid || "")}
        onStaffAdded={field.onStaffAdded} align="start" triggerTestid={`field-${field.name}`} />
    );
  }
  if (field.type === "teamselect") {
    const eventoId = form?.[field.eventFrom || "evento_id"] || "";
    return <TeamSelect value={value || ""} eventoId={eventoId} onChange={(v) => onChange(field.name, v)}
      testid={`field-${field.name}`} align="start" noEventHint={field.noEventHint || "Seleziona prima l'Evento per scegliere o creare un Team."} />;
  }
  if (field.type === "select" && field.settingKey) {
    return <SettingSelect settingKey={field.settingKey} value={value} onChange={(v) => onChange(field.name, v)}
      options={options?.[field.source] || field.options || []} placeholder={field.placeholder}
      addLabel={field.addLabel || "Aggiungi nuovo"} testid={`field-${field.name}`} />;
  }
  if (field.type === "select") {
    const baseOpts = field.dynamicOptions ? field.dynamicOptions(form) : (field.options || options?.[field.source] || []);
    const opts = sortOptions(baseOpts, field.keepOrder);
    const ADD_ENTITY = "__add_entity__";
    return (
      <Select value={value || ""} onValueChange={(v) => { if (v === ADD_ENTITY) { onAddEntity && onAddEntity(field); } else { onChange(field.name, v); } }}>
        <SelectTrigger data-testid={`field-${field.name}`}><SelectValue placeholder={field.placeholder || "Seleziona..."} /></SelectTrigger>
        <SelectContent>
          {opts.map((o) => (
            <SelectItem key={o.value} value={o.value} data-testid={`option-${field.name}-${o.value}`}>{o.label}</SelectItem>
          ))}
          {field.addEntity && <SelectItem value={ADD_ENTITY} data-testid={`add-entity-${field.name}`} className="text-tiffany-active font-semibold">+ {field.addEntity}</SelectItem>}
        </SelectContent>
      </Select>
    );
  }
  if (field.type === "gcalcheck") {
    return <CalendarSyncField kind={field.kind} form={form} value={value} onChange={(v) => onChange(field.name, v)} />;
  }
  return (
    <Input
      {...common}
      type={field.type === "number" ? "number" : field.type === "date" ? "date" : field.type === "time" ? "time" : field.type || "text"}
      value={value ?? ""}
      onChange={(e) => onChange(field.name, field.type === "number" ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)}
      placeholder={field.placeholder}
    />
  );
}

export function EntityDialog({ open, onOpenChange, title, fields, initial, onSubmit, options, testid = "entity", entityCreators, size = "medium" }) {
  const [form, setForm] = useState(initial || {});
  const [saving, setSaving] = useState(false);
  const [addField, setAddField] = useState(null);
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
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={`${MODAL[size] || MODAL.medium} ${MODAL_SCROLL}`} data-testid={`${testid}-dialog`}
          onInteractOutside={(e) => { const t = e.detail?.originalEvent?.target; if (t && t.closest && t.closest("[data-radix-popper-content-wrapper]")) e.preventDefault(); }}>
          <DialogHeader><DialogTitle className="font-display">{title}</DialogTitle><DialogDescription className="sr-only">Compila i campi e salva.</DialogDescription></DialogHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-2">
            {fields.map((f) => (
              <div key={f.name} className={f.full ? "sm:col-span-2 space-y-1.5" : "space-y-1.5"}>
                <Label htmlFor={f.name} className="text-xs font-medium text-slate-600">
                  {f.label}{f.required && <span className="text-red-500 ml-0.5">*</span>}
                </Label>
                <Field field={f} value={form[f.name]} onChange={change} options={options} onAddEntity={setAddField} form={form} />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} data-testid={`${testid}-cancel`}>Annulla</Button>
            <PrimaryButton onClick={submit} disabled={saving} data-testid={`${testid}-save`}>{saving ? "Salvataggio..." : "Salva"}</PrimaryButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {addField && entityCreators?.[addField.name] && entityCreators[addField.name]({
        onClose: () => setAddField(null),
        onCreated: (item) => { if (item?.id) change(addField.name, item.id); setAddField(null); },
        form,
      })}
    </>
  );
}

export function DeleteConfirm({ onConfirm, testid, children }) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>{children}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Confermi l'eliminazione?</AlertDialogTitle>
          <AlertDialogDescription>Questa azione non può essere annullata.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Annulla</AlertDialogCancel>
          <AlertDialogAction className="bg-red-500 hover:bg-red-600" onClick={onConfirm} data-testid={testid}>Elimina</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// Pulsante testuale compatto (mobile-first): etichetta chiara + area touch adeguata.
export function TextAction({ icon: Icon, children, danger, className = "", ...props }) {
  return (
    <Button type="button" variant="outline" size="sm" className={`h-8 px-2.5 text-xs gap-1 bg-white ${danger ? "text-red-600 border-red-200 hover:bg-red-50 hover:text-red-700" : "text-slate-700"} ${className}`} {...props}>
      {Icon && <Icon />}{children}
    </Button>
  );
}

export function EntityManager({ title, subtitle, endpoint, fields, columns, options = {}, entityLabel = "elemento", testid = "entity", searchKeys = ["nome"], filters = [], rowActions, extraActions, mobileCard, guardCreate, fullActions = false, onSaved, onMutate, entityCreators, section, renderDetail, defaultSort }) {
  const [detailRow, setDetailRow] = useState(null);
  const { user } = useAuth();
  const allow = (a) => !section || can(user, section, a);
  const { items, loading, create, update, remove } = useCollection(endpoint);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [query, setQuery] = useState("");
  const [filterVals, setFilterVals] = useState({});

  const openNew = async () => { if (guardCreate) { const ok = await guardCreate(); if (!ok) return; } setEditing(null); setDialogOpen(true); };
  const openEdit = (row) => { setEditing(row); setDialogOpen(true); };

  const onSubmit = async (form) => {
    let rec;
    if (editing) { rec = await update(editing.id, form); toast.success(`${entityLabel} aggiornato`); }
    else { rec = await create(form); toast.success(`${entityLabel} creato`); }
    if (onSaved) { try { await onSaved(rec || { ...editing, ...form }, form, !!editing); } catch { /* handled in onSaved */ } }
    if (onMutate) { try { await onMutate(); } catch { /* noop */ } }
  };

  const onDelete = async (row) => {
    try { await remove(row.id); toast.success(`${entityLabel} eliminato`); if (onMutate) { try { await onMutate(); } catch { /* noop */ } } }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const filtered = items.filter((i) =>
    (!query || searchKeys.some((k) => String(i[k] || "").toLowerCase().includes(query.toLowerCase()))) &&
    filters.every((f) => !filterVals[f.name] || filterVals[f.name] === "all" || i[f.name] === filterVals[f.name])
  );
  // Regola CRMEvent: elenchi in ordine alfabetico (prima colonna) salvo ordinamento funzionale esplicito (defaultSort)
  const { sort, toggle } = useSort(defaultSort || { key: columns[0]?.key || null, dir: "asc" });
  const sorted = sortRows(filtered, sort, columns);
  const helpers = (row) => ({ openDetail: () => setDetailRow(row), openEdit, onDelete, allow, update, filterVals });
  const cell = (c, row) => (c.render ? c.render(row, { openDetail: () => setDetailRow(row) }) : (row[c.key] || "—"));
  const mobileActions = (row) => (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {rowActions && rowActions(row, { openEdit, onDelete })}
      {!fullActions && (renderDetail
        ? <TextAction icon={Pencil} onClick={() => setDetailRow(row)} data-testid={`m-edit-${testid}-${row.id}`}>Modifica</TextAction>
        : allow("edit") && <TextAction icon={Pencil} onClick={() => openEdit(row)} data-testid={`m-edit-${testid}-${row.id}`}>Modifica</TextAction>)}
      {extraActions && extraActions(row, helpers(row))}
      {!fullActions && allow("delete") && <DeleteConfirm onConfirm={() => onDelete(row)} testid={`m-confirm-delete-${testid}-${row.id}`}>
        <TextAction icon={Trash2} danger data-testid={`m-delete-${testid}-${row.id}`}>Elimina</TextAction></DeleteConfirm>}
    </div>
  );

  return (
    <div className="animate-fade-up">
      <PageHeader
        title={title}
        subtitle={subtitle}
        action={allow("create") ? <PrimaryButton onClick={openNew} data-testid={`add-${testid}-button`}><Plus className="w-4 h-4 mr-1.5" />Aggiungi</PrimaryButton> : null}
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
      <div className="md:hidden space-y-2.5" data-testid={`${testid}-mobile-list`}>
        {loading ? <div className="py-10 text-center text-slate-400 text-sm">Caricamento...</div>
          : sorted.length === 0 ? <div className="py-10 text-center text-slate-400 text-sm">Nessun {entityLabel} trovato.</div>
          : sorted.map((row) => mobileCard ? <div key={row.id}>{mobileCard(row, helpers(row))}</div> : (
            <div key={row.id} className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={`${testid}-card-${row.id}`}>
              <div className="font-semibold text-slate-900 break-words">{columns[0] && cell(columns[0], row)}</div>
              <dl className="mt-2 space-y-1.5 text-sm">
                {columns.slice(1).map((c) => (
                  <div key={c.key} className="flex gap-3"><dt className="w-28 shrink-0 text-xs text-slate-400 pt-0.5">{c.label}</dt><dd className="min-w-0 flex-1 break-words text-slate-700">{cell(c, row)}</dd></div>
                ))}
              </dl>
              {mobileActions(row)}
            </div>
          ))}
      </div>
      <div className="hidden md:block bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/70">
                {columns.map((c) => (
                  <th key={c.key} onClick={() => c.sortable !== false && toggle(c.key)}
                    className={`text-left font-semibold text-slate-600 px-4 py-3 whitespace-nowrap ${c.sortable !== false ? "cursor-pointer select-none group" : ""}`}>
                    <span className="inline-flex items-center gap-1">{c.label}{c.sortable !== false && <SortIcon active={sort.key === c.key} dir={sort.dir} />}</span>
                  </th>
                ))}
                <th className="px-4 py-3 text-right font-semibold text-slate-600">Azioni</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={columns.length + 1} className="px-4 py-10 text-center text-slate-400">Caricamento...</td></tr>
              ) : sorted.length === 0 ? (
                <tr><td colSpan={columns.length + 1} className="px-4 py-10 text-center text-slate-400">Nessun {entityLabel} trovato.</td></tr>
              ) : sorted.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 hover:bg-slate-50/80 transition-colors" data-testid={`${testid}-row-${row.id}`}>
                  {columns.map((c) => (
                    <td key={c.key} className="px-4 py-3 text-slate-700">{cell(c, row)}</td>
                  ))}
                  <td className="px-4 py-3">
                    {fullActions ? (
                      <div className="flex items-center justify-end">
                        {rowActions && rowActions(row, { openEdit, onDelete })}
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-1">
                        {rowActions && rowActions(row, { openEdit, onDelete })}
                        {renderDetail
                          ? <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" title="Apri la scheda completa" onClick={() => setDetailRow(row)} data-testid={`edit-${testid}-${row.id}`}><Pencil className="w-4 h-4" /></Button>
                          : allow("edit") && <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-tiffany-active" onClick={() => openEdit(row)} data-testid={`edit-${testid}-${row.id}`}><Pencil className="w-4 h-4" /></Button>}
                        {extraActions && extraActions(row, helpers(row))}
                        {allow("delete") && <DeleteConfirm onConfirm={() => onDelete(row)} testid={`confirm-delete-${testid}-${row.id}`}>
                          <Button variant="ghost" size="icon" className="h-8 w-8 text-slate-500 hover:text-red-500" data-testid={`delete-${testid}-${row.id}`}><Trash2 className="w-4 h-4" /></Button>
                        </DeleteConfirm>}
                      </div>
                    )}
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
        fields={fields} initial={editing} onSubmit={onSubmit} options={options} testid={testid} entityCreators={entityCreators}
      />
      {detailRow && renderDetail && renderDetail(items.find((x) => x.id === detailRow.id) || detailRow, {
        close: () => setDetailRow(null), update,
        edit: allow("edit") ? (r) => { setDetailRow(null); openEdit(r); } : null,
      })}
    </div>
  );
}
