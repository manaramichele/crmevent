# Ristoro team selection on public availability link + Mansione auto sync (iteration 183)
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
EMAIL = open('/tmp/e6').read().strip()
CODE, EV, TEAM = open('/tmp/rist').read().split()
PWD = "TestPass123!"


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PWD})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    return ss


@pytest.fixture(scope="module")
def info():
    r = requests.get(f"{BASE_URL}/api/public/availability/{CODE}")
    assert r.status_code == 200
    return r.json()


def _payload(info, email, pref="Addetto ristoro", team=None, nome="TEST_Luigi"):
    days = [{"date": d["date"], "disponibile": True} for d in info["days"] if d["fase"] == "evento"]
    return {"nome": nome, "cognome": "TEST_Bianchi", "cellulare": "+39333" + str(int(time.time() * 1000))[-7:],
            "email": email, "data_nascita": "1990-01-01", "days": days, "preferenza_attivita": pref,
            "ristoro_team_id": team, "privacy": True}


def _link(s, email):
    ppl = s.get(f"{BASE_URL}/api/persons").json()
    p = next((x for x in ppl if (x.get("email") or "") == email), None)
    assert p, "person not saved"
    links = [x for x in s.get(f"{BASE_URL}/api/staff", params={"evento_id": EV}).json() if x["persona_id"] == p["id"]]
    assert len(links) == 1
    return p, links[0]


# Public GET exposes only ristoro teams of the event
def test_public_ristoro_teams(info):
    names = [t["nome"] for t in info["ristoro_teams"]]
    assert "Ristoro KM 12" in names
    assert "Accoglienza" not in names
    assert "Ristoro Altro Evento" not in names
    assert any(t["id"] == TEAM for t in info["ristoro_teams"])
    assert "Addetto ristoro" in info["attivita_options"]


# Submit without team -> 400; with foreign team -> 400
def test_submit_requires_team(info):
    r = requests.post(f"{BASE_URL}/api/public/availability/{CODE}", json=_payload(info, "test_rist_noteam@example.com"))
    assert r.status_code == 400 and "Team Ristoro" in r.json()["detail"]
    r = requests.post(f"{BASE_URL}/api/public/availability/{CODE}", json=_payload(info, "test_rist_noteam@example.com", team="bogus"))
    assert r.status_code == 400


# Full flow: submit -> link Da classificare with team/mansione auto; classify; team change; rename sync
def test_full_flow(s, info):
    email = f"test_rist_api_{int(time.time())}@example.com"
    r = requests.post(f"{BASE_URL}/api/public/availability/{CODE}", json=_payload(info, email, team=TEAM))
    assert r.status_code == 200, r.text
    p, ln = _link(s, email)
    assert ln["categoria"] == "da_classificare"
    assert ln["team_id"] == TEAM and ln["ruolo"] == "Ristoro KM 12" and ln["mansione_auto"] is True
    # classify volontario keeps mansione
    r = s.put(f"{BASE_URL}/api/staff/{ln['id']}", json={"categoria": "volontario"})
    assert r.status_code == 200 and r.json()["ruolo"] == "Ristoro KM 12" and r.json()["team_id"] == TEAM
    # create second ristoro team, rename it -> auto link follows
    t2 = s.post(f"{BASE_URL}/api/teams", json={"nome": "TEST_Ristoro KM 20", "evento_id": EV, "area": "Ristoro"}).json()
    assert "id" in t2
    info2 = requests.get(f"{BASE_URL}/api/public/availability/{CODE}").json()
    assert any(t["id"] == t2["id"] for t in info2["ristoro_teams"])
    s.put(f"{BASE_URL}/api/staff/{ln['id']}", json={"team_id": t2["id"], "ruolo": t2["nome"], "mansione_auto": True})
    r = s.put(f"{BASE_URL}/api/teams/{t2['id']}", json={"nome": "TEST_Ristoro KM 21"})
    assert r.status_code == 200
    _, ln2 = _link(s, email)
    assert ln2["ruolo"] == "TEST_Ristoro KM 21"
    # manual mansione -> rename does not overwrite
    s.put(f"{BASE_URL}/api/staff/{ln['id']}", json={"ruolo": "Addetto ristoro", "mansione_auto": False})
    s.put(f"{BASE_URL}/api/teams/{t2['id']}", json={"nome": "TEST_Ristoro KM 22"})
    _, ln3 = _link(s, email)
    assert ln3["ruolo"] == "Addetto ristoro" and ln3["mansione_auto"] is False
    open('/tmp/rist_t2', 'w').write(t2["id"])
    open('/tmp/rist_pid', 'a').write(p["id"] + "\n")


# Other preference -> no team required, team ignored
def test_other_pref_ignores_team(s, info):
    other = next(a for a in info["attivita_options"] if "ristoro" not in a.lower())
    email = f"test_rist_other_{int(time.time())}@example.com"
    r = requests.post(f"{BASE_URL}/api/public/availability/{CODE}", json=_payload(info, email, pref=other, team=TEAM))
    assert r.status_code == 200, r.text
    _, ln = _link(s, email)
    assert not ln.get("team_id")
