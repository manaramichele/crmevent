"""Screenshot con griglia per scegliere le coordinate. Uso: python3 probe.py lng lat zoom out.png"""
import asyncio, sys
from playwright.async_api import async_playwright
import mapkit

GRID_JS = """() => { const c = document.createElement('canvas'); c.width = innerWidth; c.height = innerHeight;
  c.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:9'; const g = c.getContext('2d');
  g.strokeStyle = 'rgba(255,0,0,.55)'; g.fillStyle = '#d00'; g.font = 'bold 12px Arial';
  for (let x = 0; x <= innerWidth; x += 100) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, innerHeight); g.stroke(); g.fillText(x, x + 2, 12); }
  for (let y = 0; y <= innerHeight; y += 100) { g.beginPath(); g.moveTo(0, y); g.lineTo(innerWidth, y); g.stroke(); g.fillText(y, 2, y - 2); }
  document.body.appendChild(c); const a = map.unproject([0, 0]), b = map.unproject([innerWidth, innerHeight]);
  return [a.lng, a.lat, b.lng, b.lat]; }"""


async def main(lng, lat, z, out):
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width": 1000, "height": 700})
        await mapkit.setup(ctx, {})
        page = await mapkit.open_map(ctx, [lng, lat], z)
        print("bounds lng0 lat0 lng1 lat1", await page.evaluate(GRID_JS))
        await page.screenshot(path=out)
        await b.close()

asyncio.run(main(float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]))
