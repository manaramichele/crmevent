import { EntityManager, useCollection } from "@/components/crm";

const columns = (companies) => [
  { key: "nome", label: "Nome", render: (r) => <span className="font-medium text-slate-800">{r.nome} {r.cognome}</span> },
  { key: "ruolo", label: "Ruolo" },
  { key: "email", label: "Email" },
  { key: "telefono", label: "Telefono" },
  { key: "azienda_id", label: "Azienda", render: (r) => companies.find((c) => c.id === r.azienda_id)?.nome || "—" },
];

export default function Persons() {
  const { items: companies, loading } = useCollection("/companies");
  const companyOpts = companies.map((c) => ({ value: c.id, label: c.nome }));

  const fields = [
    { name: "nome", label: "Nome", required: true },
    { name: "cognome", label: "Cognome" },
    { name: "ruolo", label: "Ruolo / Qualifica" },
    { name: "email", label: "Email", type: "email" },
    { name: "telefono", label: "Telefono", type: "tel" },
    { name: "azienda_id", label: "Azienda", type: "select", options: companyOpts },
    { name: "citta", label: "Città" },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];

  if (loading) return <div className="text-slate-400">Caricamento...</div>;

  return (
    <EntityManager
      title="Persone" subtitle="Contatti, referenti e collaboratori"
      endpoint="/persons" fields={fields} columns={columns(companies)}
      entityLabel="persona" testid="person" searchKeys={["nome", "cognome", "email", "ruolo"]}
    />
  );
}
