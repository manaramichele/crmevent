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

export const anchorOf = (f) => {
  const g = geometryOf(f);
  if (f.properties.center) return f.properties.center;
  if (g.type === "Point") return g.coordinates;
  const pts = g.type === "LineString" ? g.coordinates : g.coordinates[0];
  return pts[Math.floor(pts.length / 2)];
};
