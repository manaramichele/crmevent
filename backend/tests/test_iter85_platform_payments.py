"""Tests for Iteration 85: platform payments & credits endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
QA = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return s


@pytest.fixture(scope="module")
def sa_session():
    return _login(SA)


@pytest.fixture(scope="module")
def qa_session():
    return _login(QA)


# ----- GET /api/platform/payments -----
class TestPlatformPaymentsGet:
    def test_sa_access(self, sa_session):
        r = sa_session.get(f"{API}/platform/payments", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        # sorted A-Z case insensitive
        names = [(x.get("nome") or "").lower() for x in data]
        assert names == sorted(names), f"not sorted A-Z: {names}"
        # schema
        for row in data:
            assert "id" in row and "nome" in row and "tipo" in row
            assert row["tipo"] in {"Cliente", "Trial", "Test", "Interna"}
            assert "balance" in row
            assert "last_purchase" in row
            assert "invoice" in row

    def test_qa_forbidden(self, qa_session):
        r = qa_session.get(f"{API}/platform/payments", timeout=20)
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# ----- POST /api/platform/payments/refresh -----
class TestPlatformPaymentsRefresh:
    def test_qa_forbidden(self, qa_session):
        r = qa_session.post(f"{API}/platform/payments/refresh", json={}, timeout=20)
        assert r.status_code == 403

    def test_refresh_single_org_no_mutation(self, sa_session):
        # Pick first org from list
        orgs = sa_session.get(f"{API}/platform/payments").json()
        assert orgs
        oid = orgs[0]["id"]

        # Snapshot balances & counts for all orgs
        before_rows = sa_session.get(f"{API}/platform/payments").json()
        before_balances = {o["id"]: o.get("balance", 0) for o in before_rows}

        r = sa_session.post(f"{API}/platform/payments/refresh", json={"org_id": oid}, timeout=60)
        assert r.status_code == 200, r.text
        tot = r.json()
        assert "stripe_checked" in tot and "fic_checked" in tot and "errors" in tot
        assert tot["orgs"] == 1

        after_rows = sa_session.get(f"{API}/platform/payments").json()
        after_balances = {o["id"]: o.get("balance", 0) for o in after_rows}
        assert before_balances == after_balances, "credits balance changed after refresh (should be read-only)"

    def test_refresh_all_orgs_no_mutation(self, sa_session):
        before_rows = sa_session.get(f"{API}/platform/payments").json()
        before_balances = {o["id"]: o.get("balance", 0) for o in before_rows}
        before_purchases_total = sum(o.get("purchases_paid", 0) for o in before_rows)

        r = sa_session.post(f"{API}/platform/payments/refresh", json={}, timeout=180)
        assert r.status_code == 200, r.text
        tot = r.json()
        assert tot["orgs"] >= 1

        after_rows = sa_session.get(f"{API}/platform/payments").json()
        after_balances = {o["id"]: o.get("balance", 0) for o in after_rows}
        after_purchases_total = sum(o.get("purchases_paid", 0) for o in after_rows)

        assert before_balances == after_balances, "balances changed after bulk refresh"
        assert before_purchases_total == after_purchases_total, "paid purchases count changed"
