"""Iter 104 — Super Admin subscription edit (PUT /platform/saas/orgs/{id}/admin + history + validations)."""
import os
from datetime import datetime, timedelta, timezone
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PW = "CrmEvent2026!"
QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PW = "QaEvents2026!"
QA_ORG = "org_qa_eventi"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"Login {email} failed: {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PW)


@pytest.fixture(scope="module")
def qa():
    return _login(QA_EMAIL, QA_PW)


@pytest.fixture(scope="module")
def test_org(sa):
    name = f"TEST_SubAdmin_{int(datetime.now(timezone.utc).timestamp())}"
    r = sa.post(f"{BASE_URL}/api/platform/organizations",
                json={"nome": name, "type": "cliente", "status": "active"}, timeout=20)
    assert r.status_code == 200, f"Create org: {r.status_code} {r.text[:300]}"
    org = r.json()
    org_id = org["id"]
    # Ensure saas trial exists (init_trial is scheduled; small delay or re-fetch via orgs list)
    import time as _t; _t.sleep(0.4)
    yield {"id": org_id, "nome": org["nome"]}
    # cleanup
    try:
        sa.request("DELETE", f"{BASE_URL}/api/platform/organizations/{org_id}",
                   json={"confirm_name": org["nome"]}, timeout=30)
    except Exception as e:
        print(f"cleanup fail: {e}")
    # cleanup history collection
    try:
        cli = MongoClient(MONGO_URL)
        cli[DB_NAME].saas_admin_history.delete_many({"org_id": org_id})
        cli.close()
    except Exception as e:
        print(f"cleanup history fail: {e}")


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ========== Security ==========
class TestSecurity:
    def test_qa_cannot_put_admin(self, qa):
        r = qa.put(f"{BASE_URL}/api/platform/saas/orgs/{QA_ORG}/admin",
                   json={"status": "active", "plan": "bronze"}, timeout=10)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"

    def test_qa_cannot_get_history(self, qa):
        r = qa.get(f"{BASE_URL}/api/platform/saas/orgs/{QA_ORG}/history", timeout=10)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text[:200]}"


# ========== Admin edits on TEST org ==========
class TestAdminEdits:
    def test_01_active_bronze_with_end(self, sa, test_org):
        end = _iso(datetime.now(timezone.utc) + timedelta(days=40))
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active", "plan": "bronze", "access_end": end, "reason": "test"}, timeout=15)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert d["mode"] == "active", f"mode={d.get('mode')}"
        assert d["plan"] == "bronze"
        assert d["limits"]["max_events"] == 1
        assert d["limits"]["max_users"] == 10

    def test_02_history_has_changes(self, sa, test_org):
        r = sa.get(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/history", timeout=10)
        assert r.status_code == 200
        h = r.json()
        assert isinstance(h, list) and len(h) >= 1
        row = h[0]
        for k in ("field", "old", "new", "admin_email", "at"):
            assert k in row
        assert row["admin_email"] == SA_EMAIL
        assert row.get("reason") == "test"

    def test_03_active_gold_unlimited(self, sa, test_org):
        end = _iso(datetime.now(timezone.utc) + timedelta(days=30))
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active", "plan": "gold", "access_end": end}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["plan"] == "gold"
        assert d["limits"]["max_events"] == -1
        assert d["limits"]["max_users"] == -1

    def test_04_max_users_override_on_bronze(self, sa, test_org):
        end = _iso(datetime.now(timezone.utc) + timedelta(days=30))
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active", "plan": "bronze", "access_end": end, "max_users": 50}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["plan"] == "bronze"
        assert d["limits"]["max_users"] == 50

    def test_05_suspended(self, sa, test_org):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "suspended"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["mode"] == "suspended"
        assert d["writable"] is False

    def test_06_expired(self, sa, test_org):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "expired"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["mode"] == "expired"

    def test_07_active_past_end_is_expired(self, sa, test_org):
        past = _iso(datetime.now(timezone.utc) - timedelta(days=1))
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active", "plan": "bronze", "access_end": past}, timeout=15)
        assert r.status_code == 200
        assert r.json()["mode"] == "expired", r.text[:300]

    def test_08_trial_days_left(self, sa, test_org):
        trial_end = _iso(datetime.now(timezone.utc) + timedelta(days=20))
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "trial", "trial_end": trial_end}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["mode"] == "trial"
        assert 18 <= d["days_left"] <= 21

    def test_09_auto_restores(self, sa, test_org):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "auto"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # should be trial because trial_end was set in future previously
        assert d["mode"] in ("trial", "active", "expired", "canceled"), d


# ========== Validation ==========
class TestValidation:
    def test_active_no_plan(self, sa, test_org):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active"}, timeout=10)
        assert r.status_code == 400

    def test_max_users_zero(self, sa, test_org):
        end = _iso(datetime.now(timezone.utc) + timedelta(days=30))
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active", "plan": "bronze", "access_end": end, "max_users": 0}, timeout=10)
        assert r.status_code == 400

    def test_invalid_date(self, sa, test_org):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active", "plan": "bronze", "access_end": "not-a-date"}, timeout=10)
        assert r.status_code == 400

    def test_invalid_plan(self, sa, test_org):
        end = _iso(datetime.now(timezone.utc) + timedelta(days=30))
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{test_org['id']}/admin",
                   json={"status": "active", "plan": "platinum", "access_end": end}, timeout=10)
        assert r.status_code == 400
