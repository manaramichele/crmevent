"""Iter69 — Team Leader scope=leader + staff:edit may assign/remove persone senza Team."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ORG = "org_TEST_tl"
EV = "ev_TEST_tl"

ADMIN = ("test_tl_admin@crmeventqa.it", "TestTl2026!")
LEADER = ("test_tl_leader@crmeventqa.it", "TestTl2026!")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def leader():
    return _login(*LEADER)


# Create a presenza senza team (TEST_free) once per module and clean up
@pytest.fixture(scope="module")
def free_presence(admin):
    # Crea persona
    rp = admin.post(f"{BASE}/api/persons", json={"nome": "TEST_Freelancer", "cognome": "NoTeam"})
    assert rp.status_code in (200, 201), rp.text
    pid = rp.json()["id"]
    # Crea staff senza team
    rs = admin.post(f"{BASE}/api/staff", json={"evento_id": EV, "persona_id": pid, "categoria": "volontario", "team_id": "", "stato": "confermato"})
    assert rs.status_code in (200, 201), rs.text
    sid = rs.json()["id"]
    yield {"persona_id": pid, "staff_id": sid}
    # cleanup
    try:
        admin.delete(f"{BASE}/api/staff/{sid}")
        admin.delete(f"{BASE}/api/persons/{pid}")
    except Exception:
        pass


# --- Admin: assign free presence to a team via PUT, then rimuovi (team_id="") ---
class TestAdminAssignFree:
    def test_free_visible_without_team(self, admin, free_presence):
        r = admin.get(f"{BASE}/api/staff/{free_presence['staff_id']}")
        assert r.status_code == 200
        assert r.json().get("team_id") in (None, "")

    def test_assign_to_start_line(self, admin, free_presence):
        r = admin.put(f"{BASE}/api/staff/{free_presence['staff_id']}", json={"team_id": "tm_TEST_start"})
        assert r.status_code == 200
        r2 = admin.get(f"{BASE}/api/staff/{free_presence['staff_id']}")
        assert r2.json().get("team_id") == "tm_TEST_start"

    def test_remove_from_team_keeps_presence(self, admin, free_presence):
        r = admin.put(f"{BASE}/api/staff/{free_presence['staff_id']}", json={"team_id": ""})
        assert r.status_code == 200
        # Presenza esiste ancora
        r2 = admin.get(f"{BASE}/api/staff/{free_presence['staff_id']}")
        assert r2.status_code == 200
        assert r2.json().get("team_id") in (None, "")
        # Persona non cancellata
        rp = admin.get(f"{BASE}/api/persons/{free_presence['persona_id']}")
        assert rp.status_code == 200


# --- Promote leader to staff:[view,create,edit] and verify leader can assign free, cannot touch Ristori ---
class TestLeaderEditFree:
    @pytest.fixture(scope="class", autouse=True)
    def grant_edit(self, admin):
        body = {
            "sections": {"staff": ["view", "create", "edit"], "dashboard": ["view"], "anagrafiche": ["view"]},
            "events": "all",
            "teams": {"scope": "leader", "ids": []},
        }
        r = admin.put(f"{BASE}/api/org/permissions/user_TEST_tl_leader", json=body)
        assert r.status_code == 200, r.text
        yield
        # restore default seed: perms = {} (no sections → sola visualizzazione default scope leader)
        admin.put(f"{BASE}/api/org/permissions/user_TEST_tl_leader",
                  json={"teams": {"scope": "leader", "ids": []}})

    def test_leader_sees_free_presence_in_list(self, leader, free_presence):
        r = leader.get(f"{BASE}/api/staff")
        assert r.status_code == 200
        ids = {x["id"] for x in r.json()}
        assert free_presence["staff_id"] in ids, "Leader deve vedere presenze senza Team"

    def test_leader_can_get_free_presence(self, leader, free_presence):
        r = leader.get(f"{BASE}/api/staff/{free_presence['staff_id']}")
        assert r.status_code == 200

    def test_leader_can_assign_free_to_own_team(self, leader, free_presence):
        r = leader.put(f"{BASE}/api/staff/{free_presence['staff_id']}", json={"team_id": "tm_TEST_start"})
        assert r.status_code == 200
        r2 = leader.get(f"{BASE}/api/staff/{free_presence['staff_id']}")
        assert r2.json().get("team_id") == "tm_TEST_start"

    def test_leader_cannot_move_own_presence_to_other_team(self, leader, free_presence):
        # ora la presenza è già nel proprio Team: PUT a Ristori → 404
        r = leader.put(f"{BASE}/api/staff/{free_presence['staff_id']}", json={"team_id": "tm_TEST_ristori"})
        assert r.status_code == 404

    def test_leader_can_remove_free_from_own_team(self, leader, free_presence):
        r = leader.put(f"{BASE}/api/staff/{free_presence['staff_id']}", json={"team_id": ""})
        assert r.status_code == 200

    def test_leader_cannot_access_ristori_presence(self, leader, admin):
        # Trova una presenza nel Team Ristori via admin
        rs = admin.get(f"{BASE}/api/staff?evento_id={EV}").json()
        ristori = [s for s in rs if s.get("team_id") == "tm_TEST_ristori"]
        assert ristori, "fixture mancante: nessuna presenza Ristori"
        sid = ristori[0]["id"]
        # Leader GET → 404
        r1 = leader.get(f"{BASE}/api/staff/{sid}")
        assert r1.status_code == 404
        # Leader PUT su presenza di Ristori → 404
        r2 = leader.put(f"{BASE}/api/staff/{sid}", json={"team_id": "tm_TEST_start"})
        assert r2.status_code == 404

    def test_leader_cannot_delete_free_presence(self, leader, free_presence):
        # Riporta presenza libera (test precedente l'ha già rimossa) e prova DELETE
        r = leader.delete(f"{BASE}/api/staff/{free_presence['staff_id']}")
        assert r.status_code in (403, 404), f"DELETE free presence atteso 403/404, got {r.status_code}"


# --- Dashboard A-Z default sort (verifica che backend ritorni team dati per ordinamento FE) ---
class TestTeamsListShape:
    def test_teams_contain_sortable_fields(self, admin):
        r = admin.get(f"{BASE}/api/teams?evento_id={EV}")
        assert r.status_code == 200
        names = [t["nome"] for t in r.json()]
        # Il backend non ordina alfabeticamente: lo fa il FE. Verifichiamo che i 3 team siano presenti.
        assert "Start Line" in names and "Ristori" in names and "Expo" in names
