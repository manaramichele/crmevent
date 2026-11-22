# Iter 204: disponibilità dall'anagrafica (fasce-giorni, PUT /persons/{pid}/availability/{eid}), copertura, isolamento org
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TAG = uuid.uuid4().hex[:6]
D1, D2, D3 = "2026-12-19", "2026-12-20", "2026-12-21"
SLOTS = {"mattina": {"attiva": True, "start": "08:00", "end": "13:00"}, "pomeriggio": {"attiva": True, "start": "13:00", "end": "20:00"}}
FASCE = {D1: SLOTS, D2: SLOTS, D3: {"mattina": {"attiva": True, "start": "09:00", "end": "12:00"}, "pomeriggio": {"attiva": False, "start": "", "end": ""}}}


def _env():
    vals = {}
    for line in open("/app/backend/.env"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            vals[k] = v.strip('"')
    return vals


ENV = _env()
mdb = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
ST = {}


def register(n):
    s = requests.Session()
    email = f"test_{TAG}_{n}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json={"nome": "Test", "cognome": "Agent", "email": email, "password": "TestPass123!",
                                                                   "org_name": f"TEST_Org{n}_{TAG}", "telefono": "+39 333 0000000", "accept_terms": True})
    assert r.status_code == 200, r.text
    u = mdb.users.find_one({"email": email})
    return s, u["org_id"], email


@pytest.fixture(scope="module")
def orgs():
    a = register("a")
    b = register("b")
    yield a, b
    for _, org, email in (a, b):
        for c in ("availabilities", "staff", "avail_links", "events", "persons", "teams", "audit_log", "audit_logs", "settings"):
            mdb[c].delete_many({"org_id": org})
        mdb.settings.delete_many({"id": org})
        mdb.memberships.delete_many({"org_id": org})
        mdb.organizations.delete_many({"id": org})
        mdb.users.delete_many({"email": email})
    open("/tmp/iter204_state.txt", "w").write("cleaned")


@pytest.fixture(scope="module")
def sa(orgs):
    return orgs[0][0]


class TestPersonAvailability:
    def test_01_setup(self, sa, orgs):
        ev = sa.post(f"{BASE_URL}/api/events", json={"nome": f"TEST_EvA {TAG}", "data_inizio": D1, "data_fine": D2, "data_fine_disallestimento": D3,
                                                      "stato": "pianificato", "fasce_disponibilita": FASCE})
        assert ev.status_code in (200, 201), ev.text
        ST["ev"] = ev.json()["id"]
        ev2 = sa.post(f"{BASE_URL}/api/events", json={"nome": f"TEST_EvOther {TAG}", "data_inizio": D1, "data_fine": D1, "stato": "pianificato", "fasce_disponibilita": {D1: SLOTS}})
        ST["ev2"] = ev2.json()["id"]
        p = sa.post(f"{BASE_URL}/api/persons", json={"nome": "TEST_Mario", "cognome": f"TEST_Rossi{TAG}", "email": f"test_m_{TAG}@example.com"})
        assert p.status_code in (200, 201), p.text
        ST["p"] = p.json()["id"]
        for e in (ST["ev"], ST["ev2"]):
            r = sa.post(f"{BASE_URL}/api/staff", json={"persona_id": ST["p"], "evento_id": e, "categoria": "staff"})
            assert r.status_code in (200, 201), r.text
        for nm in ("zeta", "Alfa", "beta"):
            assert sa.post(f"{BASE_URL}/api/teams", json={"nome": f"{nm}", "evento_id": ST["ev"]}).status_code in (200, 201)

    def test_02_fasce_giorni(self, sa):
        r = sa.get(f"{BASE_URL}/api/events/{ST['ev']}/fasce-giorni")
        assert r.status_code == 200, r.text
        days = {d["date"]: d for d in r.json()["days"]}
        assert list(days) == [D1, D2, D3]
        assert days[D1]["fasce"][0] == {"id": "mattina", "label": "Mattina", "start": "08:00", "end": "13:00"}
        assert [f["id"] for f in days[D3]["fasce"]] == ["mattina"]

    def test_03_fasce_giorni_other_org_404(self, orgs):
        sb = orgs[1][0]
        assert sb.get(f"{BASE_URL}/api/events/{ST['ev']}/fasce-giorni").status_code == 404

    def test_04_put_creates_anagrafica_record(self, sa):
        r = sa.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev']}", json={"days": [{"date": D1, "fasce": ["mattina"]}, {"date": D2, "fasce": ["mattina", "pomeriggio"]}]})
        assert r.status_code == 200, r.text
        a = mdb.availabilities.find_one({"org_id": sa_org(), "evento_id": ST["ev"], "persona_id": ST["p"]})
        assert a["origine"] == "anagrafica" and a["ruolo_evento"] == "staff"
        assert a["days"][0] == {"date": D1, "fase": "evento", "fasce": [{"id": "mattina", "start": "08:00", "end": "13:00"}], "dalle": "08:00", "alle": "13:00"}
        assert a["days"][1]["dalle"] == "08:00" and a["days"][1]["alle"] == "20:00"
        assert mdb.availabilities.count_documents({"evento_id": ST["ev"], "persona_id": ST["p"]}) == 1

    def test_05_put_updates_same_record_and_removes_empty(self, sa):
        r = sa.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev']}", json={"days": [{"date": D1, "fasce": []}, {"date": D2, "fasce": ["pomeriggio"]}, {"date": D3, "fasce": ["mattina", "pomeriggio"]}]})
        assert r.status_code == 200, r.text
        avs = list(mdb.availabilities.find({"evento_id": ST["ev"], "persona_id": ST["p"]}))
        assert len(avs) == 1
        d = {x["date"]: x for x in avs[0]["days"]}
        assert set(d) == {D2, D3}
        assert [f["id"] for f in d[D3]["fasce"]] == ["mattina"]  # pomeriggio disabled -> ignored
        assert d[D3]["fase"] == "disallestimento"

    def test_06_date_not_in_event_400(self, sa):
        r = sa.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev']}", json={"days": [{"date": "2027-01-01", "fasce": ["mattina"]}]})
        assert r.status_code == 400, r.text

    def test_07_other_event_untouched(self, sa):
        r = sa.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev2']}", json={"days": [{"date": D1, "fasce": ["pomeriggio"]}]})
        assert r.status_code == 200
        before = mdb.availabilities.find_one({"evento_id": ST["ev2"], "persona_id": ST["p"]}, {"_id": 0})
        sa.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev']}", json={"days": [{"date": D2, "fasce": ["mattina"]}]})
        after = mdb.availabilities.find_one({"evento_id": ST["ev2"], "persona_id": ST["p"]}, {"_id": 0})
        assert before == after

    def test_08_detail_and_enriched(self, sa):
        det = sa.get(f"{BASE_URL}/api/persons/{ST['p']}/detail").json()
        pr = {p["evento_id"]: p for p in det["preferenze"]}
        assert [d["date"] for d in pr[ST["ev"]]["days"]] == [D2]
        assert [f["id"] for f in pr[ST["ev"]]["days"][0]["fasce"]] == ["mattina"]
        en = [x for x in sa.get(f"{BASE_URL}/api/persons-enriched").json() if x["id"] == ST["p"]][0]
        pr2 = {p["evento_id"]: p for p in en["preferenze"]}
        assert [d["date"] for d in pr2[ST["ev"]]["days"]] == [D2]

    def test_09_legacy_keep(self, sa):
        org = sa_org()
        pid = f"TEST_leg_{TAG}"
        mdb.persons.insert_one({"id": pid, "org_id": org, "nome": "TEST_Legacy", "cognome": f"TEST_L{TAG}"})
        ST["leg"] = pid
        mdb.availabilities.insert_one({"id": f"TEST_av_{TAG}", "org_id": org, "evento_id": ST["ev"], "persona_id": pid,
                                       "days": [{"date": D1, "fase": "evento", "dalle": "10:00", "alle": "15:00"},
                                                {"date": D2, "fase": "evento", "dalle": "08:00", "alle": "13:00"}],
                                       "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"})
        r = sa.put(f"{BASE_URL}/api/persons/{pid}/availability/{ST['ev']}", json={"days": [{"date": D1, "keep": True}, {"date": D2, "fasce": ["mattina"]}]})
        assert r.status_code == 200, r.text
        a = mdb.availabilities.find_one({"id": f"TEST_av_{TAG}"})
        assert a["days"][0] == {"date": D1, "fase": "evento", "dalle": "10:00", "alle": "15:00"}
        assert a["days"][1]["fasce"][0]["id"] == "mattina"
        assert mdb.availabilities.count_documents({"evento_id": ST["ev"], "persona_id": pid}) == 1

    def test_10_coverage_once_per_slot(self, sa):
        # add a second (older) duplicate availability for p to verify de-dupe
        mdb.availabilities.insert_one({"id": f"TEST_avold_{TAG}", "org_id": sa_org(), "evento_id": ST["ev"], "persona_id": ST["p"],
                                       "days": [{"date": D2, "fase": "evento", "fasce": [{"id": "mattina", "start": "08:00", "end": "13:00"}], "dalle": "08:00", "alle": "13:00"}],
                                       "created_at": "2025-01-01T00:00:00", "updated_at": "2025-01-01T00:00:00"})
        r = sa.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": ST["ev"], "date": D2, "step": 60})
        assert r.status_code == 200, r.text
        slots = {x["start"]: x for x in r.json()["slots"]}
        assert slots["09:00"]["full"].count(ST["p"]) == 1
        assert ST["p"] in slots["09:00"]["full"] and ST["leg"] in slots["09:00"]["full"]
        assert ST["p"] not in slots.get("15:00", {"full": []})["full"]
        # PUT now targets latest record (anagrafica), old one untouched
        sa.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev']}", json={"days": [{"date": D2, "fasce": ["mattina", "pomeriggio"]}]})
        r = sa.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": ST["ev"], "date": D2, "step": 60})
        slots = {x["start"]: x for x in r.json()["slots"]}
        assert slots["15:00"]["full"].count(ST["p"]) == 1 and slots["09:00"]["full"].count(ST["p"]) == 1
        assert mdb.availabilities.find_one({"id": f"TEST_avold_{TAG}"})["updated_at"] == "2025-01-01T00:00:00"

    def test_11_coverage_team_filter(self, sa):
        teams = [t for t in sa.get(f"{BASE_URL}/api/teams").json() if t.get("evento_id") == ST["ev"]]
        alfa = [t for t in teams if t["nome"] == "Alfa"][0]
        link = [x for x in sa.get(f"{BASE_URL}/api/staff").json() if x["persona_id"] == ST["p"] and x["evento_id"] == ST["ev"]][0]
        sa.put(f"{BASE_URL}/api/staff/{link['id']}", json={"persona_id": ST["p"], "evento_id": ST["ev"], "categoria": "staff", "team_id": alfa["id"]})
        r = sa.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": ST["ev"], "date": D2, "step": 60, "team_id": alfa["id"]})
        slots = {x["start"]: x for x in r.json()["slots"]}
        assert slots["09:00"]["full"] == [ST["p"]]

    def test_12_other_org_cannot_modify(self, sa, orgs):
        sb = orgs[1][0]
        before = mdb.availabilities.find_one({"org_id": sa_org(), "evento_id": ST["ev"], "persona_id": ST["p"], "origine": "anagrafica"}, {"_id": 0})
        assert sb.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev']}", json={"days": []}).status_code == 404
        # org B event + org A person
        evb = sb.post(f"{BASE_URL}/api/events", json={"nome": f"TEST_EvB {TAG}", "data_inizio": D1, "data_fine": D1, "stato": "pianificato"}).json()["id"]
        assert sb.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{evb}", json={"days": [{"date": D1, "fasce": ["mattina"]}]}).status_code == 404
        assert sb.get(f"{BASE_URL}/api/persons/{ST['p']}/detail").status_code in (403, 404)
        after = mdb.availabilities.find_one({"org_id": sa_org(), "evento_id": ST["ev"], "persona_id": ST["p"], "origine": "anagrafica"}, {"_id": 0})
        assert before == after

    def test_13_public_form_then_mask_edit(self, sa):
        r = sa.post(f"{BASE_URL}/api/events/{ST['ev']}/availability/link")
        assert r.status_code in (200, 201), r.text
        code = r.json().get("code")
        em = f"test_pub_{TAG}@example.com"
        body = {"nome": "TEST_Pub", "cognome": f"TEST_P{TAG}", "cellulare": f"+39 333 {int(TAG, 16) % 10000000:07d}", "email": em, "data_nascita": "1990-01-01",
                "days": [{"date": D1, "disponibile": True, "fasce": ["pomeriggio"]}], "preferenza_attivita": "Altro", "preferenza_altro": "TEST", "privacy": True}
        for _ in range(3):
            pr = requests.post(f"{BASE_URL}/api/public/availability/{code}", json=body, headers={"X-Forwarded-For": f"10.204.{int(TAG[:2], 16)}.9"})
            if pr.status_code != 429:
                break
            time.sleep(30)
        assert pr.status_code == 200, pr.text
        a = mdb.availabilities.find_one({"evento_id": ST["ev"], "submitted.email": em})
        assert a and a.get("persona_id")
        ST["pub"] = a["persona_id"]
        rr = sa.put(f"{BASE_URL}/api/persons/{a['persona_id']}/availability/{ST['ev']}", json={"days": [{"date": D1, "fasce": ["mattina", "pomeriggio"]}]})
        assert rr.status_code == 200 and rr.json()["availability_id"] == a["id"]
        a2 = mdb.availabilities.find_one({"id": a["id"]})
        assert [f["id"] for f in a2["days"][0]["fasce"]] == ["mattina", "pomeriggio"]
        assert a2.get("origine") != "anagrafica"
        assert mdb.availabilities.count_documents({"evento_id": ST["ev"], "persona_id": a["persona_id"]}) == 1

    def test_14_bad_payload_types(self, sa):
        r = sa.put(f"{BASE_URL}/api/persons/{ST['p']}/availability/{ST['ev']}", json={"days": [{"date": D2, "fasce": 5}]})
        assert r.status_code < 500, f"server error on bad fasce type: {r.status_code}"


_ORG = {}


def sa_org():
    if "a" not in _ORG:
        _ORG["a"] = mdb.users.find_one({"email": f"test_{TAG}_a@example.com"})["org_id"]
    return _ORG["a"]
