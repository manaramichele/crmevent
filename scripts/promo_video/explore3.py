import asyncio
from playwright.async_api import async_playwright
from common import open_session, clean, BASE
from explore2 import snap, step


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        await step(page, "azioni", lambda: page.goto(BASE + "/azioni-rapide", wait_until="networkidle"))
        await step(page, "partecipa", lambda: page.goto(BASE + "/partecipa/7lbyQLiif9oPO3Vus-dbqps9cBVlpHHL", wait_until="networkidle"))
        await page.goto(BASE + "/eventi", wait_until="networkidle")
        await step(page, "ev_disp", lambda: page.locator("[data-testid=availability-demo_evt_bcr]").first.click())
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        await step(page, "ev_altre", lambda: page.locator("[data-testid=more-actions-demo_evt_bcr]").first.click())
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        await step(page, "ev_edit", lambda: page.locator("[data-testid=edit-event-demo_evt_bcr]").first.click())
        await page.keyboard.press("Escape")
        await page.goto(BASE + "/sponsor", wait_until="networkidle")
        await step(page, "sp_edit", lambda: page.locator("main button:has(svg.lucide-pencil)").first.click())
        await page.keyboard.press("Escape")
        await page.goto(BASE + "/aziende", wait_until="networkidle")
        await step(page, "az_edit", lambda: page.locator("main button:has(svg.lucide-pencil)").first.click())
        await page.keyboard.press("Escape")
        await page.goto(BASE + "/staff-volontari", wait_until="networkidle")
        await step(page, "st_edit", lambda: page.locator("main button:has(svg.lucide-pencil)").nth(1).click())
        await b.close()

asyncio.run(main())
