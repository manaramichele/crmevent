# Iter209: Copertura oraria per Team e fascia (rows, needs, assign/force/move, orphans, filters, bulk, pdf)
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EV = "fbdf9b4c48d141dfab29a0c7f46cbaed"
DAY = "2026-12-20"


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": "test_tm_420d7a@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        pytest.skip("login failed")
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        ss.headers["Authorization"] = f"Bearer {tok}"
    return ss


def fx(s, **kw):
    r = s.get(f"{BASE_URL}/api/staff-coverage/fasce", params={"evento_id": EV, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def row(d, fascia, team):
    return next(r for r in d["rows"] if r["fascia"] == fascia and r["team"] == team)


def pid(d, name):
    for r in d["rows"]:
        for p in r["people"]:
            if p["nome"] == name or p["cognome"] == name:
                return p["id"]
    return None


def test_rows_order_and_shape(s):
    d = fx(s)
    names = [r["team"] for r in d["rows"] if r["date"] == DAY and r["fascia"] == "mattina"]
    assert names == ["Bici", "Ristoro Arrivo", "Segreteria"]
    m = row(d, "mattina", "Ristoro Arrivo")
    assert m["start"] == "07:00" and m["end"] == "12:00"
    assert m["needed"] == 3
    assert m["missing"] == max(0, 3 - m["assigned"])
    # da classificare never listed
    for r in d["rows"]:
        assert all("DaClass" not in (p["nome"] + p["cognome"]) for p in r["people"])
    assert any("NoTeam" in (p["nome"] + p["cognome"]) for p in d["warnings"]["no_team"])
    assert all("DaClass" not in (p["nome"] + p["cognome"]) for p in d["legacy"])


def test_team_filter(s):
    d = fx(s)
    tid = next(t["id"] for t in d["teams"] if t["nome"] == "Segreteria")
    d2 = fx(s, team_id=tid)
    assert {r["team"] for r in d2["rows"]} == {"Segreteria"}


def test_assign_partial_warn_force_move_unassign(s):
    d = fx(s)
    r = row(d, "pomeriggio", "Bici")
    rr = row(d, "pomeriggio", "Ristoro Arrivo")
    carla = next(p for p in rr["people"] if "Carla" in p["nome"] + p["cognome"])
    base = {"evento_id": EV, "date": DAY, "fascia": "pomeriggio"}
    # Carla legacy 09-11 has no pomeriggio coverage -> 409 availability
    x = s.post(f"{BASE_URL}/api/staff-coverage/assign", json={**base, "team_id": rr["team_id"], "persona_id": carla["id"], "force": False})
    assert x.status_code == 409 and x.json()["detail"]["code"] == "availability"
    x = s.post(f"{BASE_URL}/api/staff-coverage/assign", json={**base, "team_id": rr["team_id"], "persona_id": carla["id"], "force": True})
    assert x.status_code == 200
    rr2 = row(fx(s), "pomeriggio", "Ristoro Arrivo")
    assert rr2["assigned"] == rr["assigned"] + 1
    # wrong team -> 400
    x = s.post(f"{BASE_URL}/api/staff-coverage/assign", json={**base, "team_id": r["team_id"], "persona_id": carla["id"], "force": True})
    assert x.status_code == 400
    x = s.delete(f"{BASE_URL}/api/staff-coverage/assign", params={**base, "persona_id": carla["id"]})
    assert x.status_code == 200 and x.json()["removed"] == 1
    assert row(fx(s), "pomeriggio", "Ristoro Arrivo")["assigned"] == rr["assigned"]


def test_need_validation(s):
    d = fx(s)
    r = row(d, "pomeriggio", "Bici")
    body = {"evento_id": EV, "date": DAY, "fascia": "pomeriggio", "team_id": r["team_id"]}
    x = s.put(f"{BASE_URL}/api/staff-coverage/team-needs", json={**body, "needed": -1})
    assert x.status_code == 422
    x = s.put(f"{BASE_URL}/api/staff-coverage/team-needs", json={**body, "needed": 2})
    assert x.status_code == 200
    assert row(fx(s), "pomeriggio", "Bici")["missing"] == 2
    s.put(f"{BASE_URL}/api/staff-coverage/team-needs", json={**body, "needed": 0})
    assert row(fx(s), "pomeriggio", "Bici")["needed"] is None


def test_cat_filter_does_not_create_fake_orphans(s):
    """Assignments of a volunteer must not become 'da verificare' orphans when filtering Solo Staff."""
    d = fx(s)
    rr = row(d, "pomeriggio", "Ristoro Arrivo")
    carla = next(p for p in rr["people"] if "Carla" in p["nome"] + p["cognome"])
    base = {"evento_id": EV, "date": DAY, "fascia": "pomeriggio"}
    s.post(f"{BASE_URL}/api/staff-coverage/assign", json={**base, "team_id": rr["team_id"], "persona_id": carla["id"], "force": True})
    try:
        all_o = row(fx(s), "pomeriggio", "Ristoro Arrivo")["orphans"]
        st_o = row(fx(s, cat="staff"), "pomeriggio", "Ristoro Arrivo")["orphans"]
        assert st_o == all_o, f"orphans all={all_o} staff-filter={st_o}"
    finally:
        s.delete(f"{BASE_URL}/api/staff-coverage/assign", params={**base, "persona_id": carla["id"]})


def test_pdf_exports(s):
    for mode in ("fasce", "fasce_names"):
        x = s.get(f"{BASE_URL}/api/staff-coverage/export", params={"evento_id": EV, "kind": "pdf", "mode": mode})
        assert x.status_code == 200 and x.content[:4] == b"%PDF"
