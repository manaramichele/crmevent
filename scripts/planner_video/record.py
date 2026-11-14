"""Registra il video promozionale di Event Planner dall'interfaccia reale (anteprima) con mappa MapTiler.
Uso: python3 record.py  -> /app/scripts/planner_video/out/raw.webm + timings.json
Crea un'organizzazione TEST_ temporanea (va cancellata dopo con cleanup.py)."""
import asyncio, json, os, time, uuid
from pathlib import Path
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
OUT = Path(__file__).parent / "out"
W, H = 1600, 900

CAPTION_JS = """(t) => {
  let el = document.getElementById('rec-cap');
  if (!el) { el = document.createElement('div'); el.id = 'rec-cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:34px;transform:translateX(-50%);z-index:99999;background:rgba(15,23,42,.88);color:#fff;font:600 24px/1.25 Manrope,Inter,sans-serif;padding:14px 26px;border-radius:999px;box-shadow:0 12px 40px rgba(0,0,0,.25);transition:opacity .45s ease;opacity:0;display:flex;gap:12px;align-items:center;white-space:nowrap';
    document.body.appendChild(el); }
  el.style.opacity = 0;
  setTimeout(() => { el.innerHTML = '<span style="width:12px;height:12px;border-radius:99px;background:#0ABAB5;display:inline-block"></span>' + t; el.style.opacity = t ? 1 : 0; }, 450);
}"""
END_JS = """() => {
  const c = document.getElementById('rec-cap'); if (c) c.style.opacity = 0;
  const d = document.createElement('div');
  d.style.cssText = 'position:fixed;inset:0;z-index:100000;background:rgba(255,255,255,.94);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;opacity:0;transition:opacity .9s ease;font-family:Manrope,Inter,sans-serif';
  d.innerHTML = '<img src="/logo-crmevent.png" style="height:84px">' +
    '<div style="font-size:34px;font-weight:800;color:#0f172a">Il tuo evento prende forma, direttamente sulla mappa.</div>' +
    '<div style="font-size:21px;color:#475569">Event Planner è una delle funzionalità di CRMEvent</div>' +
    '<div style="margin-top:10px;background:#0ABAB5;color:#0f172a;font-weight:700;font-size:22px;padding:14px 34px;border-radius:12px">Registrati a CRMEvent</div>';
  document.body.appendChild(d); requestAnimationFrame(() => { d.style.opacity = 1; });
}"""

ROUTE = [[9.1729, 45.4754], [9.1712, 45.4741], [9.1703, 45.4726], [9.1718, 45.4711], [9.1741, 45.4700], [9.1768, 45.4693], [9.1792, 45.4699],
         [9.1806, 45.4714], [9.1802, 45.4731], [9.1785, 45.4746], [9.1760, 45.4757], [9.1740, 45.4759], [9.1729, 45.4754]]


async def main():
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width": W, "height": H}, record_video_dir=str(OUT), record_video_size={"width": W, "height": H})
        t_video = time.time()

        async def maptiler(route):
            h = {**route.request.headers, "origin": "https://crmevent.it", "referer": "https://crmevent.it/"}
            r = await route.fetch(headers=h)
            await route.fulfill(response=r, headers={**r.headers, "access-control-allow-origin": "*"})
        await ctx.route("https://api.maptiler.com/**", maptiler)
        await ctx.add_init_script("window.__PLANNER_RECORDING = true; localStorage.setItem('crmevent_cookie_consent', JSON.stringify({necessary:true,analytics:false,marketing:false,ts:Date.now()}));")

        rq = ctx.request
        email = f"test_video_{uuid.uuid4().hex[:6]}@example.com"
        r = await rq.post(f"{BASE}/api/auth/register-organization", data={"nome": "Video", "cognome": "Demo", "email": email, "password": "VideoDemo2026!",
                          "org_name": "TEST_Video Planner", "telefono": "+393331234567", "accept_terms": True}, timeout=90000)
        assert r.ok, await r.text()
        ev = await (await rq.post(f"{BASE}/api/events", data={"nome": "Corsa del Parco 10K"})).json()
        pr = await (await rq.post(f"{BASE}/api/planner/events/{ev['id']}/projects", data={"nome": "Planimetria generale"})).json()
        await rq.patch(f"{BASE}/api/planner/projects/{pr['id']}", data={"center": [9.19, 45.4642], "zoom": 11.3})
        (OUT / "test_account.json").write_text(json.dumps({"email": email}))

        page = await ctx.new_page()
        print("goto", flush=True)
        await page.goto(f"{BASE}/eventi/{ev['id']}/planner", wait_until="domcontentloaded")
        print("caricata", flush=True)
        for i in range(24):
            await page.wait_for_timeout(2500)
            st = await page.evaluate("() => [!!window.__plannerMap, window.__plannerMap ? window.__plannerMap.isStyleLoaded() : null, location.pathname]")
            print("stato", i, st, flush=True)
            if st[1]:
                break
        for name in ("Reject non-essential", "Rifiuta", "Non ora"):
            try:
                await page.get_by_role("button", name=name).first.click(timeout=1500)
            except Exception:
                pass
        await page.add_style_tag(content="[data-testid=event-planner]{position:fixed!important;inset:0!important;height:100vh!important;z-index:60} [role=dialog]{display:none!important}")
        await page.evaluate("() => window.__plannerMap.resize()")
        print("pronto", flush=True)
        await page.evaluate("() => window.__plannerMap.jumpTo({center:[9.19,45.4642], zoom:11.3})")
        await page.wait_for_timeout(4000)

        m = lambda js: page.evaluate(js)
        cap = lambda t: page.evaluate(CAPTION_JS, t)
        wait = page.wait_for_timeout

        async def click_at(ll, pause=380):
            x, y = await page.evaluate("([a,b]) => { const m=window.__plannerMap, p=m.project([a,b]), r=m.getCanvas().getBoundingClientRect(); return [r.left+p.x, r.top+p.y]; }", ll)
            await page.mouse.move(x, y, steps=8)
            await page.mouse.click(x, y)
            await wait(pause)

        async def place(lib_id, pts, pause=520):
            for ll in pts:
                await page.locator(f'[data-testid="planner-lib-{lib_id}"]').click()
                await wait(180)
                await click_at(ll, pause)

        async def line(pts, lib_id=None, pause=300):
            if lib_id:
                await page.locator(f'[data-testid="planner-lib-{lib_id}"]').click()
            else:
                await page.locator('[data-testid="planner-tool-line"]').click()
            await wait(250)
            for ll in pts:
                await click_at(ll, pause)
            await m("() => window.__plannerFinish && window.__plannerFinish()")
            await wait(500)

        async def cam(js, ms):
            print("cam", js[:30], flush=True)
            await m(f"() => window.__plannerMap.{js}")
            await wait(ms)

        t0 = time.time() - t_video
        await cap("Parti dalla mappa reale della tua città")
        await wait(3200)
        await cap("Zoom sulla zona dell'evento")
        await cam("flyTo({center:[9.1755,45.4728], zoom:16.15, duration:4800, curve:1.4})", 5200)
        await cap("Disegna il percorso della gara")
        await line(ROUTE, pause=330)
        await wait(600)
        await cap("Coni, transenne, accessi e parcheggi")
        await cam("easeTo({center:[9.1731,45.4754], zoom:17.7, duration:1800})", 2000)
        await place("lib25", [[9.1721, 45.4749], [9.1724, 45.4747], [9.1727, 45.4745], [9.1730, 45.4743]], 300)
        await line([[9.1722, 45.4758], [9.1732, 45.4762], [9.1743, 45.4764]], "lib23", 300)
        await place("lib28", [[9.1746, 45.4765], [9.1711, 45.4752]], 400)
        await place("lib27", [[9.1712, 45.4766]], 500)
        await cap("Postazioni volontari e punti di controllo")
        await cam("easeTo({center:[9.1755,45.4727], zoom:16.2, duration:1800})", 2000)
        await place("lib35", [[9.1703, 45.4726], [9.1806, 45.4714], [9.1768, 45.4693]], 380)
        await place("lib34", [[9.1741, 45.4700], [9.1785, 45.4746]], 380)
        await place("lib37", [[9.1752, 45.4763]], 450)
        await cap("Stand sponsor, banner e arco pubblicitario")
        await cam("easeTo({center:[9.1735,45.4751], zoom:18.3, duration:1800})", 2000)
        await place("lib5", [[9.1729, 45.4754]], 400)
        await place("lib33", [[9.1718, 45.4744]], 400)
        await place("lib30", [[9.1738, 45.4748], [9.1742, 45.4749], [9.1746, 45.4750]], 330)
        await line([[9.1733, 45.4757], [9.1741, 45.4759]], "lib32", 300)
        await page.locator('[data-testid="planner-tool-select"]').click()
        await page.keyboard.press("Escape")
        await cap("Tutta l'organizzazione dell'evento, in un'unica mappa")
        await cam("easeTo({center:[9.1755,45.4730], zoom:15.75, pitch:38, bearing:-12, duration:3200})", 4200)
        await m(END_JS)
        await wait(3800)
        t1 = time.time() - t_video
        video = page.video
        await ctx.close()
        raw = await video.path()
        os.replace(raw, OUT / "raw.webm")
        (OUT / "timings.json").write_text(json.dumps({"start": t0, "end": t1}))
        await b.close()
        print("ok", t0, t1)

asyncio.run(main())
