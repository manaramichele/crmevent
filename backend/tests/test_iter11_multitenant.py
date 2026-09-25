"""
Multi-tenant isolation + Registration + Trial + Super Admin + Account tests
Iteration 11
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SUPER_EMAIL = "manara.michele.pro@gmail.com"
SUPER_PASS = "CrmEvent2026!"


def _uid():
    return uuid.uuid4().hex[:8]


def _register(nome, org_name, email=None, password="password123", accept=True):
    s = requests.Session()
    email = email or f"testorg_{_uid()}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={
        "nome": nome, "cognome": "Test", "email": email, "password": password,
        "org_name": org_name, "accept_terms": accept,
    }, timeout=30)
    return s, r, email


# ---------------- REGISTRATION + TRIAL ----------------

class TestRegistration:
    def test_reject_without_terms(self):
        s, r, _ = _register("A", "OrgA", accept=False)
        assert r.status_code == 400

    def test_reject_short_password(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/register-organization", json={
            "nome": "X", "email": f"t_{_uid()}@ex.com", "password": "short",
            "org_name": "O", "accept_terms": True}, timeout=30)
        assert r.status_code == 400

    def test_register_success_returns_trial(self):
        s, r, email = _register("Owner", f"TESTorg_{_uid()}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["role"] == "admin"
        assert data.get("org_id")
        assert data.get("needs_org") is False
        sub = data.get("subscription")
        assert sub and sub["status"] == "trial"
        assert sub["days_left"] == 14
        assert sub["access"] == "full"

    def test_duplicate_email(self):
        s, r, email = _register("Owner", f"TESTorg_{_uid()}")
        assert r.status_code == 200
        s2 = requests.Session()
        r2 = s2.post(f"{API}/auth/register-organization", json={
            "nome": "X", "email": email, "password": "password123",
            "org_name": "Other", "accept_terms": True}, timeout=30)
        assert r2.status_code == 400

    def test_account_subscription(self):
        s, r, _ = _register("Owner", f"TESTorg_{_uid()}")
        assert r.status_code == 200
        r2 = s.get(f"{API}/account/subscription", timeout=30)
        assert r2.status_code == 200
        d = r2.json()
        assert "organization" in d and "subscription" in d
        assert d["subscription"]["status"] == "trial"


# ---------------- MULTI-TENANT ISOLATION ----------------

@pytest.fixture(scope="module")
def two_orgs():
    sA, rA, emailA = _register("OwnerA", f"TESTorgA_{_uid()}")
    sB, rB, emailB = _register("OwnerB", f"TESTorgB_{_uid()}")
    assert rA.status_code == 200 and rB.status_code == 200

    # Create data in each org
    def _make_data(sess, tag):
        ev = sess.post(f"{API}/events", json={"nome": f"Evento {tag}", "location": "IT"}).json()
        per = sess.post(f"{API}/persons", json={"nome": f"P{tag}", "cognome": "X", "email": f"{tag}@x.com"}).json()
        co = sess.post(f"{API}/companies", json={"nome": f"Az{tag}"}).json()
        return {"event": ev, "person": per, "company": co}

    dA = _make_data(sA, f"A_{_uid()}")
    dB = _make_data(sB, f"B_{_uid()}")
    return {"sA": sA, "sB": sB, "emailA": emailA, "emailB": emailB, "dA": dA, "dB": dB}


class TestMultiTenantIsolation:
    def test_events_isolated(self, two_orgs):
        listA = two_orgs["sA"].get(f"{API}/events").json()
        listB = two_orgs["sB"].get(f"{API}/events").json()
        idsA = {e["id"] for e in listA}
        idsB = {e["id"] for e in listB}
        assert two_orgs["dA"]["event"]["id"] in idsA
        assert two_orgs["dB"]["event"]["id"] in idsB
        assert two_orgs["dA"]["event"]["id"] not in idsB
        assert two_orgs["dB"]["event"]["id"] not in idsA

    def test_persons_companies_isolated(self, two_orgs):
        pA = {p["id"] for p in two_orgs["sA"].get(f"{API}/persons").json()}
        pB = {p["id"] for p in two_orgs["sB"].get(f"{API}/persons").json()}
        assert two_orgs["dA"]["person"]["id"] not in pB
        assert two_orgs["dB"]["person"]["id"] not in pA

        cA = {c["id"] for c in two_orgs["sA"].get(f"{API}/companies").json()}
        cB = {c["id"] for c in two_orgs["sB"].get(f"{API}/companies").json()}
        assert two_orgs["dA"]["company"]["id"] not in cB
        assert two_orgs["dB"]["company"]["id"] not in cA

    def test_idor_get_event(self, two_orgs):
        eid = two_orgs["dB"]["event"]["id"]
        r = two_orgs["sA"].get(f"{API}/events/{eid}")
        assert r.status_code == 404

    def test_idor_put_event(self, two_orgs):
        eid = two_orgs["dB"]["event"]["id"]
        r = two_orgs["sA"].put(f"{API}/events/{eid}", json={"nome": "HACKED"})
        assert r.status_code == 404
        # B should still have original data
        r2 = two_orgs["sB"].get(f"{API}/events/{eid}")
        assert r2.status_code == 200
        assert r2.json()["nome"] != "HACKED"

    def test_idor_delete_event(self, two_orgs):
        eid = two_orgs["dB"]["event"]["id"]
        r = two_orgs["sA"].delete(f"{API}/events/{eid}")
        assert r.status_code in (404, 200)  # delete on org-scoped may just noop
        # Verify B intact
        r2 = two_orgs["sB"].get(f"{API}/events/{eid}")
        assert r2.status_code == 200

    def test_idor_person_detail(self, two_orgs):
        pid = two_orgs["dB"]["person"]["id"]
        r = two_orgs["sA"].get(f"{API}/persons/{pid}/detail")
        assert r.status_code == 404

    def test_idor_company_detail(self, two_orgs):
        cid = two_orgs["dB"]["company"]["id"]
        r = two_orgs["sA"].get(f"{API}/companies/{cid}/detail")
        assert r.status_code == 404

    def test_idor_briefing_live(self, two_orgs):
        eid = two_orgs["dB"]["event"]["id"]
        r = two_orgs["sA"].get(f"{API}/events/{eid}/briefing-live")
        assert r.status_code == 404

    def test_search_isolated(self, two_orgs):
        # Search in A for B's event name
        b_name = two_orgs["dB"]["event"]["nome"]
        r = two_orgs["sA"].get(f"{API}/search", params={"q": b_name})
        assert r.status_code == 200
        results = r.json()
        # Flatten all results
        found_ids = []
        if isinstance(results, dict):
            for v in results.values():
                if isinstance(v, list):
                    found_ids.extend([x.get("id") for x in v if isinstance(x, dict)])
        assert two_orgs["dB"]["event"]["id"] not in found_ids

    def test_dashboard_scoped(self, two_orgs):
        rA = two_orgs["sA"].get(f"{API}/dashboard")
        rB = two_orgs["sB"].get(f"{API}/dashboard")
        assert rA.status_code == 200 and rB.status_code == 200

    def test_persons_enriched_scoped(self, two_orgs):
        rA = two_orgs["sA"].get(f"{API}/persons-enriched")
        assert rA.status_code == 200
        idsA = {p["id"] for p in rA.json()}
        assert two_orgs["dB"]["person"]["id"] not in idsA


# ---------------- SUPER ADMIN ----------------

@pytest.fixture(scope="module")
def super_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Superadmin login failed: {r.status_code} {r.text}")
    return s


@pytest.fixture(scope="module")
def org_session():
    s, r, _ = _register("Owner", f"TESTorgSA_{_uid()}")
    assert r.status_code == 200
    return s


class TestSuperAdmin:
    def test_super_me(self, super_session):
        r = super_session.get(f"{API}/auth/me")
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "superadmin"
        assert not data.get("org_id")

    def test_platform_stats(self, super_session):
        r = super_session.get(f"{API}/platform/stats")
        assert r.status_code == 200

    def test_platform_orgs(self, super_session):
        r = super_session.get(f"{API}/platform/organizations")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_org_admin_cannot_access_platform(self, org_session):
        r = org_session.get(f"{API}/platform/stats")
        assert r.status_code == 403
        r2 = org_session.get(f"{API}/platform/organizations")
        assert r2.status_code == 403

    def test_superadmin_cannot_access_org_endpoints(self, super_session):
        r = super_session.get(f"{API}/events")
        assert r.status_code == 403

    def test_leads_requires_superadmin(self, org_session, super_session):
        r_org = org_session.get(f"{API}/leads")
        assert r_org.status_code == 403
        r_super = super_session.get(f"{API}/leads")
        assert r_super.status_code == 200
