"""Iter65 — Team volunteer coverage (fabbisogno / assegnati / mancanti / esubero)."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

ADMIN_TEST = ("test_team@crmeventqa.it", "TestTeam2026!")
ADMIN_QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
ORG_TEST = "org_TEST_team"
EV = "ev_TEST_team"
EV2 = "ev_TEST_team_2"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email} {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def s_test():
    return _login(*ADMIN_TEST)


@pytest.fixture(scope="module")
def s_qa():
    return _login(*ADMIN_QA)


# ---------- Teams list with coverage fields ----------
def test_teams_list_coverage_values(s_test):
    r = s_test.get(f"{API}/teams?evento_id={EV}", timeout=20)
    assert r.status_code == 200, r.text
    teams = {t["id"]: t for t in r.json()}
    assert teams["tm_TEST_ristori"]["volontari_richiesti"] == 20
    assert teams["tm_TEST_percorso"]["volontari_richiesti"] == 5
    assert teams["tm_TEST_expo"]["volontari_richiesti"] == 3
    assert teams["tm_TEST_nofab"].get("volontari_richiesti") in (None, 0) or teams["tm_TEST_nofab"]["volontari_richiesti"] is None


# ---------- Staff view used by frontend for assignedVol ----------
def test_staff_assigned_counts(s_test):
    r = s_test.get(f"{API}/staff?evento_id={EV}", timeout=20)
    assert r.status_code == 200
    staff = r.json()
    rinuncia = {"rinunciato", "non_disponibile"}

    def cnt(tid):
        return len({x["persona_id"] for x in staff if x.get("team_id") == tid and x.get("categoria") == "volontario"
                    and x.get("stato") not in rinuncia and x.get("persona_id")})
    assert cnt("tm_TEST_ristori") == 14, cnt("tm_TEST_ristori")
    assert cnt("tm_TEST_percorso") == 5
    assert cnt("tm_TEST_expo") == 5
    assert cnt("tm_TEST_nofab") == 1


# ---------- Dashboard aggregates ----------
def test_dashboard_coverage(s_test):
    r = s_test.get(f"{API}/dashboard?evento_id={EV}", timeout=20)
    assert r.status_code == 200, r.text
    st = r.json()["staff"]
    assert st["volontari_richiesti"] == 28, st
    assert st["volontari_assegnati"] == 24, st
    assert st["volontari_mancanti"] == 6, st
    assert st["volontari_esubero"] == 2, st


def test_dashboard_other_event_no_counts(s_test):
    r = s_test.get(f"{API}/dashboard?evento_id={EV2}", timeout=20)
    assert r.status_code == 200
    st = r.json()["staff"]
    assert st["volontari_richiesti"] == 0 and st["volontari_assegnati"] == 0
    assert st["volontari_mancanti"] == 0 and st["volontari_esubero"] == 0


# ---------- Team create/update: volontari_richiesti field ----------
def test_team_create_update_and_negative_rejected(s_test):
    created = s_test.post(f"{API}/teams", json={"nome": "TEST_New Team", "evento_id": EV, "volontari_richiesti": 20}, timeout=20)
    assert created.status_code in (200, 201), created.text
    tid = created.json()["id"]
    try:
        r = s_test.get(f"{API}/teams?evento_id={EV}", timeout=20).json()
        t = next(x for x in r if x["id"] == tid)
        assert t["volontari_richiesti"] == 20

        # update
        upd = s_test.put(f"{API}/teams/{tid}", json={"nome": "TEST_New Team", "evento_id": EV, "volontari_richiesti": 25}, timeout=20)
        assert upd.status_code == 200, upd.text
        t2 = next(x for x in s_test.get(f"{API}/teams?evento_id={EV}", timeout=20).json() if x["id"] == tid)
        assert t2["volontari_richiesti"] == 25

        # negative rejected
        neg = s_test.post(f"{API}/teams", json={"nome": "TEST_Neg", "evento_id": EV, "volontari_richiesti": -1}, timeout=20)
        assert neg.status_code == 422, neg.text
    finally:
        s_test.delete(f"{API}/teams/{tid}", timeout=20)


# ---------- Immediate update when assignment changes ----------
def test_coverage_updates_on_assignment(s_test):
    # Assign Libero TEST to Ristori → 15/5
    r = s_test.put(f"{API}/staff/sl_TEST_free",
                   json={"evento_id": EV, "persona_id": "pe_TEST_free", "categoria": "volontario",
                         "team_id": "tm_TEST_ristori", "stato": "confermato"}, timeout=20)
    assert r.status_code == 200, r.text
    d = s_test.get(f"{API}/dashboard?evento_id={EV}", timeout=20).json()["staff"]
    assert d["volontari_assegnati"] == 25 and d["volontari_mancanti"] == 5, d

    # Transfer to Percorso → Ristori 14/6, Percorso 6/5 (+1 esubero overall)
    r2 = s_test.put(f"{API}/staff/sl_TEST_free",
                    json={"evento_id": EV, "persona_id": "pe_TEST_free", "categoria": "volontario",
                          "team_id": "tm_TEST_percorso", "stato": "confermato"}, timeout=20)
    assert r2.status_code == 200
    d2 = s_test.get(f"{API}/dashboard?evento_id={EV}", timeout=20).json()["staff"]
    # Totali: req 28, assegnati 25, mancanti 6, esubero 3 (percorso +1, expo +2)
    assert d2["volontari_assegnati"] == 25
    assert d2["volontari_mancanti"] == 6
    assert d2["volontari_esubero"] == 3

    # Remove team → back to original 24/6/2
    r3 = s_test.put(f"{API}/staff/sl_TEST_free",
                    json={"evento_id": EV, "persona_id": "pe_TEST_free", "categoria": "volontario",
                          "team_id": "", "stato": "confermato"}, timeout=20)
    assert r3.status_code == 200
    d3 = s_test.get(f"{API}/dashboard?evento_id={EV}", timeout=20).json()["staff"]
    assert d3["volontari_assegnati"] == 24 and d3["volontari_mancanti"] == 6 and d3["volontari_esubero"] == 2, d3


# ---------- Isolation: QA admin does not see TEST data ----------
def test_isolation_qa_cannot_see_test_teams(s_qa):
    r = s_qa.get(f"{API}/teams?evento_id={EV}", timeout=20)
    # Either 404 (event not in org) or empty list filtered by org
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert all(not t["id"].startswith("tm_TEST_") for t in r.json())
    r2 = s_qa.get(f"{API}/dashboard?evento_id={EV}", timeout=20)
    assert r2.status_code in (200, 404)
