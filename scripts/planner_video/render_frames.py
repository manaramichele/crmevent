"""Video promozionale Event Planner: cattura fotogramma per fotogramma dell'interfaccia reale (anteprima) con mappa MapTiler.
Ogni fotogramma viene catturato a mappa ferma, quindi il video è fluido anche se il rendering WebGL è lento.
Uso: nohup python3 render_frames.py > render.log 2>&1 &   poi   bash encode.sh
Crea un'organizzazione TEST_ temporanea (va cancellata dopo)."""
import asyncio, json, math, shutil, time, uuid
from pathlib import Path
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
OUT = Path(__file__).parent / "frames"
W, H, FPS = 1280, 720, 25
ROUTE = [[9.1729, 45.4754], [9.1712, 45.4741], [9.1703, 45.4726], [9.1718, 45.4711], [9.1741, 45.4700], [9.1768, 45.4693], [9.1792, 45.4699],
         [9.1806, 45.4714], [9.1802, 45.4731], [9.1785, 45.4746], [9.1760, 45.4757], [9.1740, 45.4759], [9.1729, 45.4754]]

OVERLAY_JS = """() => {
  const s = document.createElement('style');
  s.textContent = `[data-testid=event-planner]{position:fixed!important;inset:0!important;height:100vh!important;z-index:60;background:#fff}
    [role=dialog],[data-testid=cookie-banner]{display:none!important}
    body{pointer-events:auto!important} [data-radix-popper-content-wrapper],[data-state=open][data-aria-hidden]{display:none!important}
    #rec-cur{position:fixed;z-index:100001;width:26px;height:26px;pointer-events:none;left:-50px;top:-50px;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}
    #rec-ring{position:fixed;z-index:100000;width:34px;height:34px;border-radius:99px;border:3px solid #0ABAB5;pointer-events:none;opacity:0;transform:translate(-50%,-50%)}
    #rec-cap{pointer-events:none;position:fixed;left:50%;bottom:30px;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.9);color:#fff;font:700 21px/1.25 Manrope,Inter,sans-serif;padding:12px 24px;border-radius:999px;box-shadow:0 12px 40px rgba(0,0,0,.25);display:flex;gap:12px;align-items:center;white-space:nowrap;opacity:0}
    #rec-cap i{width:11px;height:11px;border-radius:99px;background:#0ABAB5;display:inline-block}
    #rec-end{position:fixed;inset:0;z-index:100002;pointer-events:none;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;opacity:0;font-family:Manrope,Inter,sans-serif;text-align:center;padding:0 40px}`;
  document.head.appendChild(s);
  document.body.insertAdjacentHTML('beforeend', `<svg id="rec-cur" viewBox="0 0 24 24"><path d="M4 2l15 9-6.5 1.5L16 20l-3 1.5-3.4-7.4L4 19z" fill="#fff" stroke="#0f172a" stroke-width="1.6" stroke-linejoin="round"/></svg>
    <div id="rec-ring"></div><div id="rec-cap"></div>
    <div id="rec-end"><img src="/logo-crmevent.png" style="height:70px"><div style="font-size:30px;font-weight:800;color:#0f172a">Il tuo evento prende forma, direttamente sulla mappa.</div>
    <div style="font-size:18px;color:#475569">Event Planner è una delle funzionalità di CRMEvent</div>
    <div style="margin-top:8px;background:#0ABAB5;color:#0f172a;font-weight:700;font-size:20px;padding:12px 30px;border-radius:12px">Registrati a CRMEvent</div></div>`);
}"""


class Rec:
    def __init__(self, page):
        self.p, self.n, self.cur = page, 0, [W * 0.6, H * 0.5]

    async def shot(self):
        self.n += 1
        for _ in range(4):
            try:
                await asyncio.wait_for(self.p.screenshot(path=str(OUT / f"f{self.n:05d}.jpg"), type="jpeg", quality=88, timeout=25000), 30)
                return
            except Exception as e:
                print("  shot retry", self.n, str(e)[:60], flush=True)
        raise RuntimeError("screenshot fallito")

    async def hold(self, frames):
        last = OUT / f"f{self.n:05d}.jpg"
        for _ in range(frames):
            self.n += 1
            shutil.copyfile(last, OUT / f"f{self.n:05d}.jpg")

    async def idle(self, ms=5000):
        # Mai chiamate sincrone alla mappa dentro evaluate: le richieste di tile intercettate andrebbero in stallo.
        end = time.time() + ms / 1000
        while time.time() < end:
            await self.p.wait_for_timeout(60)
            if await self.p.evaluate("() => { const m = window.__plannerMap; return m.loaded() && m.areTilesLoaded() && !m.isMoving(); }"):
                break
        await self.p.wait_for_timeout(40)

    async def caption(self, t):
        await self.p.evaluate("(t) => { const c = document.getElementById('rec-cap'); c.innerHTML = t ? '<i></i>' + t : ''; c.style.opacity = t ? 1 : 0; }", t)

    async def set_cursor(self, x, y, ring=0.0):
        await self.p.evaluate("([x,y,r]) => { const c = document.getElementById('rec-cur'); c.style.left = (x-3)+'px'; c.style.top = (y-2)+'px';"
                              " const g = document.getElementById('rec-ring'); g.style.left = x+'px'; g.style.top = y+'px'; g.style.opacity = r; }", [x, y, ring])
        self.cur = [x, y]

    async def move(self, x, y, frames=7):
        x0, y0 = self.cur
        for i in range(1, frames + 1):
            t = i / frames
            e = t * t * (3 - 2 * t)
            await self.set_cursor(x0 + (x - x0) * e, y0 + (y - y0) * e)
            await self.shot()

    async def click(self, x, y, frames=7, after=2):
        await self.move(x, y, frames)
        await self.p.mouse.click(x, y)
        await self.p.wait_for_timeout(120)
        await self.idle(3000)
        for r in (0.9, 0.5):
            await self.set_cursor(x, y, r)
            await self.shot()
        await self.set_cursor(x, y, 0)
        await self.shot()
        await self.hold(after)

    async def xy(self, ll):
        return await self.p.evaluate("([a,b]) => { const m=window.__plannerMap, p=m.project([a,b]), r=m.getCanvas().getBoundingClientRect(); return [r.left+p.x, r.top+p.y]; }", ll)

    async def click_map(self, ll, frames=7, after=2):
        x, y = await self.xy(ll)
        r = await self.p.evaluate("() => { const b = window.__plannerMap.getCanvas().getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; }")
        if not (r[0] + 75 < x < r[2] - 10 and r[1] + 10 < y < r[3] - 10):
            raise RuntimeError(f"punto fuori mappa {ll}")
        await self.click(x, y, frames, after)

    async def click_el(self, sel, frames=8):
        loc = self.p.locator(sel)
        await loc.scroll_into_view_if_needed()
        b = await loc.bounding_box()
        await self.click(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, frames, 1)

    async def camera(self, to, seconds):
        start = await self.p.evaluate("() => { const m=window.__plannerMap, c=m.getCenter(); return {lng:c.lng, lat:c.lat, zoom:m.getZoom(), pitch:m.getPitch(), bearing:m.getBearing()}; }")
        frames = int(seconds * FPS)
        for i in range(1, frames + 1):
            t = i / frames
            e = 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2
            cur = {k: start[k] + (to.get(k, start[k]) - start[k]) * e for k in start}
            await self.p.evaluate("(c) => { setTimeout(() => window.__plannerMap.jumpTo({center:[c.lng,c.lat], zoom:c.zoom, pitch:c.pitch, bearing:c.bearing}), 0); }", cur)
            await self.p.wait_for_timeout(30)
            await self.idle(6000)
            await self.shot()
            if i % 25 == 0:
                print("  camera", i, "/", frames, flush=True)


async def main():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width": W, "height": H})

        cache = {}

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
            except Exception as e:
                print("  tile err", str(e)[:80], flush=True)
                try:
                    await route.abort()
                except Exception:
                    pass
        await ctx.route("https://api.maptiler.com/**", maptiler)
        await ctx.add_init_script("window.__PLANNER_RECORDING = true;")

        rq = ctx.request
        email = f"test_video_{uuid.uuid4().hex[:6]}@example.com"
        r = await rq.post(f"{BASE}/api/auth/register-organization", data={"nome": "Video", "cognome": "Demo", "email": email, "password": "VideoDemo2026!",
                          "org_name": "TEST_Video Planner", "telefono": "+3933312345" + str(int(time.time()) % 90 + 10), "accept_terms": True}, timeout=90000)
        assert r.ok, await r.text()
        (Path(__file__).parent / "test_account.json").write_text(json.dumps({"email": email}))
        ev = await (await rq.post(f"{BASE}/api/events", data={"nome": "Corsa del Parco 10K"})).json()
        pr = await (await rq.post(f"{BASE}/api/planner/events/{ev['id']}/projects", data={"nome": "Planimetria generale"})).json()
        await rq.patch(f"{BASE}/api/planner/projects/{pr['id']}", data={"center": [9.19, 45.4642], "zoom": 11.3})

        page = await ctx.new_page()
        await page.goto(f"{BASE}/eventi/{ev['id']}/planner", wait_until="domcontentloaded")
        for _ in range(40):
            await page.wait_for_timeout(1500)
            if await page.evaluate("() => !!(window.__plannerMap && window.__plannerMap.isStyleLoaded())"):
                break
        for name in ("Reject non-essential", "Rifiuta", "Non ora"):
            try:
                await page.get_by_role("button", name=name).first.click(timeout=1000)
            except Exception:
                pass
        await page.evaluate(OVERLAY_JS)
        await page.evaluate("() => { setTimeout(() => { window.__plannerMap.resize(); window.__plannerMap.jumpTo({center:[9.19,45.4642], zoom:11.3}); }, 0); }")
        await page.wait_for_timeout(1500)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        print("body pointer-events", await page.evaluate("() => getComputedStyle(document.body).pointerEvents"), flush=True)
        rec = Rec(page)
        await rec.idle(15000)
        print("pronto", flush=True)

        await rec.caption("Parti dalla mappa reale della tua città")
        await rec.shot(); await rec.hold(55)
        await rec.caption("Zoom sulla zona dell'evento")
        await rec.camera({"lng": 9.17545, "lat": 45.4726, "zoom": 15.1}, 4.2)
        await rec.hold(8)
        print("percorso", rec.n, flush=True)
        await rec.caption("Disegna il percorso della gara")
        await rec.click_el('[data-testid="planner-tool-line"]')
        print("line tool", await page.locator('[data-testid="planner-tool-line"]').get_attribute("class"), flush=True)
        for ll in ROUTE:
            await rec.click_map(ll, frames=6, after=1)
        await page.evaluate("() => window.__plannerFinish && window.__plannerFinish()")
        await rec.idle(); await rec.shot(); await rec.hold(15)

        async def place(lib, pts):
            for ll in pts:
                await rec.click_el(f'[data-testid="planner-lib-{lib}"]', frames=7)
                await rec.click_map(ll, frames=7, after=3)

        async def line(lib, pts):
            await rec.click_el(f'[data-testid="planner-lib-{lib}"]', frames=7)
            for ll in pts:
                await rec.click_map(ll, frames=5, after=1)
            await page.evaluate("() => window.__plannerFinish && window.__plannerFinish()")
            await rec.idle(); await rec.shot(); await rec.hold(5)

        print("viabilita", rec.n, flush=True)
        await rec.caption("Coni, transenne, accessi e parcheggi")
        await rec.camera({"lng": 9.1729, "lat": 45.4756, "zoom": 16.5}, 1.6)
        await place("lib25", [[9.1721, 45.4749], [9.1726, 45.4746]])
        await line("lib23", [[9.1722, 45.4758], [9.1732, 45.4762], [9.1743, 45.4764]])
        await place("lib28", [[9.1746, 45.4765]])
        await place("lib27", [[9.1712, 45.4766]])
        print("volontari", rec.n, flush=True)
        await rec.caption("Postazioni volontari e punti di controllo")
        await rec.camera({"lng": 9.17545, "lat": 45.4726, "zoom": 15.1}, 1.6)
        await place("lib35", [[9.1703, 45.4726], [9.1806, 45.4714]])
        await place("lib34", [[9.1768, 45.4693]])
        print("sponsor", rec.n, flush=True)
        await rec.caption("Stand sponsor, banner e arco pubblicitario")
        await rec.camera({"lng": 9.1736, "lat": 45.4753, "zoom": 17.3}, 1.6)
        await place("lib33", [[9.1729, 45.4754]])
        await place("lib30", [[9.1738, 45.4748], [9.1743, 45.4750]])
        await line("lib32", [[9.1733, 45.4757], [9.1741, 45.4759]])
        await rec.click_el('[data-testid="planner-tool-select"]')
        await page.keyboard.press("Escape")
        await rec.set_cursor(-50, -50)
        print("finale", rec.n, flush=True)
        await rec.caption("Tutta l'organizzazione dell'evento, in un'unica mappa")
        await rec.camera({"lng": 9.1755, "lat": 45.4730, "zoom": 14.95, "pitch": 40, "bearing": -14}, 3.2)
        await rec.hold(20)
        await rec.caption("")
        for i in range(1, 16):
            await page.evaluate("(o) => { document.getElementById('rec-end').style.opacity = o; }", i / 15)
            await rec.shot()
        await rec.hold(60)
        print("fine", rec.n, "fotogrammi =", round(rec.n / FPS, 1), "s", flush=True)
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
