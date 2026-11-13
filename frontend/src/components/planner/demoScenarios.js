// Eventi dimostrativi della demo pubblica: solo dati inventati. Per aggiungere uno scenario: nuova voce qui + id in backend/planner_demo.py SCENARIOS.
const L = (id, nome, colore, ordine) => ({ id, nome, colore, visibile: true, bloccato: false, ordine });
const LAYERS = [L("percorsi", "Percorsi", "#E11D48", 0), L("partenza", "Partenza e arrivo", "#0ABAB5", 1), L("strutture", "Strutture", "#2563EB", 2),
  L("ristori", "Ristori", "#F59E0B", 3), L("sicurezza", "Sicurezza", "#DC2626", 4), L("viabilita", "Viabilità", "#64748B", 5),
  L("staff", "Staff e volontari", "#16A34A", 6), L("sponsor", "Sponsor", "#9333EA", 7), L("aree", "Aree operative", "#0F766E", 8)];

let n = 0;
const P = (props) => ({ id: `demo${++n}`, quantita: 1, ...props });
const pt = (c, props) => ({ type: "Feature", geometry: { type: "Point", coordinates: c }, properties: P({ tipo: "point", ...props }) });
const box = (c, w, l, rot, props) => ({ type: "Feature", geometry: null, properties: P({ tipo: "box", center: c, larghezza: w, lunghezza: l, rotazione: rot, ...props }) });
const line = (cs, props) => ({ type: "Feature", geometry: { type: "LineString", coordinates: cs }, properties: P({ tipo: "line", ...props }) });
const poly = (cs, props) => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [[...cs, cs[0]]] }, properties: P({ tipo: "polygon", ...props }) });

const ROUTE = [[9.1729, 45.4754], [9.1712, 45.4741], [9.1703, 45.4726], [9.1718, 45.4711], [9.1741, 45.4700], [9.1768, 45.4693], [9.1792, 45.4699],
  [9.1806, 45.4714], [9.1802, 45.4731], [9.1785, 45.4746], [9.1760, 45.4757], [9.1740, 45.4759], [9.1729, 45.4754]];

const running = {
  id: "running", nome: "Corsa del Parco 10K (evento demo)", center: [9.1755, 45.4728], zoom: 15.4, bounds: [[9.13, 45.45], [9.22, 45.50]],
  layers: LAYERS,
  features: [
    line(ROUTE, { nome: "Percorso gara – giro da ripetere", layer_id: "percorsi", colore: "#E11D48", categoria: "Percorsi",
      collegamenti: [{ area: "Percorsi", testo: "tracciato GPX dell'evento, condiviso con staff e volontari" }] }),
    box([9.1730, 45.4752], 12, 1, 35, { nome: "Arco partenza/arrivo", layer_id: "partenza", colore: "#E11D48", categoria: "Strutture",
      collegamenti: [{ area: "Attività", testo: "Montaggio arco – sabato 06:30, squadra allestimenti" }] }),
    poly([[9.1735, 45.4748], [9.1748, 45.4752], [9.1752, 45.4745], [9.1739, 45.4741]], { nome: "Village atleti", layer_id: "aree", colore: "#0F766E", categoria: "Aree operative",
      collegamenti: [{ area: "Eventi", testo: "planimetria collegata all'evento Corsa del Parco 10K" }] }),
    box([9.1742, 45.4747], 6, 3, 20, { nome: "Gazebo segreteria e ritiro pettorali", layer_id: "strutture", colore: "#0ABAB5", categoria: "Strutture",
      collegamenti: [{ area: "Staff e volontari", testo: "2 volontari assegnati – turno 07:00–10:00" }] }),
    box([9.1747, 45.4755], 3, 3, 20, { nome: "Stand sponsor", layer_id: "sponsor", colore: "#9333EA", categoria: "Sponsor",
      collegamenti: [{ area: "Sponsor e partner", testo: "area riservata a Sponsor Demo S.r.l." }] }),
    box([9.1720, 45.4746], 1.2, 1.2, 0, { nome: "Bagni chimici", quantita: 6, layer_id: "strutture", colore: "#2563EB", categoria: "Servizi" }),
    box([9.1756, 45.4751], 6, 2.5, 20, { nome: "Ambulanza", layer_id: "sicurezza", colore: "#DC2626", categoria: "Sicurezza",
      collegamenti: [{ area: "Briefing", testo: "posizione inclusa nel briefing operativo" }] }),
    pt([9.1768, 45.4693], { nome: "Ristoro km 2,5", layer_id: "ristori", colore: "#F59E0B", categoria: "Servizi",
      collegamenti: [{ area: "Staff e volontari", testo: "4 volontari assegnati – turno 08:00–12:00" }, { area: "Attività", testo: "Consegna acqua e frutta – ore 07:30" }] }),
    pt([9.1736, 45.4757], { nome: "Ristoro arrivo", layer_id: "ristori", colore: "#F59E0B", categoria: "Servizi" }),
    pt([9.1806, 45.4714], { nome: "Primo soccorso", layer_id: "sicurezza", colore: "#EF4444", categoria: "Sicurezza" }),
    pt([9.1703, 45.4726], { nome: "Punto controllo percorso", layer_id: "staff", colore: "#22C55E", categoria: "Staff",
      collegamenti: [{ area: "Staff e volontari", testo: "1 volontario – Addetto percorso" }] }),
    pt([9.1785, 45.4746], { nome: "Punto controllo percorso", layer_id: "staff", colore: "#22C55E", categoria: "Staff" }),
    pt([9.1752, 45.4762], { nome: "Direzione gara", layer_id: "staff", colore: "#166534", categoria: "Staff",
      collegamenti: [{ area: "Briefing", testo: "punto di ritrovo dello staff alle 06:45" }] }),
    pt([9.1695, 45.4768], { nome: "Parcheggio atleti", layer_id: "viabilita", colore: "#1E40AF", categoria: "Viabilità" }),
    line([[9.1724, 45.4757], [9.1732, 45.4761], [9.1741, 45.4763]], { nome: "Transenne (2 m)", passo: 2, layer_id: "viabilita", colore: "#64748B", categoria: "Viabilità" }),
  ],
};

export const SCENARIOS = { running };
