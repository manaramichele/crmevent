import { EntityManager, StatusBadge, useCollection } from "@/components/crm";
import api, { formatApiError } from "@/lib/api";
import { personOptions } from "@/lib/names";
import { toast } from "sonner";

const TIPO_LABEL = { chiamata: "Chiamata", email: "Email", meeting: "Meeting", task: "Task", generica: "Generica" };
const STATO_LABEL = { da_fare: "Da fare", completata: "Completata" };

const columns = (events, persons) => [
  { key: "titolo", label: "Attività", render: (r) => <span className="font-medium text-slate-800">{r.titolo}</span> },
  { key: "tipo", label: "Tipo", render: (r) => <StatusBadge color="blue">{TIPO_LABEL[r.tipo] || r.tipo}</StatusBadge> },
  { key: "evento_id", label: "Evento", render: (r) => events.find((e) => e.id === r.evento_id)?.nome || "—" },
  { key: "persona_id", label: "Referente", render: (r) => { const p = persons.find((x) => x.id === r.persona_id); return p ? `${p.cognome || ""} ${p.nome}`.trim() : "—"; } },
  { key: "responsabile_id", label: "Responsabile", render: (r) => { const p = persons.find((x) => x.id === r.responsabile_id); return p ? `${p.cognome || ""} ${p.nome}`.trim() : "—"; } },
  { key: "data", label: "Data" },
  { key: "stato", label: "Stato", render: (r) => <StatusBadge color={r.stato === "completata" ? "green" : "orange"}>{STATO_LABEL[r.stato] || r.stato}</StatusBadge> },
];

export default function Activities() {
  const { items: events, loading: l1 } = useCollection("/events");
  const { items: companies, loading: l2 } = useCollection("/companies");
  const { items: persons, loading: l3 } = useCollection("/persons");

  const fields = [
    { name: "titolo", label: "Titolo", required: true, full: true },
    { name: "tipo", label: "Tipo", keepOrder: true, type: "select", options: Object.keys(TIPO_LABEL).map((v) => ({ value: v, label: TIPO_LABEL[v] })) },
    { name: "data", label: "Data", type: "date" },
    { name: "ora", label: "Ora (facoltativa)", type: "time" },
    { name: "evento_id", label: "Evento", type: "select", options: events.map((e) => ({ value: e.id, label: e.nome })) },
    { name: "azienda_id", label: "Azienda", type: "select", options: companies.map((c) => ({ value: c.id, label: c.nome })) },
    { name: "persona_id", label: "Referente", type: "select", options: personOptions(persons) },
    { name: "responsabile_id", label: "Responsabile", type: "select", options: personOptions(persons) },
    { name: "stato", label: "Stato", keepOrder: true, type: "select", options: Object.keys(STATO_LABEL).map((v) => ({ value: v, label: STATO_LABEL[v] })) },
    { name: "note", label: "Note", type: "textarea", full: true },
    { name: "add_to_calendar", label: "Google Calendar", type: "gcalcheck", kind: "activity", full: true },
  ];

  const onSaved = async (rec, form) => {
    if (!form.add_to_calendar || !rec?.id) return;
    try {
      await api.post(`/activities/${rec.id}/calendar-sync`, { ora: form.ora || null });
      toast.success("Aggiunto a Google Calendar");
    } catch (e) {
      const d = e.response?.data?.detail || "";
      if (String(d).toLowerCase().includes("collegat")) toast.error("Collega prima Google Calendar per questo utente");
      else toast.error(formatApiError(d));
    }
  };

  if (l1 || l2 || l3) return <div className="text-slate-400">Caricamento...</div>;

  return (
    <EntityManager
      title="Attività" subtitle="Task, chiamate, email e meeting"
      endpoint="/activities" fields={fields} columns={columns(events, persons)}
      entityLabel="attività" testid="activity" section="attivita" defaultSort={{ key: "data", dir: "asc" }} searchKeys={["titolo", "tipo"]} onSaved={onSaved}
    />
  );
}
