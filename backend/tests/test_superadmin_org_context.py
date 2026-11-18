# Super Admin operating in selected org via X-Org-Id (ASD module, isolation, platform, normal org user)
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SUPER = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
NOVA = "d91c8d145b8b454ca09962d9d43fcc12"
DEMO = "b7f40862230441b9a0bedabefe8dab49"
MILANO = "50cae9fa307445f3b21ff4ce74c54b29"


@pytest.fixture(scope="module")
def su():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SUPER[0], "password": SUPER[1]})
    if r.status_code != 200:
        pytest.skip("super login failed")
    return s


def H(o):
    return {"X-Org-Id": o}


@pytest.fixture(scope="module")
def created(su):
    items = []
    yield items
    for path, iid in reversed(items):
        su.delete(f"{BASE_URL}/api/asd/{path}/{iid}", headers=H(NOVA))


# --- ASD status per org for Super Admin
class TestStatus:
    def test_nova_active_can_delete(self, su):
        d = su.get(f"{BASE_URL}/api/asd/status", headers=H(NOVA)).json()
        assert d["active"] is True and d["can_delete"] is True

    def test_demo_inactive(self, su):
        assert su.get(f"{BASE_URL}/api/asd/status", headers=H(DEMO)).json()["active"] is False

    def test_milano_inactive(self, su):
        assert su.get(f"{BASE_URL}/api/asd/status", headers=H(MILANO)).json()["active"] is False

    def test_no_header_428(self, su):
        assert su.get(f"{BASE_URL}/api/asd/soci").status_code == 428

    def test_bad_org_404(self, su):
        assert su.get(f"{BASE_URL}/api/asd/soci", headers=H("nonexistent_org_x")).status_code == 404


# --- CRUD as Super Admin in Nova, isolation vs Demo/Milano
class TestCrudIsolation:
    def test_flow(self, su, created):
        before = su.get(f"{BASE_URL}/api/asd/dashboard", headers=H(NOVA)).json()
        cog = "TEST_SAC" + uuid.uuid4().hex[:5]
        r = su.post(f"{BASE_URL}/api/asd/soci", headers=H(NOVA), json={"nome": "TEST_Super", "cognome": cog})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        created.append(("soci", sid))
        assert r.json()["org_id"] == NOVA
        q = su.post(f"{BASE_URL}/api/asd/quote", headers=H(NOVA), json={"socio_id": sid, "descrizione": "TEST_quota", "importo": 50, "data_pagamento": "2026-01-10", "metodo": "contanti"})
        assert q.status_code == 200, q.text
        created.append(("quote", q.json()["id"]))
        q2 = su.post(f"{BASE_URL}/api/asd/quote", headers=H(NOVA), json={"socio_id": sid, "descrizione": "TEST_quota2", "importo": 30})
        assert q2.status_code == 200
        created.append(("quote", q2.json()["id"]))
        after = su.get(f"{BASE_URL}/api/asd/dashboard", headers=H(NOVA)).json()
        assert after["soci_totali"] == before["soci_totali"] + 1
        assert round(after["quote_incassate"] - before["quote_incassate"], 2) == 50
        assert round(after["quote_da_incassare"] - before["quote_da_incassare"], 2) == 30
        soci = su.get(f"{BASE_URL}/api/asd/soci", headers=H(NOVA)).json()
        lst = soci if isinstance(soci, list) else soci.get("items", soci.get("soci", []))
        assert any(x["id"] == sid for x in lst)
        # other orgs: 403, and no leakage
        for o in (DEMO, MILANO):
            assert su.get(f"{BASE_URL}/api/asd/soci", headers=H(o)).status_code == 403
            assert su.get(f"{BASE_URL}/api/asd/dashboard", headers=H(o)).status_code == 403
            assert su.delete(f"{BASE_URL}/api/asd/quote/{q.json()['id']}", headers=H(o)).status_code == 403
            assert su.post(f"{BASE_URL}/api/asd/soci", headers=H(o), json={"nome": "x", "cognome": "y"}).status_code == 403
        # delete as superadmin
        assert su.delete(f"{BASE_URL}/api/asd/quote/{q2.json()['id']}", headers=H(NOVA)).status_code == 200
        created.remove(("quote", q2.json()["id"]))
        test_flow_ids.update(sid=sid, qid=q.json()["id"])


test_flow_ids = {}


# --- Platform endpoints accessible whatever org
class TestPlatform:
    @pytest.mark.parametrize("org", [NOVA, DEMO, MILANO])
    def test_platform_orgs(self, su, org):
        r = su.get(f"{BASE_URL}/api/platform/organizations", headers=H(org))
        assert r.status_code == 200 and len(r.json()) > 0

    def test_saas_me(self, su):
        for o in (NOVA, DEMO, MILANO):
            assert su.get(f"{BASE_URL}/api/saas/me", headers=H(o)).status_code == 200


# --- Normal org user unaffected
class TestNormalUser:
    def test_register_org_inactive(self, su):
        em = f"test_sac_{uuid.uuid4().hex[:8]}@example.com"
        org_name = "TEST_SAC " + uuid.uuid4().hex[:6]
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/register-organization", json={"nome": "Test", "cognome": "Sac", "email": em, "password": "TestSac2026!",
                                                                     "org_name": org_name, "telefono": "+393331234567", "accept_terms": True})
        assert r.status_code == 200, r.text
        me = s.get(f"{BASE_URL}/api/auth/me").json()
        oid = me.get("org_id")
        assert oid
        try:
            st = s.get(f"{BASE_URL}/api/asd/status").json()
            assert st["active"] is False
            assert s.get(f"{BASE_URL}/api/asd/soci").status_code == 403
            # normal user cannot pivot to Nova via header
            assert s.get(f"{BASE_URL}/api/asd/soci", headers=H(NOVA)).status_code == 403
            assert s.get(f"{BASE_URL}/api/platform/organizations").status_code in (401, 403)
        finally:
            d = su.delete(f"{BASE_URL}/api/platform/organizations/{oid}", json={"confirm_name": org_name})
            assert d.status_code == 200, d.text
            su.delete(f"{BASE_URL}/api/platform/users/{me['user_id']}")  # org delete only detaches the admin account
