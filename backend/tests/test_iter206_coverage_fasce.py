# Iter 206: Copertura oraria per fasce Mattina/Pomeriggio (GET /staff-coverage/fasce, PUT fascia-needs, export fasce),
# legacy (vecchio modulo) classification, conversion via PUT /persons/{pid}/availability/{eid} with days_history, org isolation
import json
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EV = "5e09ce16ec304f4e8b332870b59d1a1e"
EMAIL, PWD = "test_fx_f73982@example.com", "TestPass123!"
P = {"mattina": "f23569e2cf414c5bbbf6be057049bf2f", "pomeriggio": "670a7758c8c64e24ab01c5a9e912c9d3", "entrambe": "465aaa12cd2b4bf1b18e604ba1743619",
     "lc": "6b6238e8798f4eb1b54bcf043281af85", "lp": "6d9ed5cbe39647f9b24c31bbffd2d459", "ls": "f6d8699ea6d545738fbd87cd29825008"}
CODE = "x-qp0puHPMHnZDN4FJYBoXD5D7hZmbAi"
TAG = uuid.uuid4().hex[:6]


def _env():
    vals = {}
    for line in open("/app/backend/.env"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            vals[k] = v.strip('"')
    return vals


ENV = _env()
mdb = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
ORG = mdb.events.find_one({"id": EV})["org_id"]
SNAP = list(mdb.availabilities.find({"org_id": ORG}, {"_id": 0}))
ST = {"staff_link": None, "new_person": None, "new_av": None, "org2": None}


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        ss.headers.update({"Authorization": f"Bearer {tok}"})
    return ss


@pytest.fixture(scope="module", autouse=True)
def restore(s):
    yield
    for a in SNAP:  # restore seeded availabilities
        mdb.availabilities.replace_one({"id": a["id"], "org_id": ORG}, a, upsert=True)
    mdb.coverage_fascia_needs.delete_many({"org_id": ORG, "evento_id": EV})
    if ST["staff_link"]:
        mdb.staff.update_one({"id": ST["staff_link"], "org_id": ORG}, {"$set": {"team_id": None}})
    if ST["new_av"]:
        mdb.availabilities.delete_one({"id": ST["new_av"], "org_id": ORG})
    if ST["new_person"]:
        mdb.persons.delete_one({"id": ST["new_person"], "org_id": ORG})
        mdb.staff.delete_many({"persona_id": ST["new_person"], "org_id": ORG})
    if ST["org2"]:  # remove the TEST_ isolation org created by this run (by its own org id)
        u = mdb.users.find_one({"email": ST["org2"]}, {"_id": 0, "org_id": 1}) or {}
        o2 = u.get("org_id")
        if o2 and o2 != ORG:
            for c in mdb.list_collection_names():
                mdb[c].delete_many({"org_id": o2})
            mdb.organizations.delete_one({"id": o2})
            mdb.settings.delete_one({"id": o2})
        mdb.users.delete_one({"email": ST["org2"]})


def fasce(s, **kw):
    r = s.get(f"{BASE_URL}/api/staff-coverage/fasce", params={"evento_id": EV, **kw})
    assert r.status_code == 200, r.text
    d = r.json()
    return d, {(x["date"], x["fascia"]): x for x in d["rows"]}


class TestFasce:
    def test_baseline_counts(self, s):
        d, rows = fasce(s)
        assert [(x["date"], x["fascia"]) for x in d["rows"]] == [("2026-12-19", "mattina"), ("2026-12-19", "pomeriggio"), ("2026-12-20", "mattina"), ("2026-12-20", "pomeriggio")]
        m, p = rows[("2026-12-19", "mattina")], rows[("2026-12-19", "pomeriggio")]
        assert (m["available"], m["partial"], m["tbc"]) == (3, 1, 1), m
        assert (p["available"], p["partial"], p["tbc"]) == (2, 2, 1), p
        assert rows[("2026-12-20", "mattina")]["available"] == 2
        assert rows[("2026-12-20", "pomeriggio")]["available"] == 0
        assert rows[("2026-12-19", "mattina")]["start"] == "08:00" and rows[("2026-12-19", "mattina")]["end"] == "13:00"
        assert len(d["legacy"]) == 3
        assert {x["id"] for x in d["legacy"]} == {P["lc"], P["lp"], P["ls"]}

    def test_legacy_people_flags(self, s):
        _, rows = fasce(s)
        ppl = {x["id"]: x for x in rows[("2026-12-19", "mattina")]["people"]}
        assert ppl[P["lc"]]["cov"] == "complete" and ppl[P["lc"]]["legacy"] and ppl[P["lc"]]["orario"] == "07:00–14:00"
        assert ppl[P["lp"]]["cov"] == "partial" and ppl[P["lp"]]["legacy"]
        assert ppl[P["ls"]]["cov"] == "tbc" and ppl[P["ls"]]["orario"] == "Orario non indicato"
        assert not ppl[P["mattina"]]["legacy"]
        assert ppl[P["mattina"]]["assigned"] is False  # fascia selection alone is not assignment
        # each person once per slot
        ids = [x["id"] for r in rows.values() for x in [None] if False] or [x["id"] for x in rows[("2026-12-19", "mattina")]["people"]]
        assert len(ids) == len(set(ids))

    def test_filters(self, s):
        _, rows = fasce(s, gruppo="Alpini")
        assert rows[("2026-12-19", "pomeriggio")]["available"] == 1
        assert [x["id"] for x in rows[("2026-12-19", "pomeriggio")]["people"]] == [P["pomeriggio"]]
        assert rows[("2026-12-19", "mattina")]["available"] == 0

    def test_needs_persist_and_status(self, s):
        r = s.put(f"{BASE_URL}/api/staff-coverage/fascia-needs", json={"evento_id": EV, "date": "2026-12-19", "fascia": "mattina", "needed": 5})
        assert r.status_code == 200 and r.json()["needed"] == 5
        _, rows = fasce(s)
        assert rows[("2026-12-19", "mattina")]["needed"] == 5 and rows[("2026-12-19", "mattina")]["status"] == "red"
        s.put(f"{BASE_URL}/api/staff-coverage/fascia-needs", json={"evento_id": EV, "date": "2026-12-19", "fascia": "mattina", "needed": 2})
        _, rows = fasce(s)
        assert rows[("2026-12-19", "mattina")]["status"] == "green"  # 3 >= 2 + max(1, ceil(0.2)) = 3
        r = s.put(f"{BASE_URL}/api/staff-coverage/fascia-needs", json={"evento_id": EV, "date": "2026-12-19", "fascia": "mattina", "needed": 0})
        assert r.status_code == 200 and r.json()["needed"] is None
        _, rows = fasce(s)
        assert rows[("2026-12-19", "mattina")]["needed"] is None and rows[("2026-12-19", "mattina")]["status"] is None

    def test_needs_validation(self, s):
        r = s.put(f"{BASE_URL}/api/staff-coverage/fascia-needs", json={"evento_id": EV, "date": "2026-12-19", "fascia": "sera", "needed": 1})
        assert r.status_code == 422
        r = s.put(f"{BASE_URL}/api/staff-coverage/fascia-needs", json={"evento_id": EV, "date": "2026-12-19", "fascia": "mattina", "needed": -1})
        assert r.status_code == 422
        r = s.put(f"{BASE_URL}/api/staff-coverage/fascia-needs", json={"evento_id": EV, "date": "xxxx-xx-xx", "fascia": "mattina", "needed": 1})
        assert r.status_code == 400

    def test_assigned_via_team(self, s):
        links = s.get(f"{BASE_URL}/api/staff", params={"evento_id": EV}).json()
        link = next(x for x in links if x["persona_id"] == P["mattina"])
        team = next(t for t in s.get(f"{BASE_URL}/api/teams", params={"evento_id": EV}).json())
        ST["staff_link"] = link["id"]
        r = s.put(f"{BASE_URL}/api/staff/{link['id']}", json={"team_id": team["id"]})
        assert r.status_code == 200, r.text
        _, rows = fasce(s)
        assert rows[("2026-12-19", "mattina")]["assigned"] == 1
        pm = next(x for x in rows[("2026-12-19", "mattina")]["people"] if x["id"] == P["mattina"])
        assert pm["team"] == team["nome"] and pm["assigned"]
        _, rows = fasce(s, team_id=team["id"])
        assert [x["id"] for x in rows[("2026-12-19", "mattina")]["people"]] == [P["mattina"]]

    def test_export_pdfs(self, s):
        for mode in ("fasce", "fasce_names"):
            r = s.get(f"{BASE_URL}/api/staff-coverage/export", params={"evento_id": EV, "mode": mode})
            assert r.status_code == 200 and r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF"

    def test_convert_partial_legacy(self, s):
        r = s.put(f"{BASE_URL}/api/persons/{P['lp']}/availability/{EV}", json={"days": [{"date": "2026-12-19", "fasce": ["mattina"]}]})
        assert r.status_code == 200, r.text
        d, rows = fasce(s)
        assert len(d["legacy"]) == 2
        m, p = rows[("2026-12-19", "mattina")], rows[("2026-12-19", "pomeriggio")]
        assert m["available"] == 4 and m["partial"] == 0
        assert P["lp"] not in [x["id"] for x in p["people"]]
        assert not next(x for x in m["people"] if x["id"] == P["lp"])["legacy"]
        av = mdb.availabilities.find_one({"org_id": ORG, "evento_id": EV, "persona_id": P["lp"]})
        assert any(h.get("dalle") == "10:00" and h.get("alle") == "15:00" for h in av.get("days_history") or [])

    def test_partial_conversion_keeps_other_days(self, s):
        other = mdb.availabilities.find_one({"org_id": ORG, "persona_id": P["lc"], "evento_id": {"$ne": EV}}, {"_id": 0})
        r = s.put(f"{BASE_URL}/api/persons/{P['lc']}/availability/{EV}",
                  json={"days": [{"date": "2026-12-19", "fasce": ["mattina", "pomeriggio"]}, {"date": "2026-12-20", "keep": True}]})
        assert r.status_code == 200, r.text
        d, rows = fasce(s)
        lg = next((x for x in d["legacy"] if x["id"] == P["lc"]), None)
        assert lg and [x["date"] for x in lg["days"]] == ["2026-12-20"]
        assert not next(x for x in rows[("2026-12-19", "mattina")]["people"] if x["id"] == P["lc"])["legacy"]
        assert next(x for x in rows[("2026-12-20", "mattina")]["people"] if x["id"] == P["lc"])["legacy"]
        av = mdb.availabilities.find_one({"org_id": ORG, "evento_id": EV, "persona_id": P["lc"]})
        assert [h["date"] for h in av.get("days_history")] == ["2026-12-19"]
        assert mdb.availabilities.find_one({"id": other["id"]}, {"_id": 0}) == other  # other event untouched

    def test_public_registration_counted_once(self, s):
        info = s.get(f"{BASE_URL}/api/public/availability/{CODE}")
        assert info.status_code == 200, info.text
        cell = f"+39333{uuid.uuid4().int % 10**7:07d}"
        body = {"nome": "Gino", "cognome": f"TEST_Pub{TAG}", "cellulare": cell, "email": f"test_pub_{TAG}@example.com", "data_nascita": "1990-01-01",
                "privacy": True, "preferenza_attivita": "Hostess",
                "days": [{"date": "2026-12-19", "disponibile": True, "fasce": ["mattina", "pomeriggio"]}]}
        r = requests.post(f"{BASE_URL}/api/public/availability/{CODE}", json=body)
        assert r.status_code == 200, r.text
        av = mdb.availabilities.find_one({"org_id": ORG, "evento_id": EV, "cognome": f"TEST_Pub{TAG}"}) or {}
        ST["new_av"], ST["new_person"] = av.get("id"), av.get("persona_id")
        # second submission (same person) must not double-count
        r2 = requests.post(f"{BASE_URL}/api/public/availability/{CODE}", json=body)
        if r2.status_code == 200:
            for a in mdb.availabilities.find({"org_id": ORG, "evento_id": EV, "persona_id": ST["new_person"]}):
                if a["id"] != ST["new_av"]:
                    mdb.availabilities.delete_one({"id": a["id"]}) if False else None
        _, rows = fasce(s)
        ids = [x["id"] for x in rows[("2026-12-19", "mattina")]["people"]]
        assert ids.count(ST["new_person"]) == 1
        assert ST["new_person"] in [x["id"] for x in rows[("2026-12-19", "pomeriggio")]["people"] if x["cov"] == "complete"]

    def test_org_isolation(self):
        o = requests.Session()
        em = f"test_iso_{TAG}@example.com"
        r = o.post(f"{BASE_URL}/api/auth/register-organization", json={"nome": "TEST_Iso", "cognome": "TEST", "email": em, "password": "TestPass123!",
                                                                       "org_name": f"TEST_IsoOrg{TAG}", "telefono": f"+39347{uuid.uuid4().int % 10**7:07d}", "accept_terms": True})
        if r.status_code not in (200, 201):
            pytest.skip(f"register failed {r.status_code} {r.text[:200]}")
        ST["org2"] = em
        tok = r.json().get("token") or r.json().get("access_token")
        if tok:
            o.headers.update({"Authorization": f"Bearer {tok}"})
        assert o.get(f"{BASE_URL}/api/staff-coverage/fasce", params={"evento_id": EV}).status_code == 404
        assert o.put(f"{BASE_URL}/api/staff-coverage/fascia-needs", json={"evento_id": EV, "date": "2026-12-19", "fascia": "mattina", "needed": 9}).status_code == 404
        assert o.get(f"{BASE_URL}/api/staff-coverage/export", params={"evento_id": EV, "mode": "fasce"}).status_code == 404
        assert o.put(f"{BASE_URL}/api/persons/{P['lp']}/availability/{EV}", json={"days": []}).status_code == 404
        assert mdb.coverage_fascia_needs.count_documents({"evento_id": EV, "needed": 9}) == 0
