"""Iter122 - Setup/teardown + API checks for Supporto dedicato header button.
Creates 2 TEST_ orgs (bronze/silver via SA formula), verifies /api/saas/me returns
plan + enabled + trial_active correctly for the admin users. Playwright script in
testing agent output covers UI. Teardown deletes both TEST_ orgs."""
import os, uuid, time, pytest, requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PWD = "CrmEvent2026!"

STATE = {}


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, (r.status_code, r.text)
    return s


def _h(_s):
    return {"Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def setup_teardown():
    sa = _login(SA_EMAIL, SA_PWD)
    STATE["sa"] = sa
    tag = uuid.uuid4().hex[:6]
    for plan in ("bronze", "silver"):
        email = f"test_{plan}_{tag}@crmeventqa.it"
        pwd = "TestPass2026!"
        org_name = f"TEST_{plan.upper()}_{tag}"
        r = requests.post(f"{BASE}/api/auth/register-organization", json={
            "nome": "Test", "cognome": plan.capitalize(), "email": email, "password": pwd,
            "org_name": org_name, "telefono": "+393331112222", "accept_terms": True})
        assert r.status_code in (200, 201), (plan, r.status_code, r.text)
        lst = sa.get(f"{BASE}/api/platform/organizations").json()
        items = lst.get("items", lst) if isinstance(lst, dict) else lst
        oid = next(o["id"] for o in items if o.get("nome") == org_name)
        pr = sa.patch(f"{BASE}/api/platform/organizations/{oid}",
                      json={"type": "interna", "formula": plan})
        assert pr.status_code == 200, (plan, pr.status_code, pr.text)
        STATE[plan] = {"email": email, "pwd": pwd, "oid": oid, "org_name": org_name}
    yield
    for plan in ("bronze", "silver"):
        o = STATE.get(plan)
        if not o:
            continue
        try:
            sa.delete(f"{BASE}/api/platform/organizations/{o['oid']}")
        except Exception:
            pass


def test_bronze_saas_me():
    s = _login(STATE["bronze"]["email"], STATE["bronze"]["pwd"])
    me = s.get(f"{BASE}/api/auth/me").json()
    assert me.get("saas", {}).get("plan") == "bronze"
    assert me["saas"]["enabled"] is True
    assert me["saas"].get("trial_active") in (False, None)


def test_silver_saas_me():
    s = _login(STATE["silver"]["email"], STATE["silver"]["pwd"])
    me = s.get(f"{BASE}/api/auth/me").json()
    assert me.get("saas", {}).get("plan") == "silver"
    assert me["saas"]["enabled"] is True
    assert me["saas"].get("trial_active") in (False, None)
