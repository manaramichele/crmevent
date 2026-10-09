"""Iter106 - Subscription plan badges (GOLD/SILVER/BRONZE) + expires_at in /saas/me and /platform/saas/organizations.

Tests Super Admin editing QA org admin.{status,plan,access_end} and verifies:
- GET /api/saas/me returns correct {mode, plan, plan_label, expires_at}
- GET /api/platform/saas/organizations rows include expires_at
- Restores original QA org admin state at the end.
"""
import copy
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PWD = "QaEvents2026!"
QA_ORG_ID = "org_qa_eventi"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PWD = "CrmEvent2026!"

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def _login(email, pwd, org_id=None):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    if org_id:
        s.headers.update({"X-Org-Id": org_id})
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PWD)


@pytest.fixture(scope="module")
def qa():
    return _login(QA_EMAIL, QA_PWD, QA_ORG_ID)


@pytest.fixture(scope="module", autouse=True)
def snapshot_and_restore():
    """Record QA org saas doc & restore after module."""
    before = db.organizations.find_one({"id": QA_ORG_ID}, {"_id": 0, "saas": 1})
    snap = copy.deepcopy((before or {}).get("saas") or {})
    print(f"\n[iter106] original saas.admin={snap.get('admin')} trial_end={snap.get('trial_end')}")
    yield snap
    # Restore
    db.organizations.update_one({"id": QA_ORG_ID}, {"$set": {"saas": snap}})
    print(f"[iter106] restored saas for {QA_ORG_ID}")


def _set_admin(sa_session, payload):
    r = sa_session.put(f"{BASE_URL}/api/platform/saas/orgs/{QA_ORG_ID}/admin", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _me(qa_session):
    r = qa_session.get(f"{BASE_URL}/api/saas/me")
    assert r.status_code == 200, r.text
    return r.json()


def _orgs_row(sa_session):
    r = sa_session.get(f"{BASE_URL}/api/platform/saas/organizations")
    assert r.status_code == 200, r.text
    for row in r.json():
        if row["id"] == QA_ORG_ID:
            return row
    raise AssertionError("QA org not found in platform list")


# ---- active gold / silver / bronze ----
@pytest.mark.parametrize("plan,label", [("gold", "GOLD"), ("silver", "SILVER"), ("bronze", "BRONZE")])
def test_admin_active_plan_sets_mode_and_expiry(sa, qa, plan, label):
    _set_admin(sa, {"status": "active", "plan": plan, "access_end": "2027-03-07T00:00:00+00:00"})
    me = _me(qa)
    assert me["mode"] == "active", f"mode={me['mode']}"
    assert me["plan"] == plan
    assert me["plan_label"] == label
    assert me.get("expires_at", "").startswith("2027-03-07"), f"expires_at={me.get('expires_at')}"
    row = _orgs_row(sa)
    assert row["mode"] == "active"
    assert row["plan"] == plan
    assert row.get("expires_at", "").startswith("2027-03-07")


def test_admin_trial_status(sa, qa):
    # Reset admin to trial, with trial_end in the future
    _set_admin(sa, {"status": "trial", "trial_end": "2099-01-01T00:00:00+00:00"})
    me = _me(qa)
    assert me["mode"] == "trial", f"mode={me['mode']}"
    assert me["trial_active"] is True
    # expires_at = trial_end
    assert me["expires_at"].startswith("2099-01-01"), me["expires_at"]


def test_admin_expired(sa, qa):
    _set_admin(sa, {"status": "expired", "access_end": "2020-01-01T00:00:00+00:00"})
    me = _me(qa)
    assert me["mode"] == "expired"
    assert me["plan"] in (None, "")
    # expires_at should fall back to last known end (admin.access_end)
    assert me["expires_at"] and me["expires_at"].startswith("2020-01-01"), me["expires_at"]


def test_admin_suspended(sa, qa):
    _set_admin(sa, {"status": "suspended", "access_end": "2020-01-01T00:00:00+00:00"})
    me = _me(qa)
    assert me["mode"] == "suspended"
    assert me["plan"] in (None, "")
    assert me["expires_at"] and me["expires_at"].startswith("2020-01-01")


def test_orgs_table_includes_expires_at(sa):
    _set_admin(sa, {"status": "active", "plan": "silver", "access_end": "2027-03-07T00:00:00+00:00"})
    row = _orgs_row(sa)
    assert "expires_at" in row
    assert row["expires_at"].startswith("2027-03-07")
    assert row["plan"] == "silver"
    assert row["plan_label"] == "SILVER"
