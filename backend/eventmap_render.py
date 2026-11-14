"""Event Map — renderer video da GPX (processo separato). Uso: python eventmap_render.py job.json
Cartografia sostituibile: EVENTMAP_MAP_PROVIDER=openfreemap (default, dati OpenStreetMap) | maptiler (futuro, raster con MAPTILER_VIDEO_KEY)."""
import gzip
import io
import json
import math
import os
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eventmap_assets")
TS = 512
UA = {"User-Agent": "CRMEvent-EventMap/1.0 (+https://crmevent.it)"}
SIZES = {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)}
LOGO_BOX = {"9:16": (300, 140), "1:1": (240, 110), "16:9": (300, 120)}  # riquadro massimo del logo (unità U)
LOGO_MARGIN, LOGO_PAD = 32, 14
FPS = 30
STYLES = {
    "dark": {"bg": (24, 28, 36), "green": (30, 44, 40), "water": (18, 46, 66), "building": (40, 45, 56), "road": (72, 80, 96), "major": (104, 112, 128),
             "route": (255, 92, 56), "glow": (255, 120, 80), "text": (255, 255, 255)},
    "streets": {"bg": (238, 235, 228), "green": (205, 228, 196), "water": (166, 205, 232), "building": (222, 216, 206), "road": (255, 255, 255), "major": (252, 214, 140),
                "route": (230, 40, 70), "glow": (255, 90, 110), "text": (255, 255, 255)},
}
# velocità animazione: fasi (intro, fine percorso), zoom della camera che segue, oscillazione dello zoom, finestra di smussamento
SPEEDS = {"slow": {"t_in": 0.16, "t_end": 0.78, "zoom": 1.45, "wob": 0.03, "win": 0.07},
          "normal": {"t_in": 0.12, "t_end": 0.82, "zoom": 1.0, "wob": 0.08, "win": 0.04},
          "fast": {"t_in": 0.07, "t_end": 0.85, "zoom": 0.72, "wob": 0.1, "win": 0.025}}
CHART_H = {"9:16": 210, "1:1": 150, "16:9": 150}
AID_RE = re.compile(r"ristor|rifornim|refresh|aid ?station|feed ?zone|\bfood\b|\bdrinks?\b|\bwater\b(?! ?front)|\bacqua\b|spugna|ravitaill|verpfleg|avituall|vettovagl", re.I)
AID_SYM = {"food", "drinking water", "water source", "restaurant", "water"}
ATTR = {"openfreemap": "© OpenStreetMap contributors · OpenFreeMap", "maptiler": "© MapTiler © OpenStreetMap contributors"}


# ---------------- GPX ----------------
def _child(el, name):
    return next(((c.text or "").strip() for c in el if c.tag.split("}")[-1] == name), "")


def is_aid(w):
    """Ristoro solo se il GPX lo dice chiaramente (nome, descrizione, tipo o simbolo)."""
    return bool(AID_RE.search(" ".join([w.get("name", ""), w.get("desc", ""), w.get("type", "")]))) or w.get("sym", "").lower() in AID_SYM


def parse_gpx(data: bytes):
    root = ET.fromstring(data)
    pts, eles, wpts = [], [], []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in ("trkpt", "rtept"):
            lat, lon = float(el.get("lat")), float(el.get("lon"))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                pts.append((lat, lon))
                try:
                    e = float(_child(el, "ele"))
                    eles.append(e if -500 < e < 9000 else None)
                except ValueError:
                    eles.append(None)
        elif tag == "wpt":
            wpts.append({"lat": float(el.get("lat")), "lon": float(el.get("lon")), "name": _child(el, "name")[:40],
                         "desc": (_child(el, "desc") or _child(el, "cmt"))[:120], "type": _child(el, "type")[:40], "sym": _child(el, "sym")[:40]})
    if len(pts) < 2:
        raise ValueError("Il file GPX non contiene una traccia valida (servono almeno 2 punti)")
    return pts, wpts, eles


def profile(eles, dist, n=400):
    """Profilo altimetrico ricampionato su n punti equidistanti e smussato; None se le quote non sono affidabili."""
    ok = [e for e in eles if e is not None]
    if len(ok) < max(2, 0.8 * len(eles)):
        return None
    filled, last = [], ok[0]
    for e in eles:
        last = e if e is not None else last
        filled.append(last)
    import bisect
    total, out = dist[-1] or 1, []
    for k in range(n):
        m = total * k / (n - 1)
        i = min(max(bisect.bisect_left(dist, m), 1), len(dist) - 1)
        seg = dist[i] - dist[i - 1] or 1
        out.append(lerp(filled[i - 1], filled[i], (m - dist[i - 1]) / seg))
    sm = [sum(out[max(0, k - 3):k + 4]) / len(out[max(0, k - 3):k + 4]) for k in range(n)]
    return sm


def km_on_track(pts, dist, lat, lon):
    best = min(range(len(pts)), key=lambda i: (pts[i][0] - lat) ** 2 + ((pts[i][1] - lon) * math.cos(math.radians(lat))) ** 2)
    return round(dist[best] / 1000, 2), hav(pts[best], (lat, lon))


def locate(pts, dist, m):
    import bisect
    i = min(max(bisect.bisect_left(dist, m), 1), len(dist) - 1)
    seg = dist[i] - dist[i - 1] or 1
    t = (m - dist[i - 1]) / seg
    return lerp(pts[i - 1][0], pts[i][0], t), lerp(pts[i - 1][1], pts[i][1], t)


def hav(a, b):
    r = 6371008.8
    la1, la2, dl = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def cumdist(pts):
    d = [0.0]
    for a, b in zip(pts, pts[1:]):
        d.append(d[-1] + hav(a, b))
    return d


def summary(data: bytes) -> dict:
    pts, wpts, eles = parse_gpx(data)
    d = cumdist(pts)
    lats, lons = [p[0] for p in pts], [p[1] for p in pts]
    step = max(1, len(pts) // 400)
    prof = profile(eles, d)
    aid = []
    for w in wpts:
        if is_aid(w) and len(aid) < 30:
            k, off = km_on_track(pts, d, w["lat"], w["lon"])
            if off <= 300:  # solo ristori vicini al tracciato
                aid.append({"name": w["name"] or "Ristoro", "km": k, "desc": w["desc"], "lat": w["lat"], "lon": w["lon"], "source": "gpx"})
    out = {"points": len(pts), "distance_m": round(d[-1], 1), "bbox": [min(lons), min(lats), max(lons), max(lats)],
           "waypoints": [{k: w[k] for k in ("lat", "lon", "name")} for w in wpts if not is_aid(w)][:30],
           "preview": [[p[1], p[0]] for p in pts[::step]] + [[pts[-1][1], pts[-1][0]]],
           "has_elevation": bool(prof), "aid_detected": sorted(aid, key=lambda a: a["km"])}
    if prof:
        out.update(ele_min=round(min(prof)), ele_max=round(max(prof)), ele_gain=round(sum(max(0, b - a) for a, b in zip(prof, prof[1:]))))
    return out


# ---------------- proiezione ----------------
def world_px(lat, lon, z):
    n = TS * (2 ** z)
    x = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


# ---------------- provider cartografici ----------------
class OpenFreeMapProvider:
    name = "openfreemap"

    def __init__(self, cache):
        self.cache = cache
        os.makedirs(cache, exist_ok=True)
        tj = os.path.join(cache, "tilejson.json")
        if not os.path.exists(tj) or os.path.getmtime(tj) < __import__("time").time() - 86400 * 7:
            with urllib.request.urlopen(urllib.request.Request("https://tiles.openfreemap.org/planet", headers=UA), timeout=20) as r:
                open(tj, "wb").write(r.read())
        self.url = json.load(open(tj))["tiles"][0]

    def _pbf(self, z, x, y):
        p = os.path.join(self.cache, f"{z}_{x}_{y}.pbf")
        if os.path.exists(p):
            return open(p, "rb").read()
        with urllib.request.urlopen(urllib.request.Request(self.url.format(z=z, x=x, y=y), headers=UA), timeout=30) as r:
            d = r.read()
        if d:
            open(p, "wb").write(d)
        return d

    def tile(self, z, x, y, st):
        """I dati vettoriali arrivano fino a z14: oltre, il tile padre viene disegnato a risoluzione maggiore (overzoom)."""
        if z <= 14:
            return self._render(z, x, y, st, TS)
        dz = z - 14
        key = (x >> dz, y >> dz)
        if not hasattr(self, "_pc"):
            self._pc = {}
        if key not in self._pc:
            self._pc[key] = self._render(14, key[0], key[1], st, TS << dz)
        self._pimg = self._pc[key]
        ox, oy = (x - (key[0] << dz)) * TS, (y - (key[1] << dz)) * TS
        return self._pimg.crop((ox, oy, ox + TS, oy + TS))

    def _render(self, z, x, y, st, size):
        import mapbox_vector_tile
        d = self._pbf(z, x, y)
        if d[:2] == b"\x1f\x8b":
            d = gzip.decompress(d)
        layers = mapbox_vector_tile.decode(d, default_options={"y_coord_down": True}) if d else {}
        S = 2 if size <= TS else 1
        TSZ = size * S
        im = Image.new("RGB", (TSZ, TSZ), st["bg"])
        dr = ImageDraw.Draw(im)
        lw = size / TS

        def polys(f):
            g = f["geometry"]
            if g["type"] == "Polygon":
                return [g["coordinates"]]
            return g["coordinates"] if g["type"] == "MultiPolygon" else []

        def lines(f):
            g = f["geometry"]
            if g["type"] == "LineString":
                return [g["coordinates"]]
            return g["coordinates"] if g["type"] == "MultiLineString" else []

        def fill(layer, color, ok=lambda p: True):
            L = layers.get(layer)
            if not L:
                return
            k = TSZ / L.get("extent", 4096)
            for f in L["features"]:
                if ok(f["properties"]):
                    for poly in polys(f):
                        ring = [(px * k, py * k) for px, py in poly[0]]
                        if len(ring) > 2:
                            dr.polygon(ring, fill=color)
                        for hole in poly[1:]:
                            if len(hole) > 2:
                                dr.polygon([(px * k, py * k) for px, py in hole], fill=st["bg"])

        def stroke(layer, color_w):
            L = layers.get(layer)
            if not L:
                return
            k = TSZ / L.get("extent", 4096)
            for f in L["features"]:
                cw = color_w(f["properties"])
                if cw:
                    for ln in lines(f):
                        if len(ln) > 1:
                            dr.line([(px * k, py * k) for px, py in ln], fill=cw[0], width=max(1, int(cw[1] * S * lw)), joint="curve")

        green = {"grass", "wood", "forest", "park", "meadow", "farmland", "scrub", "pitch", "cemetery", "garden"}
        fill("landcover", st["green"], lambda p: p.get("class") in green or p.get("subclass") in green)
        fill("landuse", st["green"], lambda p: p.get("class") in green)
        fill("park", st["green"])
        fill("water", st["water"])
        stroke("waterway", lambda p: (st["water"], 3 if p.get("class") == "river" else 1.5))
        if z >= 13:
            fill("building", st["building"])
        major = {"motorway": 7, "trunk": 6, "primary": 5, "secondary": 4.5, "tertiary": 4}
        minor = {"minor": 3, "service": 2, "track": 1.5, "path": 1.2, "residential": 3}
        stroke("transportation", lambda p: (st["road"], minor[p["class"]]) if p.get("class") in minor else None)
        stroke("transportation", lambda p: (st["major"], major[p["class"]]) if p.get("class") in major else None)
        return im.resize((size, size), Image.LANCZOS) if S > 1 else im


class MapTilerRasterProvider:
    """Predisposto per MapTiler Flex (satellite e stili avanzati): richiede MAPTILER_VIDEO_KEY senza restrizioni di dominio."""
    name = "maptiler"
    MAPS = {"dark": "dataviz-dark", "streets": "streets-v2", "satellite": "satellite"}

    def __init__(self, cache):
        self.cache, self.key = cache, os.environ["MAPTILER_VIDEO_KEY"]
        os.makedirs(cache, exist_ok=True)

    def tile(self, z, x, y, st):
        p = os.path.join(self.cache, f"mt_{st['map']}_{z}_{x}_{y}.img")
        if not os.path.exists(p):
            u = f"https://api.maptiler.com/maps/{self.MAPS.get(st['map'], 'streets-v2')}/512/{z}/{x}/{y}.png?key={self.key}"
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
                open(p, "wb").write(r.read())
        return Image.open(p).convert("RGB").resize((TS, TS))


def provider(cache):
    return MapTilerRasterProvider(cache) if os.environ.get("EVENTMAP_MAP_PROVIDER") == "maptiler" else OpenFreeMapProvider(cache)


# ---------------- grafica ----------------
def font(size, bold=True):
    return ImageFont.truetype(os.path.join(ASSETS, "fonts", "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"), int(size))


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def fmt_km(m):
    return f"{m / 1000:.1f}".replace(".", ",") + " km"


class Renderer:
    def __init__(self, job):
        self.job = job
        self.W, self.H = SIZES[job.get("format", "9:16")]
        self.U = min(self.W, self.H) / 1080
        self.st = dict(STYLES.get(job.get("style", "dark"), STYLES["dark"]), map=job.get("style", "dark"))
        pts, wpts, eles = parse_gpx(open(job["gpx_path"], "rb").read())
        self.wpts = [w for w in wpts if not is_aid(w)]
        self.dist = cumdist(pts)
        self.total = self.dist[-1]
        dm = job.get("distance_display_m")
        self.k = dm / self.total if dm and self.total else 1.0
        self.total_label = (f"{dm / 1000:.3f}".rstrip("0").rstrip(".").replace(".", ",") + " km") if dm else fmt_km(self.total)
        self.sp = SPEEDS.get(job.get("speed"), SPEEDS["normal"])
        self.t_fin = self.sp["t_end"] + 0.04
        self.t_settle = min(0.95, self.t_fin + 0.08)  # scena finale ferma negli ultimi istanti
        self.prof = profile(eles, self.dist) if job.get("show_elevation", True) else None
        self.aid = [dict(a, m=min(self.total, max(0.0, float(a["km"]) * 1000))) for a in (job.get("aid_stations") or [])] if job.get("show_aid", True) else []
        lat_c = sum(p[0] for p in pts) / len(pts)
        span_m = max(hav((min(p[0] for p in pts), min(p[1] for p in pts)), (max(p[0] for p in pts), max(p[1] for p in pts))), 300)
        z = 15
        while z > 10:
            mpp = 156543.03 * math.cos(math.radians(lat_c)) / (2 ** z) / (TS / 256)
            if span_m / mpp * 1.6 <= 7000:
                break
            z -= 1
        self.z, self.mpp = z, mpp
        wp = [world_px(a, b, z) for a, b in pts]
        xs, ys = [p[0] for p in wp], [p[1] for p in wp]
        pad = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.35 + 600
        tx0, ty0 = int((min(xs) - pad) // TS), int((min(ys) - pad) // TS)
        tx1, ty1 = int((max(xs) + pad) // TS), int((max(ys) + pad) // TS)
        self.ox, self.oy = tx0 * TS, ty0 * TS
        prov = provider(job["cache_dir"])
        self.attribution = ATTR[prov.name]
        self.mosaic = Image.new("RGB", ((tx1 - tx0 + 1) * TS, (ty1 - ty0 + 1) * TS), self.st["bg"])
        n = (tx1 - tx0 + 1) * (ty1 - ty0 + 1)
        for i, (tx, ty) in enumerate((a, b) for a in range(tx0, tx1 + 1) for b in range(ty0, ty1 + 1)):
            self.mosaic.paste(prov.tile(z, tx, ty, self.st), ((tx - tx0) * TS, (ty - ty0) * TS))
            if i % 10 == 0:
                print(f"PROGRESS {int(15 * i / n)}", flush=True)
        self.pts = [(x - self.ox, y - self.oy) for x, y in wp]
        self.wp_px = [dict(w, xy=(lambda q: (q[0] - self.ox, q[1] - self.oy))(world_px(w["lat"], w["lon"], z))) for w in self.wpts]
        bx0, by0, bx1, by1 = min(p[0] for p in self.pts), min(p[1] for p in self.pts), max(p[0] for p in self.pts), max(p[1] for p in self.pts)
        self.full_c = ((bx0 + bx1) / 2, (by0 + by1) / 2)
        ar = self.W / self.H
        fw = max(bx1 - bx0, (by1 - by0) * ar) * 1.3
        self.full_w = fw
        self.follow_w = min(max(min(fw * 0.45, 1400 / self.mpp * (self.W / 1080)), self.W * 0.55) * self.sp["zoom"], fw)
        for a in self.aid:
            a["xy"] = self.point_at(a["m"])[0]
        self.logo = self._fit(job.get("logo_path"), *LOGO_BOX[job.get("format", "9:16")], self.U)
        self.static = self._static()
        self.chart = self._chart() if self.prof else None
        self._final_frame(bx1 - bx0, by1 - by0)

    def _final_frame(self, bw, bh):
        """Inquadratura finale: il percorso intero sta tra la scheda titolo e l'altimetria, senza esserne coperto."""
        U = self.U
        top = max(int(self.H * 0.07), self.logo_bottom() + int(20 * U)) + int(232 * U)
        bottom = (self.cbox[1] - int(24 * U)) if self.chart else self.H - int(120 * U)
        rh = max(bottom - top, self.H * 0.3)
        self.fin_w = max(bw * 1.15, bh * 1.15 * self.W / rh, self.W * 0.5)
        k = self.fin_w / self.W
        self.fin_c = (self.full_c[0], self.full_c[1] - ((top + bottom) / 2 - self.H / 2) * k)

    def _img(self, path, h):
        if not path or not os.path.exists(path):
            return None
        try:
            im = Image.open(path).convert("RGBA")
            return im.resize((max(1, int(im.width * h / im.height)), h), Image.LANCZOS)
        except Exception:
            return None

    def _fit(self, path, bw, bh, U):
        """Logo evento ridimensionato nel riquadro del formato, proporzioni originali."""
        if not path or not os.path.exists(path):
            return None
        try:
            im = Image.open(path).convert("RGBA")
            bb = im.getchannel("A").getbbox()
            im = im.crop(bb) if bb else im
            k = min(bw * U / im.width, bh * U / im.height)
            return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
        except Exception:
            return None

    def logo_bottom(self):
        return (int(LOGO_MARGIN * self.U) + self.logo.height + int(2 * LOGO_PAD * self.U)) if self.logo else 0

    def _static(self):
        """Elementi fissi: Powered by CRMEvent (non rimovibile) e attribuzione OpenStreetMap."""
        ov = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        U = self.U
        lg = self._img(os.path.join(ASSETS, "crmevent-logo.png"), int(30 * U))
        f = font(15 * U, False)
        pw, ph = lg.width + int(28 * U), lg.height + int(34 * U)
        x, y = self.W - pw - int(28 * U), self.H - ph - int(28 * U)
        self.pb_x = x
        d.rounded_rectangle((x, y, x + pw, y + ph), radius=int(12 * U), fill=(255, 255, 255, 225))
        d.text((x + int(14 * U), y + int(6 * U)), "Powered by", font=f, fill=(71, 85, 105, 255))
        ov.alpha_composite(lg, (x + int(14 * U), y + int(24 * U)))
        if self.logo:  # logo evento fisso in alto a destra per tutto il video
            p, mg = int(LOGO_PAD * U), int(LOGO_MARGIN * U)
            lx, ly = self.W - mg - self.logo.width - 2 * p, mg
            d.rounded_rectangle((lx, ly, lx + self.logo.width + 2 * p, ly + self.logo.height + 2 * p), radius=int(16 * U), fill=(255, 255, 255, 215))
            ov.alpha_composite(self.logo, (lx + p, ly + p))
        d.text((int(24 * U), self.H - int(30 * U)), self.attribution, font=font(13 * U, False), fill=(255, 255, 255, 170) if self.job.get("style") != "streets" else (40, 40, 40, 190))
        return ov

    def _chart(self):
        """Fascia altimetrica in basso (a sinistra del Powered by): versione spenta e accesa del profilo, ritagliata a ogni fotogramma."""
        U = self.U
        x0, x1 = int(36 * U), self.pb_x - int(16 * U)
        h = int(CHART_H[self.job.get("format", "9:16")] * U)
        y1 = self.H - int(52 * U)
        self.cbox = (x0, y1 - h, x1, y1)
        w = x1 - x0
        lo, hi = min(self.prof), max(self.prof)
        rng = max(hi - lo, 20)
        top, bot, pad = int(46 * U), int(14 * U), int(18 * U)
        self.c_x = lambda m: pad + (w - 2 * pad) * m / (self.total or 1)
        self.c_y = lambda e: top + (h - top - bot) * (1 - (e - lo) / rng)
        n = len(self.prof)
        line = [(self.c_x(self.total * k / (n - 1)), self.c_y(e)) for k, e in enumerate(self.prof)]
        area = line + [(line[-1][0], h - bot), (line[0][0], h - bot)]
        bg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(bg).rounded_rectangle((0, 0, w - 1, h - 1), radius=int(20 * U), fill=(10, 14, 22, 228))
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # disegnati a parte e poi fusi: ImageDraw sostituisce i pixel invece di sovrapporli
        d = ImageDraw.Draw(lay)
        d.polygon(area, fill=(255, 255, 255, 40))
        d.line(line, fill=(255, 255, 255, 120), width=max(2, int(3 * U)), joint="curve")
        d.text((w - pad, int(16 * U)), f"{round(lo)}–{round(hi)} m", font=font(18 * U, False), fill=(148, 163, 184, 255), anchor="rt")
        for a in self.aid:  # ristori anche sul profilo
            ax = self.c_x(a["m"])
            d.line((ax, top - 4 * U, ax, h - bot), fill=(56, 189, 248, 150), width=max(1, int(2 * U)))
        dim = Image.alpha_composite(bg, lay)
        lay2 = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        hd = ImageDraw.Draw(lay2)
        hd.polygon(area, fill=self.st["route"] + (150,))
        hd.line(line, fill=self.st["route"] + (255,), width=max(3, int(4 * U)), joint="curve")
        hot = Image.alpha_composite(dim, lay2)
        return dim, hot

    def ele_at(self, m):
        f = (len(self.prof) - 1) * m / (self.total or 1)
        i = min(int(f), len(self.prof) - 2)
        return lerp(self.prof[i], self.prof[i + 1], f - i)

    def draw_chart(self, base, m, alpha):
        dim, hot = self.chart
        x0, y0, _, _ = self.cbox
        layer = dim.copy()
        cx = int(self.c_x(m))
        if cx > 0:
            layer.paste(hot.crop((0, 0, cx, hot.height)), (0, 0))
        top_l = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(top_l)
        U, e = self.U, self.ele_at(m)
        cy = self.c_y(e)
        d.line((cx, int(40 * U), cx, layer.height - int(14 * U)), fill=(255, 255, 255, 200), width=max(1, int(2 * U)))
        r = int(9 * U)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=self.st["route"] + (255,), width=max(2, int(4 * U)))
        d.text((int(18 * U), int(14 * U)), f"{fmt_km(m)}  ·  quota {round(e)} m", font=font(22 * U), fill=(255, 255, 255, 255))
        layer.alpha_composite(top_l)
        if alpha < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
        base.alpha_composite(layer, (x0, y0))

    def draw_aid(self, d, tr, m, t):
        U = self.U
        win = max(self.total * 0.035, 150)
        for a in self.aid:
            px, py = tr(a["xy"])
            if not (-60 < px < self.W + 60 and -60 < py < self.H + 60):
                continue
            k = max(0.0, 1 - abs(m - a["m"]) / win) if t < self.t_fin else 0.0
            r = int((16 + 8 * k) * U)
            if k > 0:
                rr = r + int(18 * U * k)
                d.ellipse((px - rr, py - rr, px + rr, py + rr), outline=(56, 189, 248, int(220 * k)), width=max(2, int(4 * U)))
            d.ellipse((px - r, py - r, px + r, py + r), fill=(14, 165, 233, 255), outline=(255, 255, 255, 255), width=max(2, int(3 * U)))
            c = r * 0.5  # icona bicchiere
            d.polygon([(px - c, py - c), (px + c, py - c), (px + c * 0.65, py + c), (px - c * 0.65, py + c)], fill=(255, 255, 255, 255))
            if k > 0.25:
                a8 = int(255 * min(1, (k - 0.25) / 0.3))
                f1, f2 = font(26 * U), font(20 * U, False)
                sub = f"km {str(a['km']).replace('.', ',')}" + (f" · {a['desc'][:34]}" if a.get("desc") else "")
                tw = max(d.textlength(a["name"], font=f1), d.textlength(sub, font=f2), d.textlength("RISTORO", font=f2))
                bx0, by1 = px - tw / 2 - 16 * U, py - r - 14 * U
                d.rounded_rectangle((bx0, by1 - 96 * U, bx0 + tw + 32 * U, by1), radius=int(12 * U), fill=(8, 47, 73, int(a8 * 0.92)))
                d.text((px, by1 - 86 * U), "RISTORO", font=f2, fill=(125, 211, 252, a8), anchor="mt")
                d.text((px, by1 - 62 * U), a["name"], font=f1, fill=(255, 255, 255, a8), anchor="mt")
                d.text((px, by1 - 32 * U), sub, font=f2, fill=(186, 230, 253, a8), anchor="mt")

    def point_at(self, m):
        import bisect
        i = min(max(bisect.bisect_left(self.dist, m), 1), len(self.dist) - 1)
        a, b = self.pts[i - 1], self.pts[i]
        seg = self.dist[i] - self.dist[i - 1] or 1
        t = (m - self.dist[i - 1]) / seg
        return (lerp(a[0], b[0], t), lerp(a[1], b[1], t)), i

    def cam_follow(self, m):
        w = max(self.total * self.sp["win"], 200)
        xs = [self.point_at(min(self.total, max(0, m + k * w / 4)))[0] for k in range(-4, 5)]
        return (sum(p[0] for p in xs) / len(xs), sum(p[1] for p in xs) / len(xs))

    def progress(self, t):
        """Metri percorsi al tempo t: accelerazione e frenata morbide, percorso completo a t_end."""
        a, b = self.sp["t_in"], self.sp["t_end"]
        p = min(1.0, max(0.0, (t - a) / (b - a)))
        return self.total * (0.8 * p + 0.2 * ease(p))

    def t_for(self, m):
        lo, hi = self.sp["t_in"], self.sp["t_end"]
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if self.progress(mid) < m else (lo, mid)
        return hi

    def camera(self, t):
        """Scene: intro (avvicinamento) · partenza · percorso con camera che segue · arrivo · finale panoramico."""
        a, b = self.sp["t_in"], self.sp["t_end"]
        if t < a:
            k = ease(t / a)
            c0, c1 = self.full_c, self.cam_follow(0)
            w = math.exp(lerp(math.log(self.full_w * 1.8), math.log(self.follow_w), k))
            return (lerp(c0[0], c1[0], k), lerp(c0[1], c1[1], k)), w, 0.0
        if t < b:
            m = self.progress(t)
            p = (t - a) / (b - a)
            return self.cam_follow(m), self.follow_w * (1 + self.sp["wob"] * math.sin(p * math.pi * 2)), m
        if t < self.t_fin:
            return self.cam_follow(self.total), self.follow_w, self.total
        k = ease((t - self.t_fin) / (self.t_settle - self.t_fin))
        c0 = self.cam_follow(self.total)
        w = math.exp(lerp(math.log(self.follow_w), math.log(self.fin_w), k))
        return (lerp(c0[0], self.fin_c[0], k), lerp(c0[1], self.fin_c[1], k)), w, self.total

    def card(self, ov, d, alpha, big=False):
        U, j = self.U, self.job
        a = int(255 * alpha)
        tf, df = font((64 if big else 54) * U), font(30 * U, False)
        title = j.get("title") or "Evento"
        while d.textlength(title, font=tf) > self.W - 140 * U and len(title) > 8:
            title = title[:-2]
        sub = (j.get("subtitle") or "").strip()
        sf = font(34 * U)
        while sub and d.textlength(sub, font=sf) > self.W - 140 * U and len(sub) > 8:
            sub = sub[:-2]
        h = int(64 * U) + int(48 * U) + int(40 * U) + (int(48 * U) if sub else 0)
        y = max(int(self.H * (0.07 if big else 0.08)), self.logo_bottom() + int(20 * U))
        d.rounded_rectangle((int(48 * U), y, self.W - int(48 * U), y + h + (int(60 * U) if big else 0)), radius=int(28 * U), fill=(10, 14, 22, int(200 * alpha)))
        cy = y + int(26 * U)
        d.text((self.W / 2, cy), title, font=tf, fill=(255, 255, 255, a), anchor="mt")
        cy += int(72 * U)
        if sub:
            d.text((self.W / 2, cy), sub, font=sf, fill=self.st["route"] + (a,), anchor="mt")
            cy += int(48 * U)
        if j.get("date"):
            d.text((self.W / 2, cy), j["date"], font=df, fill=(203, 213, 225, a), anchor="mt")
            cy += int(46 * U)
        if big:
            d.text((self.W / 2, cy), self.total_label, font=font(58 * U), fill=self.st["route"] + (a,), anchor="mt")

    def frame(self, t):
        (cx, cy), w, m = self.camera(t)
        h = w * self.H / self.W
        x0, y0 = cx - w / 2, cy - h / 2
        base = self.mosaic.transform((self.W, self.H), Image.EXTENT, (x0, y0, x0 + w, y0 + h), Image.BILINEAR, fillcolor=self.st["bg"]).convert("RGBA")
        s = self.W / w
        tr = lambda p: ((p[0] - x0) * s, (p[1] - y0) * s)
        U = self.U
        lw = max(4, int(9 * U))
        ov = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        full = [tr(p) for p in self.pts]
        d.line(full, fill=(255, 255, 255, 70), width=max(2, lw // 2), joint="curve")
        head, i = self.point_at(m)
        done = [tr(p) for p in self.pts[:i]] + [tr(head)]
        glow = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        if len(done) > 1:
            ImageDraw.Draw(glow).line(done, fill=self.st["glow"] + (150,), width=lw * 3, joint="curve")
            glow = glow.filter(ImageFilter.GaussianBlur(lw))
        base.alpha_composite(glow)
        if len(done) > 1:
            d.line(done, fill=self.st["route"] + (255,), width=lw, joint="curve")
        r = int(16 * U)
        sx, sy = tr(self.pts[0])
        d.ellipse((sx - r, sy - r, sx + r, sy + r), fill=(22, 163, 74, 255), outline=(255, 255, 255, 255), width=max(2, int(4 * U)))
        if m >= self.total - 1:
            fx, fy = tr(self.pts[-1])
            d.ellipse((fx - r, fy - r, fx + r, fy + r), fill=(15, 23, 42, 255), outline=(255, 255, 255, 255), width=max(2, int(4 * U)))
            d.text((fx, fy - r - 8 * U), "ARRIVO", font=font(26 * U), fill=(255, 255, 255, 255), anchor="mb", stroke_width=int(4 * U), stroke_fill=(0, 0, 0, 200))
        if t < self.sp["t_in"] + 0.13:
            d.text((sx, sy - r - 8 * U), "PARTENZA", font=font(26 * U), fill=(255, 255, 255, 255), anchor="mb", stroke_width=int(4 * U), stroke_fill=(0, 0, 0, 200))
        for wpt in self.wp_px:
            px, py = tr(wpt["xy"])
            if -50 < px < self.W + 50 and -50 < py < self.H + 50:
                d.ellipse((px - 9 * U, py - 9 * U, px + 9 * U, py + 9 * U), fill=(250, 204, 21, 255), outline=(15, 23, 42, 255), width=max(1, int(3 * U)))
                near = math.hypot(px - tr(head)[0], py - tr(head)[1]) < 260 * U
                if wpt["name"] and near:
                    f = font(26 * U)
                    tw = d.textlength(wpt["name"], font=f)
                    d.rounded_rectangle((px - tw / 2 - 14 * U, py - 66 * U, px + tw / 2 + 14 * U, py - 22 * U), radius=int(10 * U), fill=(15, 23, 42, 230))
                    d.text((px, py - 44 * U), wpt["name"], font=f, fill=(255, 255, 255, 255), anchor="mm")
        self.draw_aid(d, tr, m, t)
        a_in, fin = self.sp["t_in"] * 0.8, self.t_fin
        if a_in < t < fin + 0.02:
            hx, hy = tr(head)
            d.ellipse((hx - 14 * U, hy - 14 * U, hx + 14 * U, hy + 14 * U), fill=(255, 255, 255, 255), outline=self.st["route"] + (255,), width=max(3, int(6 * U)))
        if t < self.sp["t_in"] + 0.04:
            self.card(ov, d, 1.0 if t < self.sp["t_in"] else 1 - (t - self.sp["t_in"]) / 0.04)
        elif t > fin + 0.02:
            self.card(ov, d, min(1.0, (t - fin - 0.02) / 0.04), big=True)
        if a_in < t < fin + 0.04:
            a = int(255 * min(1, (t - a_in) / 0.03, (fin + 0.04 - t) / 0.03))
            bw, bh = int(420 * U), int(164 * U)
            bx, by = int(36 * U), (self.cbox[1] - bh - int(16 * U)) if self.chart else self.H - bh - int(70 * U)
            d.rounded_rectangle((bx, by, bx + bw, by + bh), radius=int(22 * U), fill=(10, 14, 22, int(a * 0.82)))
            d.text((bx + 26 * U, by + 18 * U), (self.job.get("title") or "")[:26].upper(), font=font(20 * U), fill=(148, 163, 184, a))
            d.text((bx + 26 * U, by + 46 * U), fmt_km(m * self.k), font=font(62 * U), fill=(255, 255, 255, a))
            d.text((bx + 26 * U, by + 112 * U), f"di {self.total_label}", font=font(22 * U, False), fill=(203, 213, 225, a))
            pw = bw - int(52 * U)
            d.rounded_rectangle((bx + 26 * U, by + bh - 14 * U, bx + 26 * U + pw, by + bh - 8 * U), radius=3, fill=(255, 255, 255, int(a * 0.25)))
            d.rounded_rectangle((bx + 26 * U, by + bh - 14 * U, bx + 26 * U + max(6, pw * m / self.total), by + bh - 8 * U), radius=3, fill=self.st["route"] + (a,))
        base.alpha_composite(ov)
        if self.chart and t > self.sp["t_in"] * 0.8:
            self.draw_chart(base, m, min(1.0, (t - self.sp["t_in"] * 0.8) / 0.03))
        base.alpha_composite(self.static)
        return base.convert("RGB")


def render(job):
    R = Renderer(job)
    if job.get("still"):  # anteprima: un momento lungo il percorso (primo ristoro o metà) + scena finale
        m = R.aid[0]["m"] if R.aid else R.total / 2
        a, b = R.frame(R.t_for(m)), R.frame(1.0)
        k = min(1.0, 1600 / (2 * R.W))
        sw, sh = int(R.W * k), int(R.H * k)
        out = Image.new("RGB", (sw * 2 + 16, sh), (255, 255, 255))
        out.paste(a.resize((sw, sh), Image.LANCZOS), (0, 0))
        out.paste(b.resize((sw, sh), Image.LANCZOS), (sw + 16, 0))
        out.save(job["out_path"], "JPEG", quality=85)
        return
    dur = int(job["duration"])
    n = dur * FPS
    ff = job["ffmpeg"]
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{R.W}x{R.H}", "-r", str(FPS), "-i", "-"]
    music = job.get("music_path")
    if music:
        cmd += ["-stream_loop", "-1", "-i", music, "-af", f"afade=t=in:d=0.5,afade=t=out:st={dur - 2.5}:d=2.5", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-t", str(dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", job["out_path"]]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k in range(n):
        p.stdin.write(R.frame(k / (n - 1)).tobytes())
        if k % FPS == 0:
            print(f"PROGRESS {15 + int(83 * k / n)}", flush=True)
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("Codifica FFmpeg non riuscita")
    print("PROGRESS 100", flush=True)


if __name__ == "__main__":
    try:
        render(json.load(open(sys.argv[1])))
    except Exception as e:
        print(f"ERROR {type(e).__name__}: {e}", flush=True)
        sys.exit(1)
