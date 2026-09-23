import { EntityManager, StatusBadge, useCollection } from "@/components/crm";

const CAT_LABEL = { staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario" };
const STATO_LABEL = { invitato: "Invitato", confermato: "Confermato", da_riconfermare: "Da riconfermare", rifiutato: "Rifiutato" };
const STATO_COLOR = { invitato: "blue", confermato: "green", da_riconfermare: "orange", rifiutato: "red" };

const columns = (persons, events) => [
  { key: "persona_id", label: "Persona", render: (r) => { const p = persons.find((x) => x.id === r.persona_id); return <span className="font-medium text-slate-800">{p ? `${p.nome} ${p.cognome || ""}` : "—"}</span>; } },
  { key: "evento_id", label: "Evento", render: (r) => events.find((e) => e.id === r.evento_id)?.nome || "—" },
  { key: "categoria", label: "Categoria", render: (r) => <StatusBadge color="tiffany">{CAT_LABEL[r.categoria] || r.categoria}</StatusBadge> },
  { key: "ruolo", label: "Ruolo" },
  { key: "turno", label: "Turno", render: (r) => <span className={r.turno_coperto === false ? "text-red-500 font-medium" : ""}>{r.turno || "—"}{r.turno_coperto === false && " (scoperto)"}</span> },
  { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO_COLOR[r.stato] || "gray"}>{STATO_LABEL[r.stato] || r.stato}</StatusBadge> },
];

export default function StaffVolunteers() {
  const { items: persons, loading: l1 } = useCollection("/persons");
  const { items: events, loading: l2 } = useCollection("/events");

  const fields = [
    { name: "persona_id", label: "Persona", required: true, type: "select", options: persons.map((p) => ({ value: p.id, label: `${p.nome} ${p.cognome || ""}`.trim() })) },
    { name: "evento_id", label: "Evento", required: true, type: "select", options: events.map((e) => ({ value: e.id, label: e.nome })) },
    { name: "categoria", label: "Categoria", type: "select", options: Object.keys(CAT_LABEL).map((v) => ({ value: v, label: CAT_LABEL[v] })) },
    { name: "ruolo", label: "Ruolo", type: "select", options: ["Coordinatore", "Hostess", "Tecnico", "Sicurezza", "Accoglienza", "Logistica"].map((v) => ({ value: v, label: v })) },
    { name: "stato", label: "Stato", type: "select", options: Object.keys(STATO_LABEL).map((v) => ({ value: v, label: STATO_LABEL[v] })) },
    { name: "turno", label: "Turno", placeholder: "15 Sett 09:00-18:00", full: true },
    { name: "turno_coperto", label: "Turno coperto", type: "select", options: [{ value: "true", label: "Sì" }, { value: "false", label: "No (scoperto)" }] },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];

  if (l1 || l2) return <div className="text-slate-400">Caricamento...</div>;

  return (
    <EntityManager
      title="Staff & Volontari" subtitle="Assegnazioni, ruoli e turni per evento"
      endpoint="/staff" fields={fields} columns={columns(persons, events)}
      entityLabel="assegnazione" testid="staff" searchKeys={["ruolo", "turno"]}
    />
  );
}
