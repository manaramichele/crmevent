"""Iter 133 — Marketplace 'Avvisami' (notify-me) backend tests: idempotency, read-only orgs, members, credits, Super Admin interests, Brevo notify."""
import os
import time
import uuid
import asyncio
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
QA_ORG = "org_qa_eventi"
TAG = uuid.uuid4().hex[:6]
CREATED = {"services": [], "orgs": [], "users": []}


def _db_run(coro_fn):
    async def _r():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        return await coro_fn(db)
    return asyncio.new_event_loop().run_until_complete(_r())


def _login(creds, org_id=None):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    if org_id:
        s.headers["X-Org-Id"] = org_id
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA)


@pytest.fixture(scope="module")
def org():
    return _login(ORG, QA_ORG)


@pytest.fixture(scope="module", autouse=True)
def cleanup(sa):
    yield
    async def _c(db):
        sids = CREATED["services"]
        await db.marketplace_services.delete_many({"id": {"$in": sids}})
        await db.marketplace_services.delete_many({"name": {"$regex": "^TEST_"}})
        await db.marketplace_interests.delete_many({"$or": [{"service_id": {"$in": sids}}, {"org_id": {"$in": CREATED["orgs"] + [QA_ORG]}}]})
        await db.memberships.delete_many({"org_id": {"$in": CREATED["orgs"]}})
        await db.users.delete_many({"$or": [{"user_id": {"$in": CREATED["users"]}}, {"org_id": {"$in": CREATED["orgs"]}}]})
        await db.organizations.delete_many({"id": {"$in": CREATED["orgs"]}})
    _db_run(_c)


def _services(sess):
    r = sess.get(f"{BASE}/api/marketplace/services", timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["services"]


def _svc_body(**kw):
    b = {"name": f"TEST_svc_{TAG}", "description": "test", "icon": "Package", "category": "Altro", "price": None,
         "price_type": "monthly", "status": "coming_soon", "visible": True, "purchasable": False, "tech_ready": False,
         "billing_method": "stripe", "scope": "org", "sort": 999}
    b.update(kw)
    return b


@pytest.fixture(scope="module")
def test_svc(sa):
    r = sa.post(f"{BASE}/api/platform/marketplace/services", json=_svc_body(), timeout=20)
    assert r.status_code == 200, r.text
    CREATED["services"].append(r.json()["id"])
    return r.json()


@pytest.fixture(scope="module")
def test_svc2(sa):
    r = sa.post(f"{BASE}/api/platform/marketplace/services", json=_svc_body(name=f"TEST_svc2_{TAG}"), timeout=20)
    assert r.status_code == 200, r.text
    CREATED["services"].append(r.json()["id"])
    return r.json()


@pytest.fixture(scope="module")
def ro_org():
    """TEST_ org with expired trial (read-only)."""
    email = f"test_mkt_{TAG}@example.com"
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": "Mkt", "email": email, "password": "TestPass2026!",
        "org_name": f"TEST_Org_{TAG}", "telefono": "+393331234567", "accept_terms": True}, timeout=20)
    assert r.status_code == 200, r.text
    uid = r.json().get("user_id") or r.json().get("user", {}).get("user_id")
    async def _q(db):
        u = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "org_id": 1})
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        await db.organizations.update_one({"id": u["org_id"]}, {"$set": {"saas.trial_end": past, "saas.trial_status": "expired"}})
        return u
    u = _db_run(_q)
    CREATED["orgs"].append(u["org_id"])
    CREATED["users"].append(u["user_id"])
    s.headers["X-Org-Id"] = u["org_id"]
    return {"session": s, "org_id": u["org_id"], "user_id": uid or u["user_id"], "email": email}


# ---- Org admin notify: idempotent, multiple services ----
def test_notify_idempotent_and_flag(org, test_svc):
    for _ in range(2):
        r = org.post(f"{BASE}/api/marketplace/services/{test_svc['id']}/notify", timeout=20)
        assert r.status_code == 200, r.text
        assert r.json() == {"notify_me": True}
    n = _db_run(lambda db: db.marketplace_interests.count_documents({"service_id": test_svc["id"], "org_id": QA_ORG}))
    assert n == 1
    s = next(x for x in _services(org) if x["id"] == test_svc["id"])
    assert s["notify_me"] is True
    doc = _db_run(lambda db: db.marketplace_interests.find_one({"service_id": test_svc["id"], "org_id": QA_ORG}, {"_id": 0}))
    assert doc["user_id"] == "user_qaeventi" and doc["email"] == ORG["email"] and doc["created_at"] and doc["org_name"]


def test_multiple_services_same_org(org, test_svc, test_svc2):
    r = org.post(f"{BASE}/api/marketplace/services/{test_svc2['id']}/notify", timeout=20)
    assert r.status_code == 200
    flags = {x["id"]: x["notify_me"] for x in _services(org)}
    assert flags[test_svc["id"]] and flags[test_svc2["id"]]


def test_concurrent_notify_no_duplicates(org, sa):
    r = sa.post(f"{BASE}/api/platform/marketplace/services", json=_svc_body(name=f"TEST_svc3_{TAG}"), timeout=20)
    sid = r.json()["id"]
    CREATED["services"].append(sid)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(6) as ex:
        codes = list(ex.map(lambda _: org.post(f"{BASE}/api/marketplace/services/{sid}/notify", timeout=20).status_code, range(6)))
    n = _db_run(lambda db: db.marketplace_interests.count_documents({"service_id": sid, "org_id": QA_ORG}))
    print("concurrent codes", codes, "records", n)
    assert n == 1, f"race condition: {n} duplicate interest records"


def test_notify_non_coming_soon_400(org, sa):
    r = sa.post(f"{BASE}/api/platform/marketplace/services", json=_svc_body(name=f"TEST_avail_{TAG}", status="available"), timeout=20)
    sid = r.json()["id"]
    CREATED["services"].append(sid)
    r2 = org.post(f"{BASE}/api/marketplace/services/{sid}/notify", timeout=20)
    assert r2.status_code == 400
    r3 = org.post(f"{BASE}/api/marketplace/services/nonexistent/notify", timeout=20)
    assert r3.status_code == 400


def test_notify_no_credits_no_purchase(org, test_svc):
    before = _db_run(lambda db: db.organizations.find_one({"id": QA_ORG}, {"_id": 0, "credits": 1}))
    pur_before = _db_run(lambda db: db.marketplace_purchases.count_documents({"org_id": QA_ORG}))
    org.post(f"{BASE}/api/marketplace/services/{test_svc['id']}/notify", timeout=20)
    after = _db_run(lambda db: db.organizations.find_one({"id": QA_ORG}, {"_id": 0, "credits": 1}))
    pur_after = _db_run(lambda db: db.marketplace_purchases.count_documents({"org_id": QA_ORG}))
    assert before == after and pur_before == pur_after


# ---- Read-only org ----
def test_readonly_org_can_notify_but_not_write(ro_org, test_svc):
    s = ro_org["session"]
    st = s.get(f"{BASE}/api/saas/state", timeout=20)
    print("saas state", st.status_code, st.text[:300])
    r = s.post(f"{BASE}/api/marketplace/services/{test_svc['id']}/notify", timeout=20)
    assert r.status_code == 200, r.text
    # other write must be blocked with plan_readonly
    r2 = s.post(f"{BASE}/api/marketplace/services/{test_svc['id']}/checkout", json={"origin_url": BASE}, timeout=20)
    r3 = s.post(f"{BASE}/api/events", json={"nome": "TEST_ev"}, timeout=20)
    print("checkout", r2.status_code, r2.text[:200], "events", r3.status_code, r3.text[:200])
    assert r3.status_code == 403 and "plan_readonly" in r3.text
    assert r2.status_code == 403 and "plan_readonly" in r2.text


# ---- Non-admin member ----
def test_member_can_notify(ro_org, test_svc2):
    email = f"test_mem_{TAG}@example.com"
    uid = f"user_test_{TAG}"
    async def _ins(db):
        now = datetime.now(timezone.utc).isoformat()
        await db.users.insert_one({"user_id": uid, "email": email, "name": "TEST Member", "role": "staff", "auth_provider": "password",
                                   "org_id": ro_org["org_id"], "active": True, "created_at": now,
                                   "password_hash": bcrypt.hashpw(b"TestPass2026!", bcrypt.gensalt()).decode()})
        await db.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": uid, "org_id": ro_org["org_id"], "role": "user",
                                         "active": True, "permissions": {}, "created_at": now})
        # make org writable again so member test isn't only read-only
    _db_run(_ins)
    CREATED["users"].append(uid)
    m = _login({"email": email, "password": "TestPass2026!"}, ro_org["org_id"])
    svcs = _services(m)
    assert any(x["id"] == test_svc2["id"] for x in svcs)
    r = m.post(f"{BASE}/api/marketplace/services/{test_svc2['id']}/notify", timeout=20)
    assert r.status_code == 200, r.text
    # same-org admin sees flag
    flags = {x["id"]: x["notify_me"] for x in _services(ro_org["session"])}
    assert flags[test_svc2["id"]] is True


# ---- Super Admin interests ----
def test_admin_interest_count_and_list(sa, test_svc):
    rows = sa.get(f"{BASE}/api/platform/marketplace/services", timeout=20).json()["services"]
    s = next(x for x in rows if x["id"] == test_svc["id"])
    assert s["interest_count"] == 2  # QA org + TEST ro org
    lst = sa.get(f"{BASE}/api/platform/marketplace/services/{test_svc['id']}/interests", timeout=20)
    assert lst.status_code == 200
    data = lst.json()
    assert len(data) == 2 and all("org_name" in d and "email" in d and "created_at" in d for d in data)
    assert "_id" not in data[0]


def test_admin_endpoints_forbidden_for_org(org, test_svc):
    assert org.get(f"{BASE}/api/platform/marketplace/services/{test_svc['id']}/interests", timeout=20).status_code == 403
    assert org.post(f"{BASE}/api/platform/marketplace/services/{test_svc['id']}/interests/notify", timeout=20).status_code == 403


def test_admin_notify_requires_available(sa, test_svc):
    r = sa.post(f"{BASE}/api/platform/marketplace/services/{test_svc['id']}/interests/notify", timeout=20)
    assert r.status_code == 400


def test_status_change_triggers_notify_brevo_unconfigured(sa, org, test_svc):
    body = _svc_body(name=test_svc["name"], status="available")
    r = sa.put(f"{BASE}/api/platform/marketplace/services/{test_svc['id']}", json=body, timeout=20)
    assert r.status_code == 200, r.text
    time.sleep(3)
    docs = _db_run(lambda db: db.marketplace_interests.find({"service_id": test_svc["id"]}, {"_id": 0}).to_list(50))
    assert len(docs) == 2
    for d in docs:
        assert d["notify_status"] == "brevo_non_configurato" and d["notified_at"] is None
    r2 = sa.post(f"{BASE}/api/platform/marketplace/services/{test_svc['id']}/interests/notify", timeout=20)
    assert r2.status_code == 200
    assert r2.json() == {"sent": 0, "failed": 2}
    # notify on available service now 400
    assert org.post(f"{BASE}/api/marketplace/services/{test_svc['id']}/notify", timeout=20).status_code == 400
    # org service list: notify_me still True (notified_at null) although available
    s = next(x for x in _services(org) if x["id"] == test_svc["id"])
    print("notify_me after available:", s["notify_me"], s["status"])
