import { boxPolygon, circlePolygon, lineLength, polygonArea, perimeter, fmtM, fmtM2 } from "@/lib/geo";

export const uid = () => Math.random().toString(36).slice(2, 10);

// Geometria effettiva di un oggetto (gli oggetti in scala si rigenerano da centro, dimensioni e rotazione).
export function geometryOf(f) {
  const p = f.properties;
  if (p.tipo === "box") return { type: "Polygon", coordinates: [boxPolygon(p.center, +p.larghezza || 1, +p.lunghezza || 1, +p.rotazione || 0)] };
  if (p.tipo === "circle") return { type: "Polygon", coordinates: [circlePolygon(p.center, +p.raggio || 1)] };
  return f.geometry;
}

export function measures(f) {
  const g = geometryOf(f), p = f.properties;
  if (!g) return {};
  if (g.type === "LineString") {
    const len = lineLength(g.coordinates), giri = Math.max(1, +p.giri || 1);
    return { lunghezza: len, giro: len, giri, totale: len * giri, testo: giri > 1 ? `${giri} × ${fmtM(len)} = ${fmtM(len * giri)}` : fmtM(len), pezzi: p.passo ? Math.ceil(len / p.passo) : null };
  }
  if (g.type === "Polygon") {
    const ring = g.coordinates[0].slice(0, -1);
    const a = polygonArea(ring);
    return { area: a, perimetro: perimeter(ring), testo: p.tipo === "box" ? `${p.larghezza} × ${p.lunghezza} m` : fmtM2(a) };
  }
  return {};
}

export function displayCollection(features, layers, selectedId, hidden) {
  const vis = new Set(layers.filter((l) => l.visibile).map((l) => l.id));
  const col = Object.fromEntries(layers.map((l) => [l.id, l.colore]));
  const KC = { team: "#0F766E", staff: "#2563EB", volontario: "#16A34A", generica: "#94A3B8" };
  return {
    type: "FeatureCollection",
    features: features.filter((f) => vis.has(f.properties.layer_id) && !(hidden && hidden.has(f.properties.id))).map((f) => {
      const m = measures(f);
      const st = f.properties.station;
      return { type: "Feature", id: undefined, geometry: geometryOf(f),
        properties: { fid: f.properties.id, colore: (st && KC[st.kind]) || f.properties.colore || col[f.properties.layer_id] || "#0ABAB5", sel: f.properties.id === selectedId ? 1 : 0,
          spessore: Number(f.properties.spessore) || 2.5, frecce: f.properties.frecce ? 1 : 0, dim: Math.min(4, Math.max(0.5, Number(f.properties.dimensione) || 1)),
          etichetta: [f.properties.numero != null && f.properties.numero !== "" ? `${f.properties.numero}.` : null, f.properties.nome, st && st.kind !== "generica" ? `${{ team: "Team", staff: "Staff", volontario: "Volontari" }[st.kind]}${f.properties.n_persone ? ` (${f.properties.n_persone})` : ""}` : st ? "da assegnare" : null, m.testo].filter(Boolean).join(" · ") } };
    }),
  };
}

export function translate(f, dLng, dLat) {
  const p = f.properties;
  if (p.center) return { ...f, properties: { ...p, center: [p.center[0] + dLng, p.center[1] + dLat] } };
  const mv = (c) => [c[0] + dLng, c[1] + dLat];
  const g = f.geometry;
  const coords = g.type === "Point" ? mv(g.coordinates) : g.type === "LineString" ? g.coordinates.map(mv) : g.coordinates.map((r) => r.map(mv));
  return { ...f, geometry: { ...g, coordinates: coords } };
}

export const layerForCat = (layers, cat) => (layers.find((l) => l.nome.toLowerCase().startsWith((cat || "").toLowerCase().slice(0, 5))) || layers.find((l) => !l.bloccato) || layers[0])?.id;

// Crea un nuovo oggetto dal tipo di strumento o dall'elemento della libreria (stesso motore per area riservata e demo).
export function makeFeature(spec, c, layers, linePreset) {
  const lf = (cat) => layerForCat(layers, cat);
  const base = { id: uid(), layer_id: lf(spec.categoria), colore: spec.colore, nome: spec.nome, categoria: spec.categoria };
  let f;
  if (spec.tipo === "box") f = { properties: { ...base, tipo: "box", center: c, larghezza: spec.larghezza, lunghezza: spec.lunghezza, rotazione: 0, quantita: 1 } };
  else if (spec.tipo === "line" && linePreset) f = { properties: { ...base, nome: linePreset.nome, categoria: linePreset.categoria, colore: linePreset.colore, tipo: "line", passo: linePreset.larghezza || null, layer_id: lf(linePreset.categoria), ...(linePreset.extra || {}) }, geometry: { type: "LineString", coordinates: c } };
  else if (spec.tipo === "point") f = { properties: { ...base, nome: spec.nome || "Punto", tipo: "point", quantita: 1, ...(spec.categoria === "Boe" ? { numero: null, dimensione: 1, categoria_nome: spec.nome } : {}) }, geometry: { type: "Point", coordinates: c } };
  else if (spec.tipo === "line" || spec.tipo === "measure") f = { properties: { ...base, nome: spec.tipo === "measure" ? "Misura" : "Linea", tipo: spec.tipo, layer_id: lf("Percorsi") }, geometry: { type: "LineString", coordinates: c } };
  else if (spec.tipo === "polygon") f = { properties: { ...base, nome: "Area", tipo: "polygon", layer_id: lf("Aree") }, geometry: { type: "Polygon", coordinates: [[...c, c[0]]] } };
  else if (spec.tipo === "rect") { const [a, b] = c; f = { properties: { ...base, nome: "Rettangolo", tipo: "polygon", layer_id: lf("Aree") }, geometry: { type: "Polygon", coordinates: [[a, [b[0], a[1]], b, [a[0], b[1]], a]] } }; }
  else if (spec.tipo === "circle") f = { properties: { ...base, nome: "Cerchio", tipo: "circle", center: c, raggio: spec.raggio, layer_id: lf("Aree") } };
  return { type: "Feature", geometry: f.geometry || null, ...f };
}

// Riquadro [[minLng,minLat],[maxLng,maxLat]] di tutti gli oggetti (di ogni livello, anche nascosti); null se il progetto è vuoto.
export function boundsOf(features) {
  let b = null;
  const add = (c) => { b = b ? [[Math.min(b[0][0], c[0]), Math.min(b[0][1], c[1])], [Math.max(b[1][0], c[0]), Math.max(b[1][1], c[1])]] : [[c[0], c[1]], [c[0], c[1]]]; };
  const walk = (x) => { if (Array.isArray(x) && typeof x[0] === "number") add(x); else if (Array.isArray(x)) x.forEach(walk); };
  (features || []).forEach((f) => { const g = geometryOf(f); if (g) walk(g.coordinates); });
  return b;
}

export const DISCIPLINE = { nuoto: ["Nuoto", "#0284C7"], ciclismo: ["Ciclismo", "#2563EB"], corsa: ["Corsa", "#EA580C"], transizione: ["Transizione", "#9333EA"] };

// Percorso in acqua attorno a un centro: lunghezza per giro in metri (stima cartografica, nessun aggancio a strade).
export function waterShape(c, kind, m) {
  const k = 111320, cos = Math.cos((c[1] * Math.PI) / 180);
  const off = ([dx, dy]) => [c[0] + dx / (k * cos), c[1] + dy / k];
  let pts;
  if (kind === "lineare") pts = [[-m / 2, 0], [m / 2, 0]];
  else if (kind === "triangolo") { const s = m / 3, h = (s * Math.sqrt(3)) / 2; pts = [[-s / 2, -h / 3], [s / 2, -h / 3], [0, (2 * h) / 3], [-s / 2, -h / 3]]; }
  else if (kind === "rettangolo") { const w = m / 6, l = m / 3; pts = [[-l / 2, -w / 2], [l / 2, -w / 2], [l / 2, w / 2], [-l / 2, w / 2], [-l / 2, -w / 2]]; }
  else { const r = m / (2 * Math.PI); pts = Array.from({ length: 33 }, (_, i) => [r * Math.cos((i / 32) * 2 * Math.PI), r * Math.sin((i / 32) * 2 * Math.PI)]); }
  return pts.map(off);
}

// Boe collegate a un punto del percorso: il punto segue la boa (distanze ricalcolate). Boe senza collegamento restano indipendenti.
export function syncBuoys(features) {
  const moves = {};
  features.forEach((f) => { const p = f.properties; if (p.categoria === "Boe" && p.link_route && p.link_idx != null && f.geometry?.type === "Point") (moves[p.link_route] ||= []).push([+p.link_idx, f.geometry.coordinates]); });
  if (!Object.keys(moves).length) return features;
  let changed = false;
  const out = features.map((f) => {
    const mv = moves[f.properties.id];
    if (!mv || f.geometry?.type !== "LineString") return f;
    const cs = [...f.geometry.coordinates], closed = cs.length > 2 && cs[0][0] === cs[cs.length - 1][0] && cs[0][1] === cs[cs.length - 1][1];
    mv.forEach(([i, c]) => {
      if (i < 0 || i >= cs.length || (cs[i][0] === c[0] && cs[i][1] === c[1])) return;
      cs[i] = c; changed = true;
      if (closed && i === 0) cs[cs.length - 1] = c;
    });
    return { ...f, geometry: { ...f.geometry, coordinates: cs } };
  });
  return changed ? out : features;
}

export const anchorOf = (f) => {
  const g = geometryOf(f);
  if (f.properties.center) return f.properties.center;
  if (g.type === "Point") return g.coordinates;
  const pts = g.type === "LineString" ? g.coordinates : g.coordinates[0];
  return pts[Math.floor(pts.length / 2)];
};
