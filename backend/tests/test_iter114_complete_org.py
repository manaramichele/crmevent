"""iter114 - CRMEvent Complete Organization popup (Google user flow).

Covers:
- GET /api/auth/me -> needs_org True for Google user without org
- GET /api/my/todo -> 403 (operational APIs blocked until org exists)
- POST /api/auth/complete-organization validation errors
- Successful complete-organization creates org, admin_org membership, 14-day trial,
  terms_version/privacy_version '2026-10', marketing_consent, welcome_demo=pending
- Double-click concurrency returns 409 for the second request
- Already-completed user calling again returns 400
- Invited collaborator (existing active membership) returns 400
- Regression: /registrati register-organization still works, super admin login unchanged
"""
import os
import time
import uuid
import threading
import datetime as dt
import jwt
import pytest
import requests
from pymongo import MongoClient

def _load_env(path, key):
    try:
        for line in open(path):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        return None
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"
JWT_SECRET = os.environ.get("JWT_SECRET") or open("/app/backend/.env").read().split('JWT_SECRET="')[1].split('"')[0]
MONGO_URL = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = os.environ.get("DB_NAME") or "test_database"


def mint(uid: str, email: str) -> str:
    return jwt.encode(
        {"sub": uid, "email": email, "type": "access",
         "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)},
        JWT_SECRET, algorithm="HS256",
    )


@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(MONGO_URL)
    db = cli[DB_NAME]
    yield db
    # Teardown cleanup
    test_uids = [u["user_id"] for u in db.users.find({"email": {"$regex": "^test_google_|TEST_"}})]
    test_uids += [u["user_id"] for u in db.users.find({"user_id": {"$regex": "^user_test_"}})]
    if test_uids:
        test_orgs = [o["id"] for o in db.organizations.find({"owner_user_id": {"$in": test_uids}})]
        db.organizations.delete_many({"owner_user_id": {"$in": test_uids}})
        db.memberships.delete_many({"user_id": {"$in": test_uids}})
        if test_orgs:
            db.memberships.delete_many({"org_id": {"$in": test_orgs}})
            db.saas_subscriptions.delete_many({"org_id": {"$in": test_orgs}})
        db.users.delete_many({"user_id": {"$in": test_uids}})
    db.users.delete_many({"email": {"$regex": "^test_|TEST_"}})
    db.organizations.delete_many({"name": {"$regex": "^TEST_"}})
    db.registered_users.delete_many({"email": {"$regex": "^test_|TEST_"}})
    cli.close()


def _mk_google_user(mongo, uid, email, name="Mario Rossi"):
    mongo.users.delete_one({"user_id": uid})
    mongo.users.insert_one({
        "user_id": uid, "email": email, "name": name,
        "nome": name.split()[0], "cognome": " ".join(name.split()[1:]) or None,
        "role": "admin", "auth_provider": "google", "google_sub": f"test-sub-{uid}",
        "active": True, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    return mint(uid, email)


# ---------------- 1) needs_org / blocked operational APIs ----------------
def test_me_needs_org_and_todo_blocked(mongo):
    uid = "user_test_g1"
    tok = _mk_google_user(mongo, uid, "test_google_new@example.com", "Mario Rossi")
    s = requests.Session()
    s.cookies.set("access_token", tok)
    me = s.get(f"{API}/auth/me")
    assert me.status_code == 200, me.text
    data = me.json()
    assert data["needs_org"] is True
    assert data["email"] == "test_google_new@example.com"
    # Operational endpoint blocked
    todo = s.get(f"{API}/my/todo")
    assert todo.status_code == 403, f"expected 403, got {todo.status_code}: {todo.text[:200]}"


# ---------------- 2) validation errors ----------------
def test_complete_org_validation_errors(mongo):
    uid = "user_test_g_val"
    tok = _mk_google_user(mongo, uid, "test_google_val@example.com", "Luca Bianchi")
    s = requests.Session(); s.cookies.set("access_token", tok)
    # empty org_name
    r = s.post(f"{API}/auth/complete-organization", json={"org_name": "", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 400 and "organizzazione" in r.json()["detail"].lower()
    # missing accept
    r = s.post(f"{API}/auth/complete-organization", json={"org_name": "TEST_X", "telefono": "+393331234567", "accept_terms": False})
    assert r.status_code == 400 and "accettare" in r.json()["detail"].lower()


# ---------------- 3) success path ----------------
def test_complete_org_success(mongo):
    uid = "user_test_g_ok"
    tok = _mk_google_user(mongo, uid, "test_google_ok@example.com", "Mario Rossi")
    s = requests.Session(); s.cookies.set("access_token", tok)
    r = s.post(f"{API}/auth/complete-organization", json={
        "org_name": "TEST_Org Google", "telefono": "+39 333 1234567",
        "accept_terms": True, "marketing_consent": True,
        "nome": "Mario", "cognome": "Rossi",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["needs_org"] is False
    assert body["role"] in ("admin", "admin_org")
    # Verify DB state
    u = mongo.users.find_one({"user_id": uid})
    assert u["org_id"]
    assert u["terms_version"] == "2026-10"
    assert u["privacy_version"] == "2026-10"
    assert u["marketing_consent"] is True
    assert u.get("marketing_consent_at")
    assert u["welcome_demo"] == "pending"
    assert u["nome"] == "Mario" and u["cognome"] == "Rossi"
    org = mongo.organizations.find_one({"id": u["org_id"]})
    assert org and (org.get("nome") == "TEST_Org Google" or org.get("name") == "TEST_Org Google")
    assert org["owner_user_id"] == uid
    # trial 14 days
    sub = org.get("subscription") or {}
    trial_end = sub.get("trial_end") or org.get("trial_end") or (org.get("saas") or {}).get("trial_end")
    assert trial_end, f"no trial_end in org: {org.keys()}"
    te = dt.datetime.fromisoformat(trial_end.replace("Z", "+00:00")) if isinstance(trial_end, str) else trial_end
    delta_days = (te - dt.datetime.now(dt.timezone.utc)).days
    assert 12 <= delta_days <= 14, f"trial_end delta {delta_days} not ~14d"
    # membership admin_org
    mem = mongo.memberships.find_one({"user_id": uid, "org_id": u["org_id"], "active": True})
    assert mem and mem["role"] == "admin_org"


# ---------------- 4) double POST -> 400 ----------------
def test_complete_org_second_call_rejected(mongo):
    # reuse user from previous test
    u = mongo.users.find_one({"user_id": "user_test_g_ok"})
    assert u and u.get("org_id")
    tok = mint("user_test_g_ok", u["email"])
    s = requests.Session(); s.cookies.set("access_token", tok)
    r = s.post(f"{API}/auth/complete-organization", json={
        "org_name": "TEST_Org Another", "telefono": "+393331111111", "accept_terms": True,
        "nome": "Mario", "cognome": "Rossi",
    })
    assert r.status_code == 400
    assert "presente" in r.json()["detail"].lower() or "collegato" in r.json()["detail"].lower()


# ---------------- 5) concurrency double-click ----------------
def test_complete_org_concurrency(mongo):
    uid = "user_test_g_race"
    tok = _mk_google_user(mongo, uid, "test_google_race@example.com", "Anna Verdi")
    payload = {"org_name": "TEST_Race Org", "telefono": "+393331234567", "accept_terms": True,
               "nome": "Anna", "cognome": "Verdi"}
    results = {}
    def fire(key):
        s = requests.Session(); s.cookies.set("access_token", tok)
        try:
            r = s.post(f"{API}/auth/complete-organization", json=payload, timeout=30)
            results[key] = r.status_code
        except Exception as e:
            results[key] = f"err:{e}"
    t1 = threading.Thread(target=fire, args=("a",)); t2 = threading.Thread(target=fire, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()
    codes = sorted(str(c) for c in results.values())
    # Expect exactly one 200 + one of {409, 400}
    assert "200" in codes, f"no success in concurrency: {results}"
    other = [c for c in codes if c != "200"]
    assert other and other[0] in ("409", "400"), f"second call code unexpected: {results}"
    # Only one org created
    orgs = list(mongo.organizations.find({"owner_user_id": uid}))
    assert len(orgs) == 1, f"expected 1 org, got {len(orgs)}"


# ---------------- 6) invited collaborator (active membership) -> 400 ----------------
def test_complete_org_blocked_for_invited_collaborator(mongo):
    uid = "user_test_g_invited"
    tok = _mk_google_user(mongo, uid, "test_google_invited@example.com", "Paolo Neri")
    # Insert an active membership to simulate an invited collaborator
    mongo.memberships.insert_one({
        "id": f"mem_{uuid.uuid4().hex[:8]}", "user_id": uid,
        "org_id": "org_qa_eventi", "role": "member", "active": True,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })
    s = requests.Session(); s.cookies.set("access_token", tok)
    r = s.post(f"{API}/auth/complete-organization", json={
        "org_name": "TEST_Should Not Create", "telefono": "+393331234567",
        "accept_terms": True, "nome": "Paolo", "cognome": "Neri",
    })
    assert r.status_code == 400, r.text
    assert "collegato" in r.json()["detail"].lower() or "presente" in r.json()["detail"].lower()
    orgs = list(mongo.organizations.find({"owner_user_id": uid}))
    assert len(orgs) == 0


# ---------------- 7) regression: /auth/register-organization still works ----------------
def test_register_organization_regression():
    email = f"test_reg_{uuid.uuid4().hex[:6]}@example.com"
    r = requests.post(f"{API}/auth/register-organization", json={
        "nome": "Test", "cognome": "User", "email": email, "password": "StrongPass123!",
        "org_name": f"TEST_Reg {uuid.uuid4().hex[:4]}", "telefono": "+393331234567",
        "accept_terms": True,
    })
    assert r.status_code in (200, 201), r.text
    j = r.json()
    assert j.get("needs_org") in (False, None)


# ---------------- 8) regression: super admin login unchanged ----------------
def test_superadmin_login_regression():
    r = requests.post(f"{API}/auth/login", json={
        "email": os.environ.get("ADMIN_EMAIL", "manara.michele.pro@gmail.com"),
        "password": os.environ.get("ADMIN_PASSWORD", "CrmEvent2026!"),
    })
    assert r.status_code == 200, r.text
    assert r.json().get("role") == "superadmin"
