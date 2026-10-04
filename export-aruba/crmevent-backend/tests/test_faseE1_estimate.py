"""Fase E.1 UI transparency: /credits/estimate returns cost/balance/consumo_active for ai_content;
   Google Calendar available but consumo OFF; Super Admin can PUT consumo_active on credit-services."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ORG_ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
SUPER_ADMIN = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}


@pytest.fixture
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ORG_ADMIN)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture
def super_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SUPER_ADMIN)
    assert r.status_code == 200, r.text
    return s


def test_estimate_ai_content(admin_session):
    r = admin_session.post(f"{API}/credits/estimate", json={"service_key": "ai_content", "quantity": 1})
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ["cost", "effective_cost", "will_charge", "available", "consumo_active", "balance", "sufficient"]:
        assert k in d, f"missing {k}"
    assert d["cost"] == 2
    assert d["will_charge"] is True
    assert d["consumo_active"] is True
    assert d["available"] is True
    assert isinstance(d["balance"], int)


def test_estimate_google_calendar_free(admin_session):
    r = admin_session.post(f"{API}/credits/estimate", json={"service_key": "google_calendar", "quantity": 1})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["available"] is True
    assert d["consumo_active"] is False
    assert d["will_charge"] is False
    assert d["effective_cost"] == 0


def test_credit_services_list_has_consumo_active(super_session):
    r = super_session.get(f"{API}/platform/credit-services")
    assert r.status_code == 200
    body = r.json()
    lst = body.get("services") if isinstance(body, dict) else body
    svcs = {s["key"]: s for s in lst}
    assert "ai_content" in svcs
    assert "google_calendar" in svcs
    assert svcs["ai_content"].get("active") is True
    # ai_content should have consumo_active True
    ai = svcs["ai_content"]
    assert ai.get("consumo_active") is True or (ai.get("consumo_active") is None and ai.get("active"))
    # google_calendar available but consumo off
    gc = svcs["google_calendar"]
    assert gc.get("active") is True
    assert gc.get("consumo_active") is False


def test_super_admin_toggle_consumo_active(super_session):
    # snapshot
    r = super_session.get(f"{API}/platform/credit-services")
    body = r.json()
    lst = body.get("services") if isinstance(body, dict) else body
    ai_orig = next(s for s in lst if s["key"] == "ai_content")

    # turn consumo OFF
    r = super_session.put(f"{API}/platform/credit-services/ai_content", json={"consumo_active": False})
    assert r.status_code == 200, r.text

    # estimate for org admin -> will_charge False
    s2 = requests.Session()
    assert s2.post(f"{API}/auth/login", json=ORG_ADMIN).status_code == 200
    d = s2.post(f"{API}/credits/estimate", json={"service_key": "ai_content"}).json()
    assert d["will_charge"] is False
    assert d["consumo_active"] is False
    assert d["available"] is True

    # restore
    r = super_session.put(f"{API}/platform/credit-services/ai_content",
                          json={"consumo_active": True, "unit_cost": ai_orig["unit_cost"]})
    assert r.status_code == 200


def test_super_admin_cost_change_reflects_in_estimate(super_session):
    # change cost 2 -> 3
    r = super_session.put(f"{API}/platform/credit-services/ai_content", json={"unit_cost": 3})
    assert r.status_code == 200
    try:
        s2 = requests.Session()
        assert s2.post(f"{API}/auth/login", json=ORG_ADMIN).status_code == 200
        d = s2.post(f"{API}/credits/estimate", json={"service_key": "ai_content"}).json()
        assert d["cost"] == 3
    finally:
        # restore to 2
        r = super_session.put(f"{API}/platform/credit-services/ai_content", json={"unit_cost": 2})
        assert r.status_code == 200
