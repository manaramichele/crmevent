import { EntityManager, StatusBadge, useCollection } from "@/components/crm";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const PRIO_LABEL = { alta: "Alta", media: "Media", bassa: "Bassa" };
const PRIO_COLOR = { alta: "red", media: "orange", bassa: "gray" };

function scadColor(r) {
  if (r.stato === "completato") return "green";
  const today = new Date().toISOString().slice(0, 10);
  const s = (r.scadenza || "").slice(0, 10);
  if (s && s < today) return "red";
  if (s === today) return "orange";
  return "tiffany";
}

const columns = (events, companies) => [
  { key: "titolo", label: "Follow-up", render: (r) => <span className="font-medium text-slate-800">{r.titolo}</span> },
  { key: "azienda_id", label: "Azienda", render: (r) => companies.find((c) => c.id === r.azienda_id)?.nome || "—" },
  { key: "evento_id", label: "Evento", render: (r) => events.find((e) => e.id === r.evento_id)?.nome || "—" },
  { key: "scadenza", label: "Scadenza", render: (r) => <StatusBadge color={scadColor(r)}>{r.scadenza || "—"}</StatusBadge> },
  { key: "priorita", label: "Priorità", render: (r) => <StatusBadge color={PRIO_COLOR[r.priorita] || "gray"}>{PRIO_LABEL[r.priorita] || r.priorita}</StatusBadge> },
  { key: "stato", label: "Stato", render: (r) => <StatusBadge color={r.stato === "completato" ? "green" : "blue"}>{r.stato === "completato" ? "Completato" : "Aperto"}</StatusBadge> },
];

export default function Followups() {
  const { items: events, loading: l1 } = useCollection("/events");
  const { items: companies, loading: l2 } = useCollection("/companies");
  const { items: persons, loading: l3 } = useCollection("/persons");

  const fields = [
    { name: "titolo", label: "Titolo", required: true, full: true },
    { name: "scadenza", label: "Scadenza", type: "date" },
    { name: "ora", label: "Ora (facoltativa)", type: "time" },
    { name: "priorita", label: "Priorità", keepOrder: true, type: "select", options: Object.keys(PRIO_LABEL).map((v) => ({ value: v, label: PRIO_LABEL[v] })) },
    { name: "stato", label: "Stato", keepOrder: true, type: "select", options: [{ value: "aperto", label: "Aperto" }, { value: "completato", label: "Completato" }] },
    { name: "evento_id", label: "Evento", type: "select", options: events.map((e) => ({ value: e.id, label: e.nome })) },
    { name: "azienda_id", label: "Azienda", type: "select", options: companies.map((c) => ({ value: c.id, label: c.nome })) },
    { name: "persona_id", label: "Referente", type: "select", options: persons.map((p) => ({ value: p.id, label: `${p.nome} ${p.cognome || ""}`.trim() })) },
    { name: "note", label: "Note", type: "textarea", full: true },
    { name: "add_to_calendar", label: "Google Calendar", type: "gcalcheck", kind: "followup", full: true },
  ];

  const onSaved = async (rec, form) => {
    if (!form.add_to_calendar || !rec?.id) return;
    try {
      await api.post(`/followups/${rec.id}/calendar-sync`, { ora: form.ora || null });
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
      title="Follow-up" subtitle="Scadenze e promemoria commerciali"
      endpoint="/followups" fields={fields} columns={columns(events, companies)}
      entityLabel="follow-up" testid="followup" section="followup" defaultSort={{ key: "scadenza", dir: "asc" }} searchKeys={["titolo"]} onSaved={onSaved}
    />
  );
}
