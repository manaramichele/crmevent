"""Test backend sync abbonamenti → Brevo (iter 132)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
QA = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}


@pytest.fixture(scope="module")
def sa_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=SA)
    assert r.status_code == 200, f"SA login: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def qa_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=QA)
    assert r.status_code == 200, f"QA login: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def qa_org_id(qa_session):
    r = qa_session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200, f"auth/me: {r.status_code} {r.text}"
    data = r.json()
    oid = data.get("org_id") or data.get("active_org_id")
    assert oid, f"missing org_id in {data}"
    return oid


class TestOverview:
    def test_overview_sa_ok(self, sa_session):
        r = sa_session.get(f"{BASE_URL}/api/platform/brevo/subscription-sync")
        assert r.status_code == 200
        d = r.json()
        assert d["configured"] is False  # no BREVO_API_KEY in preview
        assert isinstance(d["attributes"], dict)
        for k in ("CRM_PIANO", "CRM_SCADENZA", "CRM_INIZIO", "CRM_DURATA", "CRM_STATO",
                  "CRM_ORGANIZZAZIONE", "CRM_ORG_ID", "CRM_RINNOVO_AUTO"):
            assert k in d["attributes"]
        assert "total_orgs" in d and "synced_ok" in d and "errors" in d and "last_sync_at" in d and "rows" in d

    def test_overview_non_sa_forbidden(self, qa_session):
        r = qa_session.get(f"{BASE_URL}/api/platform/brevo/subscription-sync")
        assert r.status_code == 403


class TestResyncOne:
    def test_resync_qa_org_fails_due_to_no_key(self, sa_session, qa_org_id):
        r = sa_session.post(f"{BASE_URL}/api/platform/brevo/subscription-sync/{qa_org_id}")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert "Brevo non configurato" in (d.get("error") or "")

    def test_row_stored_with_error(self, sa_session, qa_org_id):
        r = sa_session.get(f"{BASE_URL}/api/platform/brevo/subscription-sync")
        rows = r.json()["rows"]
        row = next((x for x in rows if x["org_id"] == qa_org_id), None)
        assert row is not None, "row for QA org not stored"
        assert row["status"] == "error"
        assert row["attrs"]["CRM_ORG_ID"] == qa_org_id
        assert row["attrs"]["CRM_STATO"] == "Trial"
        emails = [r["email"] for r in row["recipients"]]
        assert "qa.eventi@crmeventqa.it" in emails
        assert len(emails) == 1  # only QA admin

    def test_unknown_org_404(self, sa_session):
        r = sa_session.post(f"{BASE_URL}/api/platform/brevo/subscription-sync/does-not-exist-xyz")
        assert r.status_code == 404


class TestResyncAll:
    def test_only_failed(self, sa_session):
        r = sa_session.post(f"{BASE_URL}/api/platform/brevo/subscription-sync", json={"only_failed": True})
        assert r.status_code == 200
        d = r.json()
        assert "total" in d and "ok" in d and "failed" in d and "errors" in d


class TestRegression:
    def test_saas_me(self, qa_session):
        r = qa_session.get(f"{BASE_URL}/api/saas/me")
        assert r.status_code == 200

    def test_cron_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/cron/saas-trial-tick")
        assert r.status_code == 401

    def test_profile_subscription_still_works(self, qa_session):
        # Just reachability of existing endpoints the UI needs
        r = qa_session.get(f"{BASE_URL}/api/saas/me")
        assert r.status_code == 200
