import { EntityManager, StatusBadge } from "@/components/crm";

const STATO = {
  nuovo: "blue", da_contattare: "orange", contattato: "tiffany", demo_fissata: "tiffany",
  interessato: "green", cliente: "green", non_interessato: "red",
};
const STATO_LABEL = {
  nuovo: "Nuovo", da_contattare: "Da contattare", contattato: "Contattato", demo_fissata: "Demo fissata",
  interessato: "Interessato", cliente: "Cliente", non_interessato: "Non interessato",
};

const fields = [
  { name: "stato", label: "Stato", type: "select", options: Object.keys(STATO_LABEL).map((v) => ({ value: v, label: STATO_LABEL[v] })) },
  { name: "note", label: "Note", type: "textarea", full: true },
];

const columns = [
  { key: "nome", label: "Nome", render: (r) => <span className="font-medium text-slate-800">{r.nome} {r.cognome || ""}</span> },
  { key: "organizzazione", label: "Organizzazione" },
  { key: "email", label: "Email" },
  { key: "telefono", label: "Telefono" },
  { key: "tipologia_eventi", label: "Tipologia" },
  { key: "created_at", label: "Data", render: (r) => (r.created_at || "").slice(0, 10) },
  { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO[r.stato] || "gray"}>{STATO_LABEL[r.stato] || r.stato}</StatusBadge> },
];

export default function Leads() {
  return (
    <EntityManager
      title="Lead" subtitle="Richieste demo e pipeline commerciale di crmevent"
      endpoint="/leads" fields={fields} columns={columns}
      entityLabel="lead" testid="lead" searchKeys={["nome", "cognome", "organizzazione", "email"]}
      filters={[{ name: "stato", label: "Stato", options: Object.keys(STATO_LABEL).map((v) => ({ value: v, label: STATO_LABEL[v] })) }]}
    />
  );
}
