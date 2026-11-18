# Plan picker recommendation iteration: catalog, /saas/me usage, /saas/checkout over-limits guard
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
PWD = "TestPlan2026!"
BILLING = {"tipo": "azienda", "paese": "IT", "ragione_sociale": "TEST_PLAN Srl", "partita_iva": "01234567890",
           "indirizzo": "Via Roma 1", "cap": "00100", "citta": "Roma", "provincia": "RM", "codice_sdi": "0000000",
           "email_fatturazione": "test_plan_billing@example.com"}


@pytest.fixture(scope="module")
def org():
    email = f"test_plan_api_{int(time.time())}@example.com"
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "Test", "cognome": "Plan", "email": email, "password": PWD,
        "org_name": f"TEST_PLAN API {int(time.time())}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    if not s.cookies:
        lr = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD})
        assert lr.status_code == 200, lr.text
    print("CREATED ORG USER", email)
    return {"s": s, "email": email}


def test_plans_catalog():
    r = requests.get(f"{BASE_URL}/api/saas/plans-public")
    assert r.status_code == 200
    plans = {p["key"]: p for p in r.json()["plans"]}
    assert set(plans) >= {"bronze", "silver", "gold"}
    for k, p in plans.items():
        print(k, {x: p.get(x) for x in ("monthly", "semester", "yearly", "max_events", "max_users", "color")})
    assert plans["bronze"]["max_events"] == 1


def test_me_usage_fresh(org):
    r = org["s"].get(f"{BASE_URL}/api/saas/me")
    assert r.status_code == 200, r.text
    d = r.json()
    print("ME", {k: d.get(k) for k in ("mode", "plan", "billing", "purchased", "org_type", "billing_cycle", "usage")})
    assert d["usage"]["events"] == 0
    assert d["usage"]["people"] == 0


def test_checkout_billing_missing_first(org):
    r = org["s"].post(f"{BASE_URL}/api/saas/checkout", json={"plan": "bronze", "cycle": "yearly", "origin_url": BASE_URL})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "billing_missing"


def test_fill_billing(org):
    r = org["s"].put(f"{BASE_URL}/api/account/billing", json=BILLING)
    assert r.status_code == 200, r.text


def test_checkout_bronze_ok_with_zero_usage(org):
    r = org["s"].post(f"{BASE_URL}/api/saas/checkout", json={"plan": "bronze", "cycle": "semester", "origin_url": BASE_URL})
    print("bronze0", r.status_code, r.text[:200])
    assert r.status_code == 200, r.text
    assert "checkout.stripe.com" in r.json()["checkout_url"]


def test_create_two_events(org):
    ids = []
    for i in range(2):
        r = org["s"].post(f"{BASE_URL}/api/events", json={"nome": f"TEST_PLAN evento {i}"})
        print("event", r.status_code, r.text[:200])
        assert r.status_code in (200, 201), r.text
        ids.append(r.json().get("id"))
    org["events"] = ids
    me = org["s"].get(f"{BASE_URL}/api/saas/me").json()
    assert me["usage"]["events"] == 2


@pytest.mark.parametrize("cycle", ["semester", "yearly"])
def test_checkout_bronze_rejected_over_limits(org, cycle):
    r = org["s"].post(f"{BASE_URL}/api/saas/checkout", json={"plan": "bronze", "cycle": cycle, "origin_url": BASE_URL})
    print("bronze2", r.status_code, r.text)
    assert r.status_code == 400
    det = r.json()["detail"]
    assert isinstance(det, str)
    assert det.startswith("Il piano BRONZE non copre il tuo utilizzo attuale")
    assert "2 eventi (max 1)" in det


def test_checkout_silver_allowed_with_two_events(org):
    r = org["s"].post(f"{BASE_URL}/api/saas/checkout", json={"plan": "silver", "cycle": "yearly", "origin_url": BASE_URL})
    print("silver2", r.status_code, r.text[:200])
    assert r.status_code == 200, r.text
    assert r.json()["checkout_url"]


def test_checkout_invalid_plan(org):
    r = org["s"].post(f"{BASE_URL}/api/saas/checkout", json={"plan": "platinum", "cycle": "yearly", "origin_url": BASE_URL})
    assert r.status_code in (400, 422)
