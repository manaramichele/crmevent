import asyncio, sys
from playwright.async_api import async_playwright
from common import open_session, clean, BASE

PAGES = sys.argv[1:] or ["/eventi", "/staff-volontari", "/sponsor"]


async def main():
    async with async_playwright() as pw:
        b, page = await open_session(pw)
        for u in PAGES:
            await page.goto(BASE + u, wait_until="networkidle")
            await page.wait_for_timeout(1500)
            await clean(page)
            await page.screenshot(path=f"/tmp/ex_{u.strip('/').replace('/', '_').replace('?', '_')}.jpg", type="jpeg", quality=60)
        await b.close()

asyncio.run(main())
