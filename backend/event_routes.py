"""Percorsi Eventi come archivio condiviso: elenco percorsi GPX/KML/KMZ di un evento e conversione interna in coordinate/GPX."""
import io
import xml.etree.ElementTree as ET
import zipfile

EXTS = (".gpx", ".kml", ".kmz")


def _tag(el):
    return el.tag.rsplit("}", 1)[-1].lower()


def fmt_of(name):
    n = (name or "").lower()
    return next((e[1:].upper() for e in EXTS if n.endswith(e)), None)


def coords(data: bytes, name: str) -> list:
    """[[lon, lat, ele|None], ...] della linea principale (la pi\u00f9 lunga). Quote mai inventate: None se assenti."""
    f = fmt_of(name)
    if f == "KMZ":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            kml = next((n for n in z.namelist() if n.lower().endswith(".kml")), None)
            if not kml:
                raise ValueError("Il file KMZ non contiene un KML")
            data, f = z.read(kml), "KML"
    root = ET.fromstring(data)
    lines = []
    if f == "GPX":
        for seg in [e for e in root.iter() if _tag(e) in ("trkseg", "rte")]:
            pts = []
            for p in seg:
                if _tag(p) in ("trkpt", "rtept"):
                    ele = next((c.text for c in p if _tag(c) == "ele"), None)
                    pts.append([float(p.get("lon")), float(p.get("lat")), float(ele) if ele not in (None, "") else None])
            lines.append(pts)
    else:
        for c in [e for e in root.iter() if _tag(e) == "coordinates"]:
            pts = []
            for tok in (c.text or "").split():
                v = tok.split(",")
                if len(v) >= 2:
                    pts.append([float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 and v[2] not in ("", "0", "0.0") else None])
            lines.append(pts)
        for tr in [e for e in root.iter() if _tag(e) == "track"]:  # gx:Track
            pts = [[float(v.split()[0]), float(v.split()[1]), float(v.split()[2]) if len(v.split()) > 2 else None] for v in (x.text or "" for x in tr if _tag(x) == "coord") if v.strip()]
            lines.append(pts)
    best = max(lines, key=len) if lines else []
    if len(best) < 2:
        raise ValueError("Nessun tracciato trovato nel file")
    return best


def to_gpx(data: bytes, name: str) -> bytes:
    if fmt_of(name) == "GPX":
        return data
    pts = coords(data, name)
    body = "".join(f'<trkpt lat="{p[1]:.7f}" lon="{p[0]:.7f}">' + (f"<ele>{p[2]:.1f}</ele>" if p[2] is not None else "") + "</trkpt>" for p in pts)
    return ('<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="CRMEvent" xmlns="http://www.topografix.com/GPX/1/1">'
            f"<trk><trkseg>{body}</trkseg></trk></gpx>").encode()


async def list_routes(db, org_id, eid, resolve):
    """Percorsi dell'evento in Percorsi Eventi con file GPX/KML/KMZ; version = id del file attuale (cambia se il file viene sostituito)."""
    out = []
    for mp in await db.event_maps.find({"org_id": org_id, "evento_id": eid}, {"_id": 0}).sort("created_at", 1).to_list(500):
        for field in ("gpx_url", "file_url"):
            rec = await resolve(mp.get(field), org_id) if mp.get(field) else None
            fname = (rec or {}).get("original_filename") or (rec or {}).get("filename") or ""
            if rec and rec.get("storage_path") and fmt_of(fname):
                out.append({"map_id": mp["id"], "nome": mp.get("nome") or mp.get("titolo") or fname, "format": fmt_of(fname), "filename": fname,
                            "distance": mp.get("distanza"), "updated_at": mp.get("updated_at") or mp.get("created_at"), "version": rec["id"], "_rec": rec})
                break
    return out


def public(routes):
    return [{k: v for k, v in r.items() if k != "_rec"} for r in routes]
