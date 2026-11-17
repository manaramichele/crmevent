# Iter181: fixes after iteration_180 - tipologie_struttura, platform defaults, esigenze arrays usage/rename,
# tipi_postazione usage on station shifts, public taglia validation, /settings/usage == /settings/lists mapping
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/")
PWD = "TestPass123!"
_env = dotenv_values("/app/backend/.env")
DB = MongoClient(_env["MONGO_URL"])[_env["DB_NAME"]]
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
PD = "__platform_defaults__"


def _register(tag):
    ts = f"{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"
    email = f"test_i181_{tag}_{ts}@example.com"
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "Test", "cognome": "Admin", "email": email, "password": PWD,
        "org_name": f"TEST_I181_{tag}_{ts}", "telefono": "+39 333 123 4567", "accept_terms": True})
    assert r.status_code in (200, 201), r.text
    me = s.get(f"{BASE_URL}/api/auth/me").json()
    return s, email, me.get("org_id") or (me.get("user") or {}).get("org_id")


def _purge(email, oid):
    if oid:
        for c in DB.list_collection_names():
            if c not in ("organizations", "users"):
                DB[c].delete_many({"org_id": oid})
        DB.settings.delete_many({"id": oid})
        DB.organizations.delete_many({"id": oid})
    DB.users.delete_many({"email": email})


@pytest.fixture(scope="module")
def org():
    a = _register("a")
    yield a
    _purge(a[1], a[2])


def _items(s, key, params=None):
    r = s.get(f"{BASE_URL}/api/settings/lists", params=params or {})
    assert r.status_code == 200, r.text
    return [i for l in r.json()["lists"] if l["key"] == key for i in l["items"]]


def _usage(s, key, value):
    r = s.get(f"{BASE_URL}/api/settings/usage", params={"list": key, "value": value})
    assert r.status_code == 200, r.text
    return r.json()["count"]


class TestFixes:
    # 11 lists, tipologie_struttura present with defaults
    def test_lists_and_struttura(self, org):
        s, _, oid = org
        r = s.get(f"{BASE_URL}/api/settings/lists").json()
        keys = [l["key"] for l in r["lists"]]
        assert len(keys) == 11 and "tipologie_struttura" in keys
        vals = [i["value"] for i in _items(s, "tipologie_struttura")]
        assert "Hotel" in vals and "B&B" in vals
        a = s.post(f"{BASE_URL}/api/settings/lists/tipologie_struttura/items", json={"value": "TEST_Ostello"})
        assert a.status_code == 200 and a.json()["created"] is True
        st = s.post(f"{BASE_URL}/api/structures", json={"nome": "TEST_Struct", "tipologia": "TEST_Ostello"})
        assert st.status_code in (200, 201), st.text
        assert _usage(s, "tipologie_struttura", "TEST_Ostello") == 1
        u = next(i for i in _items(s, "tipologie_struttura") if i["value"] == "TEST_Ostello")
        assert u["usage"] == 1
        vals = [i["value"] for i in _items(s, "tipologie_struttura") if i["value"] != "TEST_Ostello"]
        d = s.put(f"{BASE_URL}/api/settings/lists/tipologie_struttura", json={"items": vals, "disattivati": []})
        assert d.status_code == 409
        rn = s.post(f"{BASE_URL}/api/settings/lists/tipologie_struttura/rename", json={"old": "TEST_Ostello", "new": "TEST_Ostello2"})
        assert rn.status_code == 200 and rn.json()["records_updated"] == 1
        assert DB.structures.find_one({"id": st.json()["id"]})["tipologia"] == "TEST_Ostello2"

    # esigenze_alimentari arrays: usage persons+staff, rename all array matches (arrayFilters)
    def test_esigenze_usage_rename(self, org):
        s, _, oid = org
        s.post(f"{BASE_URL}/api/settings/lists/esigenze_alimentari/items", json={"value": "TEST_Kosher"})
        p1 = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_A", "cognome": "TEST_B", "esigenze_alimentari": ["Vegano", "TEST_Kosher"]})
        p2 = s.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_C", "cognome": "TEST_D", "esigenze_alimentari": ["TEST_Kosher"]})
        assert p1.status_code in (200, 201) and p2.status_code in (200, 201), p1.text
        # staff link with esigenze override (insert directly to avoid event preconditions)
        sid = uuid.uuid4().hex
        DB.staff.insert_one({"id": sid, "org_id": oid, "persona_id": p2.json()["id"], "evento_id": "x", "esigenze_alimentari": ["TEST_Kosher", "Vegano"]})
        assert _usage(s, "esigenze_alimentari", "TEST_Kosher") == 3
        u = next(i for i in _items(s, "esigenze_alimentari") if i["value"] == "TEST_Kosher")
        assert u["usage"] == 3
        rn = s.post(f"{BASE_URL}/api/settings/lists/esigenze_alimentari/rename", json={"old": "TEST_Kosher", "new": "TEST_Kasher"})
        assert rn.status_code == 200, rn.text
        assert rn.json()["records_updated"] == 3
        assert DB.persons.find_one({"id": p1.json()["id"]})["esigenze_alimentari"] == ["Vegano", "TEST_Kasher"]
        assert DB.staff.find_one({"id": sid})["esigenze_alimentari"] == ["TEST_Kasher", "Vegano"]

    # tipi_postazione usage counts only station shifts; aree_operative excludes them
    def test_tipi_postazione_usage(self, org):
        s, _, oid = org
        DB.shifts.insert_one({"id": uuid.uuid4().hex, "org_id": oid, "evento_id": "x", "area": "Ristoro", "planner_station_id": "f1", "planner_project_id": "p1"})
        DB.shifts.insert_one({"id": uuid.uuid4().hex, "org_id": oid, "evento_id": "x", "area": "Ristoro"})
        assert _usage(s, "tipi_postazione", "Ristoro") == 1
        assert _usage(s, "aree_operative", "Ristoro") == 1
        u = next(i for i in _items(s, "tipi_postazione") if i["value"] == "Ristoro")
        assert u["usage"] == 1
        assert _usage(s, "unknown_list", "x") == 0

    # public form taglia validated against active taglie
    def test_public_taglia_validation(self, org):
        s, _, oid = org
        ev = s.post(f"{BASE_URL}/api/events", json={"nome": "TEST_Ev181", "data_inizio": "2027-06-10", "data_fine": "2027-06-10"})
        assert ev.status_code in (200, 201), ev.text
        code = s.post(f"{BASE_URL}/api/events/{ev.json()['id']}/availability/link").json()["code"]
        vals = [i["value"] for i in _items(s, "taglie")]
        s.put(f"{BASE_URL}/api/settings/lists/taglie", json={"items": vals, "disattivati": ["XS"]})
        info = requests.get(f"{BASE_URL}/api/public/availability/{code}").json()
        assert "XS" not in info["taglie_options"]
        body = {"nome": "TEST_Pub", "cognome": "TEST_Pub", "cellulare": "+393339870001", "email": f"test_pub181_{uuid.uuid4().hex[:6]}@example.com",
                "privacy": True, "data_nascita": "1990-03-03", "preferenza_attivita": "Altro", "preferenza_altro": "x",
                "days": [{"date": "2027-06-10", "disponibile": True}]}
        for bad in ("ZZZ", "XS"):
            r = requests.post(f"{BASE_URL}/api/public/availability/{code}", json={**body, "taglia": bad})
            assert r.status_code == 400 and "Taglia non valida" in r.text, (bad, r.status_code, r.text)
        ok = requests.post(f"{BASE_URL}/api/public/availability/{code}", json={**body, "taglia": "L"})
        assert ok.status_code == 200, ok.text
        no = requests.post(f"{BASE_URL}/api/public/availability/{code}", json={**body, "email": "test_pub181b_" + uuid.uuid4().hex[:6] + "@example.com", "cellulare": "+393339870002"})
        assert no.status_code == 200, no.text


class TestPlatformDefaults:
    # Super Admin platform scope: defaults shown when no doc; add keeps other defaults; new org inherits
    def test_platform_scope(self):
        orig = DB.settings.find_one({"id": PD}, {"_id": 0})
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SA[0], "password": SA[1]})
        if r.status_code != 200:
            pytest.skip("superadmin login failed")
        created = None
        try:
            DB.settings.delete_many({"id": PD})
            P = {"scope": "platform"}
            t = [i["value"] for i in _items(s, "taglie", P)]
            assert t == ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
            ev_def = [i["value"] for i in _items(s, "tipologie_evento", P)]
            assert len(ev_def) > 0
            a = s.post(f"{BASE_URL}/api/settings/lists/taglie/items", params=P, json={"value": "TEST_4XL"})
            assert a.status_code == 200, a.text
            t2 = [i["value"] for i in _items(s, "taglie", P)]
            assert t2 == t + ["TEST_4XL"]
            assert [i["value"] for i in _items(s, "tipologie_evento", P)] == ev_def
            assert len(_items(s, "esigenze_alimentari", P)) == 7
            created = _register("plat")
            assert "TEST_4XL" in [i["value"] for i in _items(created[0], "taglie")]
            # non-superadmin cannot use platform scope
            assert created[0].get(f"{BASE_URL}/api/settings/lists", params=P).status_code == 403
        finally:
            DB.settings.delete_many({"id": PD})
            if orig:
                DB.settings.insert_one(orig)
            if created:
                _purge(created[1], created[2])
