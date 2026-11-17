# Event duplicate (POST /api/events/{id}/duplicate): copies, isolation, permissions, planner, original untouched
import os
import uuid
import bcrypt
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
ORG = "b7f40862230441b9a0bedabefe8dab49"
SRC = "demo_evt_bcr"
PW = "TestPass2026!"
COLLS = ["teams", "event_maps", "activities", "planner_projects", "shifts", "deals", "lodgings", "meals", "eventmap_videos",
         "eventmap_tracks", "iscritti", "availabilities", "event_pipelines", "pipeline_tasks", "addon_activations", "event_purchases"]
CREATED_EVENTS: list = []
CREATED_PROJECTS: list = []


def _counts(eid):
    return {c: DB[c].count_documents({"evento_id": eid}) for c in COLLS}


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    tok = s.cookies.get("session_token") or (r.json() or {}).get("token") or (r.json() or {}).get("session_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def sa():
    s = _login(SA["email"], SA["password"])
    s.headers["X-Org-Id"] = ORG
    return s


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for eid in CREATED_EVENTS:
        for c in ("teams", "event_maps", "activities", "planner_projects"):
            DB[c].delete_many({"org_id": ORG, "evento_id": eid})
        DB.events.delete_one({"id": eid, "org_id": ORG})
    for pid in CREATED_PROJECTS:
        DB.planner_projects.delete_one({"id": pid})
        DB.planner_bom.delete_many({"project_id": pid})
    DB.users.delete_many({"user_id": {"$regex": "^user_test_dup_"}})
    DB.memberships.delete_many({"user_id": {"$regex": "^user_test_dup_"}})
    DB.user_sessions.delete_many({"user_id": {"$regex": "^user_test_dup_"}})


def _seed_member(tag, perms):
    now = datetime.now(timezone.utc).isoformat()
    uid, email = f"user_test_dup_{tag}", f"test_dup_{tag}@crmeventqa.it"
    DB.users.delete_many({"user_id": uid}); DB.memberships.delete_many({"user_id": uid})
    DB.users.insert_one({"user_id": uid, "email": email, "name": f"TEST_ {tag}", "password_hash": bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode(),
                         "role": "member", "auth_provider": "password", "org_id": ORG, "active": True, "created_at": now,
                         "accepted_terms_at": now, "onboarding": {"seen": True, "skipped": {}, "card_hidden": True, "started": True, "later": False}})
    DB.memberships.insert_one({"id": f"mem_test_dup_{tag}", "user_id": uid, "org_id": ORG, "role": "collaboratore", "active": True,
                               "permissions": perms, "created_at": now, "updated_at": now})
    return _login(email, PW)


class TestDuplicate:
    def test_full_duplicate_and_original_untouched(self, sa):
        src_before = DB.events.find_one({"id": SRC}, {"_id": 0})
        cnt_before = _counts(SRC)
        r = sa.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_Dup BCR 2027", "edizione": "2027", "data_inizio": "2027-10-17",
                                                                     "copy_maps": True, "copy_teams": True, "copy_activities": True, "copy_planner": False})
        assert r.status_code == 200, r.text
        d = r.json(); CREATED_EVENTS.append(d["id"])
        assert d["counts"] == {"teams": cnt_before["teams"], "maps": cnt_before["event_maps"], "activities": cnt_before["activities"]}
        ne = DB.events.find_one({"id": d["id"]}, {"_id": 0})
        assert ne["org_id"] == ORG and ne["nome"] == "TEST_Dup BCR 2027" and ne["edizione"] == "2027"
        assert ne["stato"] == "pianificato" and "entitlement" not in ne and ne["duplicated_from"] == SRC
        assert ne["data_inizio"] == "2027-10-17" and ne["data_fine"] == "2027-10-17"  # src 2026-10-18 -> delta 364
        for k in ("citta", "tipologia", "localita", "budget", "descrizione", "ora_inizio"):
            assert ne.get(k) == src_before.get(k), k
        nc = _counts(d["id"])
        for c in ("shifts", "deals", "lodgings", "meals", "eventmap_videos", "eventmap_tracks", "iscritti", "availabilities",
                  "event_pipelines", "pipeline_tasks", "addon_activations", "event_purchases", "planner_projects"):
            assert nc[c] == 0, c
        src_ids = {t["id"] for t in DB.teams.find({"evento_id": SRC})}
        for t in DB.teams.find({"evento_id": d["id"]}):
            assert t["id"] not in src_ids and t["responsabile_id"] is None and t["org_id"] == ORG
        for a in DB.activities.find({"evento_id": d["id"]}):
            assert a["stato"] == "da_fare" and a.get("persona_id") is None and a.get("responsabile_id") is None
        src_act = {a["titolo"]: a.get("data") for a in DB.activities.find({"evento_id": SRC})}
        one = DB.activities.find_one({"evento_id": d["id"], "data": {"$ne": None}})
        if one and src_act.get(one["titolo"]):
            from datetime import date
            assert (date.fromisoformat(one["data"][:10]) - date.fromisoformat(src_act[one["titolo"]][:10])).days == 364
        assert DB.event_maps.count_documents({"evento_id": d["id"]}) == cnt_before["event_maps"]
        assert _counts(SRC) == cnt_before
        src_after = DB.events.find_one({"id": SRC}, {"_id": 0})
        assert src_after == src_before
        assert DB.audit_logs.find_one({"action": "event_duplicated", "org_id": ORG, "detail": {"$regex": "TEST_Dup BCR 2027"}}) is not None
        # visible in list
        lst = sa.get(f"{BASE_URL}/api/events").json()
        rows = lst if isinstance(lst, list) else lst.get("items") or lst.get("events") or []
        assert any(e["id"] == d["id"] for e in rows)

    def test_no_copy_flags(self, sa):
        r = sa.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_Dup bare", "copy_maps": False, "copy_teams": False, "copy_activities": False})
        assert r.status_code == 200, r.text
        d = r.json(); CREATED_EVENTS.append(d["id"])
        assert d["counts"] == {}
        ne = DB.events.find_one({"id": d["id"]})
        assert ne["data_inizio"] == "2026-10-18" and ne["edizione"] is None
        assert sum(_counts(d["id"]).values()) == 0

    def test_copy_planner(self, sa):
        r = sa.post(f"{BASE_URL}/api/planner/events/{SRC}/projects", json={"nome": "TEST_Planner proj"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]; CREATED_PROJECTS.append(pid)
        r2 = sa.post(f"{BASE_URL}/api/planner/events/{SRC}/projects", json={"nome": "TEST_Planner archived"})
        pid2 = r2.json()["id"]; CREATED_PROJECTS.append(pid2)
        DB.planner_projects.update_one({"id": pid2}, {"$set": {"archiviato": True}})
        orig = DB.planner_projects.find_one({"id": pid}, {"_id": 0})
        r = sa.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_Dup planner", "data_inizio": "2027-10-18",
                                                                     "copy_maps": False, "copy_teams": False, "copy_activities": False, "copy_planner": True})
        assert r.status_code == 200, r.text
        d = r.json(); CREATED_EVENTS.append(d["id"])
        n_src = DB.planner_projects.count_documents({"evento_id": SRC, "archiviato": {"$ne": True}})
        assert d["counts"]["planner"] == n_src
        copies = list(DB.planner_projects.find({"evento_id": d["id"]}, {"_id": 0}))
        assert all(c["id"] not in (pid, pid2) for c in copies)
        assert any(c["nome"] == "TEST_Planner proj" for c in copies)
        assert not any(c["nome"] == "TEST_Planner archived" for c in copies)
        assert DB.planner_projects.find_one({"id": pid}, {"_id": 0}) == orig

    def test_isolation_and_validation(self, sa):
        other = DB.organizations.find_one({"id": {"$ne": ORG}}, {"id": 1})
        h = {"X-Org-Id": other["id"]}
        r = sa.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_x"}, headers=h)
        assert r.status_code == 404
        r = requests.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_x"})
        assert r.status_code == 401
        assert sa.post(f"{BASE_URL}/api/events/nonexistent_evt/duplicate", json={"nome": "TEST_x"}).status_code == 404
        assert sa.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "x"}).status_code == 422
        assert sa.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_x", "data_inizio": "18/10/2027"}).status_code == 422

    def test_invalid_calendar_date(self, sa):
        r = sa.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_bad date", "data_inizio": "2027-13-45"})
        if r.status_code == 200:
            CREATED_EVENTS.append(r.json()["id"])
        assert r.status_code in (400, 422), f"got {r.status_code}"

    def test_restricted_collaborator_403(self):
        s = _seed_member("restricted", {"sections": {"eventi": ["view", "create", "edit"]}, "events": [SRC]})
        r = s.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_restricted"})
        assert r.status_code == 403, r.text

    def test_view_only_collaborator_403(self):
        s = _seed_member("viewonly", {"sections": {"eventi": ["view"]}, "events": "all"})
        r = s.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_viewonly"})
        assert r.status_code == 403, r.text

    def test_create_collaborator_allowed(self):
        s = _seed_member("creator", {"sections": {"eventi": ["view", "create"]}, "events": "all"})
        r = s.post(f"{BASE_URL}/api/events/{SRC}/duplicate", json={"nome": "TEST_creator dup", "copy_teams": False, "copy_activities": False, "copy_maps": False})
        if r.status_code == 200:
            CREATED_EVENTS.append(r.json()["id"])
        assert r.status_code == 200, r.text
