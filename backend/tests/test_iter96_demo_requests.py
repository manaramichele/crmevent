"""Iter 96 — WelcomeDemo flow: /api/demo/welcome, /slots, /dismiss, /requests + Super Admin /platform/demo/requests."""
import os
import uuid

import pytest
import requests


def _load_env():
    try:
        for ln in open("/app/frontend/.env", "r", encoding="utf-8"):
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.environ.get("REACT_APP_BACKEND_URL", "")


BASE = _load_env().rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not configured"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASSWORD = "CrmEvent2026!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PASSWORD)


@pytest.fixture(scope="module")
def created():
    bag = {"orgs": [], "requests": []}
    yield bag
    try:
        from pymongo import MongoClient
        mu = os.environ.get("MONGO_URL"); dbn = os.environ.get("DB_NAME")
        if mu and dbn:
            cli = MongoClient(mu)
            d = cli[dbn]
            for info in bag["orgs"]:
                oid, uid, email = info.get("org_id"), info.get("user_id"), info.get("email")
                if oid:
                    d.organizations.delete_many({"id": oid})
                    d.memberships.delete_many({"org_id": oid})
                    d.saas_subscriptions.delete_many({"org_id": oid})
                    d.leads.delete_many({"org_id": oid})
                    d.demo_requests.delete_many({"org_id": oid})
                if uid:
                    d.users.delete_many({"user_id": uid})
                if email:
                    d.users.delete_many({"email": email})
                    d.leads.delete_many({"email": email})
            cli.close()
    except Exception as e:
        print("cleanup error:", e)


def _register(prefix: str):
    s = requests.Session()
    email = f"TEST_{prefix}_{uuid.uuid4().hex[:6]}@example.com"
    payload = {
        "nome": "Test", "cognome": "Welcome", "email": email, "password": "TestPass2026!",
        "org_name": f"TEST_DemoReq_{uuid.uuid4().hex[:6]}", "telefono": "+393331112233",
        "accept_terms": True,
    }
    r = s.post(f"{BASE}/api/auth/register-organization", json=payload, timeout=25)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return s, r.json(), email


# ---- Registration sets welcome_demo=pending ----
def test_register_sets_welcome_demo_pending(created):
    s, data, email = _register("req")
    assert data.get("welcome_demo") == "pending"
    created["orgs"].append({"org_id": data.get("org_id"), "user_id": data.get("user_id"),
                             "email": email, "session": s, "org_name": None})


# ---- /demo/welcome prefill ----
def test_demo_welcome_prefill(created):
    s = created["orgs"][0]["session"]
    r = s.get(f"{BASE}/api/demo/welcome", timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("state") == "pending"
    assert j.get("duration_min") == 30
    pf = j.get("prefill") or {}
    assert pf.get("email") == created["orgs"][0]["email"].lower()
    assert pf.get("nome")
    assert pf.get("organizzazione", "").startswith("TEST_DemoReq_")


# ---- /demo/slots returns list ----
def test_demo_slots(created):
    s = created["orgs"][0]["session"]
    r = s.get(f"{BASE}/api/demo/slots", timeout=15)
    assert r.status_code == 200
    slots = r.json().get("slots") or []
    assert isinstance(slots, list)
    assert len(slots) > 0, "Expected slots configured by SA"
    created["orgs"][0]["slot"] = slots[0]["slot_key"]


# ---- POST /demo/requests creates request, lead, flips welcome_demo ----
def test_create_demo_request(created):
    info = created["orgs"][0]
    s = info["session"]
    slot = info["slot"]
    r = s.post(f"{BASE}/api/demo/requests", json={
        "slot_key": slot, "nome": "Test Welcome", "telefono": "+393331112233",
        "organizzazione": "TEST_DemoReqOrg", "note": "nota di test"
    }, timeout=25)
    assert r.status_code == 200, f"create failed {r.status_code} {r.text}"
    j = r.json()
    assert j.get("ok") is True
    assert j.get("preferred_slot") == slot
    assert j.get("id")
    created["requests"].append(j["id"])

    # welcome_demo flipped
    me = s.get(f"{BASE}/api/auth/me", timeout=10).json()
    assert me.get("welcome_demo") == "requested"


# ---- Invalid slot -> 409 ----
def test_invalid_slot_returns_409(created):
    s = created["orgs"][0]["session"]
    r = s.post(f"{BASE}/api/demo/requests", json={
        "slot_key": "2099-01-01T09:00", "nome": "Test"
    }, timeout=15)
    assert r.status_code == 409, f"expected 409 got {r.status_code} {r.text}"


# ---- Empty name -> 400 ----
def test_empty_name_returns_400(created):
    info = created["orgs"][0]
    s = info["session"]
    r = s.get(f"{BASE}/api/demo/slots", timeout=15)
    slots = r.json().get("slots") or []
    if not slots:
        pytest.skip("no slots")
    r = s.post(f"{BASE}/api/demo/requests", json={"slot_key": slots[0]["slot_key"], "nome": "   "}, timeout=15)
    assert r.status_code == 400


# ---- Dismiss sets welcome_demo=dismissed ----
def test_dismiss(created):
    s, data, email = _register("skip")
    created["orgs"].append({"org_id": data.get("org_id"), "user_id": data.get("user_id"), "email": email, "session": s})
    r = s.post(f"{BASE}/api/demo/welcome/dismiss", timeout=10)
    assert r.status_code == 200
    me = s.get(f"{BASE}/api/auth/me", timeout=10).json()
    assert me.get("welcome_demo") == "dismissed"


# ---- Super Admin list / status change ----
def test_sa_list_demo_requests(sa, created):
    r = sa.get(f"{BASE}/api/platform/demo/requests", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert isinstance(items, list)
    if created["requests"]:
        ids = {x["id"] for x in items}
        assert created["requests"][0] in ids
        # check columns
        row = next(x for x in items if x["id"] == created["requests"][0])
        for k in ("nome", "email", "org_id", "preferred_slot", "status", "created_at"):
            assert k in row


def test_sa_filter_and_patch_status(sa, created):
    if not created["requests"]:
        pytest.skip("no request created")
    rid = created["requests"][0]
    # filter
    r = sa.get(f"{BASE}/api/platform/demo/requests", params={"status": "nuova"}, timeout=15)
    assert r.status_code == 200
    assert any(x["id"] == rid for x in r.json().get("items") or [])

    # PATCH valid
    r = sa.patch(f"{BASE}/api/platform/demo/requests/{rid}", json={"status": "confermata"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "confermata"
    # PATCH invalid
    r = sa.patch(f"{BASE}/api/platform/demo/requests/{rid}", json={"status": "bogus"}, timeout=15)
    assert r.status_code == 400
    # PATCH not found
    r = sa.patch(f"{BASE}/api/platform/demo/requests/nope", json={"status": "nuova"}, timeout=15)
    assert r.status_code == 404


def test_non_superadmin_cannot_list(created):
    s = created["orgs"][0]["session"]
    r = s.get(f"{BASE}/api/platform/demo/requests", timeout=10)
    assert r.status_code in (401, 403)
