"""Iter 82 — Permessi e accessi Team Leader (TL).
Covers:
  - Collaboratore senza sezione Staff ma Team Leader di Team A:
      GET /staff, /teams, /shifts, /persons-enriched, /events/{eid}/availabilities, /persons/{id}/detail
      limitati al Team A; persona di altro team -> 404.
  - Senza flag TL: PUT /staff/{id} -> 403; POST /shifts -> 403; PUT /teams/{id} -> 403 (sempre).
  - Con edit_members=True: PUT/DELETE staff Team A OK; staff Team B -> 404.
  - Con manage_shifts=True: CRUD shifts del Team A OK; Team B -> 403/404.
  - Due team: dashboard my_teams contiene 2 voci.
  - Revoca: Admin cambia responsabile_id -> 403/non visibile.
  - GET /auth/me per TL: led_team_ids presente; permissions.team_leader presente.
  - PUT /org/permissions/{uid} con team_leader {edit_members, manage_shifts} salva; audit 'Team Leader'.
Dati prefissati TEST_iter82_ e puliti alla fine.
"""
import os
import re
import uuid
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient
import bcrypt

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ORG = "org_qa_eventi"
ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
TAG = f"TEST_iter82_{uuid.uuid4().hex[:6]}"
TL_EMAIL = f"test_tl_{TAG}@example.com".lower()
TL_PWD = "TlPwd2026!"

STATE = {"users": [], "persons": [], "staff": [], "teams": [], "events": [],
         "memberships": [], "shifts": [], "avails": []}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup(db):
    d = db
    now = datetime.now(timezone.utc).isoformat()

    uid = f"user_{TAG}"
    pwd_hash = bcrypt.hashpw(TL_PWD.encode(), bcrypt.gensalt()).decode()
    d.users.insert_one({"user_id": uid, "email": TL_EMAIL, "name": f"TL {TAG}",
                        "role": "user", "auth_provider": "password", "password_hash": pwd_hash,
                        "org_id": ORG, "active": True, "created_at": now, "telefono": "+393490000000"})
    STATE["users"].append(uid)

    ev1 = {"id": f"{TAG}_ev1", "org_id": ORG, "nome": f"{TAG} EV1",
           "data_inizio": "2026-06-01", "data_fine": "2026-06-02",
           "credit_state": "attivo", "created_at": now}
    d.events.insert_one(ev1)
    STATE["events"].append(ev1["id"])

    # Leader person collegata al TL via email (nessuna persona_id in membership)
    leader_p = {"id": f"{TAG}_leader", "org_id": ORG, "nome": "Leader", "cognome": f"{TAG}_TL",
                "email": TL_EMAIL, "created_at": now}
    # Persona componente Team A (staff)
    p_a_staff = {"id": f"{TAG}_pA_s", "org_id": ORG, "nome": "A", "cognome": f"{TAG}_Staff",
                 "email": f"test_a_s_{TAG}@example.com", "created_at": now}
    # Persona componente Team A (volontario)
    p_a_vol = {"id": f"{TAG}_pA_v", "org_id": ORG, "nome": "A", "cognome": f"{TAG}_Vol",
               "email": f"test_a_v_{TAG}@example.com", "created_at": now}
    # Persona componente Team B
    p_b = {"id": f"{TAG}_pB", "org_id": ORG, "nome": "B", "cognome": f"{TAG}_Other",
           "email": f"test_b_{TAG}@example.com", "created_at": now}
    # Persona senza team (presenza senza team_id)
    p_free = {"id": f"{TAG}_pFree", "org_id": ORG, "nome": "F", "cognome": f"{TAG}_Free",
              "email": f"test_free_{TAG}@example.com", "created_at": now}
    d.persons.insert_many([leader_p, p_a_staff, p_a_vol, p_b, p_free])
    STATE["persons"] += [leader_p["id"], p_a_staff["id"], p_a_vol["id"], p_b["id"], p_free["id"]]

    t_a = {"id": f"{TAG}_tA", "org_id": ORG, "nome": f"{TAG} TeamA", "evento_id": ev1["id"],
           "responsabile_id": leader_p["id"], "volontari_richiesti": 2, "created_at": now}
    t_b = {"id": f"{TAG}_tB", "org_id": ORG, "nome": f"{TAG} TeamB", "evento_id": ev1["id"], "created_at": now}
    # Secondo team guidato (per test "2 team")
    t_c = {"id": f"{TAG}_tC", "org_id": ORG, "nome": f"{TAG} TeamC", "evento_id": ev1["id"],
           "responsabile_id": leader_p["id"], "created_at": now}
    d.teams.insert_many([t_a, t_b, t_c])
    STATE["teams"] += [t_a["id"], t_b["id"], t_c["id"]]

    s_rows = [
        {"id": f"{TAG}_s_aS", "org_id": ORG, "persona_id": p_a_staff["id"], "evento_id": ev1["id"],
         "team_id": t_a["id"], "categoria": "staff", "stato": "da_contattare", "created_at": now},
        {"id": f"{TAG}_s_aV", "org_id": ORG, "persona_id": p_a_vol["id"], "evento_id": ev1["id"],
         "team_id": t_a["id"], "categoria": "volontario", "stato": "da_contattare", "created_at": now},
        {"id": f"{TAG}_s_b", "org_id": ORG, "persona_id": p_b["id"], "evento_id": ev1["id"],
         "team_id": t_b["id"], "categoria": "staff", "stato": "da_contattare", "created_at": now},
        {"id": f"{TAG}_s_free", "org_id": ORG, "persona_id": p_free["id"], "evento_id": ev1["id"],
         "team_id": None, "categoria": "staff", "stato": "da_contattare", "created_at": now},
    ]
    d.staff.insert_many(s_rows)
    STATE["staff"] += [r["id"] for r in s_rows]

    # Shifts (one per team) - precreated
    sh_a = {"id": f"{TAG}_sh_a", "org_id": ORG, "evento_id": ev1["id"], "team_id": t_a["id"],
            "titolo": "SH-A", "data": "2026-06-01", "ora_inizio": "08:00", "ora_fine": "12:00",
            "created_at": now}
    sh_b = {"id": f"{TAG}_sh_b", "org_id": ORG, "evento_id": ev1["id"], "team_id": t_b["id"],
            "titolo": "SH-B", "data": "2026-06-01", "ora_inizio": "08:00", "ora_fine": "12:00",
            "created_at": now}
    d.shifts.insert_many([sh_a, sh_b])
    STATE["shifts"] += [sh_a["id"], sh_b["id"]]

    # Availabilities
    av_a = {"id": f"{TAG}_av_a", "org_id": ORG, "evento_id": ev1["id"],
            "persona_id": p_a_staff["id"], "stato": "inviata", "created_at": now}
    av_b = {"id": f"{TAG}_av_b", "org_id": ORG, "evento_id": ev1["id"],
            "persona_id": p_b["id"], "stato": "inviata", "created_at": now}
    d.availabilities.insert_many([av_a, av_b])
    STATE["avails"] += [av_a["id"], av_b["id"]]

    # Membership collaboratore, NO sezione Staff (sections.staff=[]); scope default "leader"
    perm = {"sections": {k: [] for k in [
        "dashboard", "eventi", "staff", "aziende", "anagrafiche", "ospitalita",
        "sponsor", "attivita", "followup", "briefing", "mappe", "pipeline"]},
        "events": "all",
        "teams": {"scope": "leader", "ids": [], "manage_staff": True, "manage_volunteers": True},
        "send_invites": False,
        "team_leader": {"edit_members": False, "manage_shifts": False}}
    # Allow dashboard view (to test dashboard)
    perm["sections"]["dashboard"] = ["view"]
    d.memberships.insert_one({"id": f"mem_{TAG}", "org_id": ORG, "user_id": uid,
                              "role": "collaboratore", "active": True, "created_at": now,
                              "permissions": perm})
    STATE["memberships"].append(uid)

    yield

    d.shifts.delete_many({"id": {"$in": STATE["shifts"]}})
    d.availabilities.delete_many({"id": {"$in": STATE["avails"]}})
    d.staff.delete_many({"id": {"$in": STATE["staff"]}})
    d.teams.delete_many({"id": {"$in": STATE["teams"]}})
    d.persons.delete_many({"id": {"$in": STATE["persons"]}})
    d.events.delete_many({"id": {"$in": STATE["events"]}})
    d.memberships.delete_many({"user_id": {"$in": STATE["memberships"]}, "org_id": ORG})
    d.users.delete_many({"user_id": {"$in": STATE["users"]}})
    d.audit_logs.delete_many({"org_id": ORG, "target_email": TL_EMAIL})


def _tl_session():
    return _login({"email": TL_EMAIL, "password": TL_PWD})


def _set_tl_flags(db, edit_members=False, manage_shifts=False):
    db.memberships.update_one(
        {"user_id": f"user_{TAG}", "org_id": ORG},
        {"$set": {"permissions.team_leader.edit_members": edit_members,
                  "permissions.team_leader.manage_shifts": manage_shifts}})


# ============ 1. /auth/me — led_team_ids + team_leader perms ============
class TestAuthMe:
    def test_auth_me_contains_led_team_ids_and_tl_perm(self, db):
        _set_tl_flags(db, edit_members=False, manage_shifts=False)
        s = _tl_session()
        r = s.get(f"{API}/auth/me")
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.get("led_team_ids") or []) == {f"{TAG}_tA", f"{TAG}_tC"}
        tl = (data.get("permissions") or {}).get("team_leader")
        assert isinstance(tl, dict)
        assert "edit_members" in tl and "manage_shifts" in tl


# ============ 2. Scope letture TL (no sezione Staff) ============
class TestReadScope:
    def test_list_teams_only_led(self, db):
        _set_tl_flags(db)
        s = _tl_session()
        r = s.get(f"{API}/teams")
        assert r.status_code == 200, r.text
        ids = {t["id"] for t in r.json()}
        assert ids == {f"{TAG}_tA", f"{TAG}_tC"}, f"got {ids}"

    def test_list_staff_only_team_a_c(self, db):
        s = _tl_session()
        r = s.get(f"{API}/staff")
        assert r.status_code == 200, r.text
        ids = {x["id"] for x in r.json() if x["id"].startswith(TAG)}
        # Via TL strict: no team-less staff visible
        assert f"{TAG}_s_aS" in ids
        assert f"{TAG}_s_aV" in ids
        assert f"{TAG}_s_b" not in ids
        assert f"{TAG}_s_free" not in ids

    def test_list_shifts_only_team_a(self, db):
        s = _tl_session()
        r = s.get(f"{API}/shifts")
        assert r.status_code == 200, r.text
        ids = {x["id"] for x in r.json() if x["id"].startswith(TAG)}
        assert f"{TAG}_sh_a" in ids
        assert f"{TAG}_sh_b" not in ids

    def test_persons_enriched_only_members(self, db):
        s = _tl_session()
        r = s.get(f"{API}/persons-enriched")
        assert r.status_code == 200, r.text
        pids = {p["id"] for p in r.json() if p["id"].startswith(TAG)}
        assert f"{TAG}_pA_s" in pids
        assert f"{TAG}_pA_v" in pids
        assert f"{TAG}_pB" not in pids
        assert f"{TAG}_pFree" not in pids

    def test_person_detail_other_team_404(self, db):
        s = _tl_session()
        r = s.get(f"{API}/persons/{TAG}_pB/detail")
        assert r.status_code == 404, r.text

    def test_person_detail_own_team_ok(self, db):
        s = _tl_session()
        r = s.get(f"{API}/persons/{TAG}_pA_s/detail")
        assert r.status_code == 200, r.text

    def test_event_availabilities_only_team_persons(self, db):
        s = _tl_session()
        r = s.get(f"{API}/events/{TAG}_ev1/availabilities")
        assert r.status_code == 200, r.text
        data = r.json()
        # response may be list or dict; adapt
        items = data if isinstance(data, list) else data.get("items") or data.get("availabilities") or []
        pids = {x.get("persona_id") for x in items}
        assert f"{TAG}_pA_s" in pids
        assert f"{TAG}_pB" not in pids


# ============ 3. Scrittura senza flag TL ============
class TestWriteWithoutFlags:
    def test_put_staff_forbidden(self, db):
        _set_tl_flags(db, edit_members=False, manage_shifts=False)
        s = _tl_session()
        r = s.put(f"{API}/staff/{TAG}_s_aS", json={"stato": "contattato"})
        assert r.status_code == 403, r.text

    def test_post_shift_forbidden(self, db):
        s = _tl_session()
        r = s.post(f"{API}/shifts", json={"evento_id": f"{TAG}_ev1", "team_id": f"{TAG}_tA",
                                          "titolo": "Nuovo", "data": "2026-06-01",
                                          "ora_inizio": "09:00", "ora_fine": "11:00"})
        assert r.status_code == 403, r.text

    def test_put_team_forbidden_always(self, db):
        s = _tl_session()
        r = s.put(f"{API}/teams/{TAG}_tA", json={"nome": "Hack"})
        assert r.status_code == 403, r.text


# ============ 4. edit_members=True consente CRUD staff del Team A ============
class TestEditMembers:
    def test_put_staff_own_team_ok(self, db):
        _set_tl_flags(db, edit_members=True, manage_shifts=False)
        s = _tl_session()
        r = s.put(f"{API}/staff/{TAG}_s_aS", json={"stato": "contattato"})
        assert r.status_code == 200, r.text
        row = db.staff.find_one({"id": f"{TAG}_s_aS"}, {"_id": 0, "stato": 1})
        assert row["stato"] == "contattato"

    def test_put_staff_other_team_404(self, db):
        s = _tl_session()
        r = s.put(f"{API}/staff/{TAG}_s_b", json={"stato": "contattato"})
        assert r.status_code == 404, r.text

    def test_delete_staff_other_team_404(self, db):
        s = _tl_session()
        r = s.delete(f"{API}/staff/{TAG}_s_b")
        assert r.status_code == 404, r.text


# ============ 5. manage_shifts=True consente CRUD turni del Team A ============
class TestManageShifts:
    def test_create_shift_own_team_ok(self, db):
        _set_tl_flags(db, edit_members=False, manage_shifts=True)
        s = _tl_session()
        payload = {"evento_id": f"{TAG}_ev1", "team_id": f"{TAG}_tA",
                   "titolo": "SH-TL", "data": "2026-06-01",
                   "ora_inizio": "09:00", "ora_fine": "11:00"}
        r = s.post(f"{API}/shifts", json=payload)
        assert r.status_code == 200, r.text
        new_id = r.json()["id"]
        STATE["shifts"].append(new_id)
        # Verify
        assert db.shifts.find_one({"id": new_id}) is not None

    def test_create_shift_other_team_forbidden(self, db):
        s = _tl_session()
        payload = {"evento_id": f"{TAG}_ev1", "team_id": f"{TAG}_tB",
                   "titolo": "SH-TL-B", "data": "2026-06-01",
                   "ora_inizio": "09:00", "ora_fine": "11:00"}
        r = s.post(f"{API}/shifts", json=payload)
        assert r.status_code in (403, 404), r.text

    def test_update_shift_other_team_404(self, db):
        s = _tl_session()
        r = s.put(f"{API}/shifts/{TAG}_sh_b", json={"titolo": "HACK"})
        assert r.status_code == 404, r.text

    def test_delete_shift_own_team_ok(self, db):
        s = _tl_session()
        r = s.delete(f"{API}/shifts/{TAG}_sh_a")
        assert r.status_code == 200, r.text
        assert db.shifts.find_one({"id": f"{TAG}_sh_a"}) is None


# ============ 6. Dashboard my_teams (due team) ============
class TestDashboardMyTeams:
    def test_dashboard_my_teams_two_entries(self, db):
        _set_tl_flags(db)
        s = _tl_session()
        r = s.get(f"{API}/dashboard")
        assert r.status_code == 200, r.text
        data = r.json()
        my = data.get("my_teams")
        assert isinstance(my, list), f"my_teams missing/invalid: {data.keys()}"
        ids = {t["id"] for t in my}
        assert ids == {f"{TAG}_tA", f"{TAG}_tC"}, f"got {ids}"
        a = next(t for t in my if t["id"] == f"{TAG}_tA")
        # componenti = staff + volunteer of team A
        assert a["componenti"] >= 2
        assert a["staff"] >= 1
        assert a["volontari"] >= 1
        assert a["volontari_richiesti"] == 2
        assert "turni_totali" in a and "turni_scoperti" in a and "disponibilita" in a
        assert "inviti_inviati" in a and "registrati" in a

    def test_admin_dashboard_no_my_teams(self, admin):
        r = admin.get(f"{API}/dashboard")
        assert r.status_code == 200, r.text
        assert "my_teams" not in r.json()


# ============ 7. Revoca accesso quando cambia responsabile ============
class TestRevoke:
    def test_change_responsabile_revokes_access(self, db):
        _set_tl_flags(db)
        # Admin cambia responsabile_id del Team A e del Team C
        db.teams.update_many({"id": {"$in": [f"{TAG}_tA", f"{TAG}_tC"]}, "org_id": ORG},
                             {"$set": {"responsabile_id": "someone_else"}})
        s = _tl_session()
        r = s.get(f"{API}/staff")
        assert r.status_code == 403, r.text
        # restore
        db.teams.update_one({"id": f"{TAG}_tA", "org_id": ORG},
                            {"$set": {"responsabile_id": f"{TAG}_leader"}})
        db.teams.update_one({"id": f"{TAG}_tC", "org_id": ORG},
                            {"$set": {"responsabile_id": f"{TAG}_leader"}})


# ============ 8. PUT /org/permissions/{uid} con team_leader e audit 'Team Leader' ============
class TestPutTeamLeaderPerms:
    def test_put_saves_team_leader_and_audit(self, admin, db):
        uid = f"user_{TAG}"
        r = admin.put(f"{API}/org/permissions/{uid}",
                      json={"team_leader": {"edit_members": True, "manage_shifts": True}})
        assert r.status_code == 200, r.text
        m = db.memberships.find_one({"user_id": uid, "org_id": ORG}, {"_id": 0, "permissions": 1})
        tl = (m.get("permissions") or {}).get("team_leader") or {}
        assert tl.get("edit_members") is True
        assert tl.get("manage_shifts") is True
        # Audit storico detail should contain 'Team Leader'
        r2 = admin.get(f"{API}/org/permissions/audit")
        assert r2.status_code == 200
        items = r2.json().get("items", [])
        found = [i for i in items if i.get("target_email") == TL_EMAIL and "Team Leader" in (i.get("detail") or "")]
        assert found, f"missing 'Team Leader' in audit detail; sample: {items[:2]}"
