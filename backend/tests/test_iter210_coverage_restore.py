# Iter 210: Copertura oraria (Staff/Volontari) restored chart - stato filter, team counts, to-update, matrix, export
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for ln in fh:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
EMAIL, PWD = "test_cov_admin@example.com", "TestCov2026!"
EV_NAME = "TEST_Maratona Copertura"


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    return ss


@pytest.fixture(scope="module")
def ev(s):
    evs = s.get(f"{BASE_URL}/api/events").json()
    evs = evs if isinstance(evs, list) else evs.get("items", [])
    e = next((x for x in evs if x["nome"] == EV_NAME), None)
    if not e:
        pytest.skip("seed event missing")
    return e["id"]


@pytest.fixture(scope="module")
def teams(s, ev):
    return {t["nome"]: t["id"] for t in s.get(f"{BASE_URL}/api/teams").json() if t.get("evento_id") == ev}


def cov(s, ev, **kw):
    r = s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": ev, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def by(d):
    return {x["start"]: x for x in d["slots"]}


def names(d):
    return {p["cognome"] for p in d["people"].values()}


# Default stato=attivi on 12/12
def test_default_day12(s, ev):
    d = cov(s, ev, date="2026-12-12")
    sl = by(d)
    assert list(sl)[0] == "06:00" and list(sl)[-1] == "18:00"
    exp = {"06:00": 2, "07:00": 2, "08:00": 3, "09:00": 3, "10:00": 3, "11:00": 2, "12:00": 2}
    for h in range(13, 19):
        exp[f"{h:02d}:00"] = 2
    assert {k: v["available"] for k, v in sl.items()} == exp
    assert sl["09:00"]["teams"] == {"Ristoro": 2, "Pacer": 1}
    assert sl["14:00"]["teams"] == {"Ristoro": 1, "Accoglienza": 1}
    assert d["kpis"]["day_people"] == 4 and d["kpis"]["tbc"] == 1
    assert d["days"] == ["2026-12-12", "2026-12-13"]


def test_excluded_people(s, ev):
    for st in ("attivi", "confermati"):
        for day in ("2026-12-12", "2026-12-13"):
            n = names(cov(s, ev, date=day, stato=st))
            assert "TEST_Rinuncia" not in n and "TEST_DaClass" not in n


def test_slot_09_people(s, ev):
    d = cov(s, ev, date="2026-12-12")
    sl = by(d)["09:00"]
    ppl = sorted(d["people"][i]["cognome"] for i in sl["full"] + sl["partial"])
    assert ppl == ["TEST_Bianchi", "TEST_Neri", "TEST_Rossi"]
    neri = next(p for p in d["people"].values() if p["cognome"] == "TEST_Neri")
    assert neri["legacy"] is True


def test_stato_confermati(s, ev):
    sl = by(cov(s, ev, date="2026-12-12", stato="confermati"))
    assert sl["06:00"]["available"] == 1 and sl["07:00"]["available"] == 1
    assert sl["08:00"]["available"] == 2 and sl["10:00"]["available"] == 2
    for h in range(13, 19):
        assert sl[f"{h:02d}:00"]["available"] == 1


def test_day13(s, ev):
    d = cov(s, ev, date="2026-12-13")
    sl = by(d)
    assert list(sl)[0] == "06:00" and list(sl)[-1] == "12:00"
    assert all(v["available"] == 1 and v["teams"] == {"Accoglienza": 1} for v in sl.values())


def test_team_filter(s, ev, teams):
    sl = by(cov(s, ev, date="2026-12-12", team_id=teams["Ristoro"]))
    assert sl["09:00"]["available"] == 2 and sl["14:00"]["available"] == 1
    assert all(set(v["teams"]) <= {"Ristoro"} for v in sl.values())


@pytest.mark.parametrize("step,count", [(30, 26), (15, 52)])
def test_granularity(s, ev, step, count):
    d = cov(s, ev, date="2026-12-12", step=step)
    assert len(d["slots"]) == count
    assert by(d)["06:30" if step == 30 else "06:15"]["available"] == 2


def test_to_update(s, ev):
    r = s.get(f"{BASE_URL}/api/staff-coverage/to-update", params={"evento_id": ev})
    assert r.status_code == 200
    assert sorted(p["cognome"] for p in r.json()["people"]) == ["TEST_Blu", "TEST_Gialli", "TEST_Neri"]


def test_matrix(s, ev):
    r = s.get(f"{BASE_URL}/api/staff-coverage/matrix", params={"evento_id": ev})
    assert r.status_code == 200
    m = r.json()
    assert m["days"] == ["2026-12-12", "2026-12-13"]
    row = next(x for x in m["rows"] if x["start"] == "09:00")
    assert row["cells"] == [3, 1]
    assert m["tbc"]["2026-12-12"] == 1


@pytest.mark.parametrize("kind,mode,stato", [("pdf", "summary", "attivi"), ("pdf", "by_mansione", "attivi"), ("pdf", "names", "confermati"), ("xlsx", "summary", "confermati")])
def test_export(s, ev, kind, mode, stato):
    r = s.get(f"{BASE_URL}/api/staff-coverage/export", params={"evento_id": ev, "kind": kind, "mode": mode, "stato": stato, "date": "2026-12-12"})
    assert r.status_code == 200, r.text[:200]
    assert len(r.content) > 500
    assert r.content[:4] == (b"%PDF" if kind == "pdf" else b"PK\x03\x04")


def test_bad_step(s, ev):
    assert s.get(f"{BASE_URL}/api/staff-coverage", params={"evento_id": ev, "date": "2026-12-12", "step": 20}).status_code == 400
