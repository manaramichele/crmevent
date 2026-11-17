# Control Room promo page (iteration 178): /controlroom/events promo state, SA grant/revoke/disable on Demo org, 402 when inactive, data preserved, promo-materials control-room media
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = BASE + "/api"
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG = "b7f40862230441b9a0bedabefe8dab49"
EV = "demo_evt_bcr"
DEF_MEDIA = {"mp4": "/media/control-room-demo.mp4", "poster": "/media/control-room-demo-poster.jpg", "preview": "/media/brevo/control-room-anteprima.jpg"}


def _sa(org=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SA)
    if r.status_code != 200:
        pytest.skip("SA login failed")
    s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"
    if org:
        s.headers["X-Org-Id"] = org
    return s


def _restore_preview():
    # promo media POST with poster also overwrites preview; restore original preview directly in DB
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")

    async def go():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        await c[os.environ["DB_NAME"]].promo_materials.update_one({"slug": "control-room"}, {"$set": {**DEF_MEDIA, "webm": None}})
        c.close()
    asyncio.run(go())


class TestCrPromoLifecycle:
    """Sequential: inactive -> grant -> active -> disable -> enable -> revoke"""

    def test_lifecycle(self):
        sa = _sa()
        org = _sa(ORG)
        # initial inactive
        d = org.get(f"{API}/controlroom/events").json()
        assert d["price_net"] == 119 or d["price_net"] == 119.0
        assert d["module_disabled"] is False
        assert not any(e["active"] for e in d["events"]), "Demo org should start without active CR"
        r = org.get(f"{API}/controlroom/events/{EV}/ops")
        assert r.status_code == 402, r.text
        assert "cr_posts" not in r.text and "posts" not in r.json()
        # marketplace service
        svcs = org.get(f"{API}/marketplace/services").json()["services"]
        svc = next(x for x in svcs if x["key"] == "control-room")
        assert svc["status"] != "coming_soon"
        # grant (no X-Org-Id)
        g = sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/grant", json={"event_ids": [EV], "note": "TEST_iter178"})
        assert g.status_code == 200, g.text
        assert g.json()["created"] == 1
        pid = None
        try:
            d = org.get(f"{API}/controlroom/events").json()
            assert next(e for e in d["events"] if e["id"] == EV)["active"] is True
            ops = org.get(f"{API}/controlroom/events/{EV}/ops")
            assert ops.status_code == 200, ops.text
            n_posts = len(ops.json().get("posts") or [])
            assert n_posts >= 1, "demo posts data should be preserved"
            # disable
            st = sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/state", json={"enabled": False})
            assert st.status_code == 200, st.text
            d = org.get(f"{API}/controlroom/events").json()
            assert d["module_disabled"] is True and not any(e["active"] for e in d["events"])
            assert org.get(f"{API}/controlroom/events/{EV}/ops").status_code == 402
            # enable
            assert sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/state", json={"enabled": True}).status_code == 200
            ops2 = org.get(f"{API}/controlroom/events/{EV}/ops")
            assert ops2.status_code == 200 and len(ops2.json().get("posts") or []) == n_posts
            # find purchase id
            pr = sa.get(f"{API}/platform/controlroom/purchases").json()
            rows = pr if isinstance(pr, list) else (pr.get("purchases") or pr.get("items") or [])
            pid = next(p["id"] for p in rows if p.get("event_id") == EV and p.get("status") == "active" and (p.get("org_id") in (None, ORG)))
        finally:
            sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/state", json={"enabled": True})
            if pid is None:
                pr = sa.get(f"{API}/platform/controlroom/purchases").json()
                rows = pr if isinstance(pr, list) else (pr.get("purchases") or pr.get("items") or [])
                pid = next((p["id"] for p in rows if p.get("event_id") == EV and p.get("status") == "active"), None)
            if pid:
                rv = sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/{pid}/revoke")
                assert rv.status_code == 200, rv.text
        d = org.get(f"{API}/controlroom/events").json()
        assert not any(e["active"] for e in d["events"])
        assert org.get(f"{API}/controlroom/events/{EV}/ops").status_code == 402


class TestPromoMaterialControlRoom:
    def test_public_promo(self):
        r = requests.get(f"{API}/public/promo/control-room")
        assert r.status_code == 200
        d = r.json()
        assert d["mp4"] == DEF_MEDIA["mp4"] and d["poster"] == DEF_MEDIA["poster"] and d["status"] == "pubblicato"
        assert any(x["slug"] == "control-room" for x in requests.get(f"{API}/public/promo").json())

    def test_media_files_served(self):
        for p, ct in [(DEF_MEDIA["mp4"], "video/mp4"), (DEF_MEDIA["poster"], "image/jpeg"), (DEF_MEDIA["preview"], "image/jpeg")]:
            r = requests.get(BASE + p, headers={"Range": "bytes=0-100"})
            assert r.status_code in (200, 206), p
            assert ct in r.headers.get("content-type", ""), (p, r.headers.get("content-type"))

    def test_public_video_page(self):
        r = requests.get(f"{BASE}/video/control-room")
        assert r.status_code == 200

    def test_media_rbac_and_validation(self):
        anon = requests.post(f"{API}/promo-materials/control-room/media", json={"poster": DEF_MEDIA["poster"]})
        assert anon.status_code in (401, 403)
        sa = _sa()
        import uuid
        u = requests.Session()
        email, name = f"test_cr178_{uuid.uuid4().hex[:8]}@example.com", f"TEST_CR178_{uuid.uuid4().hex[:6]}"
        rr = u.post(f"{API}/auth/register-organization", json={"nome": "Test", "cognome": "CR", "email": email, "password": "TestPass123!",
                                                               "org_name": name, "telefono": "+393331234567", "accept_terms": True})
        assert rr.status_code == 200, rr.text
        me = u.get(f"{API}/auth/me").json()
        try:
            assert u.post(f"{API}/promo-materials/control-room/media", json={"poster": DEF_MEDIA["poster"]}).status_code == 403
            # fresh org: promo state, no events, ops 402
            d = u.get(f"{API}/controlroom/events").json()
            assert d["module_disabled"] is False and d["events"] == []
        finally:
            sa.delete(f"{API}/platform/organizations/{me['org_id']}", json={"confirm_name": name})
            sa.delete(f"{API}/platform/users/{me['user_id']}")
        for bad in [{"poster": "javascript:alert(1)"}, {"mp4": "ftp://x/y.mp4"}, {}, {"poster": "/etc/passwd"}]:
            assert sa.post(f"{API}/promo-materials/control-room/media", json=bad).status_code == 400, bad
        try:
            r = sa.post(f"{API}/promo-materials/control-room/media", json={"poster": DEF_MEDIA["poster"]})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["poster"] == DEF_MEDIA["poster"] and d["mp4"] == DEF_MEDIA["mp4"]
            assert d["preview"] == DEF_MEDIA["poster"]  # preview overwritten by poster (by design)
        finally:
            _restore_preview()
        assert requests.get(f"{API}/public/promo/control-room").json()["preview"] == DEF_MEDIA["preview"]
