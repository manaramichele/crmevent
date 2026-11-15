import asyncio
from playwright.async_api import async_playwright
from common import open_session, clean, BASE


async def snap(page, name):
    await page.wait_for_timeout(1200)
    await clean(page)
    await page.screenshot(path=f"/tmp/ex2_{name}.jpg", type="jpeg", quality=55)


async def step(page, name, fn):
    try:
        await fn()
        await snap(page, name)
    except Exception as e:
        print("FAIL", name, str(e)[:150])


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        await page.goto(BASE + "/eventi", wait_until="networkidle")
        await step(page, "ev_add", lambda: page.get_by_role("button", name="Aggiungi").click())
        await page.keyboard.press("Escape")
        await step(page, "ev_altre", lambda: page.click("[data-testid=more-actions-demo_evt_bcr]"))
        await page.keyboard.press("Escape")
        await step(page, "ev_pipeline", lambda: page.goto(BASE + "/eventi/demo_evt_bcr/pipeline", wait_until="networkidle"))
        await step(page, "ev_briefing", lambda: page.goto(BASE + "/eventi/demo_evt_bcr/briefing", wait_until="networkidle"))
        await page.goto(BASE + "/staff-volontari", wait_until="networkidle")
        for t in ["volontari", "team", "turni"]:
            await step(page, f"st_{t}", lambda t=t: page.click(f"[data-testid=tab-{t}]"))
        await step(page, "st_add", lambda: page.get_by_role("button", name="Aggiungi Staff / Volontario").click())
        await page.keyboard.press("Escape")
        await page.goto(BASE + "/eventi", wait_until="networkidle")
        await step(page, "ev_disp", lambda: page.click("[data-testid=availability-demo_evt_bcr]"))
        await step(page, "az", lambda: page.goto(BASE + "/aziende", wait_until="networkidle"))
        await page.goto(BASE + "/sponsor", wait_until="networkidle")
        await step(page, "sp_new", lambda: page.click("[data-testid=add-deal-button]"))
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
