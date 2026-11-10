# WebKit iPhone 13 emulation test for ResponsivePicker bottom sheet (TeamSelect inside PersonDetailDialog)
import asyncio, json, os, sys
from playwright.async_api import async_playwright

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
IDS = json.load(open("/tmp/menuscroll_ids.json"))
PID = IDS["persons"][0]
PRES = IDS["staff"][0]
SHOT = "/app/.screenshots"
os.makedirs(SHOT, exist_ok=True)
results = []

def rep(name, ok, info=""):
    results.append((name, ok)); print(("PASS " if ok else "FAIL ") + name + (" | " + str(info) if info else ""))

TOUCH_JS = """([sel, dy]) => {
  const el = document.querySelector(sel); if (!el) return {err: 'no el'};
  const r = el.getBoundingClientRect(); const x = r.left + r.width/2, y = r.top + r.height/2;
  const mk = (yy) => { try { return [new Touch({identifier: 1, target: el, clientX: x, clientY: yy, pageX: x, pageY: yy})]; } catch (e) { return document.createTouchList(document.createTouch(window, el, 1, x, yy, x, yy)); } };
  const ts = new TouchEvent('touchstart', {bubbles: true, cancelable: true, touches: mk(y), targetTouches: mk(y), changedTouches: mk(y)});
  el.dispatchEvent(ts);
  const out = {start: ts.defaultPrevented, moves: []};
  for (let i = 1; i <= 5; i++) { const yy = y - dy * i / 5;
    const tm = new TouchEvent('touchmove', {bubbles: true, cancelable: true, touches: mk(yy), targetTouches: mk(yy), changedTouches: mk(yy)});
    el.dispatchEvent(tm); out.moves.push(tm.defaultPrevented); }
  const te = new TouchEvent('touchend', {bubbles: true, cancelable: true, changedTouches: mk(y-dy)});
  el.dispatchEvent(te);
  return out; }"""

async def open_person(page, tab, tid):
    await page.goto(f"{BASE}/staff-volontari", wait_until="domcontentloaded")
    await page.wait_for_timeout(2500)
    if await page.locator('[data-testid="cookie-accept-all"]').count():
        await page.locator('[data-testid="cookie-accept-all"]').first.tap()
    if await page.locator('[data-testid="tab-volontari"]').count():
        await page.locator('[data-testid="tab-volontari"]').first.tap(); await page.wait_for_timeout(800)
    await page.locator(f'[data-testid="m-open-person-{PID}"]').first.tap()
    await page.wait_for_selector('[data-testid="person-detail-edit"]', timeout=10000)
    await page.locator('[data-testid="person-detail-edit"]').tap(); await page.wait_for_timeout(500)
    await page.locator(f'[data-testid="ptab-{tab}"]').tap(); await page.wait_for_timeout(700)
    await page.locator(f'[data-testid="{tid}"]').scroll_into_view_if_needed()
    await page.locator(f'[data-testid="{tid}"]').tap(); await page.wait_for_timeout(700)

async def check_sheet(page, tid, label):
    sheet = f'[data-testid="{tid}-popover"]'
    lst = f'[data-testid="{tid}-list"]'
    vis = await page.locator(sheet).is_visible()
    rep(f"[{label}] sheet visible", vis)
    if not vis: return False
    info = await page.evaluate("""([s,l]) => { const e = document.querySelector(s), li = document.querySelector(l); const r = e.getBoundingClientRect();
      return {sheet: e.dataset.sheet, top: r.top, bottom: r.bottom, left: r.left, right: r.right, vh: innerHeight, vw: innerWidth,
        sh: li.scrollHeight, ch: li.clientHeight, ov: getComputedStyle(li).overflowY, n: li.querySelectorAll('button').length,
        hasSearch: !!e.querySelector('input'), title: e.querySelector('h2')?.textContent}; }""", [sheet, lst])
    print(label, info)
    rep(f"[{label}] is bottom sheet (data-sheet)", info["sheet"] == "true")
    rep(f"[{label}] sheet inside viewport", info["top"] >= 0 and info["bottom"] <= info["vh"] + 1 and info["left"] >= 0 and info["right"] <= info["vw"] + 1, info)
    rep(f"[{label}] list scroll container", info["sh"] > info["ch"] and info["ov"] == "auto")
    # (b) touch events not prevented
    last_btn = await page.evaluate("(l) => { const b = [...document.querySelectorAll(l + ' button')]; return b.length; }", lst)
    tb = await page.evaluate(TOUCH_JS, [f'{lst} button:nth-child(3)', 150])
    rep(f"[{label}] touchstart/touchmove NOT defaultPrevented on option", tb.get("start") is False and not any(tb.get("moves", [True])), tb)
    tb2 = await page.evaluate(TOUCH_JS, [lst, 150])
    rep(f"[{label}] touchmove NOT prevented on list itself", not any(tb2.get("moves", [True])), tb2)
    # control: touchmove on element OUTSIDE the sheet (person dialog behind) should be blocked by active scroll lock
    ctl = await page.evaluate(TOUCH_JS, ['[data-testid="person-detail-edit"], [data-testid="person-detail-save"]', 150])
    rep(f"[{label}] CONTROL: touchmove outside sheet IS prevented (method valid)", any(ctl.get("moves", [])), ctl)
    # (c) programmatic scroll reaches last option
    st = await page.evaluate("(l)=>{const li=document.querySelector(l);li.scrollTop=li.scrollHeight;const b=[...li.querySelectorAll('button')].pop().getBoundingClientRect();const r=li.getBoundingClientRect();return [li.scrollTop, li.scrollHeight-li.clientHeight, b.bottom<=r.bottom+1]}", lst)
    rep(f"[{label}] programmatic scroll reaches last option", st[0] > 0 and abs(st[0]-st[1]) < 3 and st[2], st)
    await page.evaluate("(l)=>{document.querySelector(l).scrollTop=0}", lst)
    return True

async def main():
    async with async_playwright() as p:
        dev = p.devices["iPhone 13"]
        browser = await p.webkit.launch()
        ctx = await browser.new_context(**dev)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR", e))
        r = await page.request.post(f"{BASE}/api/auth/login", data={"email": IDS["email"], "password": IDS["password"]})
        print("login", r.status)
        await page.request.post(f"{BASE}/api/demo/welcome/dismiss")
        tid = f"team-assign-{PRES}"
        await open_person(page, "team", tid)
        await page.screenshot(path=f"{SHOT}/wk_sheet_open.jpeg", quality=40, type="jpeg")
        if await check_sheet(page, tid, "webkit team-assign"):
            # dialog behind not scrolled? check close button exists
            rep("close btn present", await page.locator(f'[data-testid="{tid}-popover-close"]').count() == 1)
            last = IDS["teams"][17]
            opt = page.locator(f'[data-testid="{tid}-opt-{last}"]')
            await opt.scroll_into_view_if_needed()
            await page.screenshot(path=f"{SHOT}/wk_sheet_bottom.jpeg", quality=40, type="jpeg")
            await opt.tap(); await page.wait_for_timeout(1500)
            rep("tap last option closes sheet", not await page.locator(f'[data-testid="{tid}-popover"]').is_visible())
            txt = await page.locator(f'[data-testid="{tid}"]').inner_text()
            rep("trigger shows TEST_Team 17", "TEST_Team 17" in txt, txt)
            st = await page.request.get(f"{BASE}/api/staff?evento_id={IDS['events'][0]}")
            data = await st.json(); data = data if isinstance(data, list) else data.get("items", data)
            row = [x for x in data if x.get("id") == PRES]
            rep("persisted team_id", row and row[0].get("team_id") == last, row[0].get("team_id") if row else data)
            # search + none option
            await page.locator(f'[data-testid="{tid}"]').tap(); await page.wait_for_timeout(700)
            await page.locator(f'[data-testid="{tid}-search"]').fill("Team 05"); await page.wait_for_timeout(300)
            n = await page.locator(f'[data-testid="{tid}-list"] button').count()
            rep("search filters (none + 1)", n == 2, n)
            await page.locator(f'[data-testid="{tid}-search"]').fill("")
            await page.locator(f'[data-testid="{tid}-popover-close"]').tap(); await page.wait_for_timeout(500)
            rep("close button closes sheet", not await page.locator(f'[data-testid="{tid}-popover"]').is_visible())
            rep("person dialog still open after closing sheet", await page.locator('[data-testid="person-detail-save"]').count() > 0)
            await page.locator(f'[data-testid="{tid}"]').tap(); await page.wait_for_timeout(700)
            await page.locator(f'[data-testid="{tid}-opt-none"]').tap(); await page.wait_for_timeout(1200)
            txt = await page.locator(f'[data-testid="{tid}"]').inner_text()
            rep("none option resets", "Nessun team" in txt, txt)
            await page.locator(f'[data-testid="{tid}"]').tap(); await page.wait_for_timeout(700)
            await page.locator(f'[data-testid="{tid}-add"]').tap(); await page.wait_for_timeout(800)
            await page.screenshot(path=f"{SHOT}/wk_add_team.jpeg", quality=40, type="jpeg")
            dlgs = await page.locator('[role="dialog"]').count()
            rep("Aggiungi nuovo Team opens quick create", dlgs >= 2, dlgs)
            await page.keyboard.press("Escape"); await page.wait_for_timeout(500)
            # Save / cancel reachable
            for b in ["person-detail-save", "person-detail-cancel"]:
                loc = page.locator(f'[data-testid="{b}"]')
                if await loc.count():
                    await loc.scroll_into_view_if_needed(); bb = await loc.bounding_box()
                    rep(f"{b} reachable", bb is not None and bb["y"] + bb["height"] <= 844, bb)
                else:
                    rep(f"{b} present", False)
        # Eventi tab presence-edit-team
        tid2 = f"presence-edit-team-{PRES}"
        await open_person(page, "eventi", tid2)
        if await check_sheet(page, tid2, "webkit presence-edit-team"):
            last = IDS["teams"][16]
            opt = page.locator(f'[data-testid="{tid2}-opt-{last}"]'); await opt.scroll_into_view_if_needed(); await opt.tap(); await page.wait_for_timeout(1200)
            txt = await page.locator(f'[data-testid="{tid2}"]').inner_text()
            rep("presence-edit-team select TEST_Team 16", "TEST_Team 16" in txt, txt)
        await browser.close()
    print(f"TOTAL {sum(1 for _, o in results if o)}/{len(results)}")

if __name__ == "__main__":
    asyncio.run(main())
