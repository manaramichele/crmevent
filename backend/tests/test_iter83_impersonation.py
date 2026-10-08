"""Iter 83 — Super Admin 'Gestione Utenti → Accedi come utente' (impersonation / support session).

Validates:
- POST /api/platform/impersonate (403 for non-SA, 400 target superadmin, 409 choose_org multi-org)
- During support session: /auth/me (support payload), /platform/users (403), X-Org-Id ignored,
  write audit 'impersonation_action', POST /auth/change-password -> 403,
  disabled user => any write 403 (read-only).
- POST /platform/impersonate/stop restores Super Admin; audit impersonation_started/ended.
- Expiry => request returns SA and audit impersonation_expired.
- Logout during assistance ends the support session.
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASSWORD = "CrmEvent2026!"
QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASSWORD = "QaEvents2026!"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

TAG = f"TEST_iter83_{uuid.uuid4().hex[:6]}"


# --------- Fixtures ---------

@pytest.fixture(scope="module")
def db():
    cli = MongoClient(MONGO_URL)
    return cli[DB_NAME]


@pytest.fixture(scope="module")
def qa_org_id(db):
    org = db.organizations.find_one({"id": "org_qa_eventi"}) or db.organizations.find_one({"nome": {"$regex": "QA"}})
    assert org, "QA organization not found"
    return org["id"]


@pytest.fixture(scope="module")
def second_org(db):
    """Create a TEST_ secondary org for multi-org tests."""
    oid = f"org_{TAG}_second"
    db.organizations.insert_one({
        "id": oid, "nome": f"{TAG} Secondary Org", "type": "cliente", "status": "active",
        "created_at": "2026-01-01T00:00:00+00:00", "tag": TAG,
    })
    yield oid
    db.organizations.delete_many({"id": oid})


@pytest.fixture(scope="module")
def active_user(db, qa_org_id):
    """Active user with a single membership in QA org."""
    uid = f"user_{TAG}_active"
    email = f"{TAG}_active@example.com"
    from passlib.hash import bcrypt
    db.users.insert_one({
        "user_id": uid, "email": email, "name": f"Mario Rossi{TAG}", "nome": "Mario", "cognome": f"Rossi{TAG}",
        "role": "user", "org_id": qa_org_id, "active": True, "auth_provider": "password",
        "password_hash": bcrypt.hash("TestPwd2026!"), "created_at": "2026-01-01T00:00:00+00:00", "tag": TAG,
    })
    db.memberships.insert_one({
        "id": f"mem_{TAG}_active", "user_id": uid, "org_id": qa_org_id, "role": "user", "active": True,
        "created_at": "2026-01-01T00:00:00+00:00", "tag": TAG,
    })
    yield {"user_id": uid, "email": email, "org_id": qa_org_id}
    db.users.delete_many({"user_id": uid})
    db.memberships.delete_many({"user_id": uid})


@pytest.fixture(scope="module")
def disabled_user(db, qa_org_id):
    uid = f"user_{TAG}_disabled"
    email = f"{TAG}_disabled@example.com"
    db.users.insert_one({
        "user_id": uid, "email": email, "name": f"Luigi Bianchi{TAG}", "nome": "Luigi", "cognome": f"Bianchi{TAG}",
        "role": "user", "org_id": qa_org_id, "active": False, "auth_provider": "password",
        "created_at": "2026-01-01T00:00:00+00:00", "tag": TAG,
    })
    db.memberships.insert_one({
        "id": f"mem_{TAG}_disabled", "user_id": uid, "org_id": qa_org_id, "role": "user", "active": True,
        "created_at": "2026-01-01T00:00:00+00:00", "tag": TAG,
    })
    yield {"user_id": uid, "email": email, "org_id": qa_org_id}
    db.users.delete_many({"user_id": uid})
    db.memberships.delete_many({"user_id": uid})


@pytest.fixture(scope="module")
def multiorg_user(db, qa_org_id, second_org):
    uid = f"user_{TAG}_multi"
    email = f"{TAG}_multi@example.com"
    db.users.insert_one({
        "user_id": uid, "email": email, "name": f"Anna Verdi{TAG}", "nome": "Anna", "cognome": f"Verdi{TAG}",
        "role": "user", "org_id": qa_org_id, "active": True, "auth_provider": "password",
        "created_at": "2026-01-01T00:00:00+00:00", "tag": TAG,
    })
    for oid in (qa_org_id, second_org):
        db.memberships.insert_one({
            "id": f"mem_{TAG}_multi_{oid}", "user_id": uid, "org_id": oid, "role": "user", "active": True,
            "created_at": "2026-01-01T00:00:00+00:00", "tag": TAG,
        })
    yield {"user_id": uid, "email": email, "org_ids": [qa_org_id, second_org]}
    db.users.delete_many({"user_id": uid})
    db.memberships.delete_many({"user_id": uid})


def _login(session, email, password):
    r = session.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"Login failed {email}: {r.status_code} {r.text}"


@pytest.fixture
def sa():
    s = requests.Session()
    _login(s, SA_EMAIL, SA_PASSWORD)
    yield s
    # cleanup support cookie if any
    try: s.post(f"{API}/platform/impersonate/stop", timeout=10)
    except Exception: pass


@pytest.fixture
def admin():
    s = requests.Session()
    _login(s, QA_EMAIL, QA_PASSWORD)
    yield s


# --------- Access control on /platform/users and /platform/impersonate ---------

def test_platform_users_sa_ok(sa):
    r = sa.get(f"{API}/platform/users", timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 1
    assert any(u.get("email") == QA_EMAIL for u in data)
    assert all("cognome" in u and "nome" in u for u in data)


def test_platform_users_admin_forbidden(admin):
    r = admin.get(f"{API}/platform/users", timeout=20)
    assert r.status_code == 403


def test_impersonate_admin_forbidden(admin, active_user):
    r = admin.post(f"{API}/platform/impersonate", json={"user_id": active_user["user_id"]}, timeout=20)
    assert r.status_code == 403


def test_impersonate_target_superadmin_400(sa, db):
    # find any superadmin id (self)
    sa_id = db.users.find_one({"role": "superadmin"})["user_id"]
    r = sa.post(f"{API}/platform/impersonate", json={"user_id": sa_id}, timeout=20)
    assert r.status_code == 400


def test_impersonate_multiorg_choose_409(sa, multiorg_user):
    r = sa.post(f"{API}/platform/impersonate", json={"user_id": multiorg_user["user_id"]}, timeout=20)
    assert r.status_code == 409
    body = r.json()
    detail = body.get("detail") or {}
    assert detail.get("code") == "choose_org"
    orgs = detail.get("orgs") or []
    assert len(orgs) == 2
    assert set(o["org_id"] for o in orgs) == set(multiorg_user["org_ids"])


# --------- During support session ---------

def test_support_session_me_and_platform_users_403(sa, active_user, qa_org_id):
    r = sa.post(f"{API}/platform/impersonate", json={"user_id": active_user["user_id"]}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True

    # /auth/me returns target with support payload
    me = sa.get(f"{API}/auth/me", timeout=20)
    assert me.status_code == 200
    data = me.json()
    assert data["user_id"] == active_user["user_id"]
    assert data["email"] == active_user["email"]
    sup = data.get("support")
    assert sup, "support payload missing"
    assert sup["org_id"] == qa_org_id
    assert sup.get("target_name")
    assert sup.get("expires_at")
    assert sup.get("read_only") is False

    # /platform/users must now be 403 (no SA privileges while impersonating)
    r2 = sa.get(f"{API}/platform/users", timeout=20)
    assert r2.status_code == 403

    # X-Org-Id of a different org must be ignored (not promote nor error-out of support org)
    me2 = sa.get(f"{API}/auth/me", headers={"X-Org-Id": "non_existent_org_id"}, timeout=20)
    assert me2.status_code == 200
    assert me2.json().get("support", {}).get("org_id") == qa_org_id


def test_support_change_password_forbidden(sa, active_user):
    sa.post(f"{API}/platform/impersonate", json={"user_id": active_user["user_id"]}, timeout=20)
    r = sa.post(f"{API}/auth/change-password",
                json={"current_password": "x", "new_password": "newNewPass!"}, timeout=20)
    assert r.status_code == 403


def test_support_write_records_impersonation_action(sa, admin, active_user, db):
    # Perform impersonation
    sa.post(f"{API}/platform/impersonate", json={"user_id": active_user["user_id"]}, timeout=20)
    # Attempt a non-/auth write; even if endpoint returns 4xx, audit should fire in dependency.
    before = db.audit_logs.count_documents({"action": "impersonation_action",
                                            "target_email": active_user["email"]})
    r = sa.post(f"{API}/persons", json={"nome": f"X{TAG}", "cognome": f"Y{TAG}"}, timeout=20)
    # We don't require success; we just require that the audit got recorded.
    time.sleep(0.5)
    after = db.audit_logs.count_documents({"action": "impersonation_action",
                                           "target_email": active_user["email"]})
    assert after > before, f"impersonation_action not recorded (status={r.status_code})"


def test_disabled_user_read_only(sa, disabled_user):
    r = sa.post(f"{API}/platform/impersonate", json={"user_id": disabled_user["user_id"]}, timeout=20)
    assert r.status_code == 200
    assert r.json().get("read_only") is True
    # Any write op must be blocked with 403
    r2 = sa.post(f"{API}/persons", json={"nome": "A", "cognome": "B"}, timeout=20)
    assert r2.status_code == 403
    # Reads still work
    me = sa.get(f"{API}/auth/me", timeout=20)
    assert me.status_code == 200
    assert me.json().get("support", {}).get("read_only") is True


# --------- Stop / expiry / logout ---------

def test_stop_restores_superadmin(sa, active_user, db):
    r = sa.post(f"{API}/platform/impersonate", json={"user_id": active_user["user_id"]}, timeout=20)
    assert r.status_code == 200
    me1 = sa.get(f"{API}/auth/me", timeout=20).json()
    assert me1.get("support") is not None

    r2 = sa.post(f"{API}/platform/impersonate/stop", timeout=20)
    assert r2.status_code == 200
    me2 = sa.get(f"{API}/auth/me", timeout=20).json()
    assert me2.get("role") == "superadmin"
    assert me2.get("support") is None

    # Audit records
    time.sleep(0.3)
    started = db.audit_logs.count_documents({"action": "impersonation_started",
                                             "meta.target_user_id": active_user["user_id"]})
    ended = db.audit_logs.count_documents({"action": "impersonation_ended",
                                           "meta.target_user_id": active_user["user_id"]})
    assert started >= 1 and ended >= 1


def test_expiry_falls_back_to_superadmin(sa, active_user, db):
    r = sa.post(f"{API}/platform/impersonate", json={"user_id": active_user["user_id"]}, timeout=20)
    assert r.status_code == 200
    # Force expire the active session in Mongo
    db.support_sessions.update_many(
        {"target_user_id": active_user["user_id"], "active": True},
        {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}},
    )
    me = sa.get(f"{API}/auth/me", timeout=20).json()
    assert me.get("role") == "superadmin"
    assert me.get("support") is None
    time.sleep(0.3)
    expired = db.audit_logs.count_documents({"action": "impersonation_expired",
                                             "meta.target_user_id": active_user["user_id"]})
    assert expired >= 1


def test_logout_ends_support_session(active_user, db):
    s = requests.Session()
    _login(s, SA_EMAIL, SA_PASSWORD)
    r = s.post(f"{API}/platform/impersonate", json={"user_id": active_user["user_id"]}, timeout=20)
    assert r.status_code == 200
    s.post(f"{API}/auth/logout", timeout=20)
    time.sleep(0.3)
    # No active support_sessions for this target left
    active_cnt = db.support_sessions.count_documents({"target_user_id": active_user["user_id"], "active": True})
    assert active_cnt == 0


# --------- Teardown ---------

def test_zz_cleanup(db):
    db.users.delete_many({"tag": TAG})
    db.memberships.delete_many({"tag": TAG})
    db.organizations.delete_many({"tag": TAG})
    db.support_sessions.delete_many({"target_email": {"$regex": TAG}})
    db.audit_logs.delete_many({"target_email": {"$regex": TAG}})
    db.persons.delete_many({"nome": {"$regex": TAG}})
