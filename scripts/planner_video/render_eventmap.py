"""Video dimostrativo Event Map (risultato previsto): animazione verticale 720x1280 del percorso GPX dimostrativo di Pisa.
Uso: setsid nohup python3 render_eventmap.py > eventmap.log 2>&1 &  poi encode."""
import asyncio, json, math, shutil
from pathlib import Path
from playwright.async_api import async_playwright
import mapkit

HERE = Path(__file__).parent
OUT = HERE / "frames_map"
PTS = json.load(open(HERE / "pisa_route.json"))["full"]
FPS, W, H = 25, 720, 1280


def dist(a, b):
    k = math.cos(math.radians(a[1]))
    return math.hypot((b[0] - a[0]) * k, b[1] - a[1]) * 111320


CUM = [0.0]
for i in range(1, len(PTS)):
    CUM.append(CUM[-1] + dist(PTS[i - 1], PTS[i]))
TOT = CUM[-1]


def upto(m):
    out = [PTS[0]]
    for i in range(1, len(PTS)):
        if CUM[i] <= m:
            out.append(PTS[i])
        else:
            t = (m - CUM[i - 1]) / (CUM[i] - CUM[i - 1])
            out.append([PTS[i - 1][0] + (PTS[i][0] - PTS[i - 1][0]) * t, PTS[i - 1][1] + (PTS[i][1] - PTS[i - 1][1]) * t])
            break
    return out


SETUP_JS = """(pts) => new Promise((res) => {
  const go = () => {
    map.addSource('r', {type:'geojson', data:{type:'Feature', geometry:{type:'LineString', coordinates:[pts[0], pts[0]]}}});
    map.addSource('h', {type:'geojson', data:{type:'Point', coordinates:pts[0]}});
    map.addSource('se', {type:'geojson', data:{type:'Point', coordinates:pts[0]}});
    map.addLayer({id:'rc', type:'line', source:'r', layout:{'line-cap':'round','line-join':'round'}, paint:{'line-color':'#fff','line-width':11}});
    map.addLayer({id:'rl', type:'line', source:'r', layout:{'line-cap':'round','line-join':'round'}, paint:{'line-color':'#E11D48','line-width':6}});
    map.addLayer({id:'se', type:'circle', source:'se', paint:{'circle-radius':11,'circle-color':'#0ABAB5','circle-stroke-width':4,'circle-stroke-color':'#fff','circle-opacity':0,'circle-stroke-opacity':0}});
    map.addLayer({id:'h', type:'circle', source:'h', paint:{'circle-radius':9,'circle-color':'#fff','circle-stroke-width':5,'circle-stroke-color':'#E11D48'}});
    document.body.insertAdjacentHTML('beforeend', `<style>.ov{position:fixed;z-index:5;pointer-events:none;transition:none}
      #logo{top:70px;left:50%;transform:translateX(-50%);background:#0f172a;color:#fff;border-radius:28px;padding:22px 34px;text-align:center;box-shadow:0 16px 40px rgba(0,0,0,.3);opacity:0}
      #logo b{display:block;font-size:46px;letter-spacing:1px;font-weight:900}#logo span{font-size:19px;color:#5eead4;font-weight:700;letter-spacing:3px}
      #km{bottom:150px;left:50%;transform:translateX(-50%);background:rgba(255,255,255,.95);border-radius:20px;padding:14px 30px;font-size:44px;font-weight:900;color:#0f172a;opacity:0;box-shadow:0 10px 30px rgba(0,0,0,.2)}
      #km small{font-size:20px;color:#64748b;font-weight:700;margin-left:6px}
      #tag{top:16px;left:16px;background:rgba(15,23,42,.75);color:#fff;font-size:15px;padding:6px 12px;border-radius:999px}
      #se{background:#0ABAB5;color:#0f172a;font-weight:800;font-size:18px;padding:6px 12px;border-radius:10px;opacity:0;transform:translate(-50%,-150%)}
      #pw{bottom:22px;right:18px;display:flex;align-items:center;gap:6px;background:rgba(255,255,255,.9);border-radius:10px;padding:5px 9px;font-size:13px;color:#334155;font-weight:700}
      #pw img{height:18px}</style>
      <div id="tag" class="ov">Esempio dimostrativo · risultato previsto di Event Map</div>
      <div id="logo" class="ov"><b>PISA RUN</b><span>EVENTO DIMOSTRATIVO</span></div>
      <div id="km" class="ov">0,0<small>km</small></div><div id="se" class="ov">PARTENZA · ARRIVO</div>
      <div id="pw" class="ov"><img src="/icon-crmevent.png">Powered by CRMEvent</div>`);
    res();
  };
  if (map.isStyleLoaded()) go(); else map.once('load', go);
})"""
FRAME_JS = """(s) => { setTimeout(() => {
  map.getSource('r').setData({type:'Feature', geometry:{type:'LineString', coordinates:s.line}});
  map.getSource('h').setData({type:'Point', coordinates:s.line[s.line.length-1]});
  map.setPaintProperty('h','circle-opacity', s.head); map.setPaintProperty('h','circle-stroke-opacity', s.head);
  map.setPaintProperty('se','circle-opacity', s.se); map.setPaintProperty('se','circle-stroke-opacity', s.se);
  map.jumpTo(s.cam);
  const p = map.project(s.start), e = document.getElementById('se'); e.style.left = p.x + 'px'; e.style.top = p.y + 'px'; e.style.opacity = s.se;
  document.getElementById('logo').style.opacity = s.logo;
  const k = document.getElementById('km'); k.style.opacity = s.kmo; k.innerHTML = s.km + '<small>km</small>';
}, 0); }"""


def ease(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


async def main():
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width": W, "height": H})
        await mapkit.setup(ctx, {}, {"icon-crmevent.png": "/app/frontend/public/icon-crmevent.png"})
        page = await mapkit.open_map(ctx, [10.398, 43.7175], 12.6)
        await page.evaluate(SETUP_JS, PTS)
        n = 0
        c0 = {"center": [10.398, 43.7175], "zoom": 12.6, "pitch": 0, "bearing": 0}
        cf = {"center": [10.3975, 43.7172], "zoom": 14.55, "pitch": 0, "bearing": 0}
        total = 20 * FPS
        for f in range(total):
            t = f / FPS
            draw = min(1, max(0, (t - 3.0) / 11.0))
            m = TOT * ease(draw) if draw < 1 else TOT
            line = upto(m) if m > 0 else [PTS[0], PTS[0]]
            head = line[-1]
            if t < 3.0:
                e = ease(t / 3.0)
                cam = {"center": [c0["center"][0] + (head[0] - c0["center"][0]) * e, c0["center"][1] + (head[1] - c0["center"][1]) * e],
                       "zoom": 12.6 + (15.4 - 12.6) * e, "pitch": 45 * e, "bearing": -20 * e}
            elif t < 14.0:
                cam = {"center": head, "zoom": 15.4, "pitch": 45, "bearing": -20 + 60 * draw}
            else:
                e = ease(min(1, (t - 14.0) / 3.0))
                cam = {"center": [head[0] + (cf["center"][0] - head[0]) * e, head[1] + (cf["center"][1] - head[1]) * e],
                       "zoom": 15.4 + (cf["zoom"] - 15.4) * e, "pitch": 45 * (1 - e), "bearing": 40 * (1 - e)}
            s = {"line": line, "cam": cam, "start": PTS[0], "head": 1 if 3.0 <= t < 14.2 else 0, "se": min(1, max(0, (t - 2.6) * 2)),
                 "logo": min(1, t / 1.2), "kmo": min(1, max(0, (t - 3.0) * 2)), "km": f"{m / 1000:.1f}".replace(".", ",")}
            await page.evaluate(FRAME_JS, s)
            await page.wait_for_timeout(40)
            await mapkit.wait_idle(page, 8)
            n += 1
            await page.screenshot(path=str(OUT / f"f{n:05d}.jpg"), type="jpeg", quality=88)
            if n % 50 == 0:
                print("frame", n, "/", total, flush=True)
        print("fine", n, flush=True)
        await b.close()

asyncio.run(main())
