import { KINDS, PERSON_TYPES, RES_STATES } from "./meta";

const opts = (rows, l = (x) => x.nome) => rows.map((x) => [x.id, l(x)]);
const phone = (d) => ({ k: "telefono", label: "Telefono", type: "tel", disabled: () => !d.perms.contacts, placeholder: d.perms.contacts ? "" : "Riservato" });

export const sectorFields = (d) => [
  { k: "nome", label: "Nome", required: true }, { k: "codice", label: "Codice" },
  { k: "km_inizio", label: "Km iniziale", type: "number" }, { k: "km_fine", label: "Km finale", type: "number" },
  { k: "responsabile", label: "Responsabile" }, phone(d), { k: "colore", label: "Colore", type: "color" }, { k: "note", label: "Note", type: "textarea" },
];

export const postFields = (d) => [
  { k: "nome", label: "Nome postazione", required: true }, { k: "codice", label: "Codice identificativo" },
  { k: "categoria", label: "Categoria", type: "select", required: true, options: d.settings.categories.map((c) => [c.key, c.label]) },
  { k: "sector_id", label: "Settore", type: "select", options: opts(d.sectors) }, { k: "km", label: "Chilometro", type: "number" },
  { k: "lat", label: "Latitudine", type: "number" }, { k: "lng", label: "Longitudine", type: "number" },
  { k: "responsabile", label: "Responsabile" }, phone(d),
  { k: "apertura", label: "Orario apertura", type: "time" }, { k: "chiusura", label: "Orario chiusura", type: "time" },
  { k: "previsti", label: "Operatori previsti", type: "number" }, { k: "presenti_manuali", label: "Operatori presenti non registrati", type: "number" },
  { k: "attiva", label: "Stato", type: "checkbox", hint: "Postazione attiva" }, { k: "note", label: "Note", type: "textarea" },
];

export const resourceFields = (d, shifts = [], personTypes = PERSON_TYPES) => [
  { k: "kind", label: "Tipo risorsa", type: "select", required: true, options: KINDS, disabled: (v) => !!v.id },
  { k: "tipologia", label: "Categoria mezzo", type: "select", required: true, options: d.vehicles.map((x) => [x.key, x.label]), show: (v) => v.kind === "mezzo" },
  { k: "tipologia", label: "Tipologia", type: "select", options: personTypes.map((x) => [x, x]), addKey: "tipi_risorsa_persona", show: (v) => v.kind === "persona" },
  { k: "codice", label: "Identificativo" }, { k: "nome", label: "Nome", disabled: (v) => !!v.persona_id },
  { k: "targa", label: "Targa", show: (v) => v.kind === "mezzo" }, { k: "equipaggio", label: "Equipaggio", show: (v) => v.kind !== "persona" },
  { k: "responsabile", label: "Responsabile" }, { ...phone(d), disabled: (v) => !d.perms.contacts || !!v.persona_id },
  { k: "post_id", label: "Postazione assegnata", type: "select", options: opts(d.posts) }, { k: "sector_id", label: "Settore", type: "select", options: opts(d.sectors) },
  shifts.length ? { k: "shift_id", label: "Turno (Staff / Volontari)", type: "select", options: shifts.map((s) => [s.id, [s.data, s.ora_inizio && `${s.ora_inizio}-${s.ora_fine || ""}`, s.luogo].filter(Boolean).join(" · ")]) } : { k: "turno", label: "Turno" },
  { k: "stato", label: "Stato operativo", type: "select", required: true, options: RES_STATES },
  { k: "caposquadra", label: "Ruolo", type: "checkbox", hint: "Caposquadra", show: (v) => v.kind === "persona" },
  { k: "autorizzazione_ente", label: "Ente esterno", type: "checkbox", hint: "Registrazione autorizzata dall'ente", show: (v) => v.kind === "mezzo" && d.external_vehicles.includes(v.tipologia), wide: true },
  { k: "lat", label: "Posizione fissa: latitudine", type: "number" }, { k: "lng", label: "Posizione fissa: longitudine", type: "number" },
  { k: "gps_device_id", label: "Dispositivo GPS (ID)", placeholder: "Da collegare nelle fasi successive" },
  { k: "gps_device_type", label: "Tipo dispositivo", type: "select", options: [["tracker", "Tracker GPS"], ["smartphone", "Smartphone"]] },
  { k: "note", label: "Note", type: "textarea" },
];

export const interventionFields = (d) => [
  { k: "titolo", label: "Titolo", required: true, wide: true }, { k: "priorita", label: "Priorità", type: "select", required: true, options: [["normale", "Normale"], ["urgente", "Urgente"]] },
  { k: "post_id", label: "Postazione", type: "select", options: opts(d.posts) }, { k: "km", label: "Chilometro", type: "number" },
  { k: "stato", label: "Stato", type: "select", required: true, options: [["aperto", "Aperto"], ["chiuso", "Chiuso"]] }, { k: "descrizione", label: "Descrizione", type: "textarea" },
];

export const toForm = (r) => ({ ...r, gps_device_id: r.gps?.device_id, gps_device_type: r.gps?.device_type });
