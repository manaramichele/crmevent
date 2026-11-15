import asyncio
from playwright.async_api import async_playwright
from common import open_session, BASE, DEMO_ORG
from recorder import Rec, encode

HDR = {"X-Org-Id": DEMO_ORG}


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        prev = await (await page.request.get(f"{BASE}/api/events/demo_evt_bcr/availability/link", headers=HDR)).json()
        r = Rec(page, "staff-volontari")
        await page.goto(BASE + "/staff-volontari", wait_until="networkidle")
        r.card("intro", "Organizza staff e volontari", "Staff e Volontari · CRMEvent", 2.4)
        await page.wait_for_timeout(800)
        await r.leave_card()
        r.caption("Un unico elenco di staff e volontari", "Contatti, team, mansioni ed eventi di ogni persona")
        r.hold(1.8)
        await r.click(page.locator("[data-testid=tab-volontari]"), wait=1200, after=0.6)
        r.caption("Ruoli e mansioni", "Ogni persona con il suo ruolo nell'evento")
        r.hl = await r.box(page.locator("th:visible", has_text="Mansione").first)
        r.hold(1.6)
        r.hl = None
        r.caption("Raccolta delle disponibilità", "Un link pubblico per ogni evento")
        await r.goto(BASE + "/eventi", wait=1200)
        await r.click(page.locator("[data-testid=availability-demo_evt_bcr]:visible").first, wait=900, after=0.5)
        gen = page.get_by_role("button", name="Genera link pubblico")
        if await gen.count():
            await r.click(gen, wait=1200, after=1.4)
        link = await (await page.request.get(f"{BASE}/api/events/demo_evt_bcr/availability/link", headers=HDR)).json()
        r.caption("Il modulo pubblico", "Le persone indicano giorni e attività, senza registrarsi")
        await r.goto(f"{BASE}/partecipa/{link['code']}", wait=2000)
        r.show_cur = False
        r.hold(1.4)
        await r.scroll(650, steps=12)
        r.hold(1.0)
        r.caption("Team con responsabile", "Squadre operative per ogni evento")
        await r.goto(BASE + "/staff-volontari", wait=1200)
        await r.click(page.locator("[data-testid=tab-team]"), wait=1200, after=1.4)
        r.caption("Assegnazioni a turni e postazioni", "I turni scoperti saltano subito all'occhio")
        await r.click(page.locator("[data-testid=tab-turni]"), wait=1200, after=0.4)
        r.hl = await r.box(page.locator("span:visible", has_text="Scoperto").first)
        r.hold(1.6)
        r.hl = None
        r.caption("Informazioni organizzative a portata di mano", "Il briefing riunisce team, responsabili e turni")
        await r.goto(BASE + "/eventi/demo_evt_bcr/briefing", wait=2500)
        r.show_cur = False
        await r.scroll(560, steps=10)
        r.hold(2.0)
        r.caption(None)
        r.card("outro", "Le persone giuste, nel posto giusto.", "Staff e Volontari · CRMEvent", 3.6)
        if not prev.get("active"):
            await page.request.delete(f"{BASE}/api/events/demo_evt_bcr/availability/link", headers=HDR)
            import pymongo
            from dotenv import dotenv_values
            e = dotenv_values("/app/backend/.env")
            db = pymongo.MongoClient(e["MONGO_URL"])[e["DB_NAME"]]
            print("purge link", db.avail_links.delete_many({"org_id": DEMO_ORG, "evento_id": "demo_evt_bcr"}).deleted_count)
        await b.close()
    encode("staff-volontari", "elettronica", 8)

asyncio.run(main())
