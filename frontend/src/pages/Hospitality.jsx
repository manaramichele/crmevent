import { useState, useEffect, useCallback, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { PageHeader, StatusBadge, useCollection, useSettings, formatDateRange } from "@/components/crm";
import SettingSelect from "@/components/SettingSelect";
import StructureSelect from "@/components/StructureSelect";
import MapsLink from "@/components/MapsLink";
import { useAuth } from "@/context/AuthContext";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  BedDouble, UtensilsCrossed, Users, Search, Plus, Pencil, Trash2, Coffee, Sun, Moon,
  Building2, CalendarDays, Wallet, AlertTriangle, UserPlus, X,
} from "lucide-react";

const CARICO = { organizzazione: "Organizzazione", persona: "Persona", sponsor: "Sponsor/Partner", altro: "Altro", da_definire: "Da definire" };
const TIPO_STRUTTURA = { hotel: "Hotel", bnb: "B&B", appartamento: "Appartamento", foresteria: "Foresteria", altro: "Altro" };
const TIPO_CAMERA = { singola: "Singola", doppia: "Doppia", tripla: "Tripla", multipla: "Multipla" };
const MEAL_SERVICE = { ristorante: "Ristorante", catering: "Catering", hotel: "Hotel", bar: "Bar", lunch_box: "Lunch box", panino: "Panino/pasto fornito", buono: "Buono pasto", libero: "Pasto libero", altro: "Altro" };
const MEAL_TYPE = { colazione: "Colazione", pranzo: "Pranzo", cena: "Cena" };
const MEAL_ICON = { colazione: Coffee, pranzo: Sun, cena: Moon };
const ESIGENZE = ["Vegetariano", "Vegano", "Senza glutine", "Senza lattosio", "Allergie", "Intolleranze", "Altro"];
const PAY_STATE = { pagato: "Pagato", non_pagato: "Non pagato" };
const STATO_COLOR = { completo: "green", parziale: "orange", da_definire: "red" };
const STATO_LABEL = { completo: "Completo", parziale: "Parziale", da_definire: "Da definire" };
const CAT_LABEL = { referente: "Referente", staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario", team: "Team" };

function eachDay(start, end) {
  if (!start) return [];
  const s = new Date(start); const e = end ? new Date(end) : s;
  if (isNaN(s)) return [];
  const out = []; const d = new Date(s);
  while (d <= e && out.length < 60) { out.push(d.toISOString().slice(0, 10)); d.setDate(d.getDate() + 1); }
  return out;
}
const fullName = (p) => `${p.nome || ""} ${p.cognome || ""}`.trim();

function Field({ label, children, full }) {
  return <div className={`space-y-1.5 ${full ? "sm:col-span-2" : ""}`}><Label className="text-xs">{label}</Label>{children}</div>;
}
function SelectField({ label, value, onChange, options, placeholder, testid, full }) {
  return (
    <Field label={label} full={full}>
      <Select value={value || ""} onValueChange={onChange}>
        <SelectTrigger data-testid={testid}><SelectValue placeholder={placeholder || "Seleziona"} /></SelectTrigger>
        <SelectContent>{Object.entries(options).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
      </Select>
    </Field>
  );
}

function EsigenzeEditor({ value, onChange, testid }) {
  const set = new Set(value || []);
  const toggle = (e) => { const n = new Set(set); n.has(e) ? n.delete(e) : n.add(e); onChange(Array.from(n)); };
  return (
    <div className="flex flex-wrap gap-1.5" data-testid={testid}>
      {ESIGENZE.map((e) => (
        <button key={e} type="button" onClick={() => toggle(e)} data-testid={`esig-${e.toLowerCase().replace(/[^a-z]/g, "-")}`}
          className={`px-2.5 py-1 rounded-full text-xs font-medium ring-1 ring-inset transition-colors ${set.has(e) ? "bg-tiffany-light text-tiffany-fg ring-tiffany-border" : "bg-white text-slate-500 ring-slate-200 hover:bg-slate-50"}`}>
          {e}
        </button>
      ))}
    </div>
  );
}

// Auto-compilazione dai dati master della Struttura (anagrafica riutilizzabile).
// NON crea/duplica strutture: legge i campi e riempie il form; se un dato manca resta vuoto.
function fillFromStructure(set, id, s, { isMeal } = {}) {
  set("struttura_id", id);
  if (!s) return;
  set("struttura_nome", s.nome || "");
  set("indirizzo", s.indirizzo || "");
  set("referente", s.referente || "");
  set("telefono", s.telefono_referente || s.telefono || "");
  set("struttura_maps_url", s.google_maps_url || "");
  if (isMeal) set("luogo", s.nome || "");
}
function StructureMissingNote({ form }) {
  if (!form.struttura_id) return null;
  const LBL = { indirizzo: "Indirizzo", referente: "Referente", telefono: "Telefono", struttura_maps_url: "Link Google Maps" };
  const missing = Object.keys(LBL).filter((k) => !form[k]);
  if (missing.length === 0) return null;
  return (
    <div className="sm:col-span-2 text-[11px] text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5" data-testid="struct-missing-note">
      Dato non presente nell'anagrafica struttura: {missing.map((k) => LBL[k]).join(", ")}. Puoi completarlo qui o aggiornare l'anagrafica in <strong>Strutture</strong>.
    </div>
  );
}

// ---- Lodging & Meal forms ----
function LodgingForm({ form, set, canCosts }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <Field label="Struttura (da anagrafica)" full>
        <StructureSelect value={form.struttura_id} onChange={(id, s) => fillFromStructure(set, id, s)} testid="lodging" />
      </Field>
      <SelectField label="Tipologia struttura" value={form.tipo_struttura} onChange={(v) => set("tipo_struttura", v)} options={TIPO_STRUTTURA} testid="lodging-tipo" />
      <Field label="Indirizzo" full><Input value={form.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value)} /></Field>
      <Field label="Check-in"><Input type="date" value={form.check_in || ""} onChange={(e) => set("check_in", e.target.value)} data-testid="lodging-checkin" /></Field>
      <Field label="Check-out"><Input type="date" value={form.check_out || ""} onChange={(e) => set("check_out", e.target.value)} data-testid="lodging-checkout" /></Field>
      <SelectField label="Tipologia camera" value={form.tipo_camera} onChange={(v) => set("tipo_camera", v)} options={TIPO_CAMERA} testid="lodging-camera" />
      <Field label="Compagno/i di camera"><Input value={form.compagni_camera || ""} onChange={(e) => set("compagni_camera", e.target.value)} /></Field>
      <Field label="Codice prenotazione"><Input value={form.codice_prenotazione || ""} onChange={(e) => set("codice_prenotazione", e.target.value)} /></Field>
      <SelectField label="A carico di" value={form.a_carico_di} onChange={(v) => set("a_carico_di", v)} options={CARICO} testid="lodging-carico" />
      <Field label="Referente struttura"><Input value={form.referente || ""} onChange={(e) => set("referente", e.target.value)} /></Field>
      <Field label="Telefono"><Input value={form.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></Field>
      {canCosts && <>
        <Field label="Costo (€)"><Input type="number" value={form.costo ?? ""} onChange={(e) => set("costo", e.target.value === "" ? null : Number(e.target.value))} data-testid="lodging-costo" /></Field>
        <SelectField label="Stato pagamento" value={form.stato_pagamento} onChange={(v) => set("stato_pagamento", v)} options={PAY_STATE} testid="lodging-pay" />
        <Field label="Note amministrative" full><Input value={form.note_amministrative || ""} onChange={(e) => set("note_amministrative", e.target.value)} /></Field>
      </>}
      <StructureMissingNote form={form} />
      <Field label="Note" full><Input value={form.note || ""} onChange={(e) => set("note", e.target.value)} /></Field>
    </div>
  );
}
function MealForm({ form, set, canCosts, lockType }) {
  const dataInizio = form.data_inizio || form.data || "";
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      <Field label="Data inizio"><Input type="date" value={dataInizio} onChange={(e) => set("data_inizio", e.target.value)} data-testid="meal-data-inizio" /></Field>
      <Field label="Data fine"><Input type="date" value={form.data_fine || dataInizio} min={dataInizio} onChange={(e) => set("data_fine", e.target.value)} data-testid="meal-data-fine" /></Field>
      <SelectField label="Tipo pasto" value={form.tipo_pasto} onChange={(v) => set("tipo_pasto", v)} options={MEAL_TYPE} testid="meal-tipo" />
      <SelectField label="Tipologia servizio" value={form.tipologia_servizio} onChange={(v) => set("tipologia_servizio", v)} options={MEAL_SERVICE} testid="meal-servizio" />
      <Field label="Struttura / Fornitore (da anagrafica)" full>
        <StructureSelect value={form.struttura_id} onChange={(id, s) => fillFromStructure(set, id, s, { isMeal: true })} testid="meal" />
      </Field>
      <Field label="Luogo"><Input value={form.luogo || ""} onChange={(e) => set("luogo", e.target.value)} /></Field>
      <Field label="Indirizzo"><Input value={form.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value)} /></Field>
      <Field label="Orario / fascia"><Input value={form.orario || ""} onChange={(e) => set("orario", e.target.value)} placeholder="es. 13:00 o 12:30–14:00" /></Field>
      <SelectField label="A carico di" value={form.a_carico_di} onChange={(v) => set("a_carico_di", v)} options={CARICO} testid="meal-carico" />
      <Field label="Referente"><Input value={form.referente || ""} onChange={(e) => set("referente", e.target.value)} /></Field>
      <Field label="Telefono"><Input value={form.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></Field>
      {canCosts && <Field label="Costo (€)"><Input type="number" value={form.costo ?? ""} onChange={(e) => set("costo", e.target.value === "" ? null : Number(e.target.value))} /></Field>}
      <StructureMissingNote form={form} />
      <Field label="Note operative" full><Input value={form.note || ""} onChange={(e) => set("note", e.target.value)} /></Field>
    </div>
  );
}

// ---- Person plan dialog ----
function PersonPlanDialog({ person, eventId, canCosts, open, onOpenChange, onChanged }) {
  const [tab, setTab] = useState("pernottamenti");
  const [editL, setEditL] = useState(null);
  const [editM, setEditM] = useState(null);
  const [esig, setEsig] = useState({ list: [], note: "", override: false });

  useEffect(() => {
    if (person) setEsig({ list: person.esigenze_alimentari || [], note: person.esigenze_note || "", override: person.esigenze_override });
  }, [person]);

  if (!person) return null;
  const lodgings = person.lodgings || [];
  const meals = person.meals || [];

  const saveLodging = async () => {
    try {
      const body = { ...editL, evento_id: eventId, persona_id: person.persona_id };
      if (editL.id) await api.put(`/lodgings/${editL.id}`, body); else await api.post("/lodgings", body);
      toast.success("Pernottamento salvato"); setEditL(null); onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const saveMeal = async () => {
    if (!editM.tipo_pasto) return toast.error("Seleziona il tipo di pasto");
    const di = editM.data_inizio || editM.data;
    const df = editM.data_fine || di;
    if (di && df && df < di) return toast.error("La data di fine non può precedere la data di inizio");
    try {
      const body = { ...editM, data_inizio: di || null, data_fine: df || null, evento_id: eventId, persona_id: person.persona_id };
      if (editM.id) await api.put(`/meals/${editM.id}`, body); else await api.post("/meals", body);
      toast.success("Pasto salvato"); setEditM(null); onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const delItem = async (type, id) => {
    try { await api.delete(`/${type}/${id}`); toast.success("Eliminato"); onChanged(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const saveEsig = async () => {
    try {
      await api.put(`/persons/${person.persona_id}`, { esigenze_alimentari: esig.list, esigenze_note: esig.note });
      if (person.presence_id && esig.override) await api.put(`/staff/${person.presence_id}`, { esigenze_alimentari: esig.list, esigenze_note: esig.note });
      toast.success("Esigenze alimentari salvate"); onChanged();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="person-plan-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">{fullName(person)}
            <StatusBadge color={STATO_COLOR[person.stato]}>{STATO_LABEL[person.stato]}</StatusBadge></DialogTitle>
          <DialogDescription>{CAT_LABEL[person.categoria] || person.categoria || "—"}{person.ruolo ? ` · ${person.ruolo}` : ""}{person.team_nome ? ` · ${person.team_nome}` : ""}</DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border border-slate-200 p-3 mb-3">
          <div className="flex items-center justify-between mb-2"><Label className="text-xs font-semibold">Esigenze alimentari</Label>
            <span className="text-[11px] text-slate-400">Salvate in anagrafica</span></div>
          <EsigenzeEditor value={esig.list} onChange={(l) => setEsig((s) => ({ ...s, list: l }))} testid="person-esigenze" />
          <Input className="mt-2" placeholder="Note (allergie/intolleranze specifiche)" value={esig.note} onChange={(e) => setEsig((s) => ({ ...s, note: e.target.value }))} data-testid="person-esigenze-note" />
          <Button size="sm" className="mt-2 bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={saveEsig} data-testid="save-esigenze">Salva esigenze</Button>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList><TabsTrigger value="pernottamenti" data-testid="tab-pernottamenti"><BedDouble className="w-4 h-4 mr-1" />Pernottamenti</TabsTrigger>
            <TabsTrigger value="pasti" data-testid="tab-pasti"><UtensilsCrossed className="w-4 h-4 mr-1" />Pasti</TabsTrigger></TabsList>

          <TabsContent value="pernottamenti" className="space-y-2 pt-2">
            {lodgings.length === 0 && !editL && <p className="text-sm text-slate-400">Nessun pernottamento.</p>}
            {lodgings.map((l) => (
              <div key={l.id} className="border border-slate-200 rounded-lg px-3 py-2.5 flex items-start justify-between" data-testid={`lodging-row-${l.id}`}>
                <div className="text-sm">
                  <div className="font-medium text-slate-800">{l.struttura_nome || "Struttura da definire"}{l.tipo_struttura ? ` · ${TIPO_STRUTTURA[l.tipo_struttura]}` : ""}</div>
                  <div className="text-xs text-slate-500">{[l.check_in && `in ${l.check_in}`, l.check_out && `out ${l.check_out}`, l.tipo_camera && TIPO_CAMERA[l.tipo_camera], l.compagni_camera].filter(Boolean).join(" · ") || "—"}</div>
                  {l.struttura?.indirizzo && <div className="text-xs text-slate-400">{[l.struttura.indirizzo, l.struttura.citta].filter(Boolean).join(", ")}</div>}
                  {l.struttura?.google_maps_url && <div className="text-xs mt-0.5"><MapsLink url={l.struttura.google_maps_url} testid={`lod-maps-${l.id}`} /></div>}
                  <div className="text-xs mt-0.5"><StatusBadge color={l.a_carico_di === "da_definire" || !l.a_carico_di ? "orange" : "tiffany"}>{CARICO[l.a_carico_di] || "A carico: da definire"}</StatusBadge>{canCosts && l.costo != null && <span className="ml-2 text-slate-500">€ {l.costo}{l.stato_pagamento ? ` · ${PAY_STATE[l.stato_pagamento]}` : ""}</span>}</div>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-400 hover:text-tiffany-active" onClick={() => setEditL(l)} data-testid={`edit-lodging-${l.id}`}><Pencil className="w-4 h-4" /></Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-400 hover:text-red-500" onClick={() => delItem("lodgings", l.id)} data-testid={`del-lodging-${l.id}`}><Trash2 className="w-4 h-4" /></Button>
                </div>
              </div>
            ))}
            {editL ? (
              <div className="border border-tiffany-border rounded-lg p-3 bg-tiffany-light/30">
                <LodgingForm form={editL} set={(k, v) => setEditL((f) => ({ ...f, [k]: v }))} canCosts={canCosts} />
                <div className="flex gap-2 mt-3"><Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={saveLodging} data-testid="save-lodging">Salva</Button><Button variant="outline" onClick={() => setEditL(null)}>Annulla</Button></div>
              </div>
            ) : <Button variant="outline" size="sm" onClick={() => setEditL({})} data-testid="add-lodging"><Plus className="w-4 h-4 mr-1" />Aggiungi pernottamento</Button>}
          </TabsContent>

          <TabsContent value="pasti" className="space-y-2 pt-2">
            {meals.length === 0 && !editM && <p className="text-sm text-slate-400">Nessun pasto.</p>}
            {meals.map((m) => { const I = MEAL_ICON[m.tipo_pasto] || UtensilsCrossed; return (
              <div key={m.id} className="border border-slate-200 rounded-lg px-3 py-2.5 flex items-start justify-between" data-testid={`meal-row-${m.id}`}>
                <div className="text-sm">
                  <div className="font-medium text-slate-800 flex items-center gap-1.5"><I className="w-4 h-4 text-tiffany-active" />{MEAL_TYPE[m.tipo_pasto] || "Pasto"}{(m.data_inizio || m.data) ? ` · ${formatDateRange(m.data_inizio || m.data, m.data_fine)}` : ""}{m.orario ? ` · ${m.orario}` : ""}</div>
                  <div className="text-xs text-slate-500">{[m.tipologia_servizio && MEAL_SERVICE[m.tipologia_servizio], m.struttura_nome, m.luogo].filter(Boolean).join(" · ") || "—"}</div>
                  {m.struttura?.google_maps_url && <div className="text-xs mt-0.5"><MapsLink url={m.struttura.google_maps_url} testid={`meal-maps-${m.id}`} /></div>}
                  <div className="text-xs mt-0.5"><StatusBadge color={m.a_carico_di === "da_definire" || !m.a_carico_di ? "orange" : "tiffany"}>{CARICO[m.a_carico_di] || "A carico: da definire"}</StatusBadge></div>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-400 hover:text-tiffany-active" onClick={() => setEditM(m)} data-testid={`edit-meal-${m.id}`}><Pencil className="w-4 h-4" /></Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 text-slate-400 hover:text-red-500" onClick={() => delItem("meals", m.id)} data-testid={`del-meal-${m.id}`}><Trash2 className="w-4 h-4" /></Button>
                </div>
              </div>
            ); })}
            {editM ? (
              <div className="border border-tiffany-border rounded-lg p-3 bg-tiffany-light/30">
                <MealForm form={editM} set={(k, v) => setEditM((f) => ({ ...f, [k]: v }))} canCosts={canCosts} />
                <div className="flex gap-2 mt-3"><Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={saveMeal} data-testid="save-meal">Salva</Button><Button variant="outline" onClick={() => setEditM(null)}>Annulla</Button></div>
              </div>
            ) : <Button variant="outline" size="sm" onClick={() => setEditM({})} data-testid="add-meal"><Plus className="w-4 h-4 mr-1" />Aggiungi pasto</Button>}
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

// ---- Bulk assign dialog ----
function BulkAssignDialog({ eventId, persons, teams, canCosts, open, onOpenChange, onDone }) {
  const [type, setType] = useState("meal");
  const [form, setForm] = useState({});
  const [sel, setSel] = useState(new Set());
  const [q, setQ] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => { if (open) { setForm({}); setSel(new Set()); setQ(""); setType("meal"); } }, [open]);

  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectByCat = (cat) => setSel(new Set(persons.filter((p) => p.categoria === cat).map((p) => p.persona_id)));
  const selectByTeam = (tid) => setSel(new Set(persons.filter((p) => p.team_id === tid).map((p) => p.persona_id)));
  const selectAll = () => setSel(new Set(persons.map((p) => p.persona_id)));
  const filtered = persons.filter((p) => !q || fullName(p).toLowerCase().includes(q.toLowerCase()));

  const submit = async () => {
    if (sel.size === 0) return toast.error("Seleziona almeno una persona");
    if (type === "meal" && !form.tipo_pasto) return toast.error("Seleziona il tipo di pasto");
    if (type === "meal") {
      const di = form.data_inizio || form.data; const df = form.data_fine || di;
      if (di && df && df < di) return toast.error("La data di fine non può precedere la data di inizio");
    }
    try {
      const ep = type === "meal" ? "/meals/bulk" : "/lodgings/bulk";
      const { data } = await api.post(ep, { evento_id: eventId, persona_ids: Array.from(sel), data: form });
      toast.success(`Servizio assegnato a ${data.count} persone`); onOpenChange(false); onDone();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="bulk-assign-dialog">
        <DialogHeader><DialogTitle className="font-display">Assegnazione multipla</DialogTitle>
          <DialogDescription>Crea un servizio e assegnalo a più persone. La configurazione individuale potrà essere modificata dopo.</DialogDescription></DialogHeader>
        <Tabs value={type} onValueChange={setType}>
          <TabsList><TabsTrigger value="meal" data-testid="bulk-tab-meal"><UtensilsCrossed className="w-4 h-4 mr-1" />Pasto</TabsTrigger>
            <TabsTrigger value="lodging" data-testid="bulk-tab-lodging"><BedDouble className="w-4 h-4 mr-1" />Pernottamento</TabsTrigger></TabsList>
          <TabsContent value="meal" className="pt-2"><MealForm form={form} set={set} canCosts={canCosts} /></TabsContent>
          <TabsContent value="lodging" className="pt-2"><LodgingForm form={form} set={set} canCosts={canCosts} /></TabsContent>
        </Tabs>

        <div className="mt-3 border-t border-slate-100 pt-3">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="text-xs font-semibold text-slate-600">Seleziona persone:</span>
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={selectAll} data-testid="bulk-select-all">Tutti</Button>
            {["staff", "volontario", "referente", "collaboratore", "team"].map((c) => (
              <Button key={c} size="sm" variant="outline" className="h-7 text-xs" onClick={() => selectByCat(c)} data-testid={`bulk-cat-${c}`}>{CAT_LABEL[c]}</Button>
            ))}
            {teams.map((t) => <Button key={t.id} size="sm" variant="outline" className="h-7 text-xs" onClick={() => selectByTeam(t.id)}>{t.nome}</Button>)}
            {sel.size > 0 && <Button size="sm" variant="ghost" className="h-7 text-xs text-slate-500" onClick={() => setSel(new Set())}><X className="w-3 h-3 mr-1" />Azzera ({sel.size})</Button>}
          </div>
          <div className="relative mb-2"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" /><Input className="pl-9 h-9" placeholder="Cerca persona..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="bulk-search" /></div>
          <div className="max-h-48 overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
            {filtered.map((p) => (
              <button key={p.persona_id} type="button" onClick={() => toggle(p.persona_id)} data-testid={`bulk-person-${p.persona_id}`}
                className={`w-full flex items-center justify-between px-3 py-2 text-left text-sm ${sel.has(p.persona_id) ? "bg-tiffany-light/50" : "hover:bg-slate-50"}`}>
                <span className="text-slate-800">{fullName(p)}<span className="text-slate-400 text-xs ml-2">{CAT_LABEL[p.categoria] || ""}</span></span>
                {sel.has(p.persona_id) && <StatusBadge color="tiffany">Selezionato</StatusBadge>}
              </button>
            ))}
          </div>
        </div>
        <DialogFooter><Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={submit} data-testid="bulk-assign-submit"><UserPlus className="w-4 h-4 mr-1.5" />Assegna a {sel.size} persone</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---- Summary ----
function Summary({ s }) {
  const cards = [
    ["Persone gestite", `${s.persone_gestite}/${s.persone_totali}`, Users, "tiffany"],
    ["Pernottamenti", s.pernottamenti, BedDouble, "tiffany"],
    ["Colazioni", s.colazioni, Coffee, "tiffany"],
    ["Pranzi", s.pranzi, Sun, "tiffany"],
    ["Cene", s.cene, Moon, "tiffany"],
    ["Servizi da definire", s.servizi_da_definire, Wallet, s.servizi_da_definire ? "orange" : "gray"],
    ["Senza sistemazione", s.senza_sistemazione, AlertTriangle, s.senza_sistemazione ? "red" : "green"],
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
      {cards.map(([label, val, Icon, color]) => (
        <div key={label} className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm" data-testid={`summary-${label.toLowerCase().replace(/[^a-z]/g, "-")}`}>
          <Icon className={`w-4 h-4 mb-1 ${color === "red" ? "text-red-500" : color === "orange" ? "text-amber-500" : "text-tiffany-active"}`} />
          <div className="text-xl font-bold text-slate-900">{val}</div>
          <div className="text-[11px] text-slate-500 leading-tight">{label}</div>
        </div>
      ))}
    </div>
  );
}

// ---- Structures manager (org anagraphic) ----
function StructuresManager({ open, onOpenChange }) {
  const [list, setList] = useState([]);
  const [ed, setEd] = useState(null);
  const settings = useSettings();
  const empty = { nome: "", tipologia: "", indirizzo: "", cap: "", citta: "", provincia: "", telefono: "", email: "", sito_web: "", referente: "", telefono_referente: "", google_maps_url: "", note: "" };
  const load = useCallback(() => api.get("/structures").then(({ data }) => setList(data)).catch(() => {}), []);
  useEffect(() => { if (open) load(); }, [open, load]);
  const set = (k, v) => setEd((f) => ({ ...f, [k]: v }));
  const save = async () => {
    if (!ed.nome?.trim()) return toast.error("Nome obbligatorio");
    try {
      if (ed.id) await api.put(`/structures/${ed.id}`, ed); else await api.post("/structures", ed);
      toast.success("Struttura salvata"); setEd(null); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const del = async (id) => { if (!window.confirm("Eliminare la struttura?")) return; try { await api.delete(`/structures/${id}`); load(); } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); } };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto" data-testid="structures-manager">
        <DialogHeader><DialogTitle className="font-display">Strutture</DialogTitle>
          <DialogDescription>Anagrafica riutilizzabile di hotel, ristoranti, catering ecc. per tutti gli eventi dell'organizzazione.</DialogDescription></DialogHeader>
        {ed ? (
          <div className="space-y-2">
            <Input placeholder="Nome*" value={ed.nome || ""} onChange={(e) => set("nome", e.target.value)} data-testid="struct-mgr-nome" />
            <div className="space-y-1"><Label className="text-[11px] text-slate-500">Tipologia</Label>
              <SettingSelect settingKey="tipologie_struttura" value={ed.tipologia} onChange={(v) => set("tipologia", v)} options={settings?.tipologie_struttura || ["Hotel", "B&B", "Residence", "Agriturismo", "Ristorante", "Pizzeria", "Bar", "Catering", "Mensa", "Altro"]} addLabel="Aggiungi tipologia" testid="struct-mgr-tipologia" /></div>
            <div className="grid grid-cols-2 gap-2">
              <Input placeholder="Indirizzo" value={ed.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value)} />
              <Input placeholder="CAP" value={ed.cap || ""} onChange={(e) => set("cap", e.target.value)} />
              <Input placeholder="Città" value={ed.citta || ""} onChange={(e) => set("citta", e.target.value)} />
              <Input placeholder="Provincia" value={ed.provincia || ""} onChange={(e) => set("provincia", e.target.value)} />
              <Input placeholder="Telefono" value={ed.telefono || ""} onChange={(e) => set("telefono", e.target.value)} />
              <Input placeholder="Email" value={ed.email || ""} onChange={(e) => set("email", e.target.value)} />
              <Input placeholder="Sito web" value={ed.sito_web || ""} onChange={(e) => set("sito_web", e.target.value)} />
              <Input placeholder="Referente" value={ed.referente || ""} onChange={(e) => set("referente", e.target.value)} />
              <Input placeholder="Tel. referente" value={ed.telefono_referente || ""} onChange={(e) => set("telefono_referente", e.target.value)} />
            </div>
            <Input placeholder="Link Google Maps" value={ed.google_maps_url || ""} onChange={(e) => set("google_maps_url", e.target.value)} data-testid="struct-mgr-maps" />
            <Input placeholder="Note" value={ed.note || ""} onChange={(e) => set("note", e.target.value)} />
            <div className="flex gap-2"><Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={save} data-testid="struct-mgr-save">Salva</Button><Button variant="outline" onClick={() => setEd(null)}>Annulla</Button></div>
          </div>
        ) : (
          <>
            <Button size="sm" className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold mb-2 w-fit" onClick={() => setEd({ ...empty })} data-testid="struct-mgr-add"><Plus className="w-4 h-4 mr-1" />Nuova struttura</Button>
            <div className="border border-slate-200 rounded-lg divide-y divide-slate-100 max-h-80 overflow-y-auto">
              {list.length === 0 ? <p className="p-4 text-sm text-slate-400">Nessuna struttura in anagrafica.</p> :
                list.map((s) => (
                  <div key={s.id} className="flex items-center justify-between px-3 py-2 text-sm" data-testid={`struct-mgr-row-${s.id}`}>
                    <div><div className="font-medium text-slate-800">{s.nome}{s.tipologia ? ` · ${s.tipologia}` : ""}</div>
                      <div className="text-xs text-slate-500">{[s.indirizzo, s.citta].filter(Boolean).join(", ")}{s.google_maps_url ? " · 📍 Maps" : ""}</div></div>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEd(s)} data-testid={`struct-mgr-edit-${s.id}`}><Pencil className="w-4 h-4" /></Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500" onClick={() => del(s.id)} data-testid={`struct-mgr-del-${s.id}`}><Trash2 className="w-4 h-4" /></Button>
                    </div>
                  </div>
                ))}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function Hospitality() {
  const { user } = useAuth();
  const canCosts = user?.role === "admin";
  const { items: events } = useCollection("/events");
  const { items: teams } = useCollection("/teams");
  const [eventId, setEventId] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [openPerson, setOpenPerson] = useState(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [structOpen, setStructOpen] = useState(false);
  const [q, setQ] = useState("");
  const [fRuolo, setFRuolo] = useState("");
  const [fStato, setFStato] = useState("");
  const [fEsig, setFEsig] = useState("");
  const [day, setDay] = useState("");

  useEffect(() => { if (!eventId && events.length) setEventId(events[0].id); }, [events, eventId]);

  const load = useCallback(async () => {
    if (!eventId) return;
    setLoading(true);
    try { const { data } = await api.get(`/events/${eventId}/hospitality`); setData(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  }, [eventId]);
  useEffect(() => { load(); }, [load]);

  const eventTeams = useMemo(() => teams.filter((t) => t.evento_id === eventId), [teams, eventId]);
  const days = useMemo(() => {
    const e = events.find((x) => x.id === eventId);
    const set = new Set(e ? eachDay(e.data_inizio, e.data_fine) : []);
    (data?.meals || []).forEach((m) => eachDay(m.data_inizio || m.data, m.data_fine || m.data_inizio || m.data).forEach((dd) => set.add(dd)));
    (data?.lodgings || []).forEach((l) => { l.check_in && set.add(l.check_in); });
    return Array.from(set).sort();
  }, [events, eventId, data]);
  useEffect(() => { if (days.length && !days.includes(day)) setDay(days[0]); }, [days, day]);

  const persons = useMemo(() => data?.persons || [], [data]);
  const filteredPersons = persons.filter((p) => {
    if (q && !fullName(p).toLowerCase().includes(q.toLowerCase())) return false;
    if (fRuolo && p.categoria !== fRuolo) return false;
    if (fStato && p.stato !== fStato) return false;
    if (fEsig && !(p.esigenze_alimentari || []).includes(fEsig)) return false;
    return true;
  });

  const selectedPerson = openPerson ? persons.find((p) => p.persona_id === openPerson) : null;

  // per struttura grouping
  const structures = useMemo(() => {
    if (!data) return [];
    const map = {};
    const add = (key, kind, rec, personId) => {
      if (!map[key]) map[key] = { key, lodging: 0, meals: {}, people: new Set(), esig: {} };
      map[key][kind === "lodging" ? "lodging" : "meal"] = (map[key][kind === "lodging" ? "lodging" : "meal"] || 0);
      if (kind === "lodging") map[key].lodging += 1; else map[key].meals[rec.tipo_pasto] = (map[key].meals[rec.tipo_pasto] || 0) + 1;
      map[key].people.add(personId);
    };
    data.lodgings.forEach((l) => add(l.struttura_nome || "Struttura da definire", "lodging", l, l.persona_id));
    data.meals.forEach((m) => add(m.struttura_nome || (m.tipologia_servizio ? MEAL_SERVICE[m.tipologia_servizio] : "Servizio da definire"), "meal", m, m.persona_id));
    // esigenze breakdown per structure
    const pById = Object.fromEntries(persons.map((p) => [p.persona_id, p]));
    Object.values(map).forEach((g) => { g.people.forEach((pid) => { (pById[pid]?.esigenze_alimentari || []).forEach((e) => { g.esig[e] = (g.esig[e] || 0) + 1; }); }); });
    return Object.values(map).sort((a, b) => a.key.localeCompare(b.key));
  }, [data, persons]);

  const dayMeals = (data?.meals || []).filter((m) => { const s = m.data_inizio || m.data; const e = m.data_fine || s; return s && s <= day && day <= e; });
  const dayLodgings = (data?.lodgings || []).filter((l) => (l.check_in && l.check_in <= day) && (!l.check_out || l.check_out > day));

  return (
    <div className="animate-fade-up">
      <PageHeader title="Ospitalità & Pasti" subtitle="Pernottamenti, colazioni, pranzi e cene per ogni persona dell'evento"
        action={<div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setStructOpen(true)} data-testid="open-structures"><Building2 className="w-4 h-4 mr-1.5" />Strutture</Button>
          <Select value={eventId} onValueChange={setEventId}><SelectTrigger className="w-52" data-testid="hosp-event-select"><SelectValue placeholder="Seleziona evento" /></SelectTrigger>
            <SelectContent>{events.map((e) => <SelectItem key={e.id} value={e.id}>{e.nome}</SelectItem>)}</SelectContent></Select>
          <Button className="bg-tiffany hover:bg-tiffany-hover text-slate-900 font-semibold" onClick={() => setBulkOpen(true)} disabled={!persons.length} data-testid="open-bulk-assign"><UserPlus className="w-4 h-4 mr-1.5" />Assegna a più persone</Button>
        </div>} />

      {!eventId ? <p className="text-slate-400">Crea o seleziona un evento.</p> :
        loading ? <p className="text-slate-400">Caricamento...</p> :
        !data ? null : persons.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500">
            Nessuna persona collegata a questo evento. Associa staff/volontari dalla sezione <strong>Anagrafiche</strong> per gestire ospitalità e pasti.
          </div>
        ) : (
        <>
          <Summary s={data.summary} />
          <Tabs defaultValue="persona">
            <TabsList className="mb-4 flex-wrap h-auto">
              <TabsTrigger value="persona" data-testid="view-persona"><Users className="w-4 h-4 mr-1" />Per persona</TabsTrigger>
              <TabsTrigger value="giorno" data-testid="view-giorno"><CalendarDays className="w-4 h-4 mr-1" />Per giorno</TabsTrigger>
              <TabsTrigger value="struttura" data-testid="view-struttura"><Building2 className="w-4 h-4 mr-1" />Per struttura/servizio</TabsTrigger>
            </TabsList>

            <TabsContent value="persona">
              <div className="flex flex-wrap gap-2 mb-4">
                <div className="relative w-full sm:w-64"><Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" /><Input className="pl-9" placeholder="Cerca persona..." value={q} onChange={(e) => setQ(e.target.value)} data-testid="hosp-search" /></div>
                <Select value={fRuolo || "all"} onValueChange={(v) => setFRuolo(v === "all" ? "" : v)}><SelectTrigger className="w-40" data-testid="filter-ruolo"><SelectValue placeholder="Ruolo" /></SelectTrigger><SelectContent><SelectItem value="all">Tutti i ruoli</SelectItem>{Object.entries(CAT_LABEL).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select>
                <Select value={fStato || "all"} onValueChange={(v) => setFStato(v === "all" ? "" : v)}><SelectTrigger className="w-40" data-testid="filter-stato"><SelectValue placeholder="Stato" /></SelectTrigger><SelectContent><SelectItem value="all">Tutti gli stati</SelectItem>{Object.entries(STATO_LABEL).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent></Select>
                <Select value={fEsig || "all"} onValueChange={(v) => setFEsig(v === "all" ? "" : v)}><SelectTrigger className="w-40" data-testid="filter-esig"><SelectValue placeholder="Esigenze" /></SelectTrigger><SelectContent><SelectItem value="all">Tutte le esigenze</SelectItem>{ESIGENZE.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}</SelectContent></Select>
              </div>
              <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-slate-200 bg-slate-50/70">{["Persona", "Ruolo", "Pernott.", "Col.", "Pranzi", "Cene", "Esigenze", "Stato"].map((h) => <th key={h} className="text-left font-semibold text-slate-600 px-4 py-3 whitespace-nowrap">{h}</th>)}</tr></thead>
                  <tbody>
                    {filteredPersons.length === 0 ? <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">Nessuna persona.</td></tr> :
                      filteredPersons.map((p) => (
                        <tr key={p.persona_id} className="border-b border-slate-100 hover:bg-slate-50/80 cursor-pointer" onClick={() => setOpenPerson(p.persona_id)} data-testid={`hosp-person-${p.persona_id}`}>
                          <td className="px-4 py-3 font-medium text-slate-800 whitespace-nowrap">{fullName(p)}</td>
                          <td className="px-4 py-3 text-slate-600">{CAT_LABEL[p.categoria] || p.ruolo || "—"}</td>
                          <td className="px-4 py-3">{p.lodgings.length || "—"}</td>
                          <td className="px-4 py-3">{p.meals.filter((m) => m.tipo_pasto === "colazione").length || "—"}</td>
                          <td className="px-4 py-3">{p.meals.filter((m) => m.tipo_pasto === "pranzo").length || "—"}</td>
                          <td className="px-4 py-3">{p.meals.filter((m) => m.tipo_pasto === "cena").length || "—"}</td>
                          <td className="px-4 py-3"><span className="flex flex-wrap gap-1">{(p.esigenze_alimentari || []).length ? p.esigenze_alimentari.map((e) => <StatusBadge key={e} color="blue">{e}</StatusBadge>) : "—"}</span></td>
                          <td className="px-4 py-3"><StatusBadge color={STATO_COLOR[p.stato]}>{STATO_LABEL[p.stato]}</StatusBadge></td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </TabsContent>

            <TabsContent value="giorno">
              {days.length === 0 ? (
                <div className="bg-white border border-slate-200 rounded-xl p-8 text-center text-slate-500" data-testid="giorno-empty">
                  Nessuna data disponibile. Imposta le date dell'evento oppure aggiungi pernottamenti/pasti con una data.
                </div>
              ) : (
              <>
              <div className="flex items-center gap-2 mb-4">
                <Label className="text-xs text-slate-500">Giorno</Label>
                <Select value={day} onValueChange={setDay}><SelectTrigger className="w-48" data-testid="day-select"><SelectValue placeholder="Seleziona giorno" /></SelectTrigger><SelectContent>{days.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent></Select>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {[["Pernottamenti", dayLodgings, BedDouble], ...Object.keys(MEAL_TYPE).map((t) => [MEAL_TYPE[t], dayMeals.filter((m) => m.tipo_pasto === t), MEAL_ICON[t]])].map(([label, list, Icon], i) => {
                  const pName = (id) => { const p = persons.find((x) => x.persona_id === id); return p ? fullName(p) : "—"; };
                  return (
                    <div key={i} className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={`day-col-${i}`}>
                      <div className="flex items-center justify-between mb-3"><div className="flex items-center gap-1.5 font-semibold text-slate-800"><Icon className="w-4 h-4 text-tiffany-active" />{label}</div><StatusBadge color="tiffany">{list.length}</StatusBadge></div>
                      <div className="space-y-1.5">{list.length === 0 ? <p className="text-xs text-slate-400">Nessuno</p> : list.map((x) => (
                        <div key={x.id} className="text-sm text-slate-700 border border-slate-100 rounded-lg px-2.5 py-1.5">
                          <div className="font-medium">{pName(x.persona_id)}</div>
                          <div className="text-xs text-slate-500">{[x.struttura_nome, x.orario, x.tipologia_servizio && MEAL_SERVICE[x.tipologia_servizio], x.tipo_struttura && TIPO_STRUTTURA[x.tipo_struttura]].filter(Boolean).join(" · ") || "—"}</div>
                        </div>
                      ))}</div>
                    </div>
                  );
                })}
              </div>
              </>
              )}
            </TabsContent>

            <TabsContent value="struttura">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {structures.length === 0 ? <p className="text-slate-400">Nessun servizio configurato.</p> :
                  structures.map((g) => (
                    <div key={g.key} className="bg-white border border-slate-200 rounded-xl shadow-sm p-4" data-testid={`struct-${g.key.toLowerCase().replace(/[^a-z0-9]/g, "-")}`}>
                      <div className="flex items-center justify-between mb-2"><div className="font-semibold text-slate-800 flex items-center gap-1.5"><Building2 className="w-4 h-4 text-tiffany-active" />{g.key}</div><StatusBadge color="tiffany">{g.people.size} persone</StatusBadge></div>
                      <div className="flex flex-wrap gap-1.5 text-xs">
                        {g.lodging ? <StatusBadge color="gray">{g.lodging} pernott.</StatusBadge> : null}
                        {Object.entries(g.meals).map(([t, n]) => <StatusBadge key={t} color="gray">{n} {MEAL_TYPE[t] || t}</StatusBadge>)}
                      </div>
                      {Object.keys(g.esig).length > 0 && (
                        <div className="mt-2 pt-2 border-t border-slate-100 flex flex-wrap gap-1.5">
                          <span className="text-[11px] text-slate-400 w-full">Esigenze alimentari:</span>
                          {Object.entries(g.esig).map(([e, n]) => <StatusBadge key={e} color="blue">{n} {e}</StatusBadge>)}
                        </div>
                      )}
                    </div>
                  ))}
              </div>
            </TabsContent>
          </Tabs>
        </>
      )}

      {selectedPerson && <PersonPlanDialog person={selectedPerson} eventId={eventId} canCosts={canCosts} open={!!openPerson} onOpenChange={(o) => !o && setOpenPerson(null)} onChanged={load} />}
      <BulkAssignDialog eventId={eventId} persons={persons} teams={eventTeams} canCosts={canCosts} open={bulkOpen} onOpenChange={setBulkOpen} onDone={load} />
      <StructuresManager open={structOpen} onOpenChange={setStructOpen} />
    </div>
  );
}
