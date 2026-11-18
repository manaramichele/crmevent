# Novità: preview checks, simulation idempotency, audience targeting, read tracking, manual creation (iteration 189)
import os
import time
import uuid
import asyncio
import pytest
import requests
from dotenv import load_dotenv

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
REL = "2026-11-18-associazione-abbonamenti"
REL2 = "2026-10-08-novita"
TAG = uuid.uuid4().hex[:6]
STATE = {"items": [], "org": None}


def _db_exec(coro_fn):
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient
    async def run():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await coro_fn(c[os.environ["DB_NAME"]])
        finally:
            c.close()
    return asyncio.run(run())


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SA, timeout=30)
    if r.status_code != 200:
        pytest.skip("SA login failed")
    yield s
    # cleanup: withdraw + delete only items created here
    for nid in STATE["items"]:
        s.post(f"{API}/platform/news/{nid}/withdraw", timeout=30)
        s.delete(f"{API}/platform/news/{nid}", timeout=30)
    if STATE["org"]:
        o = STATE["org"]
        r = s.delete(f"{API}/platform/organizations/{o['id']}", json={"confirm_name": o["name"]}, timeout=60)
        print("org delete", r.status_code, r.text[:200])


@pytest.fixture(scope="module")
def org():
    s = requests.Session()
    name = f"TEST_NEWS Org {TAG}"
    r = s.post(f"{API}/auth/register-organization", json={
        "nome": "Test", "cognome": "News", "email": f"test_news_{TAG}@example.com", "password": "TestNews2026!",
        "org_name": name, "telefono": "+393331234567", "accept_terms": True}, timeout=60)
    assert r.status_code == 200, r.text
    STATE["org"] = {"id": r.json().get("org_id"), "name": name}
    return s


def _mine(sa, release_id):
    rows = sa.get(f"{API}/platform/news", timeout=30).json()
    return [x for x in rows if x["release_id"] == release_id and x["simulated"]]


class TestNews:
    def test_env_preview_and_check(self, sa):
        e = sa.get(f"{API}/platform/news/env", timeout=30).json()
        assert e["production"] is False
        before = len(sa.get(f"{API}/platform/news", timeout=30).json())
        r = sa.post(f"{API}/platform/news/check", timeout=30)
        assert r.status_code == 200 and r.json() == {"drafts": 0, "production": False}
        e2 = sa.get(f"{API}/platform/news/env", timeout=30).json()
        assert e2["checks"][0]["outcome"] == "skipped" and "Anteprima" in e2["checks"][0]["message"]
        assert e2["checks"][0]["at"] >= (e["checks"][0]["at"] if e["checks"] else "")
        assert len(sa.get(f"{API}/platform/news", timeout=30).json()) == before

    def test_org_baseline(self, org):
        STATE["base_count"] = org.get(f"{API}/news/unread-count", timeout=30).json()["count"]
        STATE["base_ids"] = {n["id"] for n in org.get(f"{API}/news", timeout=30).json()}
        me = org.get(f"{API}/saas/me", timeout=30).json()
        STATE["plan"] = me.get("plan")
        print("trial plan:", STATE["plan"], me.get("status"))

    def test_simulate_release(self, sa):
        if _mine(sa, REL):
            pytest.skip("release already simulated by someone else")
        r = sa.post(f"{API}/platform/news/simulate-release", json={"release_id": REL}, timeout=180)
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 3
        rows = _mine(sa, REL)
        STATE["items"] += [x["id"] for x in rows]
        by = {x["area"]: x for x in rows}
        assert set(by) == {"Gestione Società", "Abbonamento", "Super Admin"}
        assert by["Gestione Società"]["audience"] == {"type": "service", "plans": [], "service": "gestione-societa"}
        assert by["Abbonamento"]["audience"]["type"] == "all"
        assert by["Super Admin"]["audience"]["type"] == "superadmin"
        assert all(x["status"] == "bozza" for x in rows)
        STATE["by"] = {k: v["id"] for k, v in by.items()}

    def test_simulate_again_409(self, sa):
        r = sa.post(f"{API}/platform/news/simulate-release", json={"release_id": REL}, timeout=60)
        assert r.status_code == 409
        assert len(_mine(sa, REL)) == 3
        e = sa.get(f"{API}/platform/news/env", timeout=30).json()
        assert next(x for x in e["releases"] if x["id"] == REL)["simulated"] is True

    def test_simulate_unknown_404(self, sa):
        assert sa.post(f"{API}/platform/news/simulate-release", json={"release_id": "nope"}, timeout=30).status_code == 404

    def test_drafts_not_public(self, org):
        ids = {n["id"] for n in org.get(f"{API}/news", timeout=30).json()}
        assert not (ids & set(STATE["items"]))
        assert org.get(f"{API}/news/unread-count", timeout=30).json()["count"] == STATE["base_count"]

    def test_org_forbidden_admin_endpoints(self, org):
        assert org.get(f"{API}/platform/news", timeout=30).status_code in (401, 403)
        assert org.post(f"{API}/platform/news", json={"titolo": "x", "descrizione": "y"}, timeout=30).status_code in (401, 403)

    def test_edit_validation(self, sa):
        nid = STATE["by"]["Abbonamento"]
        r = sa.put(f"{API}/platform/news/{nid}", json={"titolo": "a", "descrizione": "b", "audience": {"type": "plans", "plans": []}}, timeout=30)
        assert r.status_code == 400
        r = sa.put(f"{API}/platform/news/{nid}", json={"titolo": "a", "descrizione": "b", "audience": {"type": "service", "service": ""}}, timeout=30)
        assert r.status_code == 400
        r = sa.put(f"{API}/platform/news/{nid}", json={"titolo": "", "descrizione": "b"}, timeout=30)
        assert r.status_code == 400

    def test_edit_and_publish(self, sa, org):
        nid = STATE["by"]["Abbonamento"]
        r = sa.put(f"{API}/platform/news/{nid}", json={"titolo": f"TEST_NEWS Abbonamento {TAG}", "descrizione": "Testo test abbonamento.",
                                                      "area": "TEST_Categoria", "audience": {"type": "all"}}, timeout=30)
        assert r.status_code == 200, r.text
        x = next(i for i in sa.get(f"{API}/platform/news", timeout=30).json() if i["id"] == nid)
        assert x["titolo"].startswith("TEST_NEWS") and x["area"] == "TEST_Categoria" and x["edited"] is True
        for k in ("Abbonamento", "Super Admin", "Gestione Società"):
            r = sa.post(f"{API}/platform/news/{STATE['by'][k]}/publish", timeout=30)
            assert r.status_code == 200, (k, r.text)
        assert sa.post(f"{API}/platform/news/{nid}/publish", timeout=30).status_code == 400  # already published

    def test_audience_visibility(self, sa, org):
        ids = {n["id"] for n in org.get(f"{API}/news", timeout=30).json()}
        assert STATE["by"]["Abbonamento"] in ids
        assert STATE["by"]["Super Admin"] not in ids
        assert STATE["by"]["Gestione Società"] not in ids
        sids = {n["id"] for n in sa.get(f"{API}/news", timeout=30).json()}
        assert set(STATE["by"].values()) <= sids

    def test_needs_completion_cannot_publish(self, sa):
        nid = "test_news_" + uuid.uuid4().hex
        async def ins(db):
            await db.news_items.insert_one({"id": nid, "release_id": None, "area": "TEST", "status": "bozza", "titolo": "Da completare: TEST",
                                            "descrizione": "", "needs_completion": True, "simulated": True, "audience": {"type": "all"},
                                            "created_at": "2026-01-01T00:00:00+00:00", "published_at": None})
        _db_exec(ins)
        STATE["items"].append(nid)
        r = sa.post(f"{API}/platform/news/{nid}/publish", timeout=30)
        assert r.status_code == 400 and "completare" in r.text

    def test_manual_create_plans_gold(self, sa, org):
        r = sa.post(f"{API}/platform/news", json={"titolo": f"TEST_NEWS Gold {TAG}", "descrizione": "Solo gold", "audience": {"type": "plans", "plans": ["gold"]}}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        STATE["items"].append(d["id"])
        assert d["generator"] == "manual" and d["status"] == "bozza" and d["audience"]["plans"] == ["gold"]
        assert sa.post(f"{API}/platform/news/{d['id']}/publish", timeout=30).status_code == 200
        ids = {n["id"] for n in org.get(f"{API}/news", timeout=30).json()}
        assert (d["id"] in ids) == (STATE["plan"] == "gold"), f"plan={STATE['plan']}"

    def test_manual_create_validation(self, sa):
        assert sa.post(f"{API}/platform/news", json={"titolo": " ", "descrizione": "x"}, timeout=30).status_code == 400
        assert sa.post(f"{API}/platform/news", json={"titolo": "x", "descrizione": "x", "audience": {"type": "bogus"}}, timeout=30).status_code == 400

    def test_read_tracking_and_banner(self, sa, org):
        u = org.get(f"{API}/news/unread-count", timeout=30).json()
        assert u["count"] >= 1 and u["banner"] is True
        assert org.post(f"{API}/news/mark-read", json={}, timeout=30).status_code == 200
        u = org.get(f"{API}/news/unread-count", timeout=30).json()
        assert u["count"] == 0 and u["banner"] is False
        assert all(n["read"] for n in org.get(f"{API}/news", timeout=30).json())
        # SA reads tracked separately
        assert sa.get(f"{API}/news/unread-count", timeout=30).json()["count"] >= 1

    def test_dismiss_then_newer_reappears(self, sa, org):
        r = sa.post(f"{API}/platform/news", json={"titolo": f"TEST_NEWS All A {TAG}", "descrizione": "A", "audience": {"type": "all"}}, timeout=30)
        a = r.json()["id"]; STATE["items"].append(a)
        sa.post(f"{API}/platform/news/{a}/publish", timeout=30)
        u = org.get(f"{API}/news/unread-count", timeout=30).json()
        assert u["count"] == 1 and u["banner"] is True and u["latest"]["id"] == a
        assert org.post(f"{API}/news/dismiss-banner", timeout=30).status_code == 200
        u = org.get(f"{API}/news/unread-count", timeout=30).json()
        assert u["banner"] is False and u["count"] == 1
        time.sleep(1)
        b = sa.post(f"{API}/platform/news", json={"titolo": f"TEST_NEWS All B {TAG}", "descrizione": "B", "audience": {"type": "all"}}, timeout=30).json()["id"]
        STATE["items"].append(b)
        sa.post(f"{API}/platform/news/{b}/publish", timeout=30)
        u = org.get(f"{API}/news/unread-count", timeout=30).json()
        assert u["banner"] is True and u["latest"]["id"] == b and u["count"] == 2

    def test_withdraw_hides(self, sa, org):
        nid = STATE["items"][-1]
        assert sa.post(f"{API}/platform/news/{nid}/withdraw", timeout=30).status_code == 200
        assert nid not in {n["id"] for n in org.get(f"{API}/news", timeout=30).json()}
        assert sa.delete(f"{API}/platform/news/{STATE['by']['Abbonamento']}", timeout=30).status_code == 400  # published

    def test_simulate_other_release(self, sa):
        if _mine(sa, REL2):
            pytest.skip("already simulated")
        r = sa.post(f"{API}/platform/news/simulate-release", json={"release_id": REL2}, timeout=180)
        assert r.status_code == 200, r.text
        rows = _mine(sa, REL2)
        STATE["items"] += [x["id"] for x in rows]
        assert r.json()["created"] == len(rows) == 3
