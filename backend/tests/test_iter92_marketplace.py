"""Iter 92 — Marketplace backend tests (catalog, checkout, permissions, admin CRUD)."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA)


@pytest.fixture(scope="module")
def org():
    return _login(ORG)


# ---------- Catalog visibility & seeded services ----------
def test_catalog_lists_six_seeded_services(org):
    r = org.get(f"{BASE}/api/marketplace/services", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "services" in data and "categories" in data
    keys = {s["key"] for s in data["services"]}
    expected = {"sito-organizzazione", "sito-evento", "newsletter", "whatsapp", "contratti", "magazzino"}
    assert expected.issubset(keys), f"missing seeded keys: {expected - keys}"
    # All should be coming_soon and not purchasable_now
    for s in data["services"]:
        if s["key"] in expected:
            assert s["status"] == "coming_soon"
            assert s["purchasable_now"] is False
    assert data["can_purchase"] is True  # org admin


def test_coming_soon_service_checkout_returns_400(org):
    r = org.get(f"{BASE}/api/marketplace/services", timeout=15)
    svc = next(s for s in r.json()["services"] if s["key"] == "newsletter")
    r2 = org.post(f"{BASE}/api/marketplace/services/{svc['id']}/checkout",
                  json={"origin_url": BASE}, timeout=15)
    assert r2.status_code == 400, r2.text


# ---------- Super Admin: catalog CRUD + validation ----------
def test_sa_cannot_set_purchasable_without_tech_ready(sa):
    r = sa.get(f"{BASE}/api/platform/marketplace/services", timeout=15)
    assert r.status_code == 200
    svc = next(s for s in r.json()["services"] if s["key"] == "newsletter")
    body = {**{k: svc.get(k) for k in ("name", "description", "icon", "image", "category", "price",
                                        "price_type", "usage_unit", "usage_limits", "terms", "status",
                                        "visible", "purchasable", "tech_ready", "billing_method", "scope", "sort")},
            "status": "available", "purchasable": True, "tech_ready": False, "price": 10.0, "price_type": "one_time"}
    r2 = sa.put(f"{BASE}/api/platform/marketplace/services/{svc['id']}", json=body, timeout=15)
    assert r2.status_code == 400, r2.text


def test_sa_coming_soon_forces_purchasable_false(sa):
    body = {"name": "TEST_coming_soon_svc", "description": "test", "category": "Altro",
            "price": 10.0, "price_type": "one_time", "status": "coming_soon",
            "visible": True, "purchasable": True, "tech_ready": True,
            "billing_method": "stripe", "scope": "org", "sort": 999}
    r = sa.post(f"{BASE}/api/platform/marketplace/services", json=body, timeout=15)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["purchasable"] is False  # forced
    # Cleanup -> set invisible so it doesn't clutter (API has no delete)
    sa.put(f"{BASE}/api/platform/marketplace/services/{created['id']}",
           json={**body, "visible": False, "status": "coming_soon", "purchasable": False, "tech_ready": False}, timeout=15)


@pytest.fixture(scope="module")
def test_service(sa):
    body = {"name": "TEST_mkt_service_one_time", "description": "paid test service",
            "icon": "Package", "image": None, "category": "Altro",
            "price": 10.0, "price_type": "one_time", "status": "available",
            "visible": True, "purchasable": True, "tech_ready": True,
            "billing_method": "stripe", "scope": "org", "sort": 998}
    r = sa.post(f"{BASE}/api/platform/marketplace/services", json=body, timeout=15)
    assert r.status_code == 200, r.text
    svc = r.json()
    yield svc
    # Teardown
    sa.put(f"{BASE}/api/platform/marketplace/services/{svc['id']}",
           json={**body, "visible": False, "status": "coming_soon", "purchasable": False, "tech_ready": False}, timeout=15)


def _ensure_billing(org):
    r = org.get(f"{BASE}/api/account/billing/validate", timeout=15)
    if r.status_code == 200 and r.json().get("valid"):
        return
    payload = {"tipo": "azienda", "paese": "IT", "ragione_sociale": "TEST QA Org SRL",
               "partita_iva": "12345678903", "codice_fiscale": "12345678903",
               "indirizzo": "Via Prova 1", "cap": "20100", "citta": "Milano",
               "provincia": "MI", "codice_sdi": "0000000", "pec": "test@pec.it",
               "email_fatturazione": "fatture@qa.test"}
    r2 = org.put(f"{BASE}/api/account/billing", json=payload, timeout=15)
    assert r2.status_code == 200, r2.text


def test_org_admin_checkout_returns_stripe_url(org, test_service):
    _ensure_billing(org)
    r = org.post(f"{BASE}/api/marketplace/services/{test_service['id']}/checkout",
                 json={"origin_url": BASE}, timeout=20)
    # could be 200 (TEST mode) or 502 if stripe not configured; expect 200 for TEST
    assert r.status_code == 200, r.text
    data = r.json()
    assert "checkout_url" in data
    assert "stripe.com" in data["checkout_url"] or data["checkout_url"].startswith("https://")


def test_my_marketplace_excludes_pending(org, test_service):
    # The previous test created a pending purchase. GET /my must not list it.
    r = org.get(f"{BASE}/api/marketplace/my", timeout=15)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert all(p["status"] != "pending" for p in rows)
    assert all(p["service_id"] != test_service["id"] for p in rows)


# ---------- Collaborator cannot purchase ----------
@pytest.fixture(scope="module")
def collaborator_session(org):
    """Create a TEST_ collaborator user via direct Mongo write; delete at teardown."""
    import asyncio
    import bcrypt
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["test_database"]
    # Find QA org_id via the org admin profile
    r = org.get(f"{BASE}/api/auth/me", timeout=15)
    assert r.status_code == 200, r.text
    me = r.json()
    org_id = me.get("org_id") or (me.get("memberships") or [{}])[0].get("org_id")
    assert org_id, f"could not resolve org_id for QA admin: {me}"
    uid = "TEST_mkt_collab_uid"
    email = "test_mkt_collab@crmeventqa.it"
    pw = "TestCollab2026!"
    pw_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

    async def _setup():
        await db.users.update_one({"user_id": uid}, {"$set": {
            "user_id": uid, "email": email, "name": "TEST Collab",
            "password_hash": pw_hash, "role": "user", "active": True,
            "auth_provider": "password", "created_at": "2026-01-01T00:00:00+00:00"}}, upsert=True)
        await db.memberships.update_one({"user_id": uid, "org_id": org_id}, {"$set": {
            "user_id": uid, "org_id": org_id, "role": "collaboratore", "active": True,
            "permissions": {"sections": {"dashboard": ["view"]}, "events": "all",
                            "send_invites": False, "marketplace_purchase": False},
            "created_at": "2026-01-01T00:00:00+00:00"}}, upsert=True)

    async def _teardown():
        await db.users.delete_one({"user_id": uid})
        await db.memberships.delete_one({"user_id": uid, "org_id": org_id})

    asyncio.get_event_loop().run_until_complete(_setup())
    s = _login({"email": email, "password": pw})
    yield s
    asyncio.get_event_loop().run_until_complete(_teardown())


def test_collaborator_without_perm_cannot_purchase(collaborator_session, test_service):
    r = collaborator_session.post(
        f"{BASE}/api/marketplace/services/{test_service['id']}/checkout",
        json={"origin_url": BASE}, timeout=15)
    assert r.status_code == 403, r.text
    assert "permesso" in r.text.lower() or "marketplace" in r.text.lower()


def test_collaborator_sees_catalog_but_cannot_purchase_flag(collaborator_session):
    r = collaborator_session.get(f"{BASE}/api/marketplace/services", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["can_purchase"] is False


# ---------- Super Admin purchases listing ----------
def test_sa_purchases_listing(sa):
    r = sa.get(f"{BASE}/api/platform/marketplace/purchases", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
