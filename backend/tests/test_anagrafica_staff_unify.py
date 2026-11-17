# Staff/Volontari unification: CF lookup, public availability -> Da classificare, classify via PUT /staff, places fallback
import os
import time
import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")
EMAIL = "test_anag_1794951730@example.com"
PWD = "TestPass123!"
EVENT_ID = "d28cd58693b948a09e663491d47de837"

_ODD = {**{str(i): v for i, v in enumerate([1, 0, 5, 7, 9, 13, 15, 17, 19, 21])},
        **dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23]))}


def cf_check(s15):
    tot = 0
    for i, c in enumerate(s15):
        if i % 2 == 0:
            tot += _ODD[c]
        else:
            tot += int(c) if c.isdigit() else ord(c) - 65
    return s15 + chr(65 + tot % 26)


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip("login failed")
    return ss


@pytest.fixture(scope="module")
def code(s):
    r = s.get(f"{BASE_URL}/api/events/{EVENT_ID}/availability/link")
    assert r.status_code == 200 and r.json().get("active")
    return r.json()["code"]


@pytest.fixture(scope="module")
def cleanup(s):
    created = {"persons": set()}
    yield created
    env = dotenv_values("/app/backend/.env")
    db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
    for pid in created["persons"]:
        db.staff.delete_many({"persona_id": pid, "evento_id": EVENT_ID})
        db.availabilities.delete_many({"persona_id": pid, "evento_id": EVENT_ID})
        s.delete(f"{BASE_URL}/api/persons/{pid}")


class TestCfLookup:
    def test_roma(self, s):
        d = s.get(f"{BASE_URL}/api/anagrafica/cf-lookup", params={"cf": "RSSMRA80A01H501U"}).json()
        assert d["valid"] and d["found"] and d["codice"] == "H501"
        assert d["luogo"] == "Roma (RM)" and d["estero"] is False

    def test_foreign(self, s):
        d = s.get(f"{BASE_URL}/api/anagrafica/cf-lookup", params={"cf": cf_check("RSSMRA80A01Z404")}).json()
        assert d["valid"] and d["found"] and d["estero"] is True
        assert "Stati Uniti" in d["nome"] and d["provincia"] is None

    def test_invalid(self, s):
        d = s.get(f"{BASE_URL}/api/anagrafica/cf-lookup", params={"cf": "ABC"}).json()
        assert d["valid"] is False

    def test_omocodia(self, s):
        # H501 with omocodic digits: H5L1 -> H501
        d = s.get(f"{BASE_URL}/api/anagrafica/cf-lookup", params={"cf": cf_check("RSSMRA80A01H5L1")}).json()
        assert d["valid"] and d["codice"] == "H501"

    def test_historical(self, s):
        cf = cf_check("RSSMRA00A01A001")
        old = s.get(f"{BASE_URL}/api/anagrafica/cf-lookup", params={"cf": cf, "data_nascita": "1900-01-01"}).json()
        cur = s.get(f"{BASE_URL}/api/anagrafica/cf-lookup", params={"cf": cf}).json()
        print("historical:", old, "| current:", cur)
        assert old["nome"] == "Abano" and cur["nome"] == "Abano Terme"

    def test_auth_required(self):
        assert requests.get(f"{BASE_URL}/api/anagrafica/cf-lookup", params={"cf": "RSSMRA80A01H501U"}).status_code == 401
        assert requests.get(f"{BASE_URL}/api/anagrafica/places/status").status_code == 401

    def test_places_disabled(self, s):
        assert s.get(f"{BASE_URL}/api/anagrafica/places/status").json() == {"enabled": False}
        assert s.get(f"{BASE_URL}/api/anagrafica/places/autocomplete", params={"q": "Via Roma"}).status_code == 503
        assert s.get(f"{BASE_URL}/api/anagrafica/places/ChIJabcdefghij").status_code == 503


class TestPublicSubmitFlow:
    def _submit(self, code, email, cf, pref="Hostess"):
        body = {"nome": "TEST_Giulia", "cognome": "TEST_Verdi", "cellulare": "+393339871234",
                "email": email, "codice_fiscale": cf, "privacy": True, "preferenza_attivita": pref,
                "days": [{"date": "2027-05-10", "disponibile": True, "dalle": "09:00", "alle": "13:00"}]}
        return requests.post(f"{BASE_URL}/api/public/availability/{code}", json=body)

    def test_submit_twice_and_classify(self, s, code, cleanup):
        email = f"test_avail_{int(time.time())}@example.com"
        cf = cf_check("VRDGLI85M41F205")  # Milano
        r1 = self._submit(code, email, cf)
        assert r1.status_code == 200, r1.text
        persons = [p for p in s.get(f"{BASE_URL}/api/persons-enriched").json() if p.get("email") == email]
        assert len(persons) == 1
        p = persons[0]
        cleanup["persons"].add(p["id"])
        assert p["luogo_nascita"] == "Milano (MI)"
        assert p["is_da_classificare"] is True and p["provenienza_tipo"] == "link_disponibilita"
        links = [a for a in p["assegnazioni"] if a["evento_id"] == EVENT_ID]
        assert len(links) == 1 and links[0]["categoria"] == "da_classificare"
        pr = [x for x in p["preferenze"] if x["evento_id"] == EVENT_ID]
        assert pr and pr[0]["preferenza"] == "Hostess" and pr[0]["days"][0]["dalle"] == "09:00"

        r2 = self._submit(code, email, cf, pref="Tecnico")
        assert r2.status_code == 200, r2.text
        persons = [p for p in s.get(f"{BASE_URL}/api/persons-enriched").json() if p.get("email") == email]
        assert len(persons) == 1
        p = persons[0]
        links = [a for a in p["assegnazioni"] if a["evento_id"] == EVENT_ID]
        assert len(links) == 1, links
        pr = [x for x in p["preferenze"] if x["evento_id"] == EVENT_ID]
        print("prefs after resubmit:", pr, "| link pref:", links[0].get("preferenza"))
        assert pr[0]["preferenza"] == "Tecnico"

        # classify
        u = s.put(f"{BASE_URL}/api/staff/{links[0]['id']}", json={"categoria": "staff"})
        assert u.status_code == 200 and u.json()["categoria"] == "staff"
        p = [x for x in s.get(f"{BASE_URL}/api/persons-enriched").json() if x["id"] == p["id"]][0]
        assert p["is_da_classificare"] is False and p["is_staff"] is True
        assert p["provenienza_tipo"] == "link_disponibilita"

        # resubmission after classification must not re-create a da_classificare link
        r3 = self._submit(code, email, cf)
        assert r3.status_code == 200
        p = [x for x in s.get(f"{BASE_URL}/api/persons-enriched").json() if x["id"] == p["id"]][0]
        cats = [a["categoria"] for a in p["assegnazioni"] if a["evento_id"] == EVENT_ID]
        assert cats == ["staff"], cats
        assert p["is_da_classificare"] is False
