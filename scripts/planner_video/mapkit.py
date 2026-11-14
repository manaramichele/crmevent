"""Mappa MapLibre/MapTiler autonoma per i video (Event Map) e per scegliere le coordinate. La chiave resta lato script."""
import os
from pathlib import Path

MAPLIBRE = Path("/app/frontend/node_modules/maplibre-gl/dist")
def _key():
    import subprocess
    pid = subprocess.run(["sudo", "supervisorctl", "pid", "backend"], capture_output=True, text=True).stdout.strip()
    for line in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
        if line.startswith(b"MAPTILER_API_KEY="):
            return line.split(b"=", 1)[1].decode()
    raise RuntimeError("MAPTILER_API_KEY non trovata nel backend")


KEY = os.environ.get("MAPTILER_API_KEY") or _key()
HTML = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/maplibre-gl.css">
<style>html,body,#map{margin:0;height:100%;width:100%;overflow:hidden;font-family:Manrope,Inter,Arial,sans-serif}</style>
<script src="/maplibre-gl.js"></script></head><body><div id="map"></div><script>
window.map = new maplibregl.Map({container:'map', style:'https://api.maptiler.com/maps/streets-v2/style.json?key=__KEY__', center:__C__, zoom:__Z__,
  attributionControl:{compact:false}, fadeDuration:0, preserveDrawingBuffer:true});
</script></body></html>"""


async def setup(ctx, cache: dict, extra: dict = None):
    async def local(route):
        name = route.request.url.split("/")[-1].split("?")[0]
        if name == "index.html":
            await route.fulfill(content_type="text/html", body=ctx._html)
        elif name in (extra or {}):
            p = Path(extra[name])
            await route.fulfill(body=p.read_bytes(), content_type="image/png" if p.suffix == ".png" else "application/octet-stream")
        else:
            await route.fulfill(path=str(MAPLIBRE / name), content_type="text/css" if name.endswith(".css") else "application/javascript")

    async def maptiler(route):
        url = route.request.url
        try:
            if url not in cache:
                h = {**route.request.headers, "origin": "https://crmevent.it", "referer": "https://crmevent.it/"}
                r = await route.fetch(headers=h, timeout=20000)
                hd = {k: v for k, v in r.headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
                item = (r.status, {**hd, "access-control-allow-origin": "*"}, await r.body())
                if r.status != 200:
                    await route.fulfill(status=item[0], headers=item[1], body=item[2])
                    return
                cache[url] = item
            s, hd, body = cache[url]
            await route.fulfill(status=s, headers=hd, body=body)
        except Exception:
            try:
                await route.abort()
            except Exception:
                pass
    await ctx.route("http://local.test/**", local)
    await ctx.route("https://api.maptiler.com/**", maptiler)


async def open_map(ctx, center, zoom):
    ctx._html = HTML.replace("__KEY__", KEY).replace("__C__", str(list(center))).replace("__Z__", str(zoom))
    page = await ctx.new_page()
    await page.goto("http://local.test/index.html", wait_until="domcontentloaded")
    await wait_idle(page, 30)
    return page


async def wait_idle(page, seconds=8):
    for _ in range(int(seconds / 0.1)):
        await page.wait_for_timeout(100)
        if await page.evaluate("() => !!(window.map && map.loaded() && map.areTilesLoaded() && !map.isMoving())"):
            break
    await page.wait_for_timeout(50)
