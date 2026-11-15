import asyncio
from playwright.async_api import async_playwright
from common import open_session, BASE, DEMO_ORG
from recorder import Rec, encode

AZ = "TrailFood Catering"


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        r = Rec(page, "sponsor-partner")
        await page.goto(BASE + "/aziende", wait_until="networkidle")
        r.card("intro", "Gestisci sponsor e partner", "Sponsor e Partner · CRMEvent", 2.4)
        await page.wait_for_timeout(800)
        await r.leave_card()
        r.caption("Anagrafica di sponsor e partner", "Un'unica anagrafica per aziende, fornitori e media")
        r.hold(1.8)
        await r.click(page.locator("tr", has_text="ActiveGear").locator("button:has(svg.lucide-pencil)").first, wait=900, after=0.6)
        r.caption("Contatti e referenti", "Dati aziendali e persone di riferimento")
        dlg = page.locator("[role=dialog]")
        await r.scroll(700, steps=10, target=dlg.first)
        r.hold(1.4)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)
        r.show_cur = False
        r.caption("La pipeline delle collaborazioni", "Trattative, valore e importo confermato in tempo reale")
        await r.goto(BASE + "/sponsor", wait=1500)
        r.hl = await r.box(page.get_by_text("Valore pipeline", exact=False).first.locator("xpath=.."))
        r.hold(1.6)
        r.hl = None
        r.caption("Ogni accordo collegato al suo evento", "Azienda, evento, tipo e valore della collaborazione")
        await r.click(page.locator("[data-testid=add-deal-button]"), wait=900, after=0.3)
        dlg = page.locator("[role=dialog]")
        combos = dlg.locator("button[role=combobox]")
        await r.click(combos.nth(0), wait=400, after=0.2)
        await r.click(page.get_by_role("option", name=AZ, exact=True), wait=400, after=0.2)
        await r.click(combos.nth(1), wait=400, after=0.2)
        await r.click(page.get_by_role("option", name="Bologna City Run 2026", exact=True), wait=400, after=0.2)
        await r.click(combos.nth(2), wait=400, after=0.2)
        await r.click(page.get_by_role("option", name="Sponsor", exact=True), wait=400, after=0.2)
        await r.click(combos.nth(3), wait=400, after=0.2)
        await r.click(page.get_by_role("option", name="Contattato", exact=True), wait=400, after=0.2)
        await r.type(dlg.locator("input[type=number]").first, "2500", step=4)
        await r.click(dlg.get_by_role("button", name="Salva"), wait=1500, after=0.4)
        card = page.locator("div.rounded-lg, div.rounded-xl", has_text=AZ).last
        r.hl = await r.box(card)
        r.hold(1.2)
        r.hl = None
        r.caption("Monitora l'avanzamento", "Sposta la trattativa di fase in un clic")
        await r.click(card.locator("button[role=combobox]").first, wait=400, after=0.2)
        await r.click(page.get_by_role("option", name="Proposta inviata", exact=True), wait=1500, after=0.3)
        await page.mouse.move(1700, 900)
        r.show_cur = False
        r.hl = await r.box(page.locator("div.rounded-lg, div.rounded-xl", has_text=AZ).last)
        r.hold(1.8)
        r.hl = None
        r.caption(None)
        r.card("outro", "Ogni collaborazione sotto controllo.", "Sponsor e Partner · CRMEvent", 3.6)
        import pymongo
        from dotenv import dotenv_values
        e = dotenv_values("/app/backend/.env")
        db = pymongo.MongoClient(e["MONGO_URL"])[e["DB_NAME"]]
        az = db.companies.find_one({"org_id": DEMO_ORG, "ragione_sociale": AZ}, {"_id": 0, "id": 1}) or db.companies.find_one({"org_id": DEMO_ORG, "nome": AZ}, {"_id": 0, "id": 1})
        print("purge deal", db.deals.delete_many({"org_id": DEMO_ORG, "azienda_id": az["id"], "created_at": {"$gte": "2026-11-15"}}).deleted_count)
        await b.close()
    encode("sponsor-partner", "emozionale", 8)

asyncio.run(main())
