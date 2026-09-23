import { EntityManager, StatusBadge, useCollection, useSettings, toOptions } from "@/components/crm";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const CAT = { staff: "Staff", collaboratore: "Collaboratore", volontario: "Volontario" };
const STATO = { da_contattare: "Da contattare", disponibilita_richiesta: "Disponibilità richiesta", disponibile: "Disponibile",
  da_riconfermare: "Da riconfermare", confermato: "Confermato", non_disponibile: "Non disponibile", rinunciato: "Rinunciato" };
const STATO_COLOR = { confermato: "green", disponibile: "green", da_riconfermare: "orange", disponibilita_richiesta: "blue",
  da_contattare: "gray", non_disponibile: "red", rinunciato: "red" };

export default function StaffVolunteers() {
  const settings = useSettings();
  const { items: persons, loading: l1 } = useCollection("/persons");
  const { items: events, loading: l2 } = useCollection("/events");
  const { items: teams, loading: l3 } = useCollection("/teams");
  if (l1 || l2 || l3 || !settings) return <div className="text-slate-400">Caricamento...</div>;

  const personOpts = persons.map((p) => ({ value: p.id, label: `${p.nome} ${p.cognome || ""}`.trim() }));
  const eventOpts = events.map((e) => ({ value: e.id, label: e.nome }));
  const teamOpts = teams.map((t) => ({ value: t.id, label: t.nome }));
  const areaOpts = toOptions(settings.aree_operative);
  const ruoloOpts = toOptions(settings.ruoli_staff);
  const pName = (id) => { const p = persons.find((x) => x.id === id); return p ? `${p.nome} ${p.cognome || ""}`.trim() : "—"; };
  const eName = (id) => events.find((e) => e.id === id)?.nome || "—";
  const tName = (id) => teams.find((t) => t.id === id)?.nome || "—";

  const presenceFields = [
    { name: "persona_id", label: "Persona", required: true, type: "select", options: personOpts },
    { name: "evento_id", label: "Evento", required: true, type: "select", options: eventOpts },
    { name: "categoria", label: "Categoria", type: "select", options: Object.keys(CAT).map((v) => ({ value: v, label: CAT[v] })) },
    { name: "stato", label: "Stato", type: "select", options: Object.keys(STATO).map((v) => ({ value: v, label: STATO[v] })) },
    { name: "area", label: "Area", type: "select", options: areaOpts },
    { name: "ruolo", label: "Ruolo", type: "select", options: ruoloOpts },
    { name: "team_id", label: "Team", type: "select", options: teamOpts },
    { name: "responsabile", label: "Responsabile" },
    { name: "data_arrivo", label: "Data arrivo", type: "date" },
    { name: "ora_arrivo", label: "Ora arrivo", type: "time" },
    { name: "data_partenza", label: "Data partenza", type: "date" },
    { name: "ora_partenza", label: "Ora partenza", type: "time" },
    { name: "punto_ritrovo", label: "Punto di ritrovo" },
    { name: "luogo_operativo", label: "Luogo operativo" },
    { name: "note_operative", label: "Note operative", type: "textarea", full: true },
  ];
  const presenceCols = [
    { key: "persona_id", label: "Persona", render: (r) => <span className="font-medium text-slate-800">{pName(r.persona_id)}</span> },
    { key: "evento_id", label: "Evento", render: (r) => eName(r.evento_id) },
    { key: "categoria", label: "Categoria", render: (r) => <StatusBadge color="tiffany">{CAT[r.categoria] || r.categoria}</StatusBadge> },
    { key: "ruolo", label: "Ruolo" },
    { key: "area", label: "Area" },
    { key: "team_id", label: "Team", render: (r) => r.team_id ? tName(r.team_id) : "—" },
    { key: "stato", label: "Stato", render: (r) => <StatusBadge color={STATO_COLOR[r.stato] || "gray"}>{STATO[r.stato] || r.stato}</StatusBadge> },
  ];
  const presenceFilters = [
    { name: "evento_id", label: "Evento", options: eventOpts },
    { name: "categoria", label: "Categoria", options: Object.keys(CAT).map((v) => ({ value: v, label: CAT[v] })) },
    { name: "stato", label: "Stato", options: Object.keys(STATO).map((v) => ({ value: v, label: STATO[v] })) },
    { name: "area", label: "Area", options: areaOpts },
    { name: "team_id", label: "Team", options: teamOpts },
  ];

  const teamFields = [
    { name: "nome", label: "Nome team", required: true, full: true },
    { name: "evento_id", label: "Evento", required: true, type: "select", options: eventOpts },
    { name: "area", label: "Area", type: "select", options: areaOpts },
    { name: "responsabile_id", label: "Team Leader", type: "select", options: personOpts },
    { name: "luogo_operativo", label: "Luogo operativo" },
    { name: "punto_ritrovo", label: "Punto di ritrovo" },
    { name: "descrizione", label: "Descrizione", type: "textarea", full: true },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const teamCols = [
    { key: "nome", label: "Team", render: (r) => <span className="font-medium text-slate-800">{r.nome}</span> },
    { key: "evento_id", label: "Evento", render: (r) => eName(r.evento_id) },
    { key: "area", label: "Area" },
    { key: "responsabile_id", label: "Team Leader", render: (r) => r.responsabile_id ? pName(r.responsabile_id) : <StatusBadge color="orange">Da assegnare</StatusBadge> },
    { key: "luogo_operativo", label: "Luogo" },
  ];

  const shiftFields = [
    { name: "evento_id", label: "Evento", required: true, type: "select", options: eventOpts },
    { name: "persona_id", label: "Persona (vuoto = scoperto)", type: "select", options: personOpts },
    { name: "data", label: "Data", type: "date" },
    { name: "ora_inizio", label: "Ora inizio", type: "time" },
    { name: "ora_fine", label: "Ora fine", type: "time" },
    { name: "area", label: "Area", type: "select", options: areaOpts },
    { name: "ruolo", label: "Ruolo", type: "select", options: ruoloOpts },
    { name: "team_id", label: "Team", type: "select", options: teamOpts },
    { name: "luogo", label: "Luogo" },
    { name: "punto_ritrovo", label: "Punto di ritrovo" },
    { name: "responsabile", label: "Responsabile" },
    { name: "note", label: "Note", type: "textarea", full: true },
  ];
  const shiftCols = [
    { key: "data", label: "Data", render: (r) => <span className="font-medium text-slate-800">{r.data}</span> },
    { key: "ora", label: "Orario", render: (r) => `${r.ora_inizio || ""}–${r.ora_fine || ""}` },
    { key: "persona_id", label: "Persona", render: (r) => r.persona_id ? pName(r.persona_id) : <StatusBadge color="red">Scoperto</StatusBadge> },
    { key: "area", label: "Area" },
    { key: "ruolo", label: "Ruolo" },
    { key: "team_id", label: "Team", render: (r) => r.team_id ? tName(r.team_id) : "—" },
  ];
  const shiftFilters = [
    { name: "evento_id", label: "Evento", options: eventOpts },
    { name: "area", label: "Area", options: areaOpts },
    { name: "team_id", label: "Team", options: teamOpts },
  ];

  return (
    <div className="animate-fade-up">
      <Tabs defaultValue="presenze">
        <TabsList className="mb-4">
          <TabsTrigger value="presenze" data-testid="tab-presenze">Presenze</TabsTrigger>
          <TabsTrigger value="team" data-testid="tab-team">Team</TabsTrigger>
          <TabsTrigger value="turni" data-testid="tab-turni">Turni</TabsTrigger>
        </TabsList>
        <TabsContent value="presenze">
          <EntityManager title="Staff & Volontari" subtitle="Presenze per evento: ruoli, aree, team, periodo e stato" endpoint="/staff"
            fields={presenceFields} columns={presenceCols} entityLabel="presenza" testid="staff" searchKeys={["ruolo", "area", "responsabile"]} filters={presenceFilters} />
        </TabsContent>
        <TabsContent value="team">
          <EntityManager title="Team" subtitle="Squadre operative per evento con Team Leader" endpoint="/teams"
            fields={teamFields} columns={teamCols} entityLabel="team" testid="team" searchKeys={["nome", "area"]} filters={[{ name: "evento_id", label: "Evento", options: eventOpts }]} />
        </TabsContent>
        <TabsContent value="turni">
          <EntityManager title="Turni" subtitle="Turni operativi; lascia la persona vuota per un turno scoperto" endpoint="/shifts"
            fields={shiftFields} columns={shiftCols} entityLabel="turno" testid="shift" searchKeys={["ruolo", "area", "luogo"]} filters={shiftFilters} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
