"""Video Event Planner (City Run Festival, evento di fantasia, percorso dimostrativo) dall'interfaccia reale: fotogramma per fotogramma.
Uso: setsid nohup python3 render_pisa.py > pisa.log 2>&1 &  poi  OUT_NAME=event-planner-demo FRAMES=frames bash encode.sh"""
import asyncio, json, time, uuid
from pathlib import Path
from playwright.async_api import async_playwright
import render_frames as RF
from render_frames import Rec, OVERLAY_JS, BASE

RF.OUT = OUT = Path(__file__).parent / "frames"
ROUTE = json.load(open(Path(__file__).parent / "pisa_route.json"))["simple"]
O = (10.38991, 43.714748)  # origine area operativa nel Parco Urbano della Cittadella


def M(x, y):
    return [round(O[0] + x / 80440, 7), round(O[1] + y / 111130, 7)]


async def main():
    import shutil
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width": 1280, "height": 720})
        import mapkit
        await mapkit.setup(ctx, {})
        await ctx.add_init_script("window.__PLANNER_RECORDING = true;")
        rq = ctx.request
        email = f"test_video_{uuid.uuid4().hex[:6]}@example.com"
        r = await rq.post(f"{BASE}/api/auth/register-organization", data={"nome": "Video", "cognome": "Demo", "email": email, "password": "VideoDemo2026!",
                          "org_name": "TEST_Video Planner", "telefono": "+3933312345" + str(int(time.time()) % 90 + 10), "accept_terms": True}, timeout=90000)
        assert r.ok, await r.text()
        ev = await (await rq.post(f"{BASE}/api/events", data={"nome": "City Run Festival (demo)"})).json()
        oid = (await (await rq.get(f"{BASE}/api/auth/me")).json())["org_id"]
        sa = await pw.request.new_context()
        assert (await sa.post(f"{BASE}/api/auth/login", data={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})).ok
        assert (await sa.put(f"{BASE}/api/platform/saas/orgs/{oid}/admin", data={"plan": "gold", "status": "active"})).ok
        assert (await rq.post(f"{BASE}/api/addons/planner/events/{ev['id']}/activate")).ok
        pr = await (await rq.post(f"{BASE}/api/planner/events/{ev['id']}/projects", data={"nome": "Area arrivo – Cittadella"})).json()
        await rq.patch(f"{BASE}/api/planner/projects/{pr['id']}", data={"center": [10.40, 43.716], "zoom": 12.4})
        page = await ctx.new_page()
        url = f"{BASE}/eventi/{ev['id']}/planner"
        for attempt in range(4):
            try:
                if "/planner" not in page.url:
                    await page.goto(url, wait_until="domcontentloaded")
                for _ in range(40):
                    await page.wait_for_timeout(1500)
                    if await page.evaluate("() => !!(window.__plannerMap && window.__plannerMap.isStyleLoaded())"):
                        break
                await page.wait_for_timeout(4000)
                if "/planner" in page.url and await page.evaluate("() => !!window.__plannerMap"):
                    break
            except Exception as e:
                print("retry avvio", attempt, str(e)[:60], page.url, flush=True)
        await page.evaluate(OVERLAY_JS)
        await page.add_style_tag(content="body{pointer-events:auto!important}")
        await page.keyboard.press("Escape")
        await page.evaluate("() => { setTimeout(() => { window.__plannerMap.resize(); window.__plannerMap.jumpTo({center:[10.40,43.716], zoom:12.4}); }, 0); }")
        rec = Rec(page)
        await rec.idle(15000)
        print("pronto", flush=True)

        async def place(lib, ll, nome=None, rot=None):
            await rec.click_el(f'[data-testid="planner-lib-{lib}"]', frames=6)
            await rec.click_map(ll, frames=6, after=2)
            if nome:
                await page.locator('[data-testid="planner-prop-nome"]').fill(nome)
            if rot is not None:
                await page.locator('[data-testid="planner-prop-rot"]').fill(str(rot))
            if nome or rot is not None:
                await rec.idle(); await rec.shot(); await rec.hold(4)

        async def line(lib, pts, nome=None, frames=4):
            await rec.click_el(f'[data-testid="planner-lib-{lib}"]' if lib else '[data-testid="planner-tool-line"]', frames=6)
            for ll in pts:
                await rec.click_map(ll, frames=frames, after=0)
            await page.evaluate("() => { setTimeout(() => window.__plannerFinish && window.__plannerFinish(), 0); }")
            await page.wait_for_timeout(200)
            if nome:
                await page.locator('[data-testid="planner-prop-nome"]').fill(nome)
            await rec.idle(); await rec.shot(); await rec.hold(3)

        await rec.caption("City Run Festival · esempio con percorso dimostrativo")
        await rec.shot(); await rec.hold(40)
        await rec.caption("Parti dalla mappa reale della città")
        await rec.camera({"lng": 10.3957, "lat": 43.7177, "zoom": 14.7}, 3.6)
        print("percorso", rec.n, flush=True)
        await rec.caption("Disegna il percorso lungo le strade")
        await line(None, ROUTE, "Percorso dimostrativo – 3,8 km", frames=3)
        await rec.hold(12)
        print("area", rec.n, flush=True)
        await rec.caption("Zoom sull'area di arrivo: Parco della Cittadella")
        await page.keyboard.press("Escape")
        await rec.camera({"lng": M(9, -21)[0], "lat": M(9, -21)[1], "zoom": 17.85}, 2.4)
        await rec.caption("Arco di arrivo e corridoio atleti")
        await place("lib5", M(20, -52))
        await line("lib23", [M(14, -72), M(14, -52), M(14, -22)], "Corridoio arrivo – lato ovest")
        await line("lib23", [M(26, -72), M(26, -52), M(26, -22)], "Corridoio arrivo – lato est")
        await rec.caption("Ristoro atleti dopo il traguardo")
        await place("lib1", M(20, -12), "Gazebo ristoro atleti")
        await line("lib23", [M(14, -22), M(4, -22), M(4, -2), M(36, -2), M(36, -22), M(26, -22)], "Recinzione area ristoro")
        await rec.caption("Segreteria e ritiro pettorali")
        await place("lib1", M(-24, 14), "Segreteria")
        await place("lib1", M(-16, 14), "Ritiro pettorali")
        await place("lib28", M(-20, 5), "Accesso segreteria")
        await line("lib23", [M(-28, 7), M(-28, -6)], "Fila ritiro pettorali")
        await line("lib23", [M(-12, 7), M(-12, -6)], "Fila ritiro pettorali")
        await rec.caption("Palco premiazioni e area pubblico")
        await place("lib3", M(20, 36), "Palco premiazioni")
        await line("lib23", [M(4, 8), M(4, 28), M(36, 28), M(36, 8)], "Area pubblico")
        await rec.caption("Area sponsor")
        await place("lib30", M(46, 14), "Stand sponsor")
        await place("lib30", M(46, 19), "Stand sponsor")
        await place("lib30", M(46, 24), "Stand sponsor")
        await place("lib33", M(20, -82), "Arco sponsor ingresso")
        await rec.caption("Sposta gli elementi con il trascinamento")
        x0, y0 = await rec.xy(M(46, 24))
        await rec.click(x0, y0, 6, 2)
        x1, y1 = await rec.xy(M(46, 30))
        await page.mouse.move(x0, y0); await page.mouse.down()
        for i in range(1, 9):
            await page.mouse.move(x0 + (x1 - x0) * i / 8, y0 + (y1 - y0) * i / 8)
            await rec.set_cursor(x0 + (x1 - x0) * i / 8, y0 + (y1 - y0) * i / 8)
            await rec.idle(1500); await rec.shot()
        await page.mouse.up(); await rec.idle(); await rec.shot(); await rec.hold(4)
        await rec.caption("Postazioni volontari")
        for ll in (M(10, -52), M(-20, -2), M(40, -10), M(40, 40)):
            await place("lib34", ll)
        await rec.click_el('[data-testid="planner-tool-select"]')
        await page.keyboard.press("Escape")
        await rec.set_cursor(-50, -50)
        print("finale", rec.n, flush=True)
        await rec.caption("Tutta l'area organizzata, pronta per la gara")
        await rec.camera({"lng": M(9, -21)[0], "lat": M(9, -21)[1], "zoom": 16.9, "pitch": 35, "bearing": -10}, 3.2)
        await rec.hold(15)
        await rec.caption("")
        await page.evaluate("""() => { document.querySelector('#rec-end').innerHTML = '<img src="/logo-crmevent.png" style="height:70px">' +
          '<div style="font-size:30px;font-weight:800;color:#0f172a">Organizza ogni dettaglio del tuo evento con Event Planner.</div>' +
          '<div style="font-size:16px;color:#64748b">Esempio dimostrativo · percorso non ufficiale del City Run Festival</div>'; }""")
        for i in range(1, 16):
            await page.evaluate("(o) => { document.getElementById('rec-end').style.opacity = o; }", i / 15)
            await rec.shot()
        await rec.hold(55)
        print("fine", rec.n, round(rec.n / 25, 1), "s", flush=True)
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
