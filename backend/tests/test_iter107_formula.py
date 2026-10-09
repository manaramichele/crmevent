"""iter107: Formula abbonamento across Cliente/Interna/Test orgs + admin edit guards + checkout guard."""
import json
import os
import pytest
import requests

def _load_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            for line in open("/app/frontend/.env"):
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip().strip('"')
                    break
        except Exception:
            pass
    return (v or "").rstrip("/")


BASE_URL = _load_url()
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PWD = "CrmEvent2026!"
QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PWD = "QaEvents2026!"
QA_ORG = "org_qa_eventi"
INTERNA_ORG = "d91c8d145b8b454ca09962d9d43fcc12"  # Nova Events (interna)
TEST_ORG = "b7f40862230441b9a0bedabefe8dab49"     # Demo (test)


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PWD)


@pytest.fixture(scope="module")
def qa():
    return _login(QA_EMAIL, QA_PWD)


@pytest.fixture(scope="module", autouse=True)
def snapshot_restore(sa):
    # Snapshot QA + internal + test orgs saas / type
    snap = {}
    for oid in (QA_ORG, INTERNA_ORG, TEST_ORG):
        r = sa.get(f"{BASE_URL}/api/platform/organizations/{oid}/detail")
        if r.status_code == 200:
            snap[oid] = r.json()
    yield
    # Restore: clear formula and ensure type correct for QA / internal / test
    # QA org: set type cliente + clear formula
    sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}", json={"type": "cliente", "formula": ""})
    sa.patch(f"{BASE_URL}/api/platform/organizations/{INTERNA_ORG}", json={"type": "interna", "formula": ""})
    sa.patch(f"{BASE_URL}/api/platform/organizations/{TEST_ORG}", json={"type": "test", "formula": ""})
    # Reset saas.admin to no access_end for internal orgs via PUT admin with status auto
    for oid in (INTERNA_ORG, TEST_ORG):
        sa.put(f"{BASE_URL}/api/platform/saas/orgs/{oid}/admin",
               json={"status": "auto", "comp": False})


# ---------- GET /api/platform/saas/organizations ----------
class TestAdminOrgsList:
    def test_lists_all_including_internal_test(self, sa):
        r = sa.get(f"{BASE_URL}/api/platform/saas/organizations")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        types_present = {o["type"] for o in rows}
        assert "cliente" in types_present
        assert "interna" in types_present
        assert "test" in types_present
        # internal orgs always 'abbonamento'
        for o in rows:
            if o["type"] in ("interna", "test"):
                assert o["model"] == "abbonamento", f"{o['nome']} model={o['model']}"
                assert "billing" in o


# ---------- PATCH formula on Interna/Test ----------
class TestFormulaInternal:
    def test_set_gold_on_interna(self, sa):
        r = sa.patch(f"{BASE_URL}/api/platform/organizations/{INTERNA_ORG}",
                     json={"formula": "gold"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["formula"] == "gold"
        assert d["saas"]["mode"] == "active"
        assert d["saas"]["plan"] == "gold"
        assert d["saas"]["billing"] == "free"
        assert d["saas"].get("trial_active") is False
        assert d["saas"].get("expires_at") in (None, "", False) or d["saas"]["expires_at"] is None

    def test_clear_formula_on_interna(self, sa):
        r = sa.patch(f"{BASE_URL}/api/platform/organizations/{INTERNA_ORG}",
                     json={"formula": ""})
        assert r.status_code == 200
        d = r.json()
        assert d["formula"] in (None, "")
        # enabled false -> no gating
        assert d["saas"].get("enabled") is False

    def test_set_silver_on_test(self, sa):
        r = sa.patch(f"{BASE_URL}/api/platform/organizations/{TEST_ORG}",
                     json={"formula": "silver"})
        assert r.status_code == 200
        d = r.json()
        assert d["formula"] == "silver"
        assert d["saas"]["plan"] == "silver"
        assert d["saas"]["billing"] == "free"


# ---------- PATCH formula on Cliente ----------
class TestFormulaCliente:
    def test_silver_then_clear(self, sa):
        r = sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}",
                     json={"formula": "silver"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["formula"] == "silver"
        assert d["saas"]["plan"] == "silver"
        assert d["saas"]["mode"] == "active"
        # cliente not comp -> billing paid
        assert d["saas"]["billing"] in ("paid", "free")  # free only if comp manually set

        r2 = sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}",
                      json={"formula": ""})
        assert r2.status_code == 200
        d2 = r2.json()
        # Back to trial since trial_end future
        assert d2["formula"] in (None, "")


# ---------- PUT admin on internal orgs ----------
class TestAdminEditInternal:
    def test_set_access_end_future(self, sa):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{INTERNA_ORG}/admin",
                   json={"status": "active", "plan": "gold",
                         "access_end": "2027-12-31T23:59:59+00:00", "comp": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["mode"] == "active"
        assert d["plan"] == "gold"

    def test_reject_trial_status_internal(self, sa):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{INTERNA_ORG}/admin",
                   json={"status": "trial"})
        assert r.status_code == 400

    def test_reject_trial_dates_internal(self, sa):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{INTERNA_ORG}/admin",
                   json={"status": "auto", "trial_end": "2027-01-01T00:00:00+00:00"})
        assert r.status_code == 400

    def test_access_end_past_mode_expired(self, sa):
        r = sa.put(f"{BASE_URL}/api/platform/saas/orgs/{INTERNA_ORG}/admin",
                   json={"status": "active", "plan": "gold",
                         "access_end": "2020-01-01T00:00:00+00:00", "comp": True})
        assert r.status_code == 200
        assert r.json()["mode"] == "expired"


# ---------- Non-superadmin forbidden ----------
class TestForbidden:
    def test_patch_org_as_qa(self, qa):
        r = qa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}",
                     json={"formula": "gold"})
        assert r.status_code == 403

    def test_put_saas_admin_as_qa(self, qa):
        r = qa.put(f"{BASE_URL}/api/platform/saas/orgs/{QA_ORG}/admin",
                   json={"status": "auto"})
        assert r.status_code == 403


# ---------- Checkout guard: internal org admin cannot checkout ----------
class TestCheckoutGuard:
    def test_internal_org_checkout_rejected(self, sa, qa):
        # Set QA org temporarily to interna
        r0 = sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}",
                      json={"type": "interna"})
        assert r0.status_code == 200
        try:
            r = qa.post(f"{BASE_URL}/api/saas/checkout",
                        json={"plan": "silver", "cycle": "monthly",
                              "origin_url": BASE_URL})
            assert r.status_code == 400, r.text
            body = r.json()
            # error message mentions internal/no payment
            msg = json.dumps(body).lower()
            assert "interna" in msg or "pagamento" in msg or "formula" in msg
        finally:
            sa.patch(f"{BASE_URL}/api/platform/organizations/{QA_ORG}",
                     json={"type": "cliente"})
