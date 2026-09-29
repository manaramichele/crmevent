import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { fileUrl } from "@/components/crm";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Leaflet default marker icons are not bundled by webpack; point them at the CDN.
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function parseGpx(text) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  const track = [];
  doc.querySelectorAll("trkpt, rtept").forEach((n) => {
    const lat = parseFloat(n.getAttribute("lat"));
    const lon = parseFloat(n.getAttribute("lon"));
    if (!isNaN(lat) && !isNaN(lon)) track.push([lat, lon]);
  });
  const waypoints = [];
  doc.querySelectorAll("wpt").forEach((n) => {
    const lat = parseFloat(n.getAttribute("lat"));
    const lon = parseFloat(n.getAttribute("lon"));
    const name = n.querySelector("name")?.textContent || "";
    if (!isNaN(lat) && !isNaN(lon)) waypoints.push({ latlng: [lat, lon], name });
  });
  return { track, waypoints };
}

export default function RouteMapDialog({ open, onOpenChange, gpxUrl, title }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    if (!open || !gpxUrl) return undefined;
    setStatus("loading");
    let cancelled = false;
    const timer = setTimeout(async () => {
      if (!containerRef.current || cancelled) return;
      const map = L.map(containerRef.current, { scrollWheelZoom: true });
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap", maxZoom: 19,
      }).addTo(map);
      map.setView([41.9, 12.5], 5);
      try {
        const res = await fetch(fileUrl(gpxUrl), { credentials: "include" });
        if (!res.ok) throw new Error("fetch failed");
        const { track, waypoints } = parseGpx(await res.text());
        const bounds = [];
        if (track.length > 1) {
          const line = L.polyline(track, { color: "#0d9488", weight: 4, opacity: 0.9 }).addTo(map);
          bounds.push(...track);
          L.marker(track[0]).addTo(map).bindPopup("Partenza");
          L.marker(track[track.length - 1]).addTo(map).bindPopup("Arrivo");
          void line;
        }
        waypoints.forEach((w) => { L.marker(w.latlng).addTo(map).bindPopup(w.name || "Punto"); bounds.push(w.latlng); });
        if (bounds.length) map.fitBounds(bounds, { padding: [24, 24] });
        setStatus(bounds.length ? "ok" : "empty");
      } catch {
        setStatus("error");
      }
      map.invalidateSize();
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, [open, gpxUrl]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl w-[95vw]" data-testid="route-map-dialog">
        <DialogHeader><DialogTitle className="font-display">{title || "Percorso"}</DialogTitle></DialogHeader>
        <div className="relative">
          <div ref={containerRef} className="w-full h-[60vh] rounded-xl overflow-hidden bg-slate-100" data-testid="route-map-canvas" />
          {status === "error" && <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500 bg-white/70 rounded-xl">Impossibile caricare il tracciato.</div>}
          {status === "empty" && <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-500 bg-white/70 rounded-xl">Il file non contiene un tracciato valido.</div>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
