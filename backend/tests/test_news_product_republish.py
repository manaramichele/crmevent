# Novità: product link to Marketplace, service_missing audience, versioned republish & read tracking (iteration 194)
import os
import uuid
import asyncio
import pytest
import requests
from dotenv import load_dotenv

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
TAG = uuid.uuid4().hex[:6]
ST = {"items": [], "orgs": [], "purchases": [], "cr": [], "svc": {}}


def _db(fn):
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient

    async def run():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        try:
            return await fn(c[os.environ["DB_NAME"]])
        finally:
            c.close()
    return asyncio.run(run())


def _reg(label):
    s = requests.Session()
    name = f"TEST_NEWSP {label} {TAG}"
    r = s.post(f"{API}/auth/register-organization", json={
        "nome": "Test", "cognome": label, "email": f"test_newsp_{label.lower()}_{TAG}@example.com", "password": "TestNews2026!",
        "org_name": name, "telefono": "+393331234567", "accept_terms": True}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    ST["orgs"].append({"id": d.get("org_id"), "name": name, "uid": d.get("user_id")})
    return s, d


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SA, timeout=30)
    if r.status_code != 200:
        pytest.skip("SA login failed")
    svcs = s.get(f"{API}/platform/marketplace/services", timeout=30).json()["services"]
    ST["svc"] = {x["key"]: x for x in svcs}
    yield s
    for nid in ST["items"]:
        s.post(f"{API}/platform/news/{nid}/withdraw", timeout=30)
        s.delete(f"{API}/platform/news/{nid}", timeout=30)

    async def clean(db):
        if ST["items"]:
            await db.news_items.delete_many({"id": {"$in": ST["items"]}})
        for pid in ST["purchases"]:
            await db.marketplace_purchases.delete_one({"id": pid})
        for cid in ST["cr"]:
            await db.controlroom_purchases.delete_one({"id": cid})
        uids = [o["uid"] for o in ST["orgs"] if o.get("uid")]
        if uids:
            await db.news_reads.delete_many({"user_id": {"$in": uids}})
    _db(clean)
    for o in ST["orgs"]:
        r = s.delete(f"{API}/platform/organizations/{o['id']}", json={"confirm_name": o["name"]}, timeout=60)
        print("org delete", r.status_code, r.text[:150])
    uids = [o["uid"] for o in ST["orgs"] if o.get("uid")]
    if uids:  # org delete leaves orphan users (org_id None)
        _db(lambda db: db.users.delete_many({"user_id": {"$in": uids}}))


@pytest.fixture(scope="module")
def orgs():
    a = _reg("Alpha")
    b = _reg("Beta")
    return {"a": a, "b": b}


def _create(sa, **kw):
    body = {"titolo": f"TEST_NEWSP {TAG} {kw.pop('t', 'x')}", "descrizione": "Descrizione di prova", "area": "TEST", **kw}
    r = sa.post(f"{API}/platform/news", json=body, timeout=30)
    assert r.status_code == 200, r.text
    ST["items"].append(r.json()["id"])
    return r.json()


def _find(rows, nid):
    return next((x for x in rows if x["id"] == nid), None)


# Catalog for picker
def test_catalog_contains_products(sa):
    for k in ("gestione-societa", "event-map", "control-room", "archivio-iscritti"):
        assert k in ST["svc"], k


# Validation product_id
def test_invalid_product_400(sa):
    r = sa.post(f"{API}/platform/news", json={"titolo": "TEST_x", "descrizione": "y", "product_id": "nope"}, timeout=30)
    assert r.status_code == 400
    assert r.json()["detail"]["field"] == "product_id"


# Create + admin list product payload
def test_create_with_product_and_list(sa):
    g = ST["svc"]["gestione-societa"]
    n = _create(sa, t="GS", product_id=g["id"], kind="commerciale", audience={"type": "service_missing", "service": "gestione-societa"})
    assert n["product_id"] == g["id"] and n["kind"] == "commerciale" and n["version"] == 0
    row = _find(sa.get(f"{API}/platform/news", timeout=30).json(), n["id"])
    p = row["product"]
    assert p["id"] == g["id"] and p["key"] == "gestione-societa" and p["name"] == g["name"]
    assert set(p) >= {"id", "key", "name", "status", "active", "purchasable", "route"}
    ST["gs"] = n["id"]


# service_missing audience + product flags for org without module
def test_publish_and_org_sees_product(sa, orgs):
    nid = ST["gs"]
    r = sa.post(f"{API}/platform/news/{nid}/publish", timeout=30)
    assert r.status_code == 200 and r.json()["version"] == 1
    sa_s, _ = orgs["a"]
    n = _find(sa_s.get(f"{API}/news", timeout=30).json(), nid)
    assert n and n["read"] is False
    assert n["product"]["key"] == "gestione-societa" and n["product"]["active"] is False and n["product"]["purchasable"] is False
    uc = sa_s.get(f"{API}/news/unread-count", timeout=30).json()
    assert uc["count"] >= 1 and uc["latest"]["id"] == nid and uc["latest"]["product"]["key"] == "gestione-societa" and uc["banner"] is True


def test_service_missing_excludes_org_with_module(sa, orgs):
    sb, db_ = orgs["b"]
    g = ST["svc"]["gestione-societa"]
    r = sa.post(f"{API}/platform/marketplace/services/{g['id']}/grant", json={"org_id": db_["org_id"]}, timeout=30)
    assert r.status_code == 200, r.text
    ST["purchases"].append(r.json()["id"])
    assert _find(sb.get(f"{API}/news", timeout=30).json(), ST["gs"]) is None
    sa_s, _ = orgs["a"]
    assert _find(sa_s.get(f"{API}/news", timeout=30).json(), ST["gs"]) is not None


# Purchasable product + active module -> route
def test_purchasable_and_active_route(sa, orgs):
    ai = ST["svc"]["archivio-iscritti"]
    n = _create(sa, t="AI", product_id=ai["id"], audience={"type": "all"})
    assert sa.post(f"{API}/platform/news/{n['id']}/publish", timeout=30).status_code == 200
    sa_s, _ = orgs["a"]
    pa = _find(sa_s.get(f"{API}/news", timeout=30).json(), n["id"])["product"]
    # archivio-iscritti has price None -> can_buy says "Prezzo non configurato" -> not purchasable (data, not code)
    assert pa["active"] is False and pa["route"] is None
    em = _create(sa, t="EM", product_id=ST["svc"]["event-map"]["id"], audience={"type": "all"})
    sa.post(f"{API}/platform/news/{em['id']}/publish", timeout=30)
    pe = _find(sa_s.get(f"{API}/news", timeout=30).json(), em["id"])["product"]
    assert pe["purchasable"] is True and pe["active"] is False
    sb, db_ = orgs["b"]
    r = sa.post(f"{API}/platform/marketplace/services/{ai['id']}/grant", json={"org_id": db_["org_id"]}, timeout=30)
    assert r.status_code == 200, r.text
    ST["purchases"].append(r.json()["id"])
    pb = _find(sb.get(f"{API}/news", timeout=30).json(), n["id"])["product"]
    assert pb["active"] is True and pb["route"] == "/iscritti"
    ST["ai"] = n["id"]


# Existing filters: service (has module) still works
def test_service_audience(sa, orgs):
    n = _create(sa, t="SVC", audience={"type": "service", "service": "archivio-iscritti"})
    assert sa.post(f"{API}/platform/news/{n['id']}/publish", timeout=30).status_code == 200
    assert _find(orgs["b"][0].get(f"{API}/news", timeout=30).json(), n["id"]) is not None
    assert _find(orgs["a"][0].get(f"{API}/news", timeout=30).json(), n["id"]) is None


# Republish versioning + reads
def test_republish_cycle(sa, orgs):
    nid = ST["gs"]
    s, d = orgs["a"]
    before = s.get(f"{API}/news/unread-count", timeout=30).json()["count"]
    r = s.post(f"{API}/news/mark-read", json={"ids": [nid]}, timeout=30)
    assert r.status_code == 200
    assert _find(s.get(f"{API}/news", timeout=30).json(), nid)["read"] is True
    assert s.get(f"{API}/news/unread-count", timeout=30).json()["count"] == before - 1
    assert sa.post(f"{API}/platform/news/{nid}/withdraw", timeout=30).status_code == 200
    assert _find(s.get(f"{API}/news", timeout=30).json(), nid) is None
    # edit while withdrawn keeps product
    g = ST["svc"]["gestione-societa"]
    r = sa.put(f"{API}/platform/news/{nid}", json={"titolo": f"TEST_NEWSP {TAG} GS v2", "descrizione": "Nuova descrizione", "product_id": g["id"], "kind": "commerciale",
                                                    "audience": {"type": "service_missing", "service": "gestione-societa"}}, timeout=30)
    assert r.status_code == 200 and r.json()["product_id"] == g["id"]
    r = sa.post(f"{API}/platform/news/{nid}/publish", timeout=30)
    assert r.status_code == 200 and r.json()["version"] == 2
    n = _find(s.get(f"{API}/news", timeout=30).json(), nid)
    assert n and n["read"] is False and n["version"] == 2 and n["product"]["key"] == "gestione-societa"
    uc = s.get(f"{API}/news/unread-count", timeout=30).json()
    assert uc["count"] == before and uc["latest"]["id"] == nid and uc["banner"] is True
    row = _find(sa.get(f"{API}/platform/news", timeout=30).json(), nid)
    assert row["version"] == 2 and len(row["publications"]) == 2 and row["publications"][0]["withdrawn_at"]
    cnt = _db(lambda db: db.news_items.count_documents({"id": nid}))
    assert cnt == 1
    rd = _db(lambda db: db.news_reads.find_one({"user_id": d["user_id"]}, {"_id": 0}))
    assert f"{nid}:1" in rd["read_keys"]


# Legacy read_ids valid only for v1
def test_legacy_read_ids_only_v1(sa, orgs):
    s, d = orgs["b"]
    nid = ST["ai"]
    _db(lambda db: db.news_reads.update_one({"user_id": d["user_id"]}, {"$addToSet": {"read_ids": nid}}, upsert=True))
    assert _find(s.get(f"{API}/news", timeout=30).json(), nid)["read"] is True
    sa.post(f"{API}/platform/news/{nid}/withdraw", timeout=30)
    sa.post(f"{API}/platform/news/{nid}/publish", timeout=30)
    assert _find(s.get(f"{API}/news", timeout=30).json(), nid)["read"] is False


# Dismissed banner reappears after republish
def test_banner_after_dismiss_republish(sa, orgs):
    s, _ = orgs["a"]
    s.post(f"{API}/news/dismiss-banner", timeout=30)
    assert s.get(f"{API}/news/unread-count", timeout=30).json()["banner"] is False
    nid = ST["gs"]
    sa.post(f"{API}/platform/news/{nid}/withdraw", timeout=30)
    assert sa.post(f"{API}/platform/news/{nid}/publish", timeout=30).json()["version"] == 3
    uc = s.get(f"{API}/news/unread-count", timeout=30).json()
    assert uc["banner"] is True and uc["latest"]["id"] == nid


# Control Room activation (controlroom_purchases) should yield active=True / be excluded by service_missing
def test_controlroom_active_detection(sa, orgs):
    s, d = orgs["b"]
    cr = ST["svc"]["control-room"]
    cid = uuid.uuid4().hex
    ST["cr"].append(cid)
    _db(lambda db: db.controlroom_purchases.insert_one({"id": cid, "org_id": d["org_id"], "event_id": "TEST_ev", "event_name": "TEST", "status": "active", "source": "superadmin"}))
    n = _create(sa, t="CR", product_id=cr["id"], audience={"type": "all"})
    sa.post(f"{API}/platform/news/{n['id']}/publish", timeout=30)
    p = _find(s.get(f"{API}/news", timeout=30).json(), n["id"])["product"]
    print("control-room product for org with CR:", p)
    assert p["active"] is True, "Org with active Control Room still sees 'Scopri e acquista'"
