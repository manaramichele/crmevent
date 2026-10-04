"""
Iteration 12 tests: Super Admin operational navigation with X-Org-Id header
Multi-tenant scoping and role-based access control.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")

SUPER = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG = {"email": "organizer.test@crmevent.it", "password": "Organizer2026!"}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def super_session():
    return _login(SUPER["email"], SUPER["password"])


@pytest.fixture(scope="module")
def org_session():
    return _login(ORG["email"], ORG["password"])


@pytest.fixture(scope="module")
def eventi_milano_id(super_session):
    r = super_session.get(f"{BASE_URL}/api/platform/organizations", timeout=15)
    assert r.status_code == 200, r.text
    orgs = r.json()
    milano = next((o for o in orgs if "Milano" in o.get("nome", "")), orgs[0] if orgs else None)
    assert milano, "No organizations found"
    return milano["id"]


# ---------- Super Admin: require_admin with X-Org-Id ----------
class TestSuperAdminOrgScoping:
    def test_dashboard_no_header_returns_428(self, super_session):
        r = super_session.get(f"{BASE_URL}/api/dashboard", timeout=15)
        assert r.status_code == 428, f"expected 428, got {r.status_code}: {r.text}"

    def test_dashboard_invalid_org_returns_404(self, super_session):
        r = super_session.get(f"{BASE_URL}/api/dashboard",
                              headers={"X-Org-Id": "nonexistent-id-12345"}, timeout=15)
        assert r.status_code == 404

    def test_dashboard_valid_org_returns_200(self, super_session, eventi_milano_id):
        r = super_session.get(f"{BASE_URL}/api/dashboard",
                              headers={"X-Org-Id": eventi_milano_id}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # dashboard returns some structured data (event count, etc.)
        assert isinstance(data, dict)

    def test_operational_endpoints_with_valid_org(self, super_session, eventi_milano_id):
        headers = {"X-Org-Id": eventi_milano_id}
        for path in ["/api/events", "/api/companies", "/api/persons", "/api/activities", "/api/followups"]:
            r = super_session.get(f"{BASE_URL}{path}", headers=headers, timeout=15)
            assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
            assert isinstance(r.json(), list)

    def test_operational_endpoint_without_header_428(self, super_session):
        r = super_session.get(f"{BASE_URL}/api/events", timeout=15)
        assert r.status_code == 428

    # ---------- Super Admin: superadmin endpoints reachable regardless of org ----------
    def test_platform_stats_ok(self, super_session):
        r = super_session.get(f"{BASE_URL}/api/platform/stats", timeout=15)
        assert r.status_code == 200

    def test_platform_organizations_ok(self, super_session):
        r = super_session.get(f"{BASE_URL}/api/platform/organizations", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Organizer: normal operational access + blocked from platform ----------
class TestOrganizerAccess:
    def test_dashboard_no_header_ok(self, org_session):
        r = org_session.get(f"{BASE_URL}/api/dashboard", timeout=15)
        assert r.status_code == 200, r.text

    def test_events_ok(self, org_session):
        r = org_session.get(f"{BASE_URL}/api/events", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_organizer_blocked_platform_orgs(self, org_session):
        r = org_session.get(f"{BASE_URL}/api/platform/organizations", timeout=15)
        assert r.status_code == 403

    def test_organizer_blocked_platform_stats(self, org_session):
        r = org_session.get(f"{BASE_URL}/api/platform/stats", timeout=15)
        assert r.status_code == 403

    def test_organizer_blocked_fic_status(self, org_session):
        r = org_session.get(f"{BASE_URL}/api/fic/status", timeout=15)
        assert r.status_code == 403


# ---------- Cross-tenant safety: superadmin scoped, cannot see other org's data via oq ----------
class TestScopingIsolation:
    def test_superadmin_scoping_by_org(self, super_session, eventi_milano_id):
        # Same events list must be reachable only via org header — verified above.
        # Assert that persons list length matches org scope (no bleed): should be a list, not raise
        r = super_session.get(f"{BASE_URL}/api/persons", headers={"X-Org-Id": eventi_milano_id}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        for p in data:
            # All persons should belong to the acting org
            assert p.get("org_id") in (None, eventi_milano_id), f"cross-tenant leak: {p.get('org_id')}"
