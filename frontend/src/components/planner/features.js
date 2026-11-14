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
    const len = lineLength(g.coordinates);
    return { lunghezza: len, testo: fmtM(len), pezzi: p.passo ? Math.ceil(len / p.passo) : null };
  }
  if (g.type === "Polygon") {
    const ring = g.coordinates[0].slice(0, -1);
    const a = polygonArea(ring);
    return { area: a, perimetro: perimeter(ring), testo: p.tipo === "box" ? `${p.larghezza} × ${p.lunghezza} m` : fmtM2(a) };
  }
  return {};
}

export function displayCollection(features, layers, selectedId) {
  const vis = new Set(layers.filter((l) => l.visibile).map((l) => l.id));
  const col = Object.fromEntries(layers.map((l) => [l.id, l.colore]));
  return {
    type: "FeatureCollection",
    features: features.filter((f) => vis.has(f.properties.layer_id)).map((f) => {
      const m = measures(f);
      return { type: "Feature", id: undefined, geometry: geometryOf(f),
        properties: { fid: f.properties.id, colore: f.properties.colore || col[f.properties.layer_id] || "#0ABAB5", sel: f.properties.id === selectedId ? 1 : 0,
          etichetta: [f.properties.nome, m.testo].filter(Boolean).join(" · ") } };
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
  else if (spec.tipo === "line" && linePreset) f = { properties: { ...base, nome: linePreset.nome, categoria: linePreset.categoria, colore: linePreset.colore, tipo: "line", passo: linePreset.larghezza, layer_id: lf(linePreset.categoria) }, geometry: { type: "LineString", coordinates: c } };
  else if (spec.tipo === "point") f = { properties: { ...base, nome: spec.nome || "Punto", tipo: "point", quantita: 1 }, geometry: { type: "Point", coordinates: c } };
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

export const anchorOf = (f) => {
  const g = geometryOf(f);
  if (f.properties.center) return f.properties.center;
  if (g.type === "Point") return g.coordinates;
  const pts = g.type === "LineString" ? g.coordinates : g.coordinates[0];
  return pts[Math.floor(pts.length / 2)];
};
