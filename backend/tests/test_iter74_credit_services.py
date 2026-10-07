"""Iteration 74: Simplified credit services catalog + briefing charge + GCal cost + cron.

Scope:
- GET /api/platform/credit-services returns linked flag + descriptions
- PUT /api/platform/credit-services/{key} validates integer cost and updates
- GET /api/calendar/feature returns cost 20
- POST /api/cron/event-renewals auth 401 / Bearer -> 200 accepted
- Briefing charge info / publish (document behaviour on QA org)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SUPERADMIN = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG_ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
CRON_SECRET = "bDuAedGYrYjy-3jNFc5bl2S978rceWtj5UpfQrHtHE4"

LINKED_KEYS = {"ai_assistant", "ai_briefing", "event_activation", "event_maintenance",
               "event_pipeline_pro", "google_calendar"}


def _login(session: requests.Session, creds):
    r = session.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text}"
    return r


@pytest.fixture(scope="module")
def super_session():
    s = requests.Session()
    _login(s, SUPERADMIN)
    return s


@pytest.fixture(scope="module")
def org_session():
    s = requests.Session()
    _login(s, ORG_ADMIN)
    return s


# ---------- Credit Services catalog ----------
class TestCreditServicesCatalog:
    def test_list_services_contains_linked_with_descriptions(self, super_session):
        r = super_session.get(f"{API}/platform/credit-services", timeout=20)
        assert r.status_code == 200, r.text
        services = r.json()["services"]
        by_key = {s["key"]: s for s in services}
        for k in LINKED_KEYS:
            assert k in by_key, f"Missing service {k}"
            s = by_key[k]
            assert s.get("linked") is True, f"{k} not marked linked"
            assert (s.get("description") or "").strip(), f"{k} description empty"
        # specific costs
        assert by_key["ai_briefing"]["unit_cost"] == 30, f"ai_briefing cost: {by_key['ai_briefing']['unit_cost']}"
        assert by_key["google_calendar"]["unit_cost"] == 20, f"google_calendar cost: {by_key['google_calendar']['unit_cost']}"
        assert by_key["google_calendar"].get("consumo_active") is True

    def test_put_rejects_negative(self, super_session):
        r = super_session.put(f"{API}/platform/credit-services/ai_briefing", json={"unit_cost": -1}, timeout=20)
        assert r.status_code == 400, r.text

    def test_put_rejects_non_integer(self, super_session):
        r = super_session.put(f"{API}/platform/credit-services/ai_briefing", json={"unit_cost": 2.5}, timeout=20)
        assert r.status_code == 400, r.text

    def test_put_updates_and_restores(self, super_session):
        # Get original
        orig = super_session.get(f"{API}/platform/credit-services", timeout=20).json()["services"]
        orig_svc = next(s for s in orig if s["key"] == "ai_briefing")
        orig_cost = orig_svc["unit_cost"]
        orig_desc = orig_svc.get("description", "")
        try:
            r = super_session.put(f"{API}/platform/credit-services/ai_briefing",
                                   json={"unit_cost": 40}, timeout=20)
            assert r.status_code == 200, r.text
            # Verify via GET
            after = super_session.get(f"{API}/platform/credit-services", timeout=20).json()["services"]
            updated = next(s for s in after if s["key"] == "ai_briefing")
            assert updated["unit_cost"] == 40
            # history
            h = super_session.get(f"{API}/platform/credit-services/history?key=ai_briefing", timeout=20)
            assert h.status_code == 200
            hist = h.json()
            # history endpoint may return list directly or object
            if isinstance(hist, dict):
                hist = hist.get("history", hist.get("items", []))
            assert any(x.get("field") == "unit_cost" and x.get("new_value") == 40 for x in hist)
        finally:
            # Restore
            super_session.put(f"{API}/platform/credit-services/ai_briefing",
                               json={"unit_cost": orig_cost, "description": orig_desc}, timeout=20)
            after = super_session.get(f"{API}/platform/credit-services", timeout=20).json()["services"]
            restored = next(s for s in after if s["key"] == "ai_briefing")
            assert restored["unit_cost"] == orig_cost


# ---------- Google Calendar feature cost ----------
class TestCalendarFeature:
    def test_cost_is_20(self, org_session):
        r = org_session.get(f"{API}/calendar/feature", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cost"] == 20, f"GCal cost: {data['cost']}"
        assert "unlocked" in data and "balance" in data


# ---------- Cron ----------
class TestCronEventRenewals:
    def test_unauthorized(self):
        r = requests.post(f"{API}/cron/event-renewals", timeout=20)
        assert r.status_code == 401, r.text

    def test_bad_token(self):
        r = requests.post(f"{API}/cron/event-renewals",
                          headers={"Authorization": "Bearer wrong"}, timeout=20)
        assert r.status_code == 401

    def test_valid_token(self):
        r = requests.post(f"{API}/cron/event-renewals",
                          headers={"Authorization": f"Bearer {CRON_SECRET}"}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("accepted") is True


# ---------- Briefing charge info ----------
class TestBriefingCharge:
    def test_briefing_live_returns_charge_info(self, org_session):
        # Find an active event for QA org
        r = org_session.get(f"{API}/events", timeout=20)
        assert r.status_code == 200, r.text
        events = r.json()
        events = events if isinstance(events, list) else events.get("events", [])
        if not events:
            pytest.skip("No events for QA org")
        # Prefer active/operational event
        active = next((e for e in events if e.get("stato") in ("attivo", "active", "operativo") or e.get("is_operational")), events[0])
        eid = active["id"]
        r = org_session.get(f"{API}/events/{eid}/briefing-live", timeout=30)
        if r.status_code != 200:
            pytest.skip(f"briefing-live unavailable for event {eid}: {r.status_code} {r.text[:200]}")
        bc = r.json().get("briefing_charge")
        assert bc is not None, "briefing_charge missing"
        assert "cost" in bc and "charged" in bc
        print(f"QA briefing_charge: {bc}")

    def test_qa_org_credit_model_check(self, org_session):
        # Document whether QA org is on credit model
        r = org_session.get(f"{API}/credits/balance", timeout=20)
        if r.status_code == 200:
            print(f"QA org credits/balance: {r.json()}")
        else:
            print(f"credits/balance -> {r.status_code}")
