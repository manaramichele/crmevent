# Copertura oraria Staff/Volontari: GET /api/staff-coverage, /matrix, /needs, /config, /export
import io
import os
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
DEMO = "b7f40862230441b9a0bedabefe8dab49"
OTHER = "org_qa_eventi"
EMAIL = "manara.michele.pro@gmail.com"
PWD = "CrmEvent2026!"
H = {"X-Org-Id": DEMO}

TAG = uuid.uuid4().hex[:6]
EVT = f"TEST_cov_evt_{TAG}"
P = {k: f"TEST_cov_{k}_{TAG}" for k in ("full", "part", "multi", "tbc", "overlap", "latest", "nodisp", "linkonly", "vol")}


def _env():
    vals = {}
    for line in open("/app/backend/.env"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            vals[k] = v.strip('"')
    return vals


ENV = _env()
mdb = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
CREATED = {"staff": [], "needs": []}


def _av(pid, days, ts, pref=None):
    return {"id": f"TEST_av_{uuid.uuid4().hex[:8]}", "org_id": DEMO, "evento_id": EVT, "persona_id": pid, "days": days,
            "preferenza_attivita": pref, "created_at": ts, "updated_at": ts}


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip("login failed")
    ss.headers.update(H)
    return ss


@pytest.fixture(scope="module", autouse=True)
def seed(s):
    mdb.events.insert_one({"id": EVT, "org_id": DEMO, "nome": f"TEST_Copertura {TAG}", "data_inizio": "2030-05-10", "data_fine": "2030-05-11"})
    names = {"full": ("Alfa", "Zeta"), "part": ("Beta", "Bravo"), "multi": ("Gamma", "Charlie"), "tbc": ("Delta", "Delta"),
             "overlap": ("Eco", "Echo"), "latest": ("Foxtrot", "Fox"), "nodisp": ("Golf", "Golf"), "linkonly": ("Hotel", "Hotel"), "vol": ("India", "India")}
    mdb.persons.insert_many([{"id": P[k], "org_id": DEMO, "nome": f"TEST_{n}", "cognome": f"TEST_{c}", "cellulare": "+39000000000" + str(i),
                              "gruppo_appartenenza": "TEST_GrpCov" if k in ("full", "part") else None, "taglia": "M"}
                             for i, (k, (n, c)) in enumerate(names.items())])
    d = "2030-05-10"
    mdb.availabilities.insert_many([
        _av(P["full"], [{"date": d, "dalle": "08:00", "alle": "12:00", "disponibile": True}], "2030-01-01T10:00:00"),
        _av(P["part"], [{"date": d, "dalle": "08:30", "alle": "10:00", "disponibile": True}], "2030-01-01T10:00:00"),
        _av(P["multi"], [{"date": d, "dalle": "22:00", "alle": "02:00"}, {"date": "2030-05-11", "dalle": "10:00", "alle": "11:00"}], "2030-01-01T10:00:00"),
        _av(P["tbc"], [{"date": d, "dalle": None, "alle": None}], "2030-01-01T10:00:00"),
        _av(P["overlap"], [{"date": d, "dalle": "08:00", "alle": "10:00"}, {"date": d, "dalle": "09:00", "alle": "11:00"}], "2030-01-01T10:00:00"),
        _av(P["latest"], [{"date": d, "dalle": "08:00", "alle": "12:00"}], "2030-01-01T10:00:00"),
        _av(P["latest"], [{"date": d, "dalle": "14:00", "alle": "15:00"}], "2030-02-01T10:00:00"),
        _av(P["nodisp"], [{"date": d, "dalle": "08:00", "alle": "12:00", "disponibile": False}], "2030-01-01T10:00:00"),
        _av(P["vol"], [{"date": d, "dalle": "08:00", "alle": "09:00"}], "2030-01-01T10:00:00", pref="TEST_Ristoro"),
    ])
    for pid, body in ((P["full"], {"categoria": "staff", "ruolo": "TEST_Segreteria"}),
                      (P["linkonly"], {"categoria": "staff", "ruolo": "TEST_Segreteria", "data_arrivo": d, "ora_arrivo": "09:00",
                                       "data_partenza": d, "ora_partenza": "11:00"}),
                      (P["vol"], {"categoria": "volontario"})):
        r = s.post(f"{BASE_URL}/api/staff", json={"persona_id": pid, "evento_id": EVT, **body})
        assert r.status_code in (200, 201), r.text
        CREATED["staff"].append(r.json()["id"])
    yield
    for sid in CREATED["staff"]:
        s.delete(f"{BASE_URL}/api/staff/{sid}")
    for nid in CREATED["needs"]:
        s.delete(f"{BASE_URL}/api/staff-coverage/needs/{nid}")
    mdb.staff.delete_many({"id": {"$in": CREATED["staff"]}})
    mdb.availabilities.delete_many({"org_id": DEMO, "evento_id": EVT})
    mdb.persons.delete_many({"id": {"$in": list(P.values())}})
    mdb.coverage_needs.delete_many({"org_id": DEMO, "evento_id": EVT})
    mdb.events.delete_one({"id": EVT, "org_id": DEMO})


def cov(s, **kw):
    r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": EVT, "date": "2030-05-10", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def slot(d, start):
    return next(x for x in d["slots"] if x["start"] == start)


class TestCompute:
    def test_full_partial_overlap_latest(self, s):
        d = cov(s)
        s8 = slot(d, "08:00")
        assert P["full"] in s8["full"]
        assert P["part"] in s8["partial"] and P["part"] not in s8["full"]
        assert P["overlap"] in s8["full"]
        assert P["latest"] not in s8["full"] + s8["partial"]  # latest record (14-15) wins
        assert P["nodisp"] not in s8["full"] + s8["partial"]
        s9 = slot(d, "09:00")
        ids = s9["full"] + s9["partial"]
        assert len(ids) == len(set(ids)) and P["overlap"] in s9["full"]
        assert P["linkonly"] in s9["full"]
        assert P["latest"] in slot(d, "14:00")["full"]
        assert d["kpis"]["tbc"] == 1 and P["tbc"] in d["tbc"]
        assert d["people"][P["tbc"]]["orario"] == "Orario da confermare"

    def test_overnight_and_multiday(self, s):
        d = cov(s)
        assert P["multi"] in slot(d, "23:00")["full"]
        assert d["slots"][-1]["end"] == "24:00"
        d2 = cov(s, date="2030-05-11")
        assert P["multi"] in slot(d2, "00:00")["full"] and P["multi"] in slot(d2, "01:00")["full"]
        assert P["multi"] in slot(d2, "10:00")["full"]
        assert "2030-05-10" in d["days"] and "2030-05-11" in d["days"]

    def test_step_30_15(self, s):
        d = cov(s, step=30)
        assert P["part"] in slot(d, "08:30")["full"] and P["part"] not in slot(d, "08:00")["full"] + slot(d, "08:00")["partial"]
        d = cov(s, step=15)
        assert slot(d, "08:15")["end"] == "08:30"
        r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": EVT, "date": "2030-05-10", "step": 20})
        assert r.status_code == 400

    def test_filters(self, s):
        d = cov(s, mansione="TEST_Segreteria")
        ids = set(slot(d, "09:00")["full"] + slot(d, "09:00")["partial"])
        assert ids == {P["full"], P["linkonly"]}
        assert slot(d, "09:00")["assigned"] == 2
        d = cov(s, mansione="TEST_Ristoro")  # preferred activity
        assert set(slot(d, "08:00")["full"]) == {P["vol"]} and slot(d, "08:00")["assigned"] == 0
        d = cov(s, cat="volontari")
        assert set(d["people"]) == {P["vol"]}
        d = cov(s, cat="staff")
        assert set(d["people"]) == {P["full"], P["linkonly"]}
        d = cov(s, gruppo="TEST_GrpCov")
        assert set(d["people"]) == {P["full"], P["part"]}
        assert "TEST_Segreteria" in cov(s)["mansioni"]

    def test_assigned_all(self, s):
        s8 = slot(cov(s), "08:00")
        assert s8["assigned"] == 1  # only 'full' has ruolo at 08:00

    def test_org_isolation(self, s):
        r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": EVT}, headers={"X-Org-Id": OTHER})
        assert r.status_code == 404
        r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": "demo_evt_bcr"}, headers={"X-Org-Id": OTHER})
        assert r.status_code == 404

    def test_matrix(self, s):
        r = s.get(f"{BASE_URL}/api/staff-coverage/matrix", params={"evento_id": EVT})
        assert r.status_code == 200
        m = r.json()
        assert m["days"][:2] == ["2030-05-10", "2030-05-11"]
        row0 = next(x for x in m["rows"] if x["start"] == "00:00")
        assert row0["cells"][1] == 1 and m["tbc"]["2030-05-10"] == 1


class TestDemoBcr:
    def test_overnight_days(self, s):
        r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": "demo_evt_bcr", "date": "2026-10-17"})
        assert r.status_code == 200
        d = r.json()
        assert d["slots"][0]["start"] == "16:00" and d["slots"][-1]["end"] == "24:00"
        assert all(x["available"] == 12 for x in d["slots"])
        r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": "demo_evt_bcr", "date": "2026-10-18"})
        d = r.json()
        assert d["slots"][0]["start"] == "00:00"
        assert slot(d, "00:00")["available"] == 12 and slot(d, "08:00")["available"] == 34
        assert d["kpis"]["max"] == 34 and d["kpis"]["min"] == 12
        assert d["days"] == ["2026-10-17", "2026-10-18"]


class TestNeedsAndExport:
    def test_needs_status(self, s):
        s.put(f"{BASE_URL}/api/staff-coverage/config", json={"yellow_margin_pct": 10})
        base = slot(cov(s), "08:00")["available"]  # 5 people
        res = {}
        for start, needed in (("08:00", base + 1), ("09:00", None), ("10:00", None)):
            pass
        # 08:00 red, 09:00 yellow (needed == avail -> avail < needed+1), 14:00 green
        a9 = slot(cov(s), "09:00")["available"]
        a14 = slot(cov(s), "14:00")["available"]
        for st, en, n in (("08:00", "09:00", base + 1), ("09:00", "10:00", a9), ("14:00", "15:00", max(1, a14 - 1) if a14 > 1 else 1)):
            r = s.post(f"{BASE_URL}/api/staff-coverage/needs", json={"evento_id": EVT, "mansione": "TEST_Need", "date": "2030-05-10",
                                                                     "start": st, "end": en, "needed": n})
            assert r.status_code == 200, r.text
            assert "_id" not in r.json()
            CREATED["needs"].append(r.json()["id"])
        d = cov(s)
        assert slot(d, "08:00")["status"] == "red"
        assert slot(d, "09:00")["status"] == "yellow"
        res["14"] = slot(d, "14:00")
        print("14:00", a14, res["14"]["needed"], res["14"]["status"])
        assert slot(d, "11:00")["status"] is None
        lst = s.get(f"{BASE_URL}/api/staff-coverage/needs", params={"evento_id": EVT}).json()
        assert len(lst) == 3
        # invalid
        r = s.post(f"{BASE_URL}/api/staff-coverage/needs", json={"evento_id": EVT, "mansione": "x", "date": "2030-05-10", "start": "10:00", "end": "09:00", "needed": 1})
        assert r.status_code == 400
        r = s.post(f"{BASE_URL}/api/staff-coverage/needs", json={"evento_id": "demo_evt_bcr", "mansione": "x", "date": "2030-05-10", "start": "09:00", "end": "10:00", "needed": 1},
                   headers={"X-Org-Id": OTHER})
        assert r.status_code == 404
        # cross org delete
        r = s.delete(f"{BASE_URL}/api/staff-coverage/needs/{CREATED['needs'][0]}", headers={"X-Org-Id": OTHER})
        assert r.status_code == 404
        r = s.delete(f"{BASE_URL}/api/staff-coverage/needs/{CREATED['needs'][0]}")
        assert r.status_code == 200
        assert slot(cov(s), "08:00")["status"] is None

    def test_yellow_pct(self, s):
        r = s.put(f"{BASE_URL}/api/staff-coverage/config", json={"yellow_margin_pct": 50})
        assert r.status_code == 200 and cov(s)["yellow_margin_pct"] == 50
        r = s.put(f"{BASE_URL}/api/staff-coverage/config", json={"yellow_margin_pct": 10})
        assert cov(s)["yellow_margin_pct"] == 10
        assert s.put(f"{BASE_URL}/api/staff-coverage/config", json={"yellow_margin_pct": 101}).status_code == 422

    @pytest.mark.parametrize("mode", ["summary", "by_mansione", "names"])
    def test_pdf(self, s, mode):
        from test_groups_tab_pdf import pdf_text
        r = s.get(f"{BASE_URL}/api/staff-coverage/export", params={"evento_id": EVT, "kind": "pdf", "mode": mode, "date": "2030-05-10"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf") and r.content[:4] == b"%PDF"
        t = pdf_text(r.content)
        assert "+39000000000" not in t
        if mode == "names":
            assert "TEST_Zeta" in t
        if mode == "by_mansione":
            assert "TEST_Segreteria" in t

    def test_pdf_requires_date(self, s):
        r = s.get(f"{BASE_URL}/api/staff-coverage/export", params={"evento_id": EVT, "kind": "pdf"})
        assert r.status_code == 400

    def test_xlsx(self, s):
        from openpyxl import load_workbook
        r = s.get(f"{BASE_URL}/api/staff-coverage/export", params={"evento_id": EVT, "kind": "xlsx"})
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        ws = load_workbook(io.BytesIO(r.content)).active
        rows = list(ws.values)
        assert rows[0][0] == "Cognome"
        multi = [x for x in rows if x[0] == "TEST_Charlie"]
        assert any(x[9] == "10/05/2030" and x[10] == "22:00" and x[11] == "11/05/2030" and x[12] == "02:00" for x in multi), multi


class TestAutoUpdate:
    def test_edit_link_reflects(self, s):
        sid = CREATED["staff"][1]  # linkonly 09-11
        r = s.put(f"{BASE_URL}/api/staff/{sid}", json={"ora_arrivo": "13:00", "ora_partenza": "14:00"})
        assert r.status_code == 200, r.text
        d = cov(s)
        assert P["linkonly"] not in slot(d, "09:00")["full"] and P["linkonly"] in slot(d, "13:00")["full"]
