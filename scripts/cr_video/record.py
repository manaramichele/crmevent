"""Registra il video dimostrativo di Control Room (UI reale, evento Demo, GPS simulato ed etichettato)."""
import asyncio
import shutil
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
TOKEN, ORG, EV = sys.argv[1], "b7f40862230441b9a0bedabefe8dab49", "demo_evt_bcr"
OUT = Path("/tmp/cr_video"); shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir()

BADGE = """(() => { const b = document.createElement('div'); b.id='demo-badge';
b.style.cssText='position:fixed;top:14px;right:18px;z-index:99999;background:#0f172a;color:#5EEAD4;font:600 15px system-ui;padding:8px 14px;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.2)';
b.textContent='Dimostrazione · dati fittizi'; document.body.appendChild(b); })()"""

GPS = """(() => { const m = document.querySelector('[data-testid=cr-map-wrap]'); if (!m) return 'nomap'; const r = m.getBoundingClientRect();
const st = document.createElement('style'); st.textContent = `@keyframes g1{0%{transform:translate(0,0)}50%{transform:translate(160px,90px)}100%{transform:translate(320px,40px)}}
@keyframes g2{0%{transform:translate(0,0)}50%{transform:translate(-140px,120px)}100%{transform:translate(-60px,240px)}}
@keyframes g3{0%{transform:translate(0,0)}100%{transform:translate(220px,-150px)}}
@keyframes pu{0%{box-shadow:0 0 0 0 rgba(10,186,181,.7)}100%{box-shadow:0 0 0 16px rgba(10,186,181,0)}}`; document.head.appendChild(st);
const o = document.createElement('div'); o.id='gps-sim'; o.style.cssText=`position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;z-index:9999;pointer-events:none`;
const lab = document.createElement('div'); lab.style.cssText='position:absolute;left:16px;bottom:16px;background:rgba(15,23,42,.88);color:#fff;font:600 14px system-ui;padding:8px 12px;border-radius:10px';
lab.textContent='Simulazione dimostrativa GPS · non sono posizioni reali'; o.appendChild(lab);
[['Squadra Ristoro A',0.30,0.35,'g1'],['Moto staffetta Demo',0.65,0.25,'g2'],['Ambulanza Demo 1',0.45,0.65,'g3']].forEach(([n,x,y,a]) => {
 const d = document.createElement('div'); d.style.cssText=`position:absolute;left:${x*r.width}px;top:${y*r.height}px;animation:${a} 18s ease-in-out infinite alternate`;
 d.innerHTML=`<div style="width:16px;height:16px;border-radius:50%;background:#0ABAB5;border:3px solid #fff;animation:pu 1.4s infinite"></div><div style="margin-top:4px;background:#fff;color:#0f172a;font:600 12px system-ui;padding:2px 8px;border-radius:6px;white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,.2)">${n} · GPS demo</div>`;
 o.appendChild(d); }); document.body.appendChild(o); return 'ok'; })()"""

END = """(() => { document.getElementById('gps-sim')?.remove(); const e = document.createElement('div');
e.style.cssText='position:fixed;inset:0;z-index:100000;background:#0f172a;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:28px;opacity:0;transition:opacity .8s';
e.innerHTML='<img src="/logo-crmevent-dark.png" style="height:110px" onerror="this.src=\\'/logo-crmevent.png\\'"><div style="color:#fff;font:700 44px system-ui">Control Room</div><div style="color:#5EEAD4;font:600 30px system-ui">www.crmevent.it</div>';
document.body.appendChild(e); requestAnimationFrame(() => e.style.opacity = 1); })()"""


async def click(p, sel, wait=3.5):
    try:
        await p.click(sel, timeout=4000)
    except Exception as ex:
        print("skip", sel, str(ex)[:80])
    await p.wait_for_timeout(int(wait * 1000))


async def main():
    async with async_playwright() as pw:
        br = await pw.chromium.launch()
        ctx = await br.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(OUT), record_video_size={"width": 1920, "height": 1080})
        host = URL.split("//")[1]
        await ctx.add_cookies([{"name": "access_token", "value": TOKEN, "domain": host, "path": "/", "secure": True, "httpOnly": True}])
        await ctx.add_init_script(f"localStorage.setItem('acting_org_id','{ORG}'); localStorage.setItem('cookie_consent', JSON.stringify({{necessary:true}}));")
        p = await ctx.new_page()
        await p.goto(f"{URL}/control-room?event={EV}", wait_until="networkidle")
        await p.add_style_tag(content="[data-testid=super-acting-banner]{display:none!important}")
        for t in ("Accept all", "Accetta tutti", "Accetta"):
            try:
                await p.get_by_role("button", name=t).first.click(timeout=1500)
                break
            except Exception:
                pass
        await p.wait_for_timeout(5000)
        mk = await p.query_selector(".maplibregl-marker")
        if mk:
            bb = await mk.bounding_box()
            await p.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
            for _ in range(7):
                await p.mouse.wheel(0, -400)
                await p.wait_for_timeout(450)
            await p.mouse.move(1900, 300)
        await p.evaluate(BADGE)
        await p.wait_for_timeout(4000)
        await click(p, "[data-testid=cr-tab-posts]", 5)
        await click(p, "[data-testid=cr-tab-sectors]", 4)
        await click(p, "[data-testid=cr-tab-resources]", 4)
        print(await p.evaluate(GPS))
        await p.wait_for_timeout(9000)
        await click(p, "[data-testid=cr-tab-interventions]", 5)
        await p.evaluate("document.getElementById('gps-sim')?.remove()")
        await click(p, "[data-testid=cr-view-itv]", 5)
        await click(p, "[data-testid=cr-view-map]", 2)
        await p.evaluate(GPS)
        await p.wait_for_timeout(4000)
        await p.evaluate(END)
        await p.wait_for_timeout(5000)
        await p.screenshot(path=str(OUT / "end.png"))
        await ctx.close()
        await br.close()
    print([str(x) for x in OUT.iterdir()])

asyncio.run(main())
