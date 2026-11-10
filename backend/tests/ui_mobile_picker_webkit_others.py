# WebKit iPhone 13: StaffAssignSelect (pipeline) and TeamMembersDialog add sheets - touch not prevented, scrollable, tap selects
import asyncio, json
from playwright.async_api import async_playwright
from ui_mobile_picker_webkit import TOUCH_JS, BASE, IDS, rep, results

async def check(page, sheet, lst, label):
    rep(f"[wk {label}] sheet open", await page.locator(f'[data-testid="{sheet}"]').get_attribute("data-sheet") == "true")
    i = await page.evaluate("(l)=>{const li=document.querySelector(l);return [li.scrollHeight, li.clientHeight, getComputedStyle(li).overflowY]}", f'[data-testid="{lst}"]')
    rep(f"[wk {label}] list scrollable", i[0] > i[1] and i[2] == "auto", i)
    t = await page.evaluate(TOUCH_JS, [f'[data-testid="{lst}"] button:nth-child(2)', 150])
    rep(f"[wk {label}] touch not prevented", t["start"] is False and not any(t["moves"]), t)

async def main():
    async with async_playwright() as p:
        b = await p.webkit.launch(); ctx = await b.new_context(**p.devices["iPhone 13"]); page = await ctx.new_page()
        await page.request.post(f"{BASE}/api/auth/login", data={"email": IDS["email"], "password": IDS["password"]})
        await page.goto(f"{BASE}/eventi/{IDS['events'][0]}/pipeline", wait_until="domcontentloaded"); await page.wait_for_timeout(3500)
        if await page.locator('[data-testid="cookie-accept-all"]').count(): await page.locator('[data-testid="cookie-accept-all"]').first.tap()
        await page.locator('[data-testid="pipeline-add-task"]').first.tap(); await page.wait_for_timeout(800)
        await page.locator('[data-testid="task-responsabile"]').scroll_into_view_if_needed(); await page.locator('[data-testid="task-responsabile"]').tap(); await page.wait_for_timeout(800)
        await check(page, "staff-assign-popover", "staff-assign-list", "staff assign")
        last = page.locator('[data-testid="staff-assign-list"] [data-testid^="staff-opt-"]').last; nm = (await last.inner_text()).strip()
        await last.scroll_into_view_if_needed(); await last.tap(); await page.wait_for_timeout(600)
        rep("[wk staff assign] tap last selects", nm in await page.locator('[data-testid="task-responsabile"]').inner_text(), nm)
        await page.goto(f"{BASE}/staff-volontari", wait_until="domcontentloaded"); await page.wait_for_timeout(2500)
        await page.locator('[data-testid="tab-team"]').first.tap(); await page.wait_for_timeout(1500)
        await page.locator(f'[data-testid="m-edit-team-{IDS["teams"][2]}"]').first.tap(); await page.wait_for_timeout(1200)
        await page.locator('[data-testid="team-add-member"]').first.tap(); await page.wait_for_timeout(800)
        await check(page, "team-add-popover", "team-add-list", "team add")
        o = page.locator('[data-testid^="team-add-opt-"]').last; nm = (await o.locator("span").first.inner_text()).strip()
        await o.scroll_into_view_if_needed(); await o.tap(); await page.wait_for_timeout(1500)
        rep("[wk team add] tap last adds member", nm.split()[0] in await page.locator('[role=dialog]').first.inner_text(), nm)
        await page.screenshot(path="/app/.screenshots/wk_team_add_after.jpeg", quality=40, type="jpeg")
        await b.close()
    print(f"TOTAL {sum(1 for _, o in results if o)}/{len(results)}")
asyncio.run(main())
