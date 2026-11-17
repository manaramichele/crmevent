import { createElement, useEffect, useRef } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { distance } from "@/lib/geo";
import { ICONS, VEHICLE_STYLE, posOf, nameOf } from "./meta";

const EMPTY = { type: "FeatureCollection", features: [] };
const OSM = { version: 8, glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap" } }, layers: [{ id: "osm", type: "raster", source: "osm" }] };
const svg = (name, size = 15) => renderToStaticMarkup(createElement(ICONS[name] || ICONS.MapPin, { size, color: "#fff", strokeWidth: 2.4 }));

function cumulative(coords) {
  const acc = [0];
  for (let i = 1; i < coords.length; i += 1) acc.push(acc[i - 1] + distance(coords[i - 1], coords[i]));
  return acc;
}
const slice = (coords, acc, a, b) => coords.filter((_, i) => acc[i] >= a && acc[i] <= b);

function routeData(route, sectors, highlight) {
  if (!route?.coordinates?.length) return { line: EMPTY, km: EMPTY, sec: EMPTY };
  const c = route.coordinates, acc = cumulative(c), tot = acc[acc.length - 1];
  const step = tot < 25000 ? 1000 : tot < 60000 ? 5000 : 10000, km = [];
  for (let m = step, i = 0; m < tot; m += step) { while (acc[i] < m) i += 1; km.push({ type: "Feature", geometry: { type: "Point", coordinates: c[i] }, properties: { t: `${m / 1000} km` } }); }
  const sec = sectors.filter((s) => s.km_inizio != null && s.km_fine != null).map((s) => ({ type: "Feature", properties: { colore: s.colore || "#7C3AED", hl: highlight === s.id ? 1 : 0 },
    geometry: { type: "LineString", coordinates: slice(c, acc, s.km_inizio * 1000, s.km_fine * 1000) } })).filter((f) => f.geometry.coordinates.length > 1);
  return { line: { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "LineString", coordinates: c }, properties: {} }] }, km: { type: "FeatureCollection", features: km },
    sec: { type: "FeatureCollection", features: sec } };
}

function el(color, icon, title, extra = "") {
  const d = document.createElement("div");
  d.className = `cr-marker ${extra}`;
  d.title = title;
  d.style.cssText = `background:${color};width:30px;height:30px;border-radius:9999px;display:flex;align-items:center;justify-content:center;border:2px solid #fff;box-shadow:0 2px 6px rgba(15,23,42,.35);cursor:pointer`;
  d.innerHTML = icon;
  return d;
}

// Mappa operativa: percorso, km, settori, postazioni (trascinabili), mezzi, interventi; filtri via `hidden`.
export default function OpsMap({ apiKey, route, data, hidden, highlight, placing, onPlace, onOpen, onMove, flyTo, canEdit }) {
  const box = useRef(null), map = useRef(null), markers = useRef([]), dragging = useRef(false), cb = useRef({});
  cb.current = { placing, onPlace, onOpen, onMove };
  useEffect(() => {
    if (!apiKey || !box.current) return undefined;
    const m = new maplibregl.Map({ container: box.current, style: `https://api.maptiler.com/maps/streets-v2/style.json?key=${apiKey}`, center: [12.4964, 41.9028], zoom: 5, attributionControl: { compact: true } });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "bottom-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    let styled = false;
    // Chiave cartografica non valida per il dominio: ripiego su OpenStreetMap senza bloccare la Control Room
    m.on("error", (e) => { if (!styled && [401, 403].includes(e?.error?.status)) { styled = true; m.setStyle(OSM); } });
    m.on("style.load", () => {
      styled = true;
      if (m.getSource("route")) return;
      ["route", "km", "sec"].forEach((s) => m.addSource(s, { type: "geojson", data: EMPTY }));
      m.addLayer({ id: "route", type: "line", source: "route", paint: { "line-color": "#0ABAB5", "line-width": 5, "line-opacity": 0.85 }, layout: { "line-cap": "round", "line-join": "round" } });
      m.addLayer({ id: "sec", type: "line", source: "sec", paint: { "line-color": ["get", "colore"], "line-width": ["case", ["==", ["get", "hl"], 1], 10, 6], "line-opacity": ["case", ["==", ["get", "hl"], 1], 0.95, 0.55] } });
      m.addLayer({ id: "km", type: "symbol", source: "km", layout: { "text-field": ["get", "t"], "text-size": 11, "text-offset": [0, -1.1] }, paint: { "text-color": "#0f172a", "text-halo-color": "#fff", "text-halo-width": 2 } });
      m.addLayer({ id: "km-dot", type: "circle", source: "km", paint: { "circle-radius": 3, "circle-color": "#0f172a" } });
      m.fire("cr-ready");
    });
    m.on("click", (e) => { if (cb.current.placing) cb.current.onPlace([e.lngLat.lng, e.lngLat.lat]); });
    return () => { m.remove(); map.current = null; };
  }, [apiKey]);

  useEffect(() => {
    const m = map.current;
    if (!m) return undefined;
    const apply = () => {
      const r = routeData(route, data.sectors, highlight);
      m.getSource("route")?.setData(hidden.has("route") ? EMPTY : r.line);
      m.getSource("km")?.setData(hidden.has("km") ? EMPTY : r.km);
      m.getSource("sec")?.setData(hidden.has("sectors") ? EMPTY : r.sec);
    };
    if (m.getSource("route")) apply(); else m.once("cr-ready", apply);
    return undefined;
  }, [route, data.sectors, highlight, hidden]);

  useEffect(() => {
    const m = map.current;
    if (!m?.getSource || !route?.coordinates?.length) return;
    const b = route.coordinates.reduce((bb, c) => bb.extend(c), new maplibregl.LngLatBounds(route.coordinates[0], route.coordinates[0]));
    m.fitBounds(b, { padding: 50, duration: 0 });
  }, [route]);

  useEffect(() => {
    const m = map.current;
    if (!m || dragging.current) return;
    markers.current.forEach((x) => x.remove());
    markers.current = [];
    const add = (lnglat, node, opts = {}) => { const mk = new maplibregl.Marker({ element: node, ...opts }).setLngLat(lnglat).addTo(m); markers.current.push(mk); return mk; };
    const c = route?.coordinates;
    if (c?.length > 1 && !hidden.has("route")) {
      add(c[0], el("#16A34A", svg("Flag"), "Partenza", "cr-start"));
      add(c[c.length - 1], el("#0f172a", svg("Flag"), "Arrivo", "cr-finish"));
    }
    const cats = Object.fromEntries(data.settings.categories.map((x) => [x.key, x]));
    data.posts.filter((p) => p.lng != null && !hidden.has(`post:${p.categoria}`)).forEach((p) => {
      const cat = cats[p.categoria] || { color: "#64748B", icon: "MapPin" };
      const node = el(cat.color, svg(cat.icon), `${p.nome} · ${cat.label || ""} · ${p.presenti}/${p.previsti} operatori · ${p.presidio.replace("_", " ").toUpperCase()}`, "cr-post");
      node.style.boxShadow = `0 0 0 3px ${{ presidiata: "#16A34A", parziale: "#F59E0B", non_presidiata: "#DC2626", in_attesa: "#94A3B8", non_attiva: "#CBD5E1" }[p.presidio] || "#fff"}, 0 2px 6px rgba(15,23,42,.35)`;
      node.dataset.testid = `cr-map-post-${p.id}`;
      node.addEventListener("click", (e) => { e.stopPropagation(); cb.current.onOpen("posts", p.id); });
      const mk = add([p.lng, p.lat], node, { draggable: canEdit });
      mk.on("dragstart", () => { dragging.current = true; });
      mk.on("dragend", () => { dragging.current = false; const ll = mk.getLngLat(); cb.current.onMove(p, [ll.lng, ll.lat]); });
    });
    data.resources.filter((r) => r.kind !== "persona" && !hidden.has(r.kind === "mezzo" ? `veh:${r.tipologia}` : "squadre")).forEach((r) => {
      const ll = posOf(r, data.posts);
      if (!ll) return;
      const [icon, color] = r.kind === "mezzo" ? VEHICLE_STYLE[r.tipologia] || VEHICLE_STYLE.altro : ["Users", "#7C3AED"];
      const node = el(color, svg(icon, 14), `${nameOf(r)} (posizione assegnata)`, "cr-res");
      node.style.borderRadius = "8px";
      node.addEventListener("click", (e) => { e.stopPropagation(); cb.current.onOpen("resources", r.id); });
      add(ll, node, { offset: [22, -22] });
      if (r.gps?.last_lat != null) add([r.gps.last_lng, r.gps.last_lat], el("#0f172a", svg("MapPin", 12), `${nameOf(r)} · posizione GPS rilevata ${r.gps.last_at || ""}`));
    });
    if (!hidden.has("interventions")) {
      const PCOL = { bassa: "#94A3B8", media: "#EAB308", alta: "#F97316", critica: "#DC2626" };
      const types = Object.fromEntries((data.itv_types || []).map((t) => [t.key, t.label]));
      data.interventions.filter((i) => !["chiuso", "annullato"].includes(i.stato)).forEach((i) => {
        if (i.lng == null) return;
        const ll = [i.lng, i.lat];
        const time = new Date(i.created_at).toLocaleTimeString("it-IT", { timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit" });
        const node = el(PCOL[i.priorita] || "#F97316", svg("Siren", 14), `${i.codice} · ${types[i.tipologia] || i.tipologia} · ${i.priorita.toUpperCase()} · ${i.stato.replace(/_/g, " ").toUpperCase()} · ${time}`, `cr-itv ${i.priorita === "critica" ? "animate-pulse" : ""}`);
        node.style.borderRadius = "6px";
        node.style.width = "auto";
        node.style.padding = "0 6px";
        node.style.gap = "3px";
        node.insertAdjacentHTML("beforeend", `<span style="color:#fff;font:700 10px sans-serif">${i.codice}</span>`);
        node.dataset.testid = `cr-map-itv-${i.codice}`;
        node.addEventListener("click", (e) => { e.stopPropagation(); cb.current.onOpen("interventions", i.id); });
        add(ll, node, { offset: i.post_id ? [-26, -26] : [0, 0] });
      });
    }
  }, [data, route, hidden, canEdit]);

  useEffect(() => { if (flyTo && map.current) map.current.flyTo({ center: flyTo.c, zoom: flyTo.z || 16 }); }, [flyTo]);
  useEffect(() => { if (map.current) map.current.getCanvas().style.cursor = placing ? "crosshair" : ""; }, [placing]);
  useEffect(() => {
    const m = map.current;
    if (!m || !box.current) return undefined;
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(box.current);
    return () => ro.disconnect();
  }, [apiKey]);

  if (!apiKey) return <div className="flex h-full items-center justify-center bg-slate-100 p-6 text-center text-sm text-slate-600" data-testid="cr-map-nokey">Mappa non disponibile: chiave cartografica non configurata.</div>;
  return <div ref={box} className="h-full w-full" data-testid="cr-map" />;
}
