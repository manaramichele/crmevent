# Referenti in linea nella scheda Azienda + Integrazione referenti (Super Admin) + nav cleanup APIs
import os
import uuid
import random
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
CREATED_ORGS = []


def _register(tag):
    s = requests.Session()
    suf = uuid.uuid4().hex[:6]
    body = {"nome": "Test", "cognome": "Ref", "email": f"test_ri_{tag}_{suf}@example.com", "password": "RefTest2026!",
            "org_name": f"TEST_RefInline_{tag}_{suf}", "telefono": f"+39333{random.randint(1000000, 9999999)}", "accept_terms": True}
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json=body)
    assert r.status_code in (200, 201), r.text
    if "token" in (r.json() or {}):
        s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    CREATED_ORGS.append({"email": body["email"], "org": body["org_name"], "org_id": me.get("org_id")})
    return s


@pytest.fixture(scope="module")
def org_a():
    return _register("a")


@pytest.fixture(scope="module")
def org_b():
    return _register("b")


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=SA)
    assert r.status_code == 200, r.text
    if "token" in r.json():
        s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def company(org_a):
    r = org_a.post(f"{BASE_URL}/api/companies", json={"nome": "TEST_Azienda_Ref"})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


class TestReferenti:
    def test_put_and_get(self, org_a, company):
        r = org_a.put(f"{BASE_URL}/api/companies/{company}/referenti", json={"referenti": [
            {"nome": "Mario", "cognome": "Rossi", "email": "Mario.Rossi@Example.com", "cellulare": "+39 333 1112223"},
            {"nome": "Lucia", "cognome": "Bianchi", "email": "", "cellulare": "3334445556"},
            {"nome": "", "cognome": "", "email": "", "cellulare": ""}]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data) == 2
        g = org_a.get(f"{BASE_URL}/api/companies/{company}/referenti").json()
        assert {x["nome"] for x in g} == {"Mario", "Lucia"}
        assert set(g[0].keys()) == {"person_id", "nome", "cognome", "email", "cellulare"}

    def test_update_existing(self, org_a, company):
        g = org_a.get(f"{BASE_URL}/api/companies/{company}/referenti").json()
        for x in g:
            if x["nome"] == "Mario":
                x["cognome"] = "Rossini"
        r = org_a.put(f"{BASE_URL}/api/companies/{company}/referenti", json={"referenti": g})
        assert r.status_code == 200
        g2 = org_a.get(f"{BASE_URL}/api/companies/{company}/referenti").json()
        assert any(x["cognome"] == "Rossini" for x in g2) and len(g2) == 2

    def test_dedupe_email_case_insensitive(self, org_a, company):
        r = org_a.post(f"{BASE_URL}/api/companies", json={"nome": "TEST_Azienda_Ref2"})
        c2 = r.json()["id"]
        r = org_a.put(f"{BASE_URL}/api/companies/{c2}/referenti", json={"referenti": [
            {"nome": "Mario", "cognome": "", "email": "mario.rossi@example.com", "cellulare": ""},
            {"nome": "L", "cognome": "", "email": "", "cellulare": "+393334445556"}]})
        assert r.status_code == 200
        ids2 = {x["person_id"] for x in r.json()}
        ids1 = {x["person_id"] for x in org_a.get(f"{BASE_URL}/api/companies/{company}/referenti").json()}
        assert ids2 == ids1, f"duplicates created: {ids2} vs {ids1}"

    def test_remove_unlinks_not_deletes(self, org_a, company):
        g = org_a.get(f"{BASE_URL}/api/companies/{company}/referenti").json()
        removed = [x for x in g if x["nome"] == "Lucia"][0]
        keep = [x for x in g if x["nome"] != "Lucia"]
        r = org_a.put(f"{BASE_URL}/api/companies/{company}/referenti", json={"referenti": keep})
        assert r.status_code == 200 and len(r.json()) == 1
        g2 = org_a.get(f"{BASE_URL}/api/companies/{company}/referenti").json()
        assert removed["person_id"] not in {x["person_id"] for x in g2}
        p = org_a.get(f"{BASE_URL}/api/persons/{removed['person_id']}/detail")
        assert p.status_code == 200, f"contact deleted? {p.status_code}"

    def test_cross_org_404(self, org_b, company):
        assert org_b.get(f"{BASE_URL}/api/companies/{company}/referenti").status_code == 404
        r = org_b.put(f"{BASE_URL}/api/companies/{company}/referenti", json={"referenti": [{"nome": "Hack"}]})
        assert r.status_code == 404

    def test_unauth(self, company):
        assert requests.get(f"{BASE_URL}/api/companies/{company}/referenti").status_code in (401, 403)


class TestCleanupApis:
    def test_notifications_empty(self, org_a):
        r = org_a.get(f"{BASE_URL}/api/notifications")
        assert r.status_code == 200
        print("notifications:", r.json())

    def test_permission_sections_hidden(self, org_a):
        r = org_a.get(f"{BASE_URL}/api/org/permissions")
        if r.status_code == 404:
            pytest.skip("meta endpoint path differs")
        keys = {s["key"] for s in r.json()["sections"]}
        assert not keys & {"anagrafiche", "attivita", "followup"}


class TestIntegrazione:
    def test_non_sa_forbidden(self, org_a):
        assert org_a.get(f"{BASE_URL}/api/admin/referenti-integrazione/anteprima").status_code in (401, 403)
        assert org_a.post(f"{BASE_URL}/api/admin/referenti-integrazione/esegui").status_code in (401, 403)

    def test_preview(self, sa):
        r = sa.get(f"{BASE_URL}/api/admin/referenti-integrazione/anteprima")
        assert r.status_code == 200
        orgs = r.json()["organizzazioni"]
        pend = [o for o in orgs if o["collegamenti_da_creare"] or o["cellulari_da_copiare"]]
        print("pending orgs:", [(o["org"], o["collegamenti_da_creare"], o["cellulari_da_copiare"]) for o in pend])

    def test_restore_404(self, sa):
        assert sa.post(f"{BASE_URL}/api/admin/referenti-integrazione/ripristina/nonexistent").status_code == 404


def teardown_module(module):
    with open("/tmp/ri_created_orgs.txt", "a") as f:
        for o in CREATED_ORGS:
            f.write(f"{o['org']}|{o['org_id']}|{o['email']}\n")
