"""Cattura schermate reali e pulite (senza cursore) dell'interfaccia per i Reels, organizzazione Demo ufficiale. Dati temporanei rimossi alla fine."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright
from common import open_session, clean, BASE, DEMO_ORG, purge_event_leftovers

OUT = Path("/app/backend/promo_reels/assets")
HDR = {"X-Org-Id": DEMO_ORG}


async def snap(page, name, wait=1200):
    await page.wait_for_timeout(wait)
    await clean(page)
    await page.mouse.move(1919, 1079)
    await page.screenshot(path=str(OUT / f"{name}.png"))
    print("ok", name)


async def go(page, url, name, wait=1800):
    await page.goto(BASE + url, wait_until="networkidle")
    await snap(page, name, wait)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        tmp = await (await page.request.post(f"{BASE}/api/events", data={"nome": "Lago Blu Trail 2027", "data_inizio": "2027-09-12", "citta": "Bardolino", "tipologia": "Trail"}, headers=HDR)).json()
        try:
            await go(page, "/app", "dashboard")
            await go(page, "/eventi", "eventi_list")
            await page.get_by_role("button", name="Aggiungi").click()
            dlg = page.locator("[role=dialog]")
            await dlg.locator("[data-testid=field-nome]").fill("Lago Blu Trail 2027")
            await dlg.locator("[data-testid=field-edizione]").fill("2027")
            await dlg.locator("[data-testid=field-citta]").fill("Bardolino")
            await snap(page, "eventi_new")
            await page.keyboard.press("Escape")
            await page.goto(BASE + f"/eventi/{tmp['id']}/pipeline", wait_until="networkidle")
            await page.locator("[data-testid=pipeline-activate-cta]").click()
            await page.wait_for_timeout(800)
            await page.get_by_text("Trail Running", exact=True).click()
            await page.locator("[data-testid=pipeline-create-cta]").click()
            await page.wait_for_timeout(3500)
            await snap(page, "pipeline")
            await go(page, "/eventi/demo_evt_bcr/briefing", "briefing_top", 2500)
            await page.mouse.wheel(0, 700)
            await snap(page, "briefing_mid")
            await page.goto(BASE + "/eventi", wait_until="networkidle")
            await page.locator("[data-testid=maps-demo_evt_bcr]:visible").first.click()
            await snap(page, "percorsi", 2000)
            await page.keyboard.press("Escape")
            await page.goto(BASE + "/eventi", wait_until="networkidle")
            await page.locator("[data-testid=availability-demo_evt_bcr]:visible").first.click()
            gen = page.get_by_role("button", name="Genera link pubblico")
            if await gen.count():
                await gen.click()
            await snap(page, "disponibilita")
            link = await (await page.request.get(f"{BASE}/api/events/demo_evt_bcr/availability/link", headers=HDR)).json()
            await go(page, f"/partecipa/{link['code']}", "partecipa", 2200)
            await go(page, "/staff-volontari", "staff_list")
            for t in ["volontari", "team", "turni"]:
                await page.click(f"[data-testid=tab-{t}]")
                await snap(page, t)
            await go(page, "/aziende", "aziende")
            await page.locator("tr", has_text="ActiveGear").locator("button:has(svg.lucide-pencil)").first.click()
            await snap(page, "azienda_dialog")
            await page.keyboard.press("Escape")
            await go(page, "/sponsor", "sponsor_kanban")
            await page.click("[data-testid=add-deal-button]")
            await snap(page, "deal_dialog")
            await page.keyboard.press("Escape")
            await go(page, "/ospitalita", "ospitalita")
            await go(page, "/iscritti", "iscritti", 2500)
        finally:
            await page.request.delete(f"{BASE}/api/events/{tmp['id']}", headers=HDR)
            purge_event_leftovers([tmp["id"]])
            import pymongo
            from dotenv import dotenv_values
            e = dotenv_values("/app/backend/.env")
            db = pymongo.MongoClient(e["MONGO_URL"])[e["DB_NAME"]]
            print("purge link", db.avail_links.delete_many({"org_id": DEMO_ORG, "evento_id": "demo_evt_bcr"}).deleted_count)
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
