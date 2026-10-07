"""Iter 75 — Staff-based Invite flow, renewal notice, service-costs.
Covers:
  - GET  /api/platform/organizations/{org_id}/staff-candidates (filtering, sort, teams/leader/events, pending)
  - POST /api/platform/organizations/{org_id}/staff-candidates (add staff; reuse person on dup email/phone)
  - POST /api/platform/organizations/{org_id}/invites        (persona_id guard; staff-only; email on same person;
                                                              409 if membership exists; accept → single membership)
  - POST /api/platform/organizations/{org_id}/members        (requires persona_id of a staff person)
  - POST /api/platform/events/run-renewals                    (maint_low_balance_notice idempotent + audit)
  - GET  /api/credits/service-costs                           (6 services A-Z)
All data is TEST_ prefixed and cleaned up at the end.
"""
import os, re, uuid
import pytest, requests
from datetime import datetime, timezone, date, timedelta
from pymongo import MongoClient

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]).rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ORG = "org_qa_eventi"
ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
SUPER = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}

TEST_TAG = f"TEST_iter75_{uuid.uuid4().hex[:6]}"
STATE = {"persons": [], "staff": [], "teams": [], "events": [], "invites": [], "users": [], "memberships": [],
         "orig_balance": None, "orig_evt": None}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def sa():
    return _login(SUPER)


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    database = client[DB_NAME]
    yield database
    client.close()


def _run(_loop_unused, result):
    # Kept for backward naming; pymongo calls return directly.
    return result


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup(db):
    d = db
    now = datetime.now(timezone.utc).isoformat()

    # 2 TEST events
    ev1 = {"id": f"{TEST_TAG}_ev1", "org_id": ORG, "nome": f"{TEST_TAG} Evento Uno", "data_inizio": "2026-06-01",
           "data_fine": "2026-06-02", "created_at": now, "credit_state": "attivo"}
    ev2 = {"id": f"{TEST_TAG}_ev2", "org_id": ORG, "nome": f"{TEST_TAG} Evento Due", "data_inizio": "2026-07-01",
           "data_fine": "2026-07-02", "created_at": now, "credit_state": "attivo"}
    _run(None, d.events.insert_many([ev1, ev2]))
    STATE["events"] += [ev1["id"], ev2["id"]]

    # Multi-team / multi-event staff person "ANNA ZORRO" (leader of team1)
    p_multi = {"id": f"{TEST_TAG}_p_multi", "org_id": ORG, "nome": "Anna", "cognome": f"{TEST_TAG}_Zorro",
               "email": f"test_multi_{TEST_TAG}@example.com", "cellulare": "+393491111111", "created_at": now}
    # Second person with no email, letter B
    p_noemail = {"id": f"{TEST_TAG}_p_noe", "org_id": ORG, "nome": "Bruno", "cognome": f"{TEST_TAG}_Bianchi",
                 "cellulare": "+393492222222", "created_at": now}
    # Third = volunteer-only (must be excluded)
    p_vol = {"id": f"{TEST_TAG}_p_vol", "org_id": ORG, "nome": "Carla", "cognome": f"{TEST_TAG}_Volon",
             "email": f"test_vol_{TEST_TAG}@example.com", "created_at": now}
    _run(None, d.persons.insert_many([p_multi, p_noemail, p_vol]))
    STATE["persons"] += [p_multi["id"], p_noemail["id"], p_vol["id"]]

    # Teams
    t1 = {"id": f"{TEST_TAG}_t1", "org_id": ORG, "nome": f"{TEST_TAG} TeamA", "evento_id": ev1["id"],
          "responsabile_id": p_multi["id"], "created_at": now}
    t2 = {"id": f"{TEST_TAG}_t2", "org_id": ORG, "nome": f"{TEST_TAG} TeamB", "evento_id": ev2["id"], "created_at": now}
    _run(None, d.teams.insert_many([t1, t2]))
    STATE["teams"] += [t1["id"], t2["id"]]

    # Staff presences
    s_rows = [
        {"id": f"{TEST_TAG}_s1", "org_id": ORG, "persona_id": p_multi["id"], "evento_id": ev1["id"],
         "team_id": t1["id"], "categoria": "staff", "stato": "da_contattare", "created_at": now},
        {"id": f"{TEST_TAG}_s2", "org_id": ORG, "persona_id": p_multi["id"], "evento_id": ev2["id"],
         "team_id": t2["id"], "categoria": "collaboratore", "stato": "da_contattare", "created_at": now},
        {"id": f"{TEST_TAG}_s3", "org_id": ORG, "persona_id": p_noemail["id"], "evento_id": ev1["id"],
         "categoria": "staff", "stato": "da_contattare", "created_at": now},
        # volunteer: excluded
        {"id": f"{TEST_TAG}_s4", "org_id": ORG, "persona_id": p_vol["id"], "evento_id": ev1["id"],
         "categoria": "volontario", "stato": "da_contattare", "created_at": now},
    ]
    _run(None, d.staff.insert_many(s_rows))
    STATE["staff"] += [r["id"] for r in s_rows]

    # Save original balance to restore at end
    org = _run(None, d.organizations.find_one({"id": ORG}, {"_id": 0, "credits": 1}))
    STATE["orig_balance"] = int((org.get("credits") or {}).get("balance") or 0)

    yield

    # ---------- cleanup ----------
    _run(None, d.staff.delete_many({"id": {"$in": STATE["staff"]}}))
    _run(None, d.staff.delete_many({"org_id": ORG, "persona_id": {"$in": STATE["persons"]}}))
    _run(None, d.teams.delete_many({"id": {"$in": STATE["teams"]}}))
    _run(None, d.persons.delete_many({"id": {"$in": STATE["persons"]}}))
    _run(None, d.persons.delete_many({"org_id": ORG, "cognome": re.compile(f"^{TEST_TAG}")}))
    _run(None, d.events.delete_many({"id": {"$in": STATE["events"]}}))
    _run(None, d.org_invites.delete_many({"org_id": ORG, "email": re.compile("^test_", re.I)}))
    if STATE["users"]:
        _run(None, d.memberships.delete_many({"user_id": {"$in": STATE["users"]}}))
        _run(None, d.users.delete_many({"user_id": {"$in": STATE["users"]}}))
    # restore balance
    _run(None, d.organizations.update_one({"id": ORG}, {"$set": {"credits.balance": STATE["orig_balance"]}}))


# ====================== STAFF CANDIDATES ======================
class TestStaffCandidates:
    def test_list_only_staff_sorted(self, admin):
        r = admin.get(f"{API}/platform/organizations/{ORG}/staff-candidates")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "events" in data
        ids = [i["id"] for i in data["items"]]
        # multi + noemail must be present, volunteer must NOT be
        assert f"{TEST_TAG}_p_multi" in ids
        assert f"{TEST_TAG}_p_noe" in ids
        assert f"{TEST_TAG}_p_vol" not in ids
        # sort A-Z by cognome: Bianchi before Zorro
        test_items = [i for i in data["items"] if i["cognome"].startswith(TEST_TAG)]
        cognomi = [i["cognome"] for i in test_items]
        assert cognomi == sorted(cognomi, key=str.lower)

    def test_item_has_teams_leader_events(self, admin):
        r = admin.get(f"{API}/platform/organizations/{ORG}/staff-candidates", params={"q": f"{TEST_TAG}_Zorro"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        it = items[0]
        assert set(it["teams"]) == {f"{TEST_TAG} TeamA", f"{TEST_TAG} TeamB"}
        assert set(it["events"]) == {f"{TEST_TAG} Evento Uno", f"{TEST_TAG} Evento Due"}
        assert f"{TEST_TAG} TeamA" in it["leader_of"]
        assert it["account"] is None
        assert it["pending_invite"] is None

    def test_filter_by_phone(self, admin):
        r = admin.get(f"{API}/platform/organizations/{ORG}/staff-candidates", params={"q": "393492222222"})
        assert r.status_code == 200
        ids = [i["id"] for i in r.json()["items"]]
        assert f"{TEST_TAG}_p_noe" in ids

    def test_forbidden_for_other_org_admin(self):
        # Login as superadmin to another org? We only have qa.eventi and super. Use anon.
        r = requests.get(f"{API}/platform/organizations/org_other_fake/staff-candidates", timeout=15)
        assert r.status_code in (401, 403)

    def test_add_staff_candidate_creates_person_and_staff(self, admin, db):
        d = db
        payload = {"evento_id": f"{TEST_TAG}_ev1", "nome": "Dario", "cognome": f"{TEST_TAG}_Rossi",
                   "email": f"test_dario_{TEST_TAG}@example.com", "cellulare": "+393493333333"}
        r = admin.post(f"{API}/platform/organizations/{ORG}/staff-candidates", json=payload)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        STATE["persons"].append(pid)
        # Appears in candidates
        r2 = admin.get(f"{API}/platform/organizations/{ORG}/staff-candidates",
                       params={"q": f"test_dario_{TEST_TAG}"})
        assert pid in [i["id"] for i in r2.json()["items"]]
        # Reuse person on same email (no duplicate)
        r3 = admin.post(f"{API}/platform/organizations/{ORG}/staff-candidates",
                        json={**payload, "evento_id": f"{TEST_TAG}_ev2"})
        assert r3.status_code == 200
        assert r3.json()["id"] == pid


# ====================== INVITE ======================
class TestInvites:
    def test_400_without_persona_id(self, admin):
        r = admin.post(f"{API}/platform/organizations/{ORG}/invites",
                       json={"email": f"test_x_{TEST_TAG}@example.com", "role": "user"})
        assert r.status_code == 400

    def test_400_if_not_staff(self, admin):
        r = admin.post(f"{API}/platform/organizations/{ORG}/invites",
                       json={"email": f"test_v_{TEST_TAG}@example.com", "role": "user",
                             "persona_id": f"{TEST_TAG}_p_vol"})
        assert r.status_code == 400

    def test_staff_without_email_saved_on_same_person(self, admin, db):
        d = db
        before = _run(None, d.persons.count_documents({"org_id": ORG}))
        email = f"test_noe_{TEST_TAG}@example.com"
        r = admin.post(f"{API}/platform/organizations/{ORG}/invites",
                       json={"email": email, "role": "user", "persona_id": f"{TEST_TAG}_p_noe"})
        assert r.status_code == 200, r.text
        after = _run(None, d.persons.count_documents({"org_id": ORG}))
        assert after == before  # no new person
        p = _run(None, d.persons.find_one({"id": f"{TEST_TAG}_p_noe"}, {"_id": 0}))
        assert (p.get("email") or "").lower() == email.lower()
        inv = _run(None, d.org_invites.find_one({"org_id": ORG, "email": re.compile(f"^{re.escape(email)}$", re.I)}, {"_id": 0}))
        assert inv and inv.get("persona_id") == f"{TEST_TAG}_p_noe"
        STATE["invites"].append(inv["id"])

    def test_accept_creates_single_membership(self, admin, db):
        d = db
        # Use multi person: send invite then accept via /register
        email = f"test_accept_{TEST_TAG}@example.com"
        # Patch person email first (anna currently has test_multi_... email). Instead use her existing email.
        p = _run(None, d.persons.find_one({"id": f"{TEST_TAG}_p_multi"}, {"_id": 0, "email": 1}))
        email = p["email"]
        r = admin.post(f"{API}/platform/organizations/{ORG}/invites",
                       json={"email": email, "role": "user", "persona_id": f"{TEST_TAG}_p_multi"})
        assert r.status_code == 200, r.text
        inv = _run(None, d.org_invites.find_one({"org_id": ORG, "persona_id": f"{TEST_TAG}_p_multi",
                                                 "status": "pending"}, {"_id": 0}))
        assert inv and inv.get("token")
        STATE["invites"].append(inv["id"])
        # Register
        rr = requests.post(f"{API}/invites/{inv['token']}/register",
                          json={"password": "PwdTest1234!", "name": "Anna Z"}, timeout=20)
        assert rr.status_code == 200, rr.text
        u = _run(None, d.users.find_one({"email": email.lower()}, {"_id": 0}))
        assert u
        STATE["users"].append(u["user_id"])
        mems = list(d.memberships.find({"user_id": u["user_id"], "org_id": ORG}).limit(10))
        assert len(mems) == 1
        assert mems[0]["role"] == "user"
        assert mems[0].get("persona_id") == f"{TEST_TAG}_p_multi"

    def test_409_if_person_already_has_account(self, admin, db):
        d = db
        # multi person now has membership → re-invite returns 409
        r = admin.post(f"{API}/platform/organizations/{ORG}/invites",
                       json={"email": f"test_dup_{TEST_TAG}@example.com", "role": "user",
                             "persona_id": f"{TEST_TAG}_p_multi"})
        assert r.status_code == 409
        assert "account CRMEvent" in r.json().get("detail", "")


# ====================== ADD MEMBER requires staff persona ======================
class TestAddMember:
    def test_members_requires_persona_id(self, admin):
        r = admin.post(f"{API}/platform/organizations/{ORG}/members",
                       json={"email": "foo@example.com", "role": "user"})
        assert r.status_code == 400
        assert "Staff" in r.json().get("detail", "")


# ====================== RENEWAL NOTICE ======================
class TestRenewalNotice:
    def test_notify_once_and_audit(self, sa, db):
        d = db
        # Create a TEST event with next_maintenance_at = today+5, data_fine 60d, credit_state attivo
        today = date.today()
        due = today + timedelta(days=5)
        far = today + timedelta(days=60)
        ev = {"id": f"{TEST_TAG}_evren", "org_id": ORG, "nome": f"{TEST_TAG} RenEvent",
              "data_inizio": today.isoformat(), "data_fine": far.isoformat(),
              "credit_state": "attivo", "next_maintenance_at": due.isoformat(),
              "created_at": datetime.now(timezone.utc).isoformat()}
        _run(None, d.events.insert_one(ev))
        STATE["events"].append(ev["id"])
        # Lower balance to 0
        _run(None, d.organizations.update_one({"id": ORG}, {"$set": {"credits.balance": 0}}))

        r = sa.post(f"{API}/platform/events/run-renewals")
        assert r.status_code == 200, r.text
        data = r.json()
        notified = data.get("notified") or []
        assert ev["id"] in notified, f"expected notify, got {data}"

        ev2 = _run(None, d.events.find_one({"id": ev["id"]}, {"_id": 0}))
        assert ev2.get("maint_notice_for") == due.isoformat()

        # Audit
        audit = _run(None, d.audit_logs.find_one({"action": "maint_low_balance_notice", "org_id": ORG}))
        assert audit

        # Second call must not re-notify
        r2 = sa.post(f"{API}/platform/events/run-renewals")
        assert r2.status_code == 200
        notified2 = r2.json().get("notified") or []
        assert ev["id"] not in notified2


# ====================== SERVICE COSTS ======================
class TestServiceCosts:
    def test_6_services_sorted_az(self, admin):
        r = admin.get(f"{API}/credits/service-costs")
        assert r.status_code == 200
        svcs = r.json()["services"]
        assert len(svcs) == 6
        names = [s["name"] for s in svcs]
        assert names == sorted(names, key=str.lower)
        for s in svcs:
            assert "unit_cost" in s and isinstance(s["unit_cost"], (int, float))
            assert s.get("description")
