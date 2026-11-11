# Iteration 152 Scenario E: mobile 390px (Chromium Pixel 5 + WebKit iPhone 13) preference cards
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from playwright.async_api import async_playwright
from avp_helpers import BASE, _db

d = json.load(open("/tmp/avp_ui.json"))
P1, P2, P3 = d["pid"]["p1"], d["pid"]["p2"], d["pid"]["p3"]


async def run(pw, kind):
    _db().persons.update_one({"id": P1, "org_id": d["org_id"]}, {"$unset": {"ruolo": ""}})
    if kind == "chromium":
        b = await pw.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROME_EXECUTABLE_PATH"))
        ctx = await b.new_context(**pw.devices["Pixel 5"])
    else:
        b = await pw.webkit.launch()
        ctx = await b.new_context(**pw.devices["iPhone 13"])
    page = await ctx.new_page()
    try:
        await page.goto(BASE + "/login")
        await page.wait_for_timeout(1500)
        try:
            await page.get_by_role("button", name="Reject non-essential").click(timeout=4000)
        except Exception:
            pass
        await page.fill('[data-testid="email-input"]', d["email"])
        await page.fill('[data-testid="password-input"]', "TestPass123!")
        await page.click('[data-testid="submit-auth-button"]')
        await page.wait_for_timeout(3000)
        await page.goto(BASE + "/staff-volontari")
        await page.wait_for_timeout(3000)
        try:
            await page.get_by_role("button", name="Reject non-essential").click(timeout=3000)
        except Exception:
            pass
        vw = await page.evaluate("[window.innerWidth, document.documentElement.scrollWidth]")
        print(kind, "viewport/scrollWidth:", vw)
        await page.tap('[data-testid="tab-da-classificare"]')
        await page.wait_for_timeout(1500)
        tp = '[role="tabpanel"][data-state="active"] [data-testid="people-mobile-list-da_classificare"]'
        print(kind, "m-pref P1 visible:", await page.locator(f'{tp} [data-testid="m-pref-{P1}"]').is_visible(), "text:", await page.locator(f'{tp} [data-testid="m-pref-{P1}"]').inner_text())
        btn = page.locator(f'{tp} [data-testid="pref-confirm-{P1}"]')
        bb = await btn.bounding_box()
        print(kind, "confirm btn box:", bb)
        await btn.tap()
        await page.wait_for_timeout(2500)
        print(kind, "after tap mansione:", await page.locator(f'{tp} [data-testid="m-mansione-{P1}"]').inner_text(), "done:", await page.locator(f'{tp} [data-testid="pref-done-{P1}"]').count())
        print(kind, "P3 pick visible:", await page.locator(f'{tp} [data-testid="pref-pick-{P3}"]').is_visible())
        await page.tap(f'{tp} [data-testid="select-invite-{P3}"]')
        await page.wait_for_timeout(400)
        bar = page.locator('[role="tabpanel"][data-state="active"] [data-testid="bulk-mansione-bar"]')
        print(kind, "bulk bar visible:", await bar.is_visible(), await bar.bounding_box())
        await page.screenshot(path=f"/app/test_reports/avp_mobile_{kind}.jpg", type="jpeg", quality=40, full_page=False)
        await page.tap('[data-testid="tab-volontari"]')
        await page.wait_for_timeout(1200)
        tv = '[role="tabpanel"][data-state="active"] [data-testid="people-mobile-list-volontari"]'
        print(kind, "volontari m-pref P2:", await page.locator(f'{tv} [data-testid="m-pref-{P2}"]').inner_text())
        vw = await page.evaluate("[window.innerWidth, document.documentElement.scrollWidth]")
        print(kind, "viewport/scrollWidth volontari:", vw)
    except Exception as e:
        print(kind, "ERR", e)
        await page.screenshot(path=f"/app/test_reports/avp_mobile_{kind}_err.jpg", type="jpeg", quality=40, full_page=False)
    await b.close()


async def main():
    async with async_playwright() as pw:
        for k in sys.argv[1:] or ["chromium", "webkit"]:
            await run(pw, k)

asyncio.run(main())
