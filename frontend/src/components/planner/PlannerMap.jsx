import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { displayCollection, translate, uid, boundsOf } from "./features";
import { distance } from "@/lib/geo";

const STYLES = { strade: "streets-v2", satellite: "hybrid" };
const EMPTY = { type: "FeatureCollection", features: [] };

// Mappa MapLibre con disegno (punto, linea, poligono, rettangolo, cerchio, misura), selezione e trascinamento.
export default function PlannerMap({ apiKey, stile, center, zoom, features, layers, selectedId, mode, placing, onSelect, onCreate, onChange, onDraft, onView, flyTo,
  bounds, minZoom, cooperative = false, onError, emptyText, fitReq = 0, hidden }) {
  const box = useRef(null), map = useRef(null), st = useRef({}), draft = useRef([]), fitDone = useRef(0);
  st.current = { features, layers, selectedId, mode, placing, onSelect, onCreate, onChange, onDraft, hidden };
  // Inquadra tutti gli elementi (apertura/cambio progetto o pulsante): mai durante il lavoro.
  const fit = (animate) => {
    const m = map.current;
    if (!m || !fitReq || fitDone.current === fitReq) return;
    fitDone.current = fitReq;
    const b = boundsOf(st.current.features);
    if (!b) return;
    const pad = Math.min(80, Math.round(Math.min(m.getContainer().clientWidth, m.getContainer().clientHeight) * 0.12));
    if (b[0][0] === b[1][0] && b[0][1] === b[1][1]) m.jumpTo({ center: b[0], zoom: 18 });
    else m.fitBounds(b, { padding: pad, maxZoom: 19, duration: animate ? 600 : 0 });
  };

  const lockedLayer = (fid) => {
    const f = st.current.features.find((x) => x.properties.id === fid);
    return f && st.current.layers.find((l) => l.id === f.properties.layer_id)?.bloccato;
  };
  const pushDraft = (pts) => {
    draft.current = pts;
    const m = map.current;
    if (!m?.getSource("draft")) return;
    const fs = pts.length > 1 ? [{ type: "Feature", geometry: { type: "LineString", coordinates: pts } }] : [];
    m.getSource("draft").setData({ type: "FeatureCollection", features: [...fs, ...pts.map((c) => ({ type: "Feature", geometry: { type: "Point", coordinates: c } }))] });
    st.current.onDraft(pts);
  };

  useEffect(() => {
    if (!apiKey || !box.current) return undefined;
    const m = new maplibregl.Map({ container: box.current, style: `https://api.maptiler.com/maps/${STYLES[stile] || STYLES.strade}/style.json?key=${apiKey}`,
      center: center || [12.4964, 41.9028], zoom: zoom || (center ? 16 : 5), attributionControl: { compact: true }, doubleClickZoom: false,
      maxBounds: bounds, minZoom: minZoom || 0, cooperativeGestures: cooperative });
    map.current = m;
    if (window.__PLANNER_RECORDING) window.__plannerMap = m;
    let loaded = false;
    m.on("load", () => { loaded = true; fit(false); });
    m.on("error", (e) => { if (!loaded && onError) onError(e?.error?.status || 0); });
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "bottom-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    m.on("style.load", () => {
      m.addSource("feat", { type: "geojson", data: EMPTY });
      m.addSource("draft", { type: "geojson", data: EMPTY });
      m.addLayer({ id: "f-fill", type: "fill", source: "feat", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": ["get", "colore"], "fill-opacity": ["case", ["==", ["get", "sel"], 1], 0.55, 0.35] } });
      m.addLayer({ id: "f-line", type: "line", source: "feat", filter: ["!=", ["geometry-type"], "Point"], paint: { "line-color": ["case", ["==", ["get", "sel"], 1], "#0f172a", ["get", "colore"]], "line-width": ["case", ["==", ["get", "sel"], 1], ["+", ["get", "spessore"], 1], ["get", "spessore"]] } });
      m.addLayer({ id: "f-pt", type: "circle", source: "feat", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": ["case", ["==", ["get", "sel"], 1], 9, 7], "circle-color": ["get", "colore"], "circle-stroke-width": 2, "circle-stroke-color": ["case", ["==", ["get", "sel"], 1], "#0f172a", "#ffffff"] } });
      m.addLayer({ id: "f-lbl", type: "symbol", source: "feat", layout: { "text-field": ["get", "etichetta"], "text-size": 11, "text-offset": [0, 1.2], "text-anchor": "top", "text-optional": true }, paint: { "text-color": "#0f172a", "text-halo-color": "#fff", "text-halo-width": 1.5 }, minzoom: 15 });
      m.addLayer({ id: "d-line", type: "line", source: "draft", paint: { "line-color": "#0f172a", "line-width": 2, "line-dasharray": [2, 2] } });
      m.addLayer({ id: "d-pt", type: "circle", source: "draft", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 4, "circle-color": "#0f172a" } });
      m.getSource("feat").setData(displayCollection(st.current.features, st.current.layers, st.current.selectedId, st.current.hidden));
    });
    const HIT = ["f-pt", "f-line", "f-fill"];
    const hit = (e) => m.queryRenderedFeatures([[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]], { layers: HIT.filter((l) => m.getLayer(l)) })[0];
    let drag = null;
    const down = (e) => {
      if (st.current.mode !== "select") return;
      const h = hit(e);
      if (!h || h.properties.fid !== st.current.selectedId || lockedLayer(h.properties.fid)) return;
      e.preventDefault(); m.dragPan.disable();
      drag = { fid: h.properties.fid, last: e.lngLat, start: st.current.features };
    };
    const move = (e) => {
      if (!drag) return;
      const dLng = e.lngLat.lng - drag.last.lng, dLat = e.lngLat.lat - drag.last.lat;
      drag.last = e.lngLat;
      st.current.onChange(st.current.features.map((f) => (f.properties.id === drag.fid ? translate(f, dLng, dLat) : f)), true);
    };
    const up = () => { if (drag) { st.current.onChange(st.current.features, false, drag.start); drag = null; m.dragPan.enable(); } };
    m.on("mousedown", down); m.on("touchstart", down); m.on("mousemove", move); m.on("touchmove", move); m.on("mouseup", up); m.on("touchend", up);
    m.on("click", (e) => {
      const c = [e.lngLat.lng, e.lngLat.lat], { mode: md, placing: pl } = st.current;
      if (pl) { st.current.onCreate(pl, c); return; }
      if (md === "select") { const h = hit(e); st.current.onSelect(h && !lockedLayer(h.properties.fid) ? h.properties.fid : null); return; }
      if (md === "point") { st.current.onCreate({ tipo: "point" }, c); return; }
      const pts = [...draft.current, c];
      if (md === "rect" && pts.length === 2) { pushDraft([]); st.current.onCreate({ tipo: "rect" }, pts); return; }
      if (md === "circle" && pts.length === 2) { pushDraft([]); st.current.onCreate({ tipo: "circle", raggio: distance(pts[0], pts[1]) }, pts[0]); return; }
      pushDraft(pts);
    });
    m.on("dblclick", () => { if (["line", "polygon", "measure"].includes(st.current.mode)) finish(); });
    m.on("moveend", () => onView && onView([m.getCenter().lng, m.getCenter().lat], m.getZoom()));
    const finish = () => {
      const pts = draft.current, md = st.current.mode;
      pushDraft([]);
      if ((md === "line" || md === "measure") && pts.length >= 2) st.current.onCreate({ tipo: md === "measure" ? "measure" : "line" }, pts);
      if (md === "polygon" && pts.length >= 3) st.current.onCreate({ tipo: "polygon" }, pts);
    };
    st.current.finish = finish;
    window.__plannerFinish = finish;
    return () => { m.remove(); map.current = null; };
  }, [apiKey, stile]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { const c = map.current?.cooperativeGestures; if (c) { if (cooperative) c.enable(); else c.disable(); } }, [cooperative]);
  useEffect(() => { if (map.current?.loaded()) fit(fitDone.current > 0); }, [fitReq]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { map.current?.getSource("feat")?.setData(displayCollection(features, layers, selectedId, hidden)); }, [features, layers, selectedId, hidden]);
  useEffect(() => { if (flyTo && map.current) map.current.flyTo({ center: flyTo.center, zoom: flyTo.zoom || 16 }); }, [flyTo]);
  useEffect(() => { pushDraft([]); if (map.current) map.current.getCanvas().style.cursor = mode === "select" && !placing ? "" : "crosshair"; }, [mode, placing]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!apiKey) return <div className="flex h-full items-center justify-center bg-slate-100 p-6 text-center text-sm text-slate-600" data-testid="planner-no-key">{emptyText || "Mappa non disponibile: manca la chiave MapTiler (MAPTILER_API_KEY) nel backend."}</div>;
  return <div ref={box} className="h-full w-full" data-testid="planner-map" />;
}

export { uid };
