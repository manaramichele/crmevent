# Dropdown management (/api/settings/lists), Person taglia/note, archive-on-delete, public availability taglia
import os
import time
import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")
PWD = "TestPass123!"
_env = dotenv_values("/app/backend/.env")
DB = MongoClient(_env["MONGO_URL"])[_env["DB_NAME"]]
ORG_COLLS = ["persons", "staff", "availabilities", "events", "settings", "avail_links", "shifts", "teams", "companies", "deals"]


def _register(tag):
    ts = f"{int(time.time() * 1000)}{__import__('uuid').uuid4().hex[:6]}"
    email = f"test_ol_{tag}_{ts}@example.com"
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "Test", "cognome": "Admin", "email": email, "password": PWD,
        "org_name": f"TEST_OL_{tag}_{ts}", "telefono": "+39 333 123 4567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    org_id = me.get("org_id") or (me.get("user") or {}).get("org_id")
    return s, email, org_id


@pytest.fixture(scope="module")
def orgs():
    a = _register("a")
    b = _register("b")
    yield {"A": a, "B": b}
    for _, email, oid in (a, b):
        if not oid:
            continue
        for c in DB.list_collection_names():
            if c in ("organizations", "users"):
                continue
            DB[c].delete_many({"org_id": oid})
        DB.settings.delete_many({"id": oid})
        DB.organizations.delete_many({"id": oid})
        DB.users.delete_many({"email": email})


def _lists(s):
    r = s.get(f"{BASE_URL}/api/settings/lists")
    assert r.status_code == 200, r.text
    return r.json()


def _items(s, key):
    return next(l for l in _lists(s)["lists"] if l["key"] == key)["items"]


class TestLists:
    def test_overview(self, orgs):
        s = orgs["A"][0]
        d = _lists(s)
        assert len(d["lists"]) == 11
        assert d["can_manage"] is True and d["platform"] is False
        assert isinstance(d["technical"], dict) and len(d["technical"]) >= 1
        groups = {l["group"] for l in d["lists"]}
        assert {"Eventi", "Staff e Volontari", "Aziende, Sponsor e Partner", "Ospitalità e Pasti", "Event Planner", "Control Room"} <= groups
        tg = next(l for l in d["lists"] if l["key"] == "taglie")
        assert [i["value"] for i in tg["items"]] == ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
        assert set(tg["items"][0].keys()) >= {"value", "active", "usage"}

    def test_unknown_key(self, orgs):
        r = orgs["A"][0].post(f"{BASE_URL}/api/settings/lists/foo/items", json={"value": "x"})
        assert r.status_code == 404

    def test_add_dedupe_and_isolation(self, orgs):
        s = orgs["A"][0]
        r = s.post(f"{BASE_URL}/api/settings/lists/taglie/items", json={"value": "  4XL "})
        assert r.status_code == 200 and r.json()["created"] is True and r.json()["value"] == "4XL"
        r = s.post(f"{BASE_URL}/api/settings/lists/taglie/items", json={"value": "4xl"})
        assert r.json()["created"] is False and r.json()["value"] == "4XL"
        assert [i["value"] for i in _items(s, "taglie")].count("4XL") == 1
        # org B isolation
        assert "4XL" not in [i["value"] for i in _items(orgs["B"][0], "taglie")]
        assert "4XL" in s.get(f"{BASE_URL}/api/settings").json()["taglie"]

    def test_disable_reactivate_via_add(self, orgs):
        s = orgs["A"][0]
        vals = [i["value"] for i in _items(s, "taglie")]
        r = s.put(f"{BASE_URL}/api/settings/lists/taglie", json={"items": vals, "disattivati": ["4XL"]})
        assert r.status_code == 200
        assert next(i for i in _items(s, "taglie") if i["value"] == "4XL")["active"] is False
        r = s.post(f"{BASE_URL}/api/settings/lists/taglie/items", json={"value": "4XL"})
        assert r.json()["created"] is False
        assert next(i for i in _items(s, "taglie") if i["value"] == "4XL")["active"] is True

    def test_reorder(self, orgs):
        s = orgs["A"][0]
        vals = [i["value"] for i in _items(s, "taglie")]
        rev = list(reversed(vals))
        assert s.put(f"{BASE_URL}/api/settings/lists/taglie", json={"items": rev, "disattivati": []}).status_code == 200
        assert [i["value"] for i in _items(s, "taglie")] == rev
        s.put(f"{BASE_URL}/api/settings/lists/taglie", json={"items": vals, "disattivati": []})


class TestPersonTagliaArchive:
    def test_taglia_note_rename_409_archive(self, orgs):
        s = orgs["A"][0]
        r = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_Mario", "cognome": "TEST_Rossi", "taglia": "4XL", "note": "riga1\nriga2"})
        assert r.status_code in (200, 201), r.text
        p = r.json()
        pid = p["id"]
        assert p["taglia"] == "4XL" and p["note"] == "riga1\nriga2"
        r = s.put(f"{BASE_URL}/api/persons/{pid}", json={"taglia": "XL", "note": "aggiornata"})
        assert r.status_code == 200
        g = s.get(f"{BASE_URL}/api/persons/{pid}").json()
        assert g["taglia"] == "XL" and g["note"] == "aggiornata"
        # usage + 409 on removing used value
        assert next(i for i in _items(s, "taglie") if i["value"] == "XL")["usage"] == 1
        vals = [i["value"] for i in _items(s, "taglie") if i["value"] != "XL"]
        r = s.put(f"{BASE_URL}/api/settings/lists/taglie", json={"items": vals, "disattivati": []})
        assert r.status_code == 409, r.text
        # delete unused ok
        vals2 = [i["value"] for i in _items(s, "taglie") if i["value"] != "4XL"]
        assert s.put(f"{BASE_URL}/api/settings/lists/taglie", json={"items": vals2, "disattivati": []}).status_code == 200
        # rename updates records
        r = s.post(f"{BASE_URL}/api/settings/lists/taglie/rename", json={"old": "XL", "new": "XL Large"})
        assert r.status_code == 200 and r.json()["records_updated"] == 1
        assert s.get(f"{BASE_URL}/api/persons/{pid}").json()["taglia"] == "XL Large"
        r = s.post(f"{BASE_URL}/api/settings/lists/taglie/rename", json={"old": "XL Large", "new": "m"})
        assert r.status_code == 409
        s.post(f"{BASE_URL}/api/settings/lists/taglie/rename", json={"old": "XL Large", "new": "XL"})
        # hard delete with no history
        r = s.delete(f"{BASE_URL}/api/persons/{pid}")
        assert r.status_code == 200 and not r.json().get("archived")
        assert s.get(f"{BASE_URL}/api/persons/{pid}").status_code == 404

    def test_archive_with_staff_link_and_public_form(self, orgs):
        s, _, oid = orgs["A"]
        ev = s.post(f"{BASE_URL}/api/events", json={"nome": "TEST_Evento OL", "data_inizio": "2027-05-10", "data_fine": "2027-05-11", "tipologia": "Fiera"})
        assert ev.status_code in (200, 201), ev.text
        eid = ev.json()["id"]
        lk = s.post(f"{BASE_URL}/api/events/{eid}/availability/link")
        assert lk.status_code == 200, lk.text
        code = lk.json()["code"]
        # disable "S" -> excluded from public options
        vals = [i["value"] for i in _items(s, "taglie")]
        s.put(f"{BASE_URL}/api/settings/lists/taglie", json={"items": vals, "disattivati": ["S"]})
        info = requests.get(f"{BASE_URL}/api/public/availability/{code}").json()
        assert info["active"] is True
        assert "S" not in info["taglie_options"] and "M" in info["taglie_options"]
        assert "note" not in info
        email = f"test_pub_{int(time.time())}@example.com"
        body = {"nome": "TEST_Giulia", "cognome": "TEST_Verdi", "cellulare": "+393339871299", "email": email,
                "privacy": True, "data_nascita": "1990-03-03", "preferenza_attivita": "Hostess", "taglia": "M", "days": [{"date": "2027-05-10", "disponibile": True}]}
        r1 = requests.post(f"{BASE_URL}/api/public/availability/{code}", json=body)
        assert r1.status_code == 200, r1.text
        r2 = requests.post(f"{BASE_URL}/api/public/availability/{code}", json={**body, "taglia": "L"})
        assert r2.status_code == 200, r2.text
        ps = [p for p in s.get(f"{BASE_URL}/api/persons-enriched").json() if p.get("email") == email]
        assert len(ps) == 1
        p = ps[0]
        assert p["taglia"] == "M"  # fill only if missing
        links = [a for a in p["assegnazioni"] if a["evento_id"] == eid]
        assert len(links) == 1 and links[0]["categoria"] == "da_classificare"
        print("auto note on public person:", repr(p.get("note")))
        # delete => archived (has staff link)
        r = s.delete(f"{BASE_URL}/api/persons/{p['id']}")
        assert r.status_code == 200 and r.json().get("archived") is True
        assert DB.persons.find_one({"id": p["id"]})["archiviato"] is True
        assert not [x for x in s.get(f"{BASE_URL}/api/persons-enriched").json() if x["id"] == p["id"]]
        assert not [x for x in s.get(f"{BASE_URL}/api/persons").json() if x["id"] == p["id"]]
        # repeat submission un-archives same person (no duplicate)
        r3 = requests.post(f"{BASE_URL}/api/public/availability/{code}", json=body)
        assert r3.status_code == 200
        assert DB.persons.count_documents({"org_id": oid, "email": email}) == 1
        assert DB.persons.find_one({"org_id": oid, "email": email})["archiviato"] is False


class TestPerms:
    def test_unauth(self):
        assert requests.get(f"{BASE_URL}/api/settings/lists").status_code in (401, 403)

    def test_superadmin_platform(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"})
        if r.status_code != 200:
            pytest.skip("superadmin login failed")
        r = s.get(f"{BASE_URL}/api/settings/lists", params={"scope": "platform"})
        print("superadmin lists:", r.status_code, r.text[:200])
        assert r.status_code == 200
        assert r.json()["platform"] is True and r.json()["can_manage"] is True
