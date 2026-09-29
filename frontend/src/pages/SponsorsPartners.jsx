import { useState } from "react";
import { toast } from "sonner";
import { useCollection, EntityDialog, PageHeader, PrimaryButton, StatusBadge, formatEUR, useSettings, toOptions } from "@/components/crm";
import { formatApiError } from "@/lib/api";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Plus, Pencil, Trash2 } from "lucide-react";
import api from "@/lib/api";

const FASI = ["prospect", "contattato", "proposta_inviata", "in_trattativa", "confermato", "perso"];
const FASE_LABEL = { prospect: "Prospect", contattato: "Contattato", proposta_inviata: "Proposta inviata", in_trattativa: "In trattativa", confermato: "Confermato", perso: "Perso" };
const FASE_ACCENT = { prospect: "border-t-slate-300", contattato: "border-t-sky-400", proposta_inviata: "border-t-amber-400", in_trattativa: "border-t-tiffany", confermato: "border-t-emerald-400", perso: "border-t-red-400" };
const TIPO_LABEL = { sponsor: "Sponsor", partner: "Partner", fornitore: "Fornitore", prospect: "Prospect" };

export default function SponsorsPartners() {
  const { items: deals, loading, create, update, remove, setItems } = useCollection("/deals");
  const { items: companies } = useCollection("/companies");
  const { items: events } = useCollection("/events");
  const { items: persons } = useCollection("/persons");
  const settings = useSettings();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const compName = (id) => companies.find((c) => c.id === id)?.nome || "—";
  const eventName = (id) => events.find((e) => e.id === id)?.nome || "";

  const fields = [
    { name: "azienda_id", label: "Azienda", required: true, type: "select", options: companies.map((c) => ({ value: c.id, label: c.nome })) },
    { name: "evento_id", label: "Evento", required: true, type: "select", options: events.map((e) => ({ value: e.id, label: e.nome })) },
    { name: "tipo", label: "Tipo", keepOrder: true, type: "select", options: Object.keys(TIPO_LABEL).map((v) => ({ value: v, label: TIPO_LABEL[v] })) },
    { name: "fase", label: "Fase pipeline", keepOrder: true, type: "select", options: FASI.map((v) => ({ value: v, label: FASE_LABEL[v] })) },
    { name: "valore", label: "Valore (€)", type: "number" },
    { name: "valore_confermato", label: "Valore confermato (€)", type: "number" },
    { name: "livello", label: "Livello sponsorship", keepOrder: true, type: "select", options: toOptions(settings?.livelli_sponsorship) },
    { name: "referente_id", label: "Referente", type: "select", options: persons.map((p) => ({ value: p.id, label: `${p.nome} ${p.cognome || ""}`.trim() })) },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];

  const onSubmit = async (form) => {
    if (editing) { await update(editing.id, form); toast.success("Trattativa aggiornata"); }
    else { await create(form); toast.success("Trattativa creata"); }
  };

  const changeFase = async (deal, fase) => {
    setItems((p) => p.map((d) => (d.id === deal.id ? { ...d, fase } : d)));
    try { await api.put(`/deals/${deal.id}`, { fase }); toast.success(`Spostato in "${FASE_LABEL[fase]}"`); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const onDelete = async (id) => {
    try { await remove(id); toast.success("Trattativa eliminata"); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const totale = deals.filter((d) => d.fase !== "perso").reduce((s, d) => s + Number(d.valore || 0), 0);
  const confermato = deals.filter((d) => d.fase === "confermato").reduce((s, d) => s + Number(d.valore_confermato || d.valore || 0), 0);

  return (
    <div className="animate-fade-up">
      <PageHeader
        title="Sponsor & Partner"
        subtitle="Pipeline commerciale per sponsor, partner e fornitori"
        action={<PrimaryButton onClick={() => { setEditing(null); setOpen(true); }} data-testid="add-deal-button"><Plus className="w-4 h-4 mr-1.5" />Nuova trattativa</PrimaryButton>}
      />

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-6">
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm"><div className="text-xs uppercase text-slate-500 font-medium">Trattative</div><div className="text-2xl font-bold font-display text-slate-900">{deals.length}</div></div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm"><div className="text-xs uppercase text-slate-500 font-medium">Valore pipeline</div><div className="text-2xl font-bold font-display text-slate-900">{formatEUR(totale)}</div></div>
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm"><div className="text-xs uppercase text-slate-500 font-medium">Confermato</div><div className="text-2xl font-bold font-display text-emerald-600">{formatEUR(confermato)}</div></div>
      </div>

      {loading ? <div className="text-slate-400">Caricamento...</div> : (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 overflow-x-auto pb-4">
          {FASI.map((fase) => {
            const col = deals.filter((d) => d.fase === fase);
            const val = col.reduce((s, d) => s + Number(d.valore || 0), 0);
            return (
              <div key={fase} className={`bg-slate-50/70 rounded-xl border border-slate-200 border-t-4 ${FASE_ACCENT[fase]} min-w-[240px]`} data-testid={`pipeline-col-${fase}`}>
                <div className="px-3 py-3 border-b border-slate-200">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-sm text-slate-700">{FASE_LABEL[fase]}</span>
                    <span className="text-xs font-bold text-slate-400">{col.length}</span>
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">{formatEUR(val)}</div>
                </div>
                <div className="p-2.5 space-y-2.5 min-h-[80px]">
                  {col.map((d) => (
                    <div key={d.id} className="bg-white rounded-lg border border-slate-200 shadow-sm p-3 hover:shadow-md transition-shadow" data-testid={`deal-card-${d.id}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-medium text-sm text-slate-800 leading-snug">{compName(d.azienda_id)}</div>
                        <div className="flex gap-0.5 shrink-0">
                          <Button variant="ghost" size="icon" className="h-6 w-6 text-slate-400 hover:text-tiffany-active" onClick={() => { setEditing(d); setOpen(true); }} data-testid={`edit-deal-${d.id}`}><Pencil className="w-3.5 h-3.5" /></Button>
                          <Button variant="ghost" size="icon" className="h-6 w-6 text-slate-400 hover:text-red-500" onClick={() => onDelete(d.id)} data-testid={`delete-deal-${d.id}`}><Trash2 className="w-3.5 h-3.5" /></Button>
                        </div>
                      </div>
                      <div className="mt-1.5 flex items-center gap-1.5">
                        <StatusBadge color="tiffany">{TIPO_LABEL[d.tipo] || d.tipo}</StatusBadge>
                        <span className="text-xs font-semibold text-slate-600">{formatEUR(d.valore)}</span>
                      </div>
                      {eventName(d.evento_id) && <div className="text-xs text-slate-400 mt-1.5 truncate">{eventName(d.evento_id)}</div>}
                      <div className="mt-2">
                        <Select value={d.fase} onValueChange={(v) => changeFase(d, v)}>
                          <SelectTrigger className="h-7 text-xs" data-testid={`deal-stage-${d.id}`}><SelectValue /></SelectTrigger>
                          <SelectContent>{FASI.map((f) => <SelectItem key={f} value={f} className="text-xs">{FASE_LABEL[f]}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <EntityDialog
        open={open} onOpenChange={setOpen}
        title={editing ? "Modifica trattativa" : "Nuova trattativa"}
        fields={fields} initial={editing} onSubmit={onSubmit} testid="deal"
      />
    </div>
  );
}
