# Pipeline StaffAssignSelect mobile sheet (Pixel 5 CDP touch) + Desktop 1920x800 regression (Popover anchored, wheel scroll, select) for TeamSelect / StaffAssignSelect / TeamMembersDialog add
import asyncio, json, sys
from playwright.async_api import async_playwright
sys.path.insert(0, "/app/backend/tests")
from ui_mobile_picker_chromium_touch import swipe, sheet_swipe, rep, results, BASE, IDS, PID, PRES, EV  # noqa

async def desktop_check(page, trig, pop, lst, label):
    await page.locator(f'[data-testid="{trig}"]').click(); await page.wait_for_timeout(600)
    p = page.locator(f'[data-testid="{pop}"]')
    ok = await p.is_visible(); rep(f"[desk {label}] popover opens", ok)
    if not ok: return
    ds = await p.get_attribute("data-sheet"); rep(f"[desk {label}] is Popover not sheet", ds is None, ds)
    inwrap = await page.evaluate(f"() => !!document.querySelector('[data-testid=\"{pop}\"]').closest('[data-radix-popper-content-wrapper]')")
    tb = await page.locator(f'[data-testid="{trig}"]').bounding_box(); pb = await p.bounding_box()
    anchored = inwrap and abs(pb["x"] - tb["x"]) < 400 and (abs(pb["y"] - (tb["y"] + tb["height"])) < 20 or abs(pb["y"] + pb["height"] - tb["y"]) < 20)
    rep(f"[desk {label}] anchored to trigger", anchored, (tb, pb))
    lb = await page.locator(f'[data-testid="{lst}"]').bounding_box()
    await page.mouse.move(lb["x"] + lb["width"] / 2, lb["y"] + lb["height"] / 2)
    for _ in range(5): await page.mouse.wheel(0, 200); await page.wait_for_timeout(100)
    st = await page.evaluate(f"() => document.querySelector('[data-testid=\"{lst}\"]').scrollTop")
    rep(f"[desk {label}] mouse wheel scrolls list", st > 0, st)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/local/bin/browser-use-chromium")
        ctx = await b.new_context(**p.devices["Pixel 5"]); page = await ctx.new_page(); cdp = await ctx.new_cdp_session(page)
        page.on("pageerror", lambda e: print("PAGEERROR", e))
        await page.request.post(f"{BASE}/api/auth/login", data={"email": IDS["email"], "password": IDS["password"]})
        await page.goto(f"{BASE}/eventi/{EV}/pipeline", wait_until="domcontentloaded"); await page.wait_for_timeout(3500)
        if await page.locator('[data-testid="cookie-accept-all"]').count(): await page.locator('[data-testid="cookie-accept-all"]').first.tap()
        await page.locator('[data-testid="pipeline-add-task"]').first.tap(); await page.wait_for_timeout(800)
        await page.locator('[data-testid="task-responsabile"]').scroll_into_view_if_needed()
        await page.locator('[data-testid="task-responsabile"]').tap(); await page.wait_for_timeout(800)
        await sheet_swipe(page, cdp, "staff-assign-popover", "staff-assign-list", "staff assign", '[role=dialog]')
        lastp = page.locator('[data-testid="staff-assign-list"] [data-testid^="staff-opt-"]').last
        name = (await lastp.inner_text()).strip(); await lastp.scroll_into_view_if_needed(); await lastp.tap(); await page.wait_for_timeout(700)
        rep("[staff assign] last option selected", name in await page.locator('[data-testid="task-responsabile"]').inner_text(), name)
        rep("[staff assign] sheet closed, task dialog still open", not await page.locator('[data-testid="staff-assign-popover"]').is_visible() and await page.locator('[data-testid="task-titolo"]').is_visible())
        await page.locator('[data-testid="task-responsabile"]').tap(); await page.wait_for_timeout(600)
        await page.locator('[data-testid="staff-assign-search"]').fill("Staff03"); await page.wait_for_timeout(300)
        rep("[staff assign] search filters", await page.locator('[data-testid="staff-assign-list"] [data-testid^="staff-opt-"]:not([data-testid="staff-opt-none"]):not([data-testid="staff-opt-empty"])').count() == 1)
        await page.locator('[data-testid="staff-add-new"]').tap(); await page.wait_for_timeout(500)
        rep("[staff assign] quick add form in sheet", await page.locator('[data-testid="staff-quick-add-form"]').is_visible())
        await page.locator('[data-testid="staff-assign-popover-close"]').tap(); await page.wait_for_timeout(500)
        rep("[staff assign] close works", not await page.locator('[data-testid="staff-assign-popover"]').is_visible())
        await ctx.close()
        # ---------------- Desktop regression
        ctx = await b.new_context(viewport={"width": 1920, "height": 800}); page = await ctx.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR", e))
        await page.request.post(f"{BASE}/api/auth/login", data={"email": IDS["email"], "password": IDS["password"]})
        await page.goto(f"{BASE}/eventi/{EV}/pipeline", wait_until="domcontentloaded"); await page.wait_for_timeout(3500)
        if await page.locator('[data-testid="cookie-accept-all"]').count(): await page.locator('[data-testid="cookie-accept-all"]').first.click()
        await page.locator('[data-testid="pipeline-add-task"]').first.click(); await page.wait_for_timeout(800)
        await desktop_check(page, "task-responsabile", "staff-assign-popover", "staff-assign-list", "staff assign")
        rep("[desk staff assign] search autofocused", await page.evaluate("() => document.activeElement?.dataset?.testid") == "staff-assign-search")
        opt = page.locator('[data-testid="staff-assign-list"] [data-testid^="staff-opt-"]').nth(3); nm = (await opt.inner_text()).strip()
        await opt.click(); await page.wait_for_timeout(500)
        rep("[desk staff assign] select works", nm in await page.locator('[data-testid="task-responsabile"]').inner_text(), nm)
        await page.keyboard.press("Escape"); await page.wait_for_timeout(500)
        # TeamSelect in person dialog
        await page.goto(f"{BASE}/staff-volontari", wait_until="domcontentloaded"); await page.wait_for_timeout(2500)
        await page.locator('[data-testid="tab-volontari"]').click(); await page.wait_for_timeout(800)
        op = page.locator(f'[data-testid="person-row-{PID}"]')
        if not await op.count(): op = page.locator(f'[data-testid="m-person-row-{PID}"]')
        if not await op.count(): op = page.get_by_text("TEST_Rossi", exact=False)
        await op.first.click(); await page.wait_for_timeout(1000)
        await page.locator('[data-testid="person-detail-edit"]').click(); await page.wait_for_timeout(400)
        await page.locator('[data-testid="ptab-team"]').click(); await page.wait_for_timeout(500)
        tid = f"team-assign-{PRES}"
        await desktop_check(page, tid, f"{tid}-popover", f"{tid}-list", "team select")
        rep("[desk team select] no search field on desktop (unchanged)", await page.locator(f'[data-testid="{tid}-search"]').count() == 0)
        await page.locator(f'[data-testid="{tid}-opt-{IDS["teams"][12]}"]').click(); await page.wait_for_timeout(1200)
        rep("[desk team select] select works", "TEST_Team 12" in await page.locator(f'[data-testid="{tid}"]').inner_text())
        await page.screenshot(path="/app/.screenshots/desk_team.jpeg", quality=40, type="jpeg")
        await page.keyboard.press("Escape"); await page.wait_for_timeout(500)
        # TeamMembersDialog add
        await page.goto(f"{BASE}/staff-volontari", wait_until="domcontentloaded"); await page.wait_for_timeout(2500)
        await page.locator('[data-testid="tab-team"]').first.click(); await page.wait_for_timeout(1500)
        t1 = IDS["teams"][1]
        r = page.locator(f'[data-testid="team-name-{t1}"]')
        await r.first.click(); await page.wait_for_timeout(1200)
        if not await page.locator('[data-testid="team-add-member"]').count():
            ed = page.locator(f'[data-testid="edit-team-{t1}"], [data-testid="view-team-{t1}"], [data-testid="open-team-{t1}"]')
            if await ed.count(): await ed.first.click(); await page.wait_for_timeout(1200)
        if await page.locator('[data-testid="team-add-member"]').count():
            await desktop_check(page, "team-add-member", "team-add-popover", "team-add-list", "team add")
            o = page.locator('[data-testid^="team-add-opt-"]').first; nm = (await o.locator("span").first.inner_text()).strip()
            await o.click(); await page.wait_for_timeout(1500)
            rep("[desk team add] member added", nm.split()[0] in await page.locator('[role=dialog]').first.inner_text(), nm)
        else:
            rep("[desk team add] could not open TeamMembersDialog", False, [x for x in await page.evaluate("() => [...document.querySelectorAll('[data-testid]')].map(e=>e.dataset.testid)") if t1 in x])
        await b.close()
    print(f"TOTAL {sum(1 for _, o in results if o)}/{len(results)}")
asyncio.run(main())
