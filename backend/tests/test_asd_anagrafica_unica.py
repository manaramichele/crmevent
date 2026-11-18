# ASD <-> Staff/Volontari shared person registry (db.persons): search, link, duplicates, sync, sections, isolation, super admin
import os
import random
import uuid
from datetime import date, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SUPER = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PWD = "TestAsd2026!"


def _env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


MDB = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]

_ODD = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]))


def make_cf():
    base = "TST" + "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3)) + "80A01H501"
    tot = sum(_ODD[c] if i % 2 == 0 else (int(c) if c.isdigit() else ord(c) - 65) for i, c in enumerate(base))
    return base + chr(65 + tot % 26)


def rand_cell():
    return "+39 333 " + "".join(random.choice("0123456789") for _ in range(7))


def register(tag):
    s = requests.Session()
    email = f"test_asdu_{tag.lower()}_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": tag, "email": email, "password": PWD, "org_name": f"TEST_ASDU_{tag}_{uuid.uuid4().hex[:4]}",
        "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    u = MDB.users.find_one({"email": email})
    s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": PWD})
    return s, u["org_id"], email


ORGS = []


@pytest.fixture(scope="module")
def A():
    s, org, email = register("A")
    ORGS.append((org, email))
    MDB.org_services.insert_one({"org_id": org, "service": "gestione-societa", "active": True})
    return {"s": s, "org": org}


@pytest.fixture(scope="module")
def B():
    s, org, email = register("B")
    ORGS.append((org, email))
    MDB.org_services.insert_one({"org_id": org, "service": "gestione-societa", "active": True})
    return {"s": s, "org": org}


@pytest.fixture(scope="module")
def C():  # module inactive
    s, org, email = register("C")
    ORGS.append((org, email))
    return {"s": s, "org": org}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for org, email in ORGS:
        for c in ("persons", "staff", "events", "teams", "asd_soci", "asd_tesseramenti", "asd_quote", "asd_certificati", "asd_adempimenti",
                  "org_services", "memberships", "availability_prefs", "subscriptions"):
            MDB.settings.delete_one({"id": org})
            MDB[c].delete_many({"org_id": org})
        MDB.organizations.delete_one({"id": org})
        MDB.users.delete_many({"email": email})


@pytest.fixture(scope="module")
def staff_person(A):
    """Person created only in Staff/Volontari (db.persons + db.staff link)."""
    s = A["s"]
    sur = "TEST_Verdi" + uuid.uuid4().hex[:5]
    cf, email, cell = make_cf(), f"test_{uuid.uuid4().hex[:6]}@example.com", rand_cell()
    p = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_Luigi", "cognome": sur, "codice_fiscale": cf, "email": email, "cellulare": cell,
                                                 "indirizzo": "Via Roma 1", "cap": "20100", "citta": "Milano", "provincia": "MI"})
    assert p.status_code == 200, p.text
    ev = s.post(f"{BASE_URL}/api/events", json={"nome": "TEST_Evento"})
    assert ev.status_code == 200, ev.text
    st = s.post(f"{BASE_URL}/api/staff", json={"persona_id": p.json()["id"], "evento_id": ev.json()["id"], "categoria": "staff", "ruolo": "TEST_Mansione"})
    assert st.status_code == 200, st.text
    return {**p.json(), "sur": sur, "evento_id": ev.json()["id"]}


def search(s, q, **h):
    r = s.get(f"{BASE_URL}/api/asd/anagrafica", params={"q": q}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


class TestSearch:
    def test_search_all_keys(self, A, staff_person):
        p = staff_person
        digits = "".join(ch for ch in p["cellulare"] if ch.isdigit())[-6:]
        for q in (p["sur"], f"TEST_Luigi {p['sur']}", f"{p['sur']} TEST_Luigi", p["codice_fiscale"], p["codice_fiscale"].lower(), p["email"], digits):
            res = search(A["s"], q)
            hit = [x for x in res if x["id"] == p["id"]]
            assert hit, f"not found by {q!r}"
            assert hit[0]["socio"] is None and hit[0]["classificazione"] == ["staff"], hit[0]

    def test_short_query(self, A):
        assert search(A["s"], "a") == []


class TestLinkExisting:
    def test_link_no_dup(self, A, staff_person):
        s, p = A["s"], staff_person
        n0 = MDB.persons.count_documents({"org_id": A["org"]})
        body = {k: p.get(k) for k in ("nome", "cognome", "codice_fiscale", "email", "cellulare", "indirizzo", "cap", "citta", "provincia")}
        r = s.post(f"{BASE_URL}/api/asd/soci", json={**body, "persona_id": p["id"], "numero_socio": "TEST_N1"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["persona_id"] == p["id"] and d["indirizzo"] == "Via Roma 1" and d["citta"] == "Milano"
        assert MDB.persons.count_documents({"org_id": A["org"]}) == n0
        assert MDB.asd_soci.find_one({"org_id": A["org"], "id": d["id"]})["persona_id"] == p["id"]
        assert "nome" not in MDB.asd_soci.find_one({"org_id": A["org"], "id": d["id"]})
        p["socio_id"] = d["id"]
        # search now shows socio; numero socio searchable
        hit = [x for x in search(s, "TEST_N1") if x["id"] == p["id"]]
        assert hit and hit[0]["socio"]["id"] == d["id"]

    def test_link_partial_body_keeps_address(self, A):
        """Linking with only nome/cognome must NOT wipe shared fields already present."""
        s = A["s"]
        p = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_P", "cognome": "TEST_Partial" + uuid.uuid4().hex[:4], "indirizzo": "Via Keep 9", "citta": "Roma"}).json()
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": p["nome"], "cognome": p["cognome"], "persona_id": p["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["indirizzo"] == "Via Keep 9", f"address wiped: {r.json().get('indirizzo')}"

    def test_link_again_409(self, A, staff_person):
        p = staff_person
        r = A["s"].post(f"{BASE_URL}/api/asd/soci", json={"nome": p["nome"], "cognome": p["cognome"], "persona_id": p["id"]})
        assert r.status_code == 409 and r.json()["detail"]["field"] == "persona_id"

    def test_socio_not_auto_classified(self, A, staff_person):
        rows = {x["id"]: x for x in A["s"].get(f"{BASE_URL}/api/persons-enriched").json()}
        x = rows[staff_person["id"]]
        assert x["is_socio"] is True and x["is_staff"] is True


class TestDuplicates:
    def test_email_cell_match_then_force(self, A, staff_person):
        s, p = A["s"], staff_person
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_Altro", "cognome": "TEST_Dup", "email": p["email"].upper()})
        assert r.status_code == 409, r.text
        det = r.json()["detail"]
        assert det["field"] == "duplicati" and det["cf"] is False and det["matches"][0]["id"] == p["id"] and "email" in det["matches"][0]["campi"]
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_Altro", "cognome": "TEST_Dup", "cellulare": p["cellulare"]})
        assert r.status_code == 409 and "cellulare" in r.json()["detail"]["matches"][0]["campi"]
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_Altro", "cognome": "TEST_Dup", "email": f"x{uuid.uuid4().hex[:4]}@example.com", "cellulare": p["cellulare"], "conferma_nuova": True})
        assert r.status_code == 200, r.text
        assert r.json()["persona_id"] != p["id"]

    def test_cf_match_always_409(self, A, staff_person):
        r = A["s"].post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_X", "cognome": "TEST_CF", "codice_fiscale": staff_person["codice_fiscale"], "conferma_nuova": True})
        assert r.status_code == 409 and r.json()["detail"]["cf"] is True

    def test_invalid_cf_400(self, A):
        r = A["s"].post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_X", "cognome": "TEST_Y", "codice_fiscale": "ABC"})
        assert r.status_code == 400


class TestSync:
    def test_socio_edit_updates_person(self, A, staff_person):
        s, p = A["s"], staff_person
        new_cell = rand_cell()
        soci = {x["id"]: x for x in s.get(f"{BASE_URL}/api/asd/soci").json()}
        cur = soci[p["socio_id"]]
        body = {k: cur.get(k) for k in ("nome", "cognome", "codice_fiscale", "email", "indirizzo", "cap", "citta", "provincia", "tipo", "stato", "numero_socio")}
        r = s.put(f"{BASE_URL}/api/asd/soci/{p['socio_id']}", json={**body, "cellulare": new_cell})
        assert r.status_code == 200, r.text
        assert s.get(f"{BASE_URL}/api/persons/{p['id']}").json()["cellulare"] == new_cell
        en = {x["id"]: x for x in s.get(f"{BASE_URL}/api/persons-enriched").json()}
        assert en[p["id"]]["cellulare"] == new_cell
        p["cellulare"] = new_cell

    def test_person_edit_updates_socio(self, A, staff_person):
        s, p = A["s"], staff_person
        r = s.put(f"{BASE_URL}/api/persons/{p['id']}", json={"nome": p["nome"], "indirizzo": "Via Nuova 22", "cap": "10100", "citta": "Torino"})
        assert r.status_code == 200, r.text
        soci = {x["id"]: x for x in s.get(f"{BASE_URL}/api/asd/soci").json()}
        x = soci[p["socio_id"]]
        assert (x["indirizzo"], x["cap"], x["citta"]) == ("Via Nuova 22", "10100", "Torino")

    def test_socio_edit_email_conflict_400(self, A, staff_person):
        s = A["s"]
        other = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_O", "cognome": "TEST_Other", "email": f"o{uuid.uuid4().hex[:5]}@example.com"}).json()
        cur = {x["id"]: x for x in s.get(f"{BASE_URL}/api/asd/soci").json()}[staff_person["socio_id"]]
        r = s.put(f"{BASE_URL}/api/asd/soci/{staff_person['socio_id']}", json={**{k: cur.get(k) for k in ("nome", "cognome", "codice_fiscale", "cellulare")}, "email": other["email"]})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "email"


class TestNewFromAsd:
    def test_new_person_then_staff(self, A, staff_person):
        s = A["s"]
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_Nuovo", "cognome": "TEST_Asd" + uuid.uuid4().hex[:4], "codice_fiscale": make_cf(), "tipo": "socio"})
        assert r.status_code == 200, r.text
        pid = r.json()["persona_id"]
        en = {x["id"]: x for x in s.get(f"{BASE_URL}/api/persons-enriched").json()}[pid]
        assert en["is_socio"] and not en["is_staff"] and not en["is_volontario"] and en["provenienza_tipo"] == "associazione"
        n0 = MDB.persons.count_documents({"org_id": A["org"]})
        st = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": staff_person["evento_id"], "categoria": "volontario"})
        assert st.status_code == 200, st.text
        assert MDB.persons.count_documents({"org_id": A["org"]}) == n0
        en = {x["id"]: x for x in s.get(f"{BASE_URL}/api/persons-enriched").json()}[pid]
        assert en["is_volontario"] and en["is_socio"]
        sec = s.get(f"{BASE_URL}/api/asd/soci/{r.json()['id']}/staff").json()
        assert sec["classificazione"] == ["volontario"] and sec["eventi"][0]["evento_nome"] == "TEST_Evento"


class TestSections:
    def test_socio_staff_section(self, A, staff_person):
        d = A["s"].get(f"{BASE_URL}/api/asd/soci/{staff_person['socio_id']}/staff").json()
        assert d["classificazione"] == ["staff"] and d["eventi"][0]["mansione"] == "TEST_Mansione"
        assert "disponibilita" in d

    def test_persona_link_and_no_cert(self, A, staff_person):
        s = A["s"]
        sid = staff_person["socio_id"]
        t = s.post(f"{BASE_URL}/api/asd/tesseramenti", json={"socio_id": sid, "stagione": "2026/2027", "ente_id": "fidal", "data_scadenza": (date.today() + timedelta(days=200)).isoformat()})
        assert t.status_code == 200, t.text
        c = s.post(f"{BASE_URL}/api/asd/certificati", json={"socio_id": sid, "data_scadenza": (date.today() + timedelta(days=100)).isoformat(), "medico": "TEST_Dr"})
        assert c.status_code == 200, c.text
        q = s.post(f"{BASE_URL}/api/asd/quote", json={"socio_id": sid, "descrizione": "TEST_Quota", "importo": 30})
        assert q.status_code == 200, q.text
        d = s.get(f"{BASE_URL}/api/asd/persona/{staff_person['id']}").json()
        assert d["active"] is True and d["socio"]["id"] == sid and d["tesseramento"]["ente"] == "FIDAL – Federazione Italiana di Atletica Leggera" and d["tesseramento"]["stato"] == "valido"
        assert "cert" not in str(d).lower() and "TEST_Dr" not in str(d)
        exp = f"{staff_person['sur']} TEST_Luigi"
        for path in ("tesseramenti", "quote", "certificati"):
            rows = [x for x in s.get(f"{BASE_URL}/api/asd/{path}").json() if x["socio_id"] == sid]
            assert rows and rows[0]["socio_nome"] == exp, (path, rows[0].get("socio_nome"))
        assert s.get(f"{BASE_URL}/api/asd/persona/nonexistent").json() == {"active": True, "socio": None}

    def test_inactive_module(self, C):
        s = C["s"]
        assert s.get(f"{BASE_URL}/api/asd/persona/x").json() == {"active": False}
        assert s.get(f"{BASE_URL}/api/asd/anagrafica", params={"q": "TEST"}).status_code == 403
        p = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_C", "cognome": "TEST_Inactive"})
        assert p.status_code == 200
        en = s.get(f"{BASE_URL}/api/persons-enriched")
        assert en.status_code == 200 and all(x["is_socio"] is False for x in en.json())


class TestDelete:
    def test_delete_membership_keeps_person(self, A):
        s = A["s"]
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_Del", "cognome": "TEST_Del" + uuid.uuid4().hex[:4]}).json()
        assert s.delete(f"{BASE_URL}/api/asd/soci/{r['id']}").status_code == 200
        assert MDB.asd_soci.find_one({"id": r["id"]}) is None
        assert s.get(f"{BASE_URL}/api/persons/{r['persona_id']}").status_code == 200

    def test_delete_person_with_socio_archives(self, A):
        s = A["s"]
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_Arc", "cognome": "TEST_Arc" + uuid.uuid4().hex[:4]}).json()
        d = s.delete(f"{BASE_URL}/api/persons/{r['persona_id']}")
        assert d.status_code == 200 and d.json().get("archived") is True
        assert MDB.persons.find_one({"id": r["persona_id"]})["archiviato"] is True

    def test_delete_socio_with_history_409(self, A, staff_person):
        assert A["s"].delete(f"{BASE_URL}/api/asd/soci/{staff_person['socio_id']}").status_code == 409


class TestIsolation:
    def test_b_cannot_see_or_link_a(self, A, B, staff_person):
        s = B["s"]
        assert not [x for x in search(s, staff_person["sur"]) if x["id"] == staff_person["id"]]
        assert not [x for x in search(s, staff_person["codice_fiscale"])]
        r = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_X", "cognome": "TEST_X", "persona_id": staff_person["id"]})
        assert r.status_code == 400 and r.json()["detail"]["field"] == "persona_id"
        assert s.get(f"{BASE_URL}/api/asd/soci/{staff_person['socio_id']}/staff").status_code == 404
        assert s.get(f"{BASE_URL}/api/asd/persona/{staff_person['id']}").json() == {"active": True, "socio": None}

    def test_superadmin_x_org(self, A, staff_person):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SUPER[0], "password": SUPER[1]})
        if r.status_code != 200:
            pytest.skip("superadmin login failed")
        h = {"X-Org-Id": A["org"]}
        res = search(s, staff_person["sur"], **h)
        assert [x for x in res if x["id"] == staff_person["id"]]
        p = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_SA", "cognome": "TEST_SuperLink"}, headers=h)
        assert p.status_code == 200, p.text
        l = s.post(f"{BASE_URL}/api/asd/soci", json={"nome": "TEST_SA", "cognome": "TEST_SuperLink", "persona_id": p.json()["id"]}, headers=h)
        assert l.status_code == 200, l.text
        assert s.get(f"{BASE_URL}/api/asd/anagrafica", params={"q": "TEST"}).status_code in (403, 428)
