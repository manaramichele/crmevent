import { EntityManager, StatusBadge } from "@/components/crm";

const STATO = { attivo: "green", pianificato: "tiffany", concluso: "gray", annullato: "red" };
const STATO_LABEL = { attivo: "Attivo", pianificato: "Pianificato", concluso: "Concluso", annullato: "Annullato" };

const fields = [
  { name: "nome", label: "Nome evento", required: true, full: true },
  { name: "edizione", label: "Edizione", placeholder: "2026" },
  { name: "tipologia", label: "Tipologia", type: "select", options: ["Fiera", "Congresso", "Concerto", "Festival", "Conferenza", "Workshop", "Gala"].map((v) => ({ value: v, label: v })) },
  { name: "data_inizio", label: "Data inizio", type: "date" },
  { name: "data_fine", label: "Data fine", type: "date" },
  { name: "localita", label: "Località / Venue" },
  { name: "indirizzo", label: "Indirizzo" },
  { name: "citta", label: "Città" },
  { name: "provincia", label: "Provincia" },
  { name: "regione", label: "Regione" },
  { name: "nazione", label: "Nazione" },
  { name: "organizzatore", label: "Organizzatore" },
  { name: "responsabile", label: "Responsabile evento" },
  { name: "sito_web", label: "Sito web" },
  { name: "email", label: "Email", type: "email" },
  { name: "telefono", label: "Telefono", type: "tel" },
  { name: "partecipanti_previsti", label: "Partecipanti previsti", type: "number" },
  { name: "budget", label: "Budget (€)", type: "number" },
  { name: "stato", label: "Stato", type: "select", options: Object.keys(STATO_LABEL).map((v) => ({ value: v, label: STATO_LABEL[v] })) },
  { name: "note", label: "Note", type: "textarea", full: true },
];

const columns = [
  { key: "nome", label: "Evento", render: (r) => <div><div className="font-medium text-slate-800">{r.nome}</div>{r.edizione && <div className="text-xs text-slate-400">Ed. {r.edizione}</div>}</div> },
  { key: "tipologia", label: "Tipologia" },
  { key: "citta", label: "Città" },
  { key: "data_inizio", label: "Inizio" },
  { key: "partecipanti_previsti", label: "Partecipanti", render: (r) => r.partecipanti_previsti?.toLocaleString("it-IT") || "—" },
  { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO[r.stato] || "gray"}>{STATO_LABEL[r.stato] || r.stato}</StatusBadge> },
];

export default function Events() {
  return (
    <EntityManager
      title="Eventi" subtitle="Gestione multi-evento e schede complete"
      endpoint="/events" fields={fields} columns={columns}
      entityLabel="evento" testid="event" searchKeys={["nome", "citta", "tipologia"]}
    />
  );
}
