# Chromium Pixel 5 (real CDP Input.dispatchTouchEvent swipes) test for ResponsivePicker sheets: TeamSelect, StaffAssignSelect, TeamMembersDialog add
import asyncio, json, os
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
IDS = json.load(open("/tmp/menuscroll_ids.json"))
PID, PRES, EV = IDS["persons"][0], IDS["staff"][0], IDS["events"][0]
SHOT = "/app/.screenshots"
results = []
def rep(n, ok, info=""):
    results.append((n, ok)); print(("PASS " if ok else "FAIL ") + n + (" | " + str(info) if info != "" else ""))

async def swipe(cdp, x, y0, y1, steps=8):
    await cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y0}]})
    for i in range(1, steps + 1):
        await cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y0 + (y1 - y0) * i / steps}]})
        await asyncio.sleep(0.02)
    await cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    await asyncio.sleep(0.6)

SCROLLERS = """() => [...document.querySelectorAll('[role=dialog]')].map(d => { let m = d; d.querySelectorAll('*').forEach(e => { if (e.scrollTop > m.scrollTop) m = e; }); return [d.dataset.testid || d.id, d.scrollTop, m.scrollTop]; })"""

async def sheet_swipe(page, cdp, sheet_tid, list_tid, label, outer_sel):
    sheet = page.locator(f'[data-testid="{sheet_tid}"]')
    ok = await sheet.is_visible(); rep(f"[{label}] sheet opened", ok)
    if not ok: return
    ds = await sheet.get_attribute("data-sheet"); rep(f"[{label}] mobile sheet (not popover)", ds == "true", ds)
    bb = await sheet.bounding_box(); vp = page.viewport_size
    rep(f"[{label}] sheet inside viewport", bb["y"] >= 0 and bb["y"] + bb["height"] <= vp["height"] + 1, bb)
    lb = await page.locator(f'[data-testid="{list_tid}"]').bounding_box()
    outer_before = await page.evaluate(f"() => {{ const e = document.querySelector('{outer_sel}'); return e ? e.scrollTop : null; }}")
    y_before = await page.evaluate("() => scrollY")
    x = lb["x"] + lb["width"] / 2
    await swipe(cdp, x, lb["y"] + lb["height"] * 0.85, lb["y"] + lb["height"] * 0.15)
    st1 = await page.evaluate(f"() => document.querySelector('[data-testid=\"{list_tid}\"]').scrollTop")
    rep(f"[{label}] CDP touch swipe scrolls list", st1 > 0, st1)
    for _ in range(4): await swipe(cdp, x, lb["y"] + lb["height"] * 0.85, lb["y"] + lb["height"] * 0.15)
    st2 = await page.evaluate(f"() => {{ const l = document.querySelector('[data-testid=\"{list_tid}\"]'); return [l.scrollTop, l.scrollHeight - l.clientHeight]; }}")
    rep(f"[{label}] swipes reach bottom", abs(st2[0] - st2[1]) < 3, st2)
    outer_after = await page.evaluate(f"() => {{ const e = document.querySelector('{outer_sel}'); return e ? e.scrollTop : null; }}")
    y_after = await page.evaluate("() => scrollY")
    rep(f"[{label}] dialog behind / window not scrolled", outer_before == outer_after and y_before == y_after, (outer_before, outer_after, y_before, y_after))
    await swipe(cdp, x, lb["y"] + lb["height"] * 0.2, lb["y"] + lb["height"] * 0.9)
    st3 = await page.evaluate(f"() => document.querySelector('[data-testid=\"{list_tid}\"]').scrollTop")
    rep(f"[{label}] swipe down scrolls back up", st3 < st2[0], st3)
    await page.screenshot(path=f"{SHOT}/cr_{label.replace(' ', '_')}.jpeg", quality=40, type="jpeg")

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/local/bin/browser-use-chromium")
        ctx = await b.new_context(**p.devices["Pixel 5"])
        page = await ctx.new_page(); cdp = await ctx.new_cdp_session(page)
        page.on("pageerror", lambda e: print("PAGEERROR", e))
        await page.request.post(f"{BASE}/api/auth/login", data={"email": IDS["email"], "password": IDS["password"]})
        await page.request.post(f"{BASE}/api/demo/welcome/dismiss")
        # ---- TeamSelect in PersonDetailDialog
        await page.goto(f"{BASE}/staff-volontari", wait_until="domcontentloaded"); await page.wait_for_timeout(2500)
        if await page.locator('[data-testid="cookie-accept-all"]').count(): await page.locator('[data-testid="cookie-accept-all"]').first.tap()
        await page.locator('[data-testid="tab-volontari"]').tap(); await page.wait_for_timeout(800)
        await page.locator(f'[data-testid="m-open-person-{PID}"]').first.tap()
        await page.locator('[data-testid="person-detail-edit"]').tap(); await page.wait_for_timeout(500)
        await page.locator('[data-testid="ptab-team"]').tap(); await page.wait_for_timeout(600)
        tid = f"team-assign-{PRES}"
        await page.locator(f'[data-testid="{tid}"]').tap(); await page.wait_for_timeout(700)
        await sheet_swipe(page, cdp, f"{tid}-popover", f"{tid}-list", "team select", '[role=dialog]')
        last = IDS["teams"][15]
        await page.locator(f'[data-testid="{tid}-opt-{last}"]').scroll_into_view_if_needed()
        await page.locator(f'[data-testid="{tid}-opt-{last}"]').tap(); await page.wait_for_timeout(1200)
        rep("[team select] selection after swipe", "TEST_Team 15" in await page.locator(f'[data-testid="{tid}"]').inner_text())
        # ---- TeamMembersDialog add
        await page.goto(f"{BASE}/staff-volontari", wait_until="domcontentloaded"); await page.wait_for_timeout(2500)
        await page.locator('[data-testid="tab-team"]').first.tap(); await page.wait_for_timeout(1500)
        t0 = IDS["teams"][0]
        await page.locator(f'[data-testid="m-edit-team-{t0}"]').first.tap(); await page.wait_for_timeout(1200)
        await page.locator('[data-testid="team-add-member"]').first.tap(); await page.wait_for_timeout(800)
        await sheet_swipe(page, cdp, "team-add-popover", "team-add-list", "team add", '[role=dialog]')
        rep("[team add] close btn present", await page.locator('[data-testid="team-add-popover-close"]').count() == 1)
        await page.locator('[data-testid="team-add-search"]').fill("Staff1"); await page.wait_for_timeout(300)
        opts = page.locator('[data-testid^="team-add-opt-"]'); n = await opts.count()
        total = await page.evaluate("() => 0")
        rep("[team add] search filters (<=6 for 'Staff1')", 1 <= n <= 6, n)
        if n:
            nm = (await opts.first.locator('span').first.inner_text()).strip()
            await opts.first.tap(); await page.wait_for_timeout(1500)
            body = await page.locator('[role=dialog]').first.inner_text()
            rep("[team add] member added", nm.split()[0] in body, nm)
        if not await page.locator('[data-testid="team-add-popover"]').is_visible():
            await page.locator('[data-testid="team-add-member"]').first.tap(); await page.wait_for_timeout(700)
        await page.locator('[data-testid="team-add-new-person"]').tap(); await page.wait_for_timeout(600)
        await page.locator('[data-testid="tp-tipo"]').tap(); await page.wait_for_timeout(500)
        lb = page.get_by_role("option", name="Volontario")
        vis = await lb.is_visible(); rep("[team add] Tipo Select opens above sheet", vis)
        if vis:
            z = await page.evaluate("() => { const o=[...document.querySelectorAll('[role=option]')].pop(); const r=o.getBoundingClientRect(); const top=document.elementFromPoint(r.x+r.width/2, r.y+r.height/2); return o.contains(top) || top===o; }")
            rep("[team add] Tipo option is topmost element (z-index)", z)
            await lb.tap(); await page.wait_for_timeout(400)
            rep("[team add] Tipo value set", "Volontario" in await page.locator('[data-testid="tp-tipo"]').inner_text())
            rep("[team add] sheet still open after Tipo", await page.locator('[data-testid="team-new-person-form"]').is_visible())
        await page.screenshot(path=f"{SHOT}/cr_team_new_person.jpeg", quality=40, type="jpeg")
        # ---- StaffAssignSelect in pipeline task dialog
        await page.goto(f"{BASE}/eventi/{EV}/pipeline", wait_until="domcontentloaded"); await page.wait_for_timeout(3000)
        if await page.locator('[data-testid="pipeline-activate-cta"]').count():
            await page.locator('[data-testid="pipeline-activate-cta"]').tap(); await page.wait_for_timeout(2000)
        if await page.locator('[data-testid="pipeline-template-chooser"]').count():
            await page.locator('[data-testid^="pipeline-tpl-"]:not([data-testid^="pipeline-tpl-suggested"])').first.tap(); await page.wait_for_timeout(500)
            await page.locator('[data-testid="pipeline-create-cta"]').tap(); await page.wait_for_timeout(3000)
        await page.locator('[data-testid="pipeline-add-task"]').first.tap(); await page.wait_for_timeout(800)
        await page.locator('[data-testid="task-responsabile"]').scroll_into_view_if_needed()
        await page.locator('[data-testid="task-responsabile"]').tap(); await page.wait_for_timeout(800)
        await sheet_swipe(page, cdp, "staff-assign-popover", "staff-assign-list", "staff assign", '[role=dialog]')
        lastp = page.locator('[data-testid="staff-assign-list"] [data-testid^="staff-opt-"]').last
        name = await lastp.inner_text(); await lastp.scroll_into_view_if_needed(); await lastp.tap(); await page.wait_for_timeout(700)
        rep("[staff assign] last option selected", name.strip() in await page.locator('[data-testid="task-responsabile"]').inner_text(), name)
        rep("[staff assign] sheet closed after pick", not await page.locator('[data-testid="staff-assign-popover"]').is_visible())
        await b.close()
    print(f"TOTAL {sum(1 for _, o in results if o)}/{len(results)}")
if __name__ == "__main__":
    asyncio.run(main())
