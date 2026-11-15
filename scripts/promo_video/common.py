"""Sessione Playwright sull'interfaccia reale (anteprima) con l'organizzazione Demo ufficiale (dati di fantasia)."""
BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
DEMO_ORG = "b7f40862230441b9a0bedabefe8dab49"
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
W, H = 1920, 1080
CHROME = "/pw-browsers/chromium_headless_shell-1248/chrome-headless-shell-linux-arm64/chrome-headless-shell"

CLEAN_CSS = """
[data-testid=org-switcher],[data-testid=super-acting-banner],[data-testid=cookie-banner],[data-testid=mobile-org-switcher],
nav > div:has([data-testid=nav-group-platform]),[data-testid=support-chat-launcher],[data-testid=header-assistant-button],#webpack-dev-server-client-overlay{display:none!important}
[data-testid=profile-button] span{visibility:hidden}
"""

CLEAN_JS = """(css) => {
  if (!document.getElementById('rec-clean')) { const s = document.createElement('style'); s.id = 'rec-clean'; s.textContent = css; document.head.appendChild(s); }
  document.querySelectorAll('[role=dialog]').forEach(d => { if (/privacy|cookie/i.test(d.textContent) && /Accept|Accetta/.test(d.textContent)) d.remove(); });
  document.querySelectorAll('tr').forEach(r => { if (/TEST/.test(r.textContent)) r.remove(); });
}"""


async def open_session(pw):
    browser = await pw.chromium.launch(executable_path=CHROME, args=["--disable-dev-shm-usage"])
    ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, locale="it-IT")
    page = await ctx.new_page()
    r = await page.request.post(f"{BASE}/api/auth/login", data=SA)
    assert r.status == 200, r.status
    await page.goto(f"{BASE}/")
    await page.evaluate(f"localStorage.setItem('acting_org_id','{DEMO_ORG}')")
    return browser, page


async def clean(page):
    for _ in range(5):
        try:
            await page.evaluate(CLEAN_JS, CLEAN_CSS)
            return
        except Exception:
            await page.wait_for_timeout(500)


def purge_event_leftovers(event_ids):
    import pymongo
    from dotenv import dotenv_values
    e = dotenv_values("/app/backend/.env")
    db = pymongo.MongoClient(e["MONGO_URL"])[e["DB_NAME"]]
    for c in ["event_pipelines", "pipeline_tasks", "pipeline_categories", "avail_links", "availabilities"]:
        r = db[c].delete_many({"org_id": DEMO_ORG, "$or": [{"event_id": {"$in": event_ids}}, {"evento_id": {"$in": event_ids}}]})
        print("purge", c, r.deleted_count)
