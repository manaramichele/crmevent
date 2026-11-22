# Iter 203: fasce Mattina/Pomeriggio per giorno (Event.fasce_disponibilita), modulo pubblico, fasce-stale/sync, copertura, PDF
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
DEMO = "b7f40862230441b9a0bedabefe8dab49"
EMAIL = "manara.michele.pro@gmail.com"
PWD = "CrmEvent2026!"
TAG = uuid.uuid4().hex[:6]
D1, D2, D3 = "2030-06-09", "2030-06-10", "2030-06-11"


def _env():
    vals = {}
    for line in open("/app/backend/.env"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            vals[k] = v.strip('"')
    return vals


ENV = _env()
mdb = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
ST = {"event": None, "code": None, "persons": set(), "legacy_av": None}

FASCE = {
    D1: {"mattina": {"attiva": True, "start": "08:00", "end": "12:00"}, "pomeriggio": {"attiva": False, "start": "", "end": ""}},
    D2: {"mattina": {"attiva": True, "start": "08:00", "end": "13:00"}, "pomeriggio": {"attiva": True, "start": "13:00", "end": "20:00"}},
    D3: {"mattina": {"attiva": True, "start": "09:00", "end": "12:00"}, "pomeriggio": {"attiva": True, "start": "14:00", "end": "18:00"}},
}


def ev_payload(fasce):
    return {"nome": f"TEST_Fasce {TAG}", "data_inizio_allestimento": D1, "data_inizio": D2, "data_fine": D2,
            "data_fine_disallestimento": D3, "stato": "pianificato", "fasce_disponibilita": fasce}


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip("login failed")
    ss.headers.update({"X-Org-Id": DEMO})
    return ss


@pytest.fixture(scope="module", autouse=True)
def cleanup(s):
    yield
    eid = ST["event"]
    if os.environ.get("KEEP_FX"):
        open("/tmp/fx_state.txt", "w").write(f"{eid} {ST['code']} {TAG}")
        return
    if eid:
        av = list(mdb.availabilities.find({"org_id": DEMO, "evento_id": eid}, {"persona_id": 1}))
        ST["persons"] |= {a["persona_id"] for a in av if a.get("persona_id")}
        mdb.availabilities.delete_many({"org_id": DEMO, "evento_id": eid})
        mdb.staff.delete_many({"org_id": DEMO, "evento_id": eid})
        mdb.avail_links.delete_many({"org_id": DEMO, "evento_id": eid})
        mdb.events.delete_one({"org_id": DEMO, "id": eid})
    pids = [p for p in ST["persons"] if p]
    if pids:
        mdb.persons.delete_many({"org_id": DEMO, "id": {"$in": pids}, "nome": {"$regex": "^Test_|^TEST_", "$options": "i"}})


def submit(code, nome, email, days, ip):
    body = {"nome": f"TEST_{nome}", "cognome": f"TEST_Fx{TAG}", "cellulare": f"+39 333 {abs(hash(email)) % 10000000:07d}",
            "email": email, "data_nascita": "1990-01-01", "days": days, "preferenza_attivita": "Altro",
            "preferenza_altro": "TEST", "privacy": True}
    for _ in range(3):
        r = requests.post(f"{BASE_URL}/api/public/availability/{code}", json=body, headers={"X-Forwarded-For": ip})
        if r.status_code != 429:
            return r
        time.sleep(30)
    return r


class TestFasce:
    def test_01_create_event_with_fasce(self, s):
        r = s.post(f"{BASE_URL}/api/events", json=ev_payload(FASCE))
        assert r.status_code in (200, 201), r.text
        ST["event"] = r.json()["id"]
        g = s.get(f"{BASE_URL}/api/events/{ST['event']}").json()
        f = g["fasce_disponibilita"]
        assert f[D1]["pomeriggio"]["attiva"] is False and f[D1]["pomeriggio"]["start"] is None
        assert f[D2]["mattina"] == {"attiva": True, "start": "08:00", "end": "13:00"}

    def test_02_invalid_end_before_start_422(self, s):
        bad = {**FASCE, D2: {"mattina": {"attiva": True, "start": "13:00", "end": "08:00"}, "pomeriggio": FASCE[D2]["pomeriggio"]}}
        r = s.put(f"{BASE_URL}/api/events/{ST['event']}", json=ev_payload(bad))
        assert r.status_code == 422, r.text
        assert "successivo" in r.text

    def test_03_overlap_422(self, s):
        bad = {**FASCE, D2: {"mattina": {"attiva": True, "start": "08:00", "end": "14:00"}, "pomeriggio": {"attiva": True, "start": "13:00", "end": "20:00"}}}
        r = s.put(f"{BASE_URL}/api/events/{ST['event']}", json=ev_payload(bad))
        assert r.status_code == 422
        assert "sovrappongono" in r.text
        # disabled slot overlap is allowed
        ok = {**FASCE, D2: {"mattina": {"attiva": True, "start": "08:00", "end": "14:00"}, "pomeriggio": {"attiva": False, "start": "13:00", "end": "20:00"}}}
        r2 = s.put(f"{BASE_URL}/api/events/{ST['event']}", json=ev_payload(ok))
        assert r2.status_code == 200, r2.text
        r3 = s.put(f"{BASE_URL}/api/events/{ST['event']}", json=ev_payload(FASCE))
        assert r3.status_code == 200

    def test_04_link_and_public_days(self, s):
        r = s.post(f"{BASE_URL}/api/events/{ST['event']}/availability/link")
        assert r.status_code in (200, 201), r.text
        ST["code"] = r.json().get("code") or r.json()["url"].rsplit("/", 1)[-1]
        p = requests.get(f"{BASE_URL}/api/public/availability/{ST['code']}").json()
        days = {d["date"]: d for d in p["days"]}
        assert list(days) == [D1, D2, D3]
        assert [x["id"] for x in days[D1]["fasce"]] == ["mattina"]
        assert days[D2]["fasce"][1] == {"id": "pomeriggio", "label": "Pomeriggio", "start": "13:00", "end": "20:00"}

    def test_05_submit_variants(self, s):
        c = ST["code"]
        base = f"10.203.{int(TAG[:2], 16)}."
        rA = submit(c, "Alfa", f"test_a_{TAG}@example.com", [{"date": D2, "disponibile": True, "fasce": ["mattina"]}], base + "1")
        assert rA.status_code == 200, rA.text
        rB = submit(c, "Beta", f"test_b_{TAG}@example.com", [{"date": D2, "disponibile": True, "fasce": ["pomeriggio"]},
                                                              {"date": D3, "disponibile": True, "fasce": ["mattina", "pomeriggio"]}], base + "2")
        assert rB.status_code == 200, rB.text
        rC = submit(c, "Gamma", f"test_c_{TAG}@example.com", [{"date": D1, "disponibile": True, "fasce": ["mattina"]},
                                                               {"date": D2, "disponibile": True, "fasce": ["mattina", "pomeriggio"]}], base + "3")
        assert rC.status_code == 200, rC.text
        av = {a["submitted"]["email"]: a for a in mdb.availabilities.find({"org_id": DEMO, "evento_id": ST["event"]}, {"_id": 0})}
        a = av[f"test_a_{TAG}@example.com"]["days"]
        assert a == [{"date": D2, "fase": "evento", "fasce": [{"id": "mattina", "start": "08:00", "end": "13:00"}], "dalle": "08:00", "alle": "13:00"}]
        b = av[f"test_b_{TAG}@example.com"]["days"]
        assert b[1]["fase"] == "disallestimento" and b[1]["dalle"] == "09:00" and b[1]["alle"] == "18:00" and len(b[1]["fasce"]) == 2
        cc = av[f"test_c_{TAG}@example.com"]["days"]
        assert cc[0]["fase"] == "allestimento" and cc[1]["dalle"] == "08:00" and cc[1]["alle"] == "20:00"

    def test_06_disabled_slot_and_empty_slot_rejected(self):
        c = ST["code"]
        base = f"10.204.{int(TAG[:2], 16)}."
        r = submit(c, "Delta", f"test_d_{TAG}@example.com", [{"date": D1, "disponibile": True, "fasce": ["pomeriggio"]},
                                                              {"date": D2, "disponibile": True, "fasce": ["mattina"]}], base + "1")
        assert r.status_code == 400 and "Mattina e/o Pomeriggio" in r.text, r.text
        r = submit(c, "Delta", f"test_d_{TAG}@example.com", [{"date": D2, "disponibile": True, "fasce": []}], base + "2")
        assert r.status_code == 400, r.text

    def test_07_resubmit_no_duplicate(self):
        c = ST["code"]
        em = f"test_a_{TAG}@example.com"
        r = submit(c, "Alfa", em, [{"date": D2, "disponibile": True, "fasce": ["mattina", "pomeriggio"]}], f"10.205.{int(TAG[:2], 16)}.1")
        assert r.status_code == 200, r.text
        assert mdb.persons.count_documents({"org_id": DEMO, "email": em}) == 1
        avs = list(mdb.availabilities.find({"org_id": DEMO, "evento_id": ST["event"], "submitted.email": em}))
        assert len(avs) == 1 and len(avs[0]["days"][0]["fasce"]) == 2
        # revert A to mattina only for later checks
        time.sleep(1)
        r = submit(c, "Alfa", em, [{"date": D2, "disponibile": True, "fasce": ["mattina"]}], f"10.205.{int(TAG[:2], 16)}.2")
        assert r.status_code == 200

    def test_08_legacy_and_coverage(self, s):
        eid = ST["event"]
        pid = f"TEST_fx_legacy_{TAG}"
        mdb.persons.insert_one({"id": pid, "org_id": DEMO, "nome": "TEST_Legacy", "cognome": f"TEST_Fx{TAG}"})
        ST["persons"].add(pid)
        mdb.availabilities.insert_one({"id": f"TEST_av_{TAG}", "org_id": DEMO, "evento_id": eid, "persona_id": pid,
                                       "days": [{"date": D2, "fase": "evento", "dalle": "10:00", "alle": "15:00"}],
                                       "created_at": "2030-01-01T00:00:00", "updated_at": "2030-01-01T00:00:00"})
        r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": eid, "date": D2, "step": 60})
        assert r.status_code == 200, r.text
        slots = {x["start"]: x for x in r.json()["slots"]}
        names = {k: v.get("nome") for k, v in r.json()["people"].items()}
        def who(t):
            return sorted(names[p] for p in slots[t]["full"])
        assert who("09:00") == ["Test_Alfa", "Test_Gamma"] or who("09:00") == ["TEST_Alfa", "TEST_Gamma"], who("09:00")
        assert len(slots["10:00"]["full"]) == 3  # A, C, legacy
        assert len(slots["14:00"]["full"]) == 3  # B, C, legacy
        assert len(slots["16:00"]["full"]) == 2  # B, C
        assert "20:00" not in slots or len(slots["20:00"]["full"]) == 0

    def test_09_pdf_volunteers_disp_columns(self, s):
        eid = ST["event"]
        mdb.staff.update_many({"org_id": DEMO, "evento_id": eid}, {"$set": {"categoria": "volontario"}})
        r = s.post(f"{BASE_URL}/api/staff/export-pdf", json={"section": "volontari", "evento_id": eid, "person_ids": None,
                                                             "team_ids": None, "columns": ["disp_dal", "disp_al"]})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF"

    def test_10_stale_and_sync(self, s):
        eid = ST["event"]
        assert s.get(f"{BASE_URL}/api/events/{eid}/fasce-stale").json()["stale"] == 0
        new = {**FASCE, D2: {"mattina": {"attiva": True, "start": "07:30", "end": "12:30"}, "pomeriggio": FASCE[D2]["pomeriggio"]}}
        assert s.put(f"{BASE_URL}/api/events/{eid}", json=ev_payload(new)).status_code == 200
        st = s.get(f"{BASE_URL}/api/events/{eid}/fasce-stale").json()["stale"]
        assert st == 2, st  # A and C have D2 mattina
        r = s.post(f"{BASE_URL}/api/events/{eid}/fasce-sync")
        assert r.status_code == 200 and r.json()["updated"] == 2
        a = mdb.availabilities.find_one({"org_id": DEMO, "evento_id": eid, "submitted.email": f"test_a_{TAG}@example.com"})
        assert a["days"][0]["fasce"] == [{"id": "mattina", "start": "07:30", "end": "12:30"}]
        assert a["days"][0]["dalle"] == "07:30" and a["days"][0]["alle"] == "12:30"
        c = mdb.availabilities.find_one({"org_id": DEMO, "evento_id": eid, "submitted.email": f"test_c_{TAG}@example.com"})
        assert [f["id"] for f in c["days"][1]["fasce"]] == ["mattina", "pomeriggio"] and c["days"][1]["alle"] == "20:00"
        legacy = mdb.availabilities.find_one({"id": f"TEST_av_{TAG}"})
        assert legacy["days"][0]["dalle"] == "10:00" and "fasce" not in legacy["days"][0]
        assert s.get(f"{BASE_URL}/api/events/{eid}/fasce-stale").json()["stale"] == 0

    def test_11_stale_other_org_404(self, s):
        r = requests.Session()
        r.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
        r.headers.update({"X-Org-Id": "org_qa_eventi"})
        assert r.get(f"{BASE_URL}/api/events/{ST['event']}/fasce-stale").status_code == 404
        assert r.post(f"{BASE_URL}/api/events/{ST['event']}/fasce-sync").status_code == 404
