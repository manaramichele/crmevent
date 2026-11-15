import asyncio
from playwright.async_api import async_playwright
from common import open_session, BASE
from capture_reels import snap


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        await page.goto(BASE + "/ospitalita", wait_until="networkidle")
        await page.wait_for_timeout(1200)
        for name in ["Bologna City Run 2026", "Maratona Demo", "Green Trail Experience 2026", "Sunset Triathlon 2027"]:
            await page.locator("main button[role=combobox]").first.click()
            await page.wait_for_timeout(400)
            opt = page.get_by_role("option", name=name)
            if not await opt.count():
                await page.keyboard.press("Escape")
                continue
            await opt.first.click()
            await page.wait_for_timeout(1500)
            if not await page.get_by_text("Nessuna persona collegata").count():
                await snap(page, "ospitalita")
                print("event", name)
                break
        await b.close()

asyncio.run(main())
