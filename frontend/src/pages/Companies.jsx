import { EntityManager, StatusBadge } from "@/components/crm";

const TIPO_LABEL = { azienda: "Azienda", prospect: "Prospect", fornitore: "Fornitore" };
const TIPO_COLOR = { azienda: "tiffany", prospect: "orange", fornitore: "blue" };

const fields = [
  { name: "nome", label: "Ragione sociale", required: true, full: true },
  { name: "settore", label: "Settore", type: "select", options: ["Tecnologia", "Food & Beverage", "Moda", "Automotive", "Finanza", "Media", "No Profit"].map((v) => ({ value: v, label: v })) },
  { name: "tipo", label: "Tipo", type: "select", options: Object.keys(TIPO_LABEL).map((v) => ({ value: v, label: TIPO_LABEL[v] })) },
  { name: "partita_iva", label: "Partita IVA" },
  { name: "sito_web", label: "Sito web" },
  { name: "email", label: "Email", type: "email" },
  { name: "telefono", label: "Telefono", type: "tel" },
  { name: "citta", label: "Città" },
  { name: "provincia", label: "Provincia" },
  { name: "regione", label: "Regione" },
  { name: "nazione", label: "Nazione" },
  { name: "note", label: "Note", type: "textarea", full: true },
];

const columns = [
  { key: "nome", label: "Azienda", render: (r) => <span className="font-medium text-slate-800">{r.nome}</span> },
  { key: "settore", label: "Settore" },
  { key: "citta", label: "Città" },
  { key: "email", label: "Email" },
  { key: "tipo", label: "Tipo", render: (r) => <StatusBadge color={TIPO_COLOR[r.tipo] || "gray"}>{TIPO_LABEL[r.tipo] || r.tipo}</StatusBadge> },
];

export default function Companies() {
  return (
    <EntityManager
      title="Aziende" subtitle="Anagrafica aziende, prospect e fornitori"
      endpoint="/companies" fields={fields} columns={columns}
      entityLabel="azienda" testid="company" searchKeys={["nome", "settore", "citta"]}
    />
  );
}
