"""Backend tests for Dashboard RBAC (iter 80).

Verifica che GET /api/dashboard esponga solo le sezioni per cui l'utente ha permesso 'view',
rimuovendo i blocchi dalla risposta (non solo nascosti). Testa anche cambio permessi senza re-login.
"""
import os
import uuid
import bcrypt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SUPER_EMAIL = "manara.michele.pro@gmail.com"
SUPER_PASS = "CrmEvent2026!"
ADMIN_EMAIL = "qa.eventi@crmeventqa.it"
ADMIN_PASS = "QaEvents2026!"

TEST_USER_EMAIL = f"test_dash_user_{uuid.uuid4().hex[:6]}@crmeventqa.it"
TEST_USER_PASS = "TestPass123!"


def _hash(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def super_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PASS})
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def qa_org_id(admin_session, mongo):
    # qa.eventi user org
    u = mongo.users.find_one({"email": ADMIN_EMAIL})
    assert u, "qa.eventi user not found in DB"
    org_id = u.get("org_id")
    assert org_id, "qa.eventi has no org_id"
    return org_id


@pytest.fixture(scope="module")
def test_user(mongo, qa_org_id):
    """Create TEST_ user in QA org with sections: dashboard+eventi+staff only."""
    uid = f"user_{uuid.uuid4().hex[:12]}"
    now = "2026-01-01T00:00:00+00:00"
    mongo.users.insert_one({
        "user_id": uid, "email": TEST_USER_EMAIL, "name": "TEST Dash User",
        "password_hash": _hash(TEST_USER_PASS), "role": "member", "auth_provider": "password",
        "org_id": qa_org_id, "active": True, "created_at": now, "last_login_at": now,
    })
    sections = {"dashboard": ["view"], "eventi": ["view"], "staff": ["view"],
                "aziende": [], "anagrafiche": [], "ospitalita": [], "sponsor": [],
                "attivita": [], "followup": [], "briefing": [], "mappe": [], "pipeline": []}
    mem = {
        "id": f"mem_{uuid.uuid4().hex[:12]}", "user_id": uid, "org_id": qa_org_id,
        "role": "user", "active": True, "created_at": now,
        "permissions": {"sections": sections, "events": "all",
                        "teams": {"scope": "all", "ids": [], "manage_staff": True, "manage_volunteers": True}},
    }
    mongo.memberships.insert_one(mem)
    yield {"user_id": uid, "email": TEST_USER_EMAIL, "password": TEST_USER_PASS, "org_id": qa_org_id}
    # cleanup
    mongo.users.delete_many({"email": {"$regex": "^test_dash_user_"}})
    mongo.memberships.delete_many({"user_id": uid})


@pytest.fixture
def test_user_session(test_user):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": test_user["email"], "password": test_user["password"]})
    assert r.status_code == 200, f"TEST user login failed: {r.status_code} {r.text}"
    return s


# ---------- Regression: admin & superadmin see full dashboard ----------

class TestFullAccess:
    def test_org_admin_full_dashboard(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        d = r.json()
        secs = d.get("sections", {})
        for k in ("eventi", "aziende", "anagrafiche", "staff", "sponsor", "attivita", "followup"):
            assert secs.get(k) is True, f"admin missing section {k}: {secs}"
        for k in ("eventi", "crm", "commerciale", "attivita", "staff", "pipeline_chart", "tipo_chart"):
            assert k in d, f"admin dashboard missing block {k}: keys={list(d)}"

    def test_superadmin_dashboard(self, super_session):
        # Superadmin has no org, dashboard may 403; just ensure endpoint is reachable
        r = super_session.get(f"{BASE_URL}/api/dashboard")
        # 428 = must pick an org context first (superadmin has no default org)
        assert r.status_code in (200, 400, 403, 428), f"unexpected {r.status_code}"


# ---------- RBAC restricted user ----------

class TestRestrictedUser:
    def test_dashboard_shows_only_eventi_and_staff(self, test_user_session):
        r = test_user_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        secs = d.get("sections", {})
        assert secs.get("eventi") is True
        assert secs.get("staff") is True
        for k in ("aziende", "anagrafiche", "sponsor", "attivita", "followup", "pipeline", "ospitalita", "briefing"):
            assert secs.get(k) is False, f"{k} should be False, got {secs.get(k)}"
        # Blocks removed from response
        assert "eventi" in d
        assert "staff" in d
        assert "crm" not in d, "crm block must be absent"
        assert "commerciale" not in d, "commerciale must be absent (no sponsor.view)"
        assert "pipeline_chart" not in d
        assert "tipo_chart" not in d
        assert "attivita" not in d, "attivita block must be absent"

    def test_deals_endpoint_forbidden(self, test_user_session):
        r = test_user_session.get(f"{BASE_URL}/api/deals")
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_pipeline_attention_forbidden(self, test_user_session):
        r = test_user_session.get(f"{BASE_URL}/api/pipeline/attention")
        assert r.status_code == 403, f"expected 403, got {r.status_code}"

    def test_companies_endpoint_forbidden(self, test_user_session):
        r = test_user_session.get(f"{BASE_URL}/api/companies")
        assert r.status_code == 403


# ---------- Permission change applied without re-login ----------

class TestPermissionChangeLive:
    def test_add_sponsor_remove_staff_without_relogin(self, test_user_session, test_user, mongo):
        # Modify membership permissions in DB directly
        new_sections = {"dashboard": ["view"], "eventi": ["view"], "sponsor": ["view"],
                        "staff": [], "aziende": [], "anagrafiche": [], "ospitalita": [],
                        "attivita": [], "followup": [], "briefing": [], "mappe": [], "pipeline": []}
        mongo.memberships.update_one(
            {"user_id": test_user["user_id"], "org_id": test_user["org_id"]},
            {"$set": {"permissions.sections": new_sections}},
        )
        # Reload dashboard with same session (no re-login)
        r = test_user_session.get(f"{BASE_URL}/api/dashboard")
        assert r.status_code == 200
        d = r.json()
        secs = d["sections"]
        assert secs["sponsor"] is True
        assert secs["staff"] is False
        assert "commerciale" in d, "commerciale must appear after granting sponsor.view"
        assert "pipeline_chart" in d
        assert "tipo_chart" in d
        assert "staff" not in d, "staff block must be gone"


# ---------- Collaboratore defaults: sponsor & pipeline hidden ----------

class TestCollaboratoreDefaults:
    def test_collaboratore_no_sponsor_block(self, mongo, qa_org_id):
        # Create temporary collaboratore user with default permissions
        uid = f"user_{uuid.uuid4().hex[:12]}"
        email = f"test_collab_{uuid.uuid4().hex[:6]}@crmeventqa.it"
        pwd = "TestPass123!"
        now = "2026-01-01T00:00:00+00:00"
        mongo.users.insert_one({"user_id": uid, "email": email, "name": "TEST Collab",
                                "password_hash": _hash(pwd), "role": "member", "auth_provider": "password",
                                "org_id": qa_org_id, "active": True, "created_at": now, "last_login_at": now})
        # No explicit permissions -> defaults for collaboratore
        mongo.memberships.insert_one({
            "id": f"mem_{uuid.uuid4().hex[:12]}", "user_id": uid, "org_id": qa_org_id,
            "role": "collaboratore", "active": True, "created_at": now,
        })
        try:
            s = requests.Session()
            r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
            assert r.status_code == 200, r.text
            r = s.get(f"{BASE_URL}/api/dashboard")
            assert r.status_code == 200
            d = r.json()
            secs = d["sections"]
            assert secs.get("sponsor") is False, "collaboratore should not see sponsor"
            assert secs.get("pipeline") is False
            assert "commerciale" not in d
            assert "pipeline_chart" not in d
        finally:
            mongo.users.delete_one({"user_id": uid})
            mongo.memberships.delete_many({"user_id": uid})


# ---------- Dashboard-only user: empty state ----------

class TestDashboardOnlyUser:
    def test_only_dashboard_perm(self, mongo, qa_org_id):
        uid = f"user_{uuid.uuid4().hex[:12]}"
        email = f"test_dashonly_{uuid.uuid4().hex[:6]}@crmeventqa.it"
        pwd = "TestPass123!"
        now = "2026-01-01T00:00:00+00:00"
        mongo.users.insert_one({"user_id": uid, "email": email, "name": "TEST DashOnly",
                                "password_hash": _hash(pwd), "role": "member", "auth_provider": "password",
                                "org_id": qa_org_id, "active": True, "created_at": now, "last_login_at": now})
        sections = {k: [] for k in ("eventi", "aziende", "anagrafiche", "staff", "sponsor",
                                     "attivita", "followup", "ospitalita", "briefing", "mappe", "pipeline")}
        sections["dashboard"] = ["view"]
        mongo.memberships.insert_one({
            "id": f"mem_{uuid.uuid4().hex[:12]}", "user_id": uid, "org_id": qa_org_id,
            "role": "user", "active": True, "created_at": now,
            "permissions": {"sections": sections, "events": "all",
                            "teams": {"scope": "all", "ids": [], "manage_staff": True, "manage_volunteers": True}},
        })
        try:
            s = requests.Session()
            r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
            assert r.status_code == 200
            r = s.get(f"{BASE_URL}/api/dashboard")
            assert r.status_code == 200
            d = r.json()
            # No section blocks should be present
            for k in ("eventi", "crm", "commerciale", "attivita", "staff", "pipeline_chart", "tipo_chart"):
                assert k not in d, f"{k} unexpectedly present: {list(d)}"
            assert d.get("sections", {}).get("eventi") is False
        finally:
            mongo.users.delete_one({"user_id": uid})
            mongo.memberships.delete_many({"user_id": uid})
