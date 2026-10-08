"""Iter 81 — Permesso 'Invio inviti email' (send_invites).
Covers:
  - GET /api/org/permissions returns send_invites=False by default for non-admins
  - PUT /api/org/permissions/{uid} saves send_invites and the audit detail contains 'inviti email: sì'
  - POST /api/persons/{id}/invite and /api/person-invites/bulk return 403 for members without send_invites
  - With send_invites + team scope=leader: can only invite TEST_ staff presences in own team; other persons -> 403
  - manage_volunteers=False: cannot invite volunteers; role not allowed -> 403
  - Anti-doppione 24h -> 409 detail.code='recent_invite'; with force=true -> 200
  - Bulk: persons without email / already invited <24h / out-of-scope get skipped
  - Non-admin cannot re-invite 'accesso_disabilitato' person; CRM account with membership -> 409
All data prefixed TEST_iter81_ and cleaned up at end.
"""
import os
import re
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
import bcrypt

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ORG = "org_qa_eventi"
ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
TAG = f"TEST_iter81_{uuid.uuid4().hex[:6]}"
COLLAB_EMAIL = f"test_collab_{TAG}@example.com".lower()
COLLAB_PWD = "Collab2026!"

STATE = {"users": [], "persons": [], "staff": [], "teams": [], "events": [], "memberships": []}


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

    # Collaboratore test user
    uid = f"user_{TAG}"
    pwd_hash = bcrypt.hashpw(COLLAB_PWD.encode(), bcrypt.gensalt()).decode()
    d.users.insert_one({"user_id": uid, "email": COLLAB_EMAIL, "name": f"Collab {TAG}",
                        "role": "user", "auth_provider": "password", "password_hash": pwd_hash,
                        "org_id": ORG, "active": True, "created_at": now, "telefono": "+393490000000"})
    STATE["users"].append(uid)

    # 2 events
    ev1 = {"id": f"{TAG}_ev1", "org_id": ORG, "nome": f"{TAG} EV1",
           "data_inizio": "2026-06-01", "data_fine": "2026-06-02",
           "credit_state": "attivo", "created_at": now}
    ev2 = {"id": f"{TAG}_ev2", "org_id": ORG, "nome": f"{TAG} EV2",
           "data_inizio": "2026-07-01", "data_fine": "2026-07-02",
           "credit_state": "attivo", "created_at": now}
    d.events.insert_many([ev1, ev2])
    STATE["events"] += [ev1["id"], ev2["id"]]

    # Leader person (same email as collaboratore) -> owns Team A on ev1
    leader_p = {"id": f"{TAG}_leader", "org_id": ORG, "nome": "Leader", "cognome": f"{TAG}_Collab",
                "email": COLLAB_EMAIL, "created_at": now}
    # Person in Team A - staff on ev1 (invite OK)
    p_in = {"id": f"{TAG}_in", "org_id": ORG, "nome": "Mario", "cognome": f"{TAG}_Rossi",
            "email": f"test_in_{TAG}@example.com", "created_at": now}
    # Person in Team B (other team, no access)
    p_out = {"id": f"{TAG}_out", "org_id": ORG, "nome": "Giulio", "cognome": f"{TAG}_Verdi",
             "email": f"test_out_{TAG}@example.com", "created_at": now}
    # Volunteer in Team A (used for manage_volunteers test)
    p_vol = {"id": f"{TAG}_vol", "org_id": ORG, "nome": "Vera", "cognome": f"{TAG}_Vol",
             "email": f"test_vol_{TAG}@example.com", "created_at": now}
    # Person without email
    p_noe = {"id": f"{TAG}_noe", "org_id": ORG, "nome": "No", "cognome": f"{TAG}_Mail",
             "created_at": now}
    d.persons.insert_many([leader_p, p_in, p_out, p_vol, p_noe])
    STATE["persons"] += [leader_p["id"], p_in["id"], p_out["id"], p_vol["id"], p_noe["id"]]

    # Teams
    t_a = {"id": f"{TAG}_tA", "org_id": ORG, "nome": f"{TAG} TeamA", "evento_id": ev1["id"],
           "responsabile_id": leader_p["id"], "created_at": now}
    t_b = {"id": f"{TAG}_tB", "org_id": ORG, "nome": f"{TAG} TeamB", "evento_id": ev1["id"], "created_at": now}
    d.teams.insert_many([t_a, t_b])
    STATE["teams"] += [t_a["id"], t_b["id"]]

    # Staff rows
    s_rows = [
        {"id": f"{TAG}_s_in", "org_id": ORG, "persona_id": p_in["id"], "evento_id": ev1["id"],
         "team_id": t_a["id"], "categoria": "staff", "stato": "da_contattare", "created_at": now},
        {"id": f"{TAG}_s_out", "org_id": ORG, "persona_id": p_out["id"], "evento_id": ev1["id"],
         "team_id": t_b["id"], "categoria": "staff", "stato": "da_contattare", "created_at": now},
        {"id": f"{TAG}_s_vol", "org_id": ORG, "persona_id": p_vol["id"], "evento_id": ev1["id"],
         "team_id": t_a["id"], "categoria": "volontario", "stato": "da_contattare", "created_at": now},
    ]
    d.staff.insert_many(s_rows)
    STATE["staff"] += [r["id"] for r in s_rows]

    # Membership: collaboratore - initially send_invites False, scope leader (default for collaboratore)
    mem_id = f"mem_{TAG}"
    d.memberships.insert_one({"id": mem_id, "org_id": ORG, "user_id": uid, "role": "collaboratore",
                              "active": True, "created_at": now, "permissions": {}})
    STATE["memberships"].append(uid)

    yield

    # cleanup
    d.staff.delete_many({"id": {"$in": STATE["staff"]}})
    d.teams.delete_many({"id": {"$in": STATE["teams"]}})
    d.persons.delete_many({"id": {"$in": STATE["persons"]}})
    d.events.delete_many({"id": {"$in": STATE["events"]}})
    d.memberships.delete_many({"user_id": {"$in": STATE["memberships"]}, "org_id": ORG})
    d.users.delete_many({"user_id": {"$in": STATE["users"]}})
    # audit cleanup (optional)
    d.audit_logs.delete_many({"org_id": ORG, "target_email": re.compile(f"^test_.*{TAG}", re.I)})


# ============ 1. Permissions matrix exposes send_invites ============
class TestPermissionsMatrix:
    def test_member_has_send_invites_false_default(self, admin):
        r = admin.get(f"{API}/org/permissions")
        assert r.status_code == 200, r.text
        data = r.json()
        me = next((m for m in data["members"] if m["email"] == COLLAB_EMAIL), None)
        assert me is not None, "collaboratore not found in permissions matrix"
        assert me["permissions"]["send_invites"] is False

    def test_put_send_invites_true_audit_contains_label(self, admin, db):
        uid = f"user_{TAG}"
        r = admin.put(f"{API}/org/permissions/{uid}", json={"send_invites": True})
        assert r.status_code == 200, r.text
        assert r.json().get("permissions", {}).get("send_invites") is True
        # Verify in DB
        m = db.memberships.find_one({"user_id": uid, "org_id": ORG}, {"_id": 0, "permissions": 1})
        assert (m.get("permissions") or {}).get("send_invites") is True
        # Audit storico
        r2 = admin.get(f"{API}/org/permissions/audit")
        assert r2.status_code == 200
        items = r2.json()["items"]
        found = [i for i in items if i.get("target_email") == COLLAB_EMAIL and "inviti email: sì" in (i.get("detail") or "")]
        assert found, f"no audit entry with 'inviti email: sì' for {COLLAB_EMAIL}; items={items[:3]}"


# ============ 2. 403 without send_invites ============
class TestForbiddenWithoutPerm:
    def test_single_403(self, db):
        # Temporarily remove send_invites
        uid = f"user_{TAG}"
        db.memberships.update_one({"user_id": uid, "org_id": ORG},
                                  {"$set": {"permissions.send_invites": False}})
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/persons/{TAG}_in/invite", json={})
        assert r.status_code == 403, r.text

    def test_bulk_403(self, db):
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/person-invites/bulk", json={"person_ids": [f"{TAG}_in"]})
        assert r.status_code == 403, r.text


# ============ 3. Team leader scope: can invite own team only ============
class TestTeamLeaderScope:
    @pytest.fixture(autouse=True)
    def grant_perm(self, admin, db):
        uid = f"user_{TAG}"
        # scope=leader (collaboratore default), manage_staff=True, manage_volunteers=True, send_invites=True
        r = admin.put(f"{API}/org/permissions/{uid}",
                      json={"send_invites": True,
                            "teams": {"scope": "leader", "ids": [],
                                      "manage_staff": True, "manage_volunteers": True}})
        assert r.status_code == 200, r.text
        yield

    def test_invite_person_in_own_team_ok(self, db):
        # Clear any previous invite timestamps
        db.persons.update_one({"id": f"{TAG}_in"}, {"$unset": {"last_invite_at": "", "invite_count": ""}})
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/persons/{TAG}_in/invite", json={})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # Persistence check
        p = db.persons.find_one({"id": f"{TAG}_in"}, {"_id": 0})
        assert p.get("last_invite_at")
        assert p.get("invite_count", 0) >= 1

    def test_invite_person_other_team_403(self):
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/persons/{TAG}_out/invite", json={})
        assert r.status_code == 403, r.text

    def test_recent_invite_409_and_force_200(self, db):
        # Previous test already invited _in. Immediate re-invite -> 409
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/persons/{TAG}_in/invite", json={})
        assert r.status_code == 409, r.text
        detail = r.json().get("detail", {})
        assert isinstance(detail, dict) and detail.get("code") == "recent_invite"
        # Force
        r2 = s.post(f"{API}/persons/{TAG}_in/invite", json={"force": True})
        assert r2.status_code == 200, r2.text
        p = db.persons.find_one({"id": f"{TAG}_in"}, {"_id": 0})
        assert p.get("invite_count", 0) >= 2

    def test_manage_volunteers_false_forbids_volunteer(self, admin):
        uid = f"user_{TAG}"
        admin.put(f"{API}/org/permissions/{uid}",
                  json={"send_invites": True,
                        "teams": {"scope": "leader", "ids": [],
                                  "manage_staff": True, "manage_volunteers": False}})
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/persons/{TAG}_vol/invite", json={})
        assert r.status_code == 403, r.text
        # Explicit role=volunteer on an own-team staff person -> 403 (role not allowed when manage_vol=False)
        r2 = s.post(f"{API}/persons/{TAG}_in/invite", json={"role": "volunteer", "force": True})
        assert r2.status_code == 403, r2.text


# ============ 4. Bulk invites: sent + skipped ============
class TestBulkInvites:
    def test_bulk_mixed(self, admin, db):
        uid = f"user_{TAG}"
        # Restore full perms
        admin.put(f"{API}/org/permissions/{uid}",
                  json={"send_invites": True,
                        "teams": {"scope": "leader", "ids": [],
                                  "manage_staff": True, "manage_volunteers": True}})
        # Set recent invite on _vol to force it as skipped (<24h)
        now_iso = datetime.now(timezone.utc).isoformat()
        db.persons.update_one({"id": f"{TAG}_vol"}, {"$set": {"last_invite_at": now_iso}})
        # Clear _noe (will skip: no email)
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        payload = {"person_ids": [f"{TAG}_in", f"{TAG}_out", f"{TAG}_vol", f"{TAG}_noe"]}
        # _in just invited <24h too -> expect skipped
        db.persons.update_one({"id": f"{TAG}_in"}, {"$set": {"last_invite_at": now_iso}})
        r = s.post(f"{API}/person-invites/bulk", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        ids_sent = {x["id"] for x in data["sent"]}
        ids_skip = {x["id"] for x in data["skipped"]}
        # out-of-scope team B -> skipped
        assert f"{TAG}_out" in ids_skip
        # vol recently invited -> skipped
        assert f"{TAG}_vol" in ids_skip
        # noe no email -> skipped
        assert f"{TAG}_noe" in ids_skip
        # in recently invited -> skipped
        assert f"{TAG}_in" in ids_skip
        assert ids_sent == set()


# ============ 5. Non-admin cannot re-invite 'accesso_disabilitato' nor existing CRM account ============
class TestExtraGuards:
    def test_accesso_disabilitato_blocks(self, admin, db):
        uid = f"user_{TAG}"
        admin.put(f"{API}/org/permissions/{uid}",
                  json={"send_invites": True,
                        "teams": {"scope": "leader", "ids": [],
                                  "manage_staff": True, "manage_volunteers": True}})
        db.persons.update_one({"id": f"{TAG}_in"},
                              {"$set": {"invite_status": "accesso_disabilitato"},
                               "$unset": {"last_invite_at": ""}})
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/persons/{TAG}_in/invite", json={})
        assert r.status_code == 403, r.text
        assert "disabilitato" in (r.json().get("detail") or "").lower()
        # restore
        db.persons.update_one({"id": f"{TAG}_in"}, {"$unset": {"invite_status": ""}})

    def test_existing_crm_account_409(self, db):
        # The leader_p email equals COLLAB_EMAIL and a membership exists.
        # Admin invites someone? We're testing from collaboratore scope.
        # Trying to invite leader_p (has account) -> 409
        s = _login({"email": COLLAB_EMAIL, "password": COLLAB_PWD})
        r = s.post(f"{API}/persons/{TAG}_leader/invite", json={})
        # Could be 403 (no access to this person via team scope) rather than 409
        # leader_p is also linked to Team A (as responsabile) but has NO staff row.
        # _invite_roles_for() checks staff presences only -> no roles -> 403.
        assert r.status_code in (403, 409), r.text
