import asyncio, json, time
from playwright.async_api import async_playwright
BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle","--use-angle=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width":1600,"height":900})
        n={"c":0,"err":0}
        async def mt(route):
            try:
                h={**route.request.headers,"origin":"https://crmevent.it","referer":"https://crmevent.it/"}
                r=await route.fetch(headers=h); n["c"]+=1
                if r.status!=200: n["err"]+=1
                await route.fulfill(response=r, headers={**r.headers,"access-control-allow-origin":"*"})
            except Exception as e: print("route err", e)
        await ctx.route("https://api.maptiler.com/**", mt)
        await ctx.add_init_script("window.__PLANNER_RECORDING = true;")
        email=json.load(open("out/test_account.json"))["email"]
        r=await ctx.request.post(f"{BASE}/api/auth/login", data={"email":email,"password":"VideoDemo2026!"}); print("login",r.status)
        evs=await (await ctx.request.get(f"{BASE}/api/events")).json(); ev=(evs if isinstance(evs,list) else evs.get("items"))[0]
        page=await ctx.new_page(); page.on("console", lambda m: print("console", m.type, m.text[:150]) if m.type in ("error","warning") else None)
        t=time.time(); await page.goto(f"{BASE}/eventi/{ev['id']}/planner")
        for i in range(8):
            await page.wait_for_timeout(5000)
            st=await page.evaluate("() => ({hook: !!window.__plannerMap, loaded: window.__plannerMap ? window.__plannerMap.loaded() : null, style: window.__plannerMap ? window.__plannerMap.isStyleLoaded() : null})")
            print(round(time.time()-t), st, n)
        await page.screenshot(path="out/probe.png")
        await b.close()
asyncio.run(main())
