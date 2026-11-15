import asyncio
from playwright.async_api import async_playwright
from common import open_session, BASE, DEMO_ORG, purge_event_leftovers
from recorder import Rec, encode

HDR = {"X-Org-Id": DEMO_ORG}
NAME = "Lago Blu Trail 2027"


async def cleanup(page):
    evs = await (await page.request.get(f"{BASE}/api/events", headers=HDR)).json()
    for e in evs if isinstance(evs, list) else evs.get("items", []):
        if e.get("nome") == NAME:
            print("cleanup", e["id"], (await page.request.delete(f"{BASE}/api/events/{e['id']}", headers=HDR)).status)
            purge_event_leftovers([e["id"]])


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        await cleanup(page)
        r = Rec(page, "eventi")
        await page.goto(BASE + "/eventi", wait_until="networkidle")
        r.card("intro", "Gestisci tutti i tuoi eventi", "Eventi · CRMEvent", 2.4)
        await page.wait_for_timeout(800)
        await r.leave_card()
        r.caption("Tutti i tuoi eventi in un'unica lista", "Date, città, tipologia e fase di ogni manifestazione")
        r.hold(2.2)
        r.caption("Crea un nuovo evento", "Bastano pochi dati per iniziare")
        await r.click(page.get_by_role("button", name="Aggiungi"))
        dlg = page.locator("[role=dialog]")
        await r.type(dlg.locator("[data-testid=field-nome]"), NAME)
        await r.type(dlg.locator("[data-testid=field-edizione]"), "2027", step=4)
        await r.click(dlg.locator("button[role=combobox]").first, wait=400, after=0.2)
        await r.click(page.get_by_role("option", name="Trail", exact=True), wait=400, after=0.2)
        await r.type(dlg.locator("[data-testid=field-data_inizio]"), "09122027", step=8)
        await r.type(dlg.locator("[data-testid=field-citta]"), "Bardolino", step=5)
        r.hold(0.4)
        await r.click(dlg.get_by_role("button", name="Salva"), wait=1500, after=0.3)
        r.caption("Gestisci più eventi insieme", "Ogni evento ha i suoi dati, il suo staff, i suoi sponsor")
        r.hl = await r.box(page.locator("tr", has_text=NAME).first)
        r.hold(1.6)
        r.hl = None
        r.caption("Tutte le funzioni collegate all'evento", "Disponibilità, Pipeline, Percorsi, Calendario e Briefing")
        row = page.locator("tr", has_text=NAME).first
        await r.point(row.locator("td").last, sec=0.8)
        r.hold(1.6)
        r.caption("Organizza le attività", "Pipeline con scadenze calcolate sulla data dell'evento")
        await r.click(row.get_by_role("button", name="Pipeline"), wait=1500)
        await r.click(page.locator("[data-testid=pipeline-activate-cta]"), wait=1500, after=0.6)
        await r.click(page.get_by_text("Trail Running", exact=True), wait=500, after=0.3)
        await r.click(page.locator("[data-testid=pipeline-create-cta]"), wait=3500, after=0.4)
        await page.mouse.move(1500, 600)
        await r.capture(0.3)
        r.show_cur = False
        r.hold(1.0)
        await r.scroll(500, steps=10)
        r.hold(0.8)
        r.caption("Panoramica dell'evento", "Il briefing raccoglie team, turni, percorsi e ospitalità")
        await r.goto(BASE + "/eventi/demo_evt_bcr/briefing", wait=2500)
        r.hold(1.2)
        await r.scroll(700, steps=10)
        r.hold(1.0)
        r.caption(None)
        r.card("outro", "Tutti i tuoi eventi, un'unica piattaforma.", "Eventi · CRMEvent", 3.6)
        await cleanup(page)
        await b.close()
    encode("eventi", "sportiva", 9)

asyncio.run(main())
