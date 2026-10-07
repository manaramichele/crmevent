"""Iter66 — Team card + Team-scoped memberships (/teams, /staff, /shifts, /dashboard, /org/permissions)."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ORG = "org_TEST_tl"
EV = "ev_TEST_tl"

ADMIN = ("test_tl_admin@crmeventqa.it", "TestTl2026!")
LEADER = ("test_tl_leader@crmeventqa.it", "TestTl2026!")
RESP = ("test_tl_resp@crmeventqa.it", "TestTl2026!")
QA_ADMIN = ("qa.eventi@crmeventqa.it", "QaEvents2026!")


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


@pytest.fixture(scope="module")
def resp():
    return _login(*RESP)


@pytest.fixture(scope="module")
def qa():
    return _login(*QA_ADMIN)


# ---------- Admin: tutti i team visibili ----------
class TestAdminTeams:
    def test_list_teams(self, admin):
        r = admin.get(f"{BASE}/api/teams?evento_id={EV}")
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        assert {"tm_TEST_start", "tm_TEST_ristori", "tm_TEST_expo"} <= ids

    def test_dashboard_totals(self, admin):
        r = admin.get(f"{BASE}/api/dashboard?evento_id={EV}")
        assert r.status_code == 200
        s = r.json().get("staff", {})
        # Start=20 richiesti,18 assegnati; Ristori=10,7; Expo=None (escluso dai totali)
        assert s.get("volontari_richiesti") == 30
        assert s.get("volontari_assegnati") == 25
        assert s.get("volontari_mancanti") == 5

    def test_team_detail(self, admin):
        r = admin.get(f"{BASE}/api/teams/tm_TEST_start")
        assert r.status_code == 200
        t = r.json()
        assert t["responsabile_id"] == "pe_TEST_leader"
        assert t["volontari_richiesti"] == 20

    def test_update_team_luogo_persisted(self, admin):
        new_val = "Luogo UPDATED TEST"
        r = admin.put(f"{BASE}/api/teams/tm_TEST_start", json={"luogo_operativo": new_val})
        assert r.status_code == 200
        r2 = admin.get(f"{BASE}/api/teams/tm_TEST_start")
        assert r2.json().get("luogo_operativo") == new_val
        # restore
        admin.put(f"{BASE}/api/teams/tm_TEST_start", json={"luogo_operativo": "Luogo Start Line"})


# ---------- Collaboratore Team Leader (scope=leader) ----------
class TestLeaderScope:
    def test_teams_only_start(self, leader):
        r = leader.get(f"{BASE}/api/teams")
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        assert ids == {"tm_TEST_start"}

    def test_team_ristori_404(self, leader):
        r = leader.get(f"{BASE}/api/teams/tm_TEST_ristori")
        assert r.status_code == 404

    def test_staff_only_start(self, leader):
        r = leader.get(f"{BASE}/api/staff")
        assert r.status_code == 200
        rows = r.json()
        # tutti con team_id = Start Line; conteggio = 4 staff + 18 volontari + 1 leader-as-staff = 23
        assert len(rows) == 23
        assert all(x.get("team_id") == "tm_TEST_start" for x in rows)

    def test_staff_other_team_404(self, leader):
        # sl_TEST_tl25 è nel Team Ristori (indice 23 (leader as staff? no, i partiva da 0 su start: 4+18=22, poi ristori 2+7=9 => indici 22..30)
        # proviamo un id probabile di Ristori
        r = leader.get(f"{BASE}/api/staff/sl_TEST_tl23")
        assert r.status_code == 404

    def test_shifts_only_start(self, leader):
        r = leader.get(f"{BASE}/api/shifts")
        assert r.status_code == 200
        assert all(x.get("team_id") == "tm_TEST_start" for x in r.json())

    def test_create_team_forbidden(self, leader):
        r = leader.post(f"{BASE}/api/teams", json={"evento_id": EV, "nome": "TEST_NewTeam"})
        assert r.status_code == 403

    def test_dashboard_scoped(self, leader):
        r = leader.get(f"{BASE}/api/dashboard?evento_id={EV}")
        assert r.status_code == 200
        s = r.json().get("staff", {})
        assert s.get("volontari_richiesti") == 20
        assert s.get("volontari_assegnati") == 18
        assert s.get("volontari_mancanti") == 2


# ---------- Responsabile Volontari (teams.scope=all, read-only) ----------
class TestRespScope:
    def test_sees_all_teams(self, resp):
        r = resp.get(f"{BASE}/api/teams?evento_id={EV}")
        assert r.status_code == 200
        ids = {t["id"] for t in r.json()}
        assert {"tm_TEST_start", "tm_TEST_ristori", "tm_TEST_expo"} <= ids

    def test_cannot_edit(self, resp):
        r = resp.put(f"{BASE}/api/teams/tm_TEST_ristori", json={"nome": "X"})
        assert r.status_code == 403


# ---------- Admin changes leader scope to selected ----------
class TestPermissionsFlow:
    def test_meta_includes_teams(self, admin):
        r = admin.get(f"{BASE}/api/org/permissions")
        assert r.status_code == 200
        j = r.json()
        tids = {t["id"] for t in j.get("teams", [])}
        assert {"tm_TEST_start", "tm_TEST_ristori", "tm_TEST_expo"} <= tids

    def test_assign_selected_and_restore(self, admin, leader):
        # Switch leader → selected + tm_TEST_ristori
        body = {"teams": {"scope": "selected", "ids": ["tm_TEST_ristori"]}}
        r = admin.put(f"{BASE}/api/org/permissions/user_TEST_tl_leader", json=body)
        assert r.status_code == 200
        # leader session: new call → sees Start Line (as leader) + Ristori (selected)
        r2 = leader.get(f"{BASE}/api/teams")
        assert r2.status_code == 200
        ids = {t["id"] for t in r2.json()}
        assert ids == {"tm_TEST_start", "tm_TEST_ristori"}
        # Audit mentions Team
        au = admin.get(f"{BASE}/api/org/permissions/audit").json()
        assert any("Team" in (it.get("detail") or "") for it in au.get("items", []))
        # Restore default scope=leader
        r3 = admin.put(f"{BASE}/api/org/permissions/user_TEST_tl_leader",
                       json={"teams": {"scope": "leader", "ids": []}})
        assert r3.status_code == 200
        ids2 = {t["id"] for t in leader.get(f"{BASE}/api/teams").json()}
        assert ids2 == {"tm_TEST_start"}


# ---------- Isolamento multi-tenant ----------
class TestIsolation:
    def test_qa_admin_cannot_see_test_org(self, qa):
        r = qa.get(f"{BASE}/api/teams/tm_TEST_start")
        assert r.status_code == 404
        r2 = qa.get(f"{BASE}/api/teams?evento_id={EV}")
        # evento appartiene ad altra org → vuoto
        assert r2.status_code in (200, 404)
        if r2.status_code == 200:
            assert not any(t.get("org_id") == ORG for t in r2.json())
