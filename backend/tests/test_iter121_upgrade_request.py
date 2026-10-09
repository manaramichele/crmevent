"""Iter121 — Plan upgrade-request flow for internal/test orgs + cliente guards.

Covers:
- POST /api/saas/upgrade-request with invalid plan → 400
- Super Admin flips QA org to type=interna + formula=silver → saas/me shows org_type=interna,
  plan=silver, can_manage_billing=True
- POST /api/saas/upgrade-request with plan='bronze' (lower) → 400
- POST /api/saas/upgrade-request with plan='gold' (higher) → 200, saas.upgrade_request persisted
- saas/me reflects upgrade_request
- /platform/saas/organizations row has upgrade_request for org_qa_eventi
- POST /api/saas/checkout for internal org → 400 (no charges)
- Super Admin PATCH formula=gold → upgrade_request cleared
- Restore QA org to cliente, no formula, no saas.admin, no upgrade_request, trial active
"""
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

QA_ADMIN = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
QA_ORG = "org_qa_eventi"

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def qa():
    s = _login(QA_ADMIN)
    s.headers.update({"X-Org-Id": QA_ORG})
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA)


@pytest.fixture(scope="module", autouse=True)
def _restore_at_end(qa, sa):
    yield
    # Restore QA org to cliente, no formula; also clear saas.admin and upgrade_request directly in DB
    sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}", json={"type": "cliente", "formula": ""})
    db.organizations.update_one({"id": QA_ORG}, {"$unset": {"saas.upgrade_request": "", "saas.admin": ""}})
    # Verify
    o = db.organizations.find_one({"id": QA_ORG})
    assert o.get("type") == "cliente"
    assert not (o.get("saas") or {}).get("upgrade_request")
    assert not (o.get("saas") or {}).get("admin")


def test_a_invalid_plan_returns_400(qa):
    r = qa.post(f"{BASE_URL}/api/saas/upgrade-request", json={"plan": "platinum"})
    assert r.status_code == 400


def test_b_switch_qa_to_internal_silver(qa, sa):
    r = sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}",
                 json={"type": "interna", "formula": "silver"})
    assert r.status_code == 200, r.text
    me = qa.get(f"{BASE_URL}/api/saas/me").json()
    assert me.get("org_type") == "interna"
    assert me.get("plan") == "silver" or me.get("assigned_plan") == "silver"
    assert me.get("can_manage_billing") is True


def test_c_lower_or_equal_plan_rejected(qa):
    # equal
    r = qa.post(f"{BASE_URL}/api/saas/upgrade-request", json={"plan": "silver"})
    assert r.status_code == 400
    # lower
    r = qa.post(f"{BASE_URL}/api/saas/upgrade-request", json={"plan": "bronze"})
    assert r.status_code == 400


def test_d_upgrade_request_gold_ok(qa):
    r = qa.post(f"{BASE_URL}/api/saas/upgrade-request", json={"plan": "gold", "note": "please"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["upgrade_request"]["plan"] == "gold"

    me = qa.get(f"{BASE_URL}/api/saas/me").json()
    assert (me.get("upgrade_request") or {}).get("plan") == "gold"


def test_e_saas_admin_orgs_row_has_upgrade_request(sa):
    rows = sa.get(f"{BASE_URL}/api/platform/saas/organizations").json()
    row = next((r for r in rows if r["id"] == QA_ORG), None)
    assert row is not None
    assert (row.get("upgrade_request") or {}).get("plan") == "gold"


def test_f_internal_checkout_rejected(qa):
    r = qa.post(f"{BASE_URL}/api/saas/checkout",
                json={"plan": "gold", "cycle": "semester", "origin_url": BASE_URL})
    assert r.status_code == 400


def test_g_set_formula_gold_clears_request(qa, sa):
    r = sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}",
                 json={"formula": "gold"})
    assert r.status_code == 200, r.text
    me = qa.get(f"{BASE_URL}/api/saas/me").json()
    assert me.get("plan") == "gold" or me.get("assigned_plan") == "gold"
    assert not me.get("upgrade_request")
