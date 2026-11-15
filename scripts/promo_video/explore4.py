import asyncio
from playwright.async_api import async_playwright
from common import open_session, BASE
from explore2 import step


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        hdr = {"X-Org-Id": "b7f40862230441b9a0bedabefe8dab49"}
        ev = await (await page.request.post(f"{BASE}/api/events", data={"nome": "ZZ Esplorazione"}, headers=hdr)).json()
        print("ev", ev.get("id"))
        try:
            await page.goto(BASE + "/eventi", wait_until="networkidle")
            await page.get_by_role("button", name="Aggiungi").click()
            await step(page, "x_tipologia", lambda: page.locator("[role=dialog] button[role=combobox]").first.click())
            await page.keyboard.press("Escape"); await page.keyboard.press("Escape")
            await page.goto(BASE + "/eventi", wait_until="networkidle")
            await step(page, "x_disp", lambda: page.locator("[data-testid=availability-demo_evt_bcr]:visible").first.click())
            await page.goto(BASE + "/eventi", wait_until="networkidle")
            await step(page, "x_altre", lambda: page.locator("[data-testid=more-actions-demo_evt_bcr]:visible").first.click())
            await page.goto(BASE + f"/eventi/{ev['id']}/pipeline", wait_until="networkidle")
            await step(page, "x_pipe1", lambda: page.get_by_role("button", name="Attiva Pipeline Evento").click())
            await page.wait_for_timeout(2000)
            await step(page, "x_pipe2", lambda: page.wait_for_timeout(100))
            await page.goto(BASE + "/aziende", wait_until="networkidle")
            await step(page, "x_az_edit", lambda: page.locator("main button:has(svg.lucide-pencil):visible").first.click())
            await page.goto(BASE + "/sponsor", wait_until="networkidle")
            await step(page, "x_sp_filter", lambda: page.click("[data-testid=sponsor-event-filter]"))
            await page.keyboard.press("Escape")
            await page.click("[data-testid=add-deal-button]")
            await step(page, "x_sp_az", lambda: page.locator("[role=dialog] button[role=combobox]").first.click())
        finally:
            print(await page.request.delete(f"{BASE}/api/events/{ev['id']}", headers=hdr))
        await b.close()

asyncio.run(main())
