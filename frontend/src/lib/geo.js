// Calcoli geografici (sfera WGS84 media): distanze, lunghezze, superfici, oggetti in scala reale.
const R = 6371008.8;
const rad = (d) => (d * Math.PI) / 180;
const deg = (r) => (r * 180) / Math.PI;

export function distance([lng1, lat1], [lng2, lat2]) {
  const dLat = rad(lat2 - lat1), dLng = rad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
}

export const lineLength = (coords) => coords.slice(1).reduce((s, c, i) => s + distance(coords[i], c), 0);

export function polygonArea(ring) {
  if (ring.length < 3) return 0;
  let s = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length];
    s += rad(x2 - x1) * (2 + Math.sin(rad(y1)) + Math.sin(rad(y2)));
  }
  return Math.abs((s * R * R) / 2);
}

export const perimeter = (ring) => lineLength([...ring, ring[0]]);

// Spostamento di dx/dy metri (est/nord) da un punto.
export function offset([lng, lat], dx, dy) {
  return [lng + deg(dx / (R * Math.cos(rad(lat)))), lat + deg(dy / R)];
}

export function boxPolygon(center, w, l, rot = 0) {
  const t = rad(rot), c = Math.cos(t), s = Math.sin(t);
  const pts = [[-w / 2, -l / 2], [w / 2, -l / 2], [w / 2, l / 2], [-w / 2, l / 2]].map(([x, y]) => offset(center, x * c - y * s, x * s + y * c));
  return [...pts, pts[0]];
}

export function circlePolygon(center, r, n = 48) {
  const pts = Array.from({ length: n }, (_, i) => offset(center, r * Math.cos((2 * Math.PI * i) / n), r * Math.sin((2 * Math.PI * i) / n)));
  return [...pts, pts[0]];
}

export const fmtM = (m) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${m.toFixed(1)} m`);
export const fmtM2 = (a) => (a >= 10000 ? `${(a / 10000).toFixed(2)} ha (${Math.round(a).toLocaleString("it-IT")} m²)` : `${a.toFixed(1)} m²`);
