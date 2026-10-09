"""Iter105 - To Do List: responsible-person assignment per activity (pipeline/attivita/followup)."""
import os
import time
import uuid
import pytest
import requests
import jwt as pyjwt
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
JWT_SECRET = os.environ['JWT_SECRET']

QA_ADMIN_EMAIL = "qa.eventi@crmeventqa.it"
QA_ADMIN_PWD = "QaEvents2026!"
QA_ORG_ID = "org_qa_eventi"
NON_ADMIN_USER_ID = "user_f7b931f6759f"

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def mint_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": QA_ADMIN_EMAIL, "password": QA_ADMIN_PWD})
    assert r.status_code == 200, r.text
    s.headers.update({"X-Org-Id": QA_ORG_ID})
    return s


@pytest.fixture(scope="module")
def qa_person(admin_session):
    # pick any existing person in QA org as responsabile
    p = db.persons.find_one({"org_id": QA_ORG_ID}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
    assert p, "No persons in org_qa_eventi; cannot test"
    return p


@pytest.fixture(scope="module")
def foreign_person():
    p = db.persons.find_one({"org_id": {"$ne": QA_ORG_ID}}, {"_id": 0, "id": 1})
    assert p, "No person outside org_qa_eventi"
    return p


@pytest.fixture(scope="module")
def test_records(admin_session, qa_person):
    """Create TEST_ activity and followup, cleanup after."""
    ev = db.events.find_one({"org_id": QA_ORG_ID}, {"_id": 0, "id": 1})
    ev_id = ev["id"] if ev else None

    a = admin_session.post(f"{BASE_URL}/api/activities", json={
        "titolo": f"TEST_iter105_act_{uuid.uuid4().hex[:6]}", "tipo": "generica",
        "evento_id": ev_id, "data": datetime.now(timezone.utc).date().isoformat(),
        "stato": "da_fare"
    })
    assert a.status_code in (200, 201), a.text
    aid = a.json()["id"]

    f = admin_session.post(f"{BASE_URL}/api/followups", json={
        "titolo": f"TEST_iter105_fu_{uuid.uuid4().hex[:6]}", "evento_id": ev_id,
        "scadenza": datetime.now(timezone.utc).date().isoformat(), "stato": "aperto"
    })
    assert f.status_code in (200, 201), f.text
    fid = f.json()["id"]

    yield {"activity_id": aid, "followup_id": fid, "event_id": ev_id}

    admin_session.delete(f"{BASE_URL}/api/activities/{aid}")
    admin_session.delete(f"{BASE_URL}/api/followups/{fid}")


# ---- GET /my/todo contains responsabile_id ----
def test_todo_items_have_responsabile_id(admin_session, test_records):
    r = admin_session.get(f"{BASE_URL}/api/my/todo")
    assert r.status_code == 200
    items = r.json()["items"]
    found = [i for i in items if i["id"] in (test_records["activity_id"], test_records["followup_id"])]
    assert len(found) >= 2
    for it in found:
        assert "responsabile_id" in it
        assert "responsabile" in it


# ---- GET /my/todo/assignees sorted cognome,nome, only org persons ----
def test_assignees_sorted_and_scoped(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/my/todo/assignees")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    # verify sorted by (cognome, nome) case-insensitive
    keys = [((p.get("cognome") or "").lower(), (p.get("nome") or "").lower()) for p in items]
    assert keys == sorted(keys)
    ids = {p["id"] for p in items}
    org_ids = {p["id"] for p in db.persons.find({"org_id": QA_ORG_ID}, {"_id": 0, "id": 1})}
    assert ids == org_ids


# ---- Assign activity ----
def test_assign_activity_sets_only_responsabile(admin_session, test_records, qa_person):
    aid = test_records["activity_id"]
    before = db.activities.find_one({"id": aid}, {"_id": 0})
    r = admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                            json={"tipo": "attivita", "id": aid, "responsabile_id": qa_person["id"]})
    assert r.status_code == 200, r.text
    after = db.activities.find_one({"id": aid}, {"_id": 0})
    assert after["responsabile_id"] == qa_person["id"]
    for k in ("stato", "priorita", "evento_id", "data"):
        assert before.get(k) == after.get(k), f"Field {k} changed: {before.get(k)} vs {after.get(k)}"


def test_assign_followup_sets_only_responsabile(admin_session, test_records, qa_person):
    fid = test_records["followup_id"]
    before = db.followups.find_one({"id": fid}, {"_id": 0})
    r = admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                            json={"tipo": "followup", "id": fid, "responsabile_id": qa_person["id"]})
    assert r.status_code == 200, r.text
    after = db.followups.find_one({"id": fid}, {"_id": 0})
    assert after["responsabile_id"] == qa_person["id"]
    for k in ("stato", "priorita", "evento_id", "scadenza"):
        assert before.get(k) == after.get(k)


# ---- Unassign (null) removes ----
def test_unassign_followup(admin_session, test_records):
    fid = test_records["followup_id"]
    r = admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                            json={"tipo": "followup", "id": fid, "responsabile_id": None})
    assert r.status_code == 200
    assert db.followups.find_one({"id": fid}, {"_id": 0, "responsabile_id": 1})["responsabile_id"] is None


# ---- Foreign org person -> 400 ----
def test_foreign_person_rejected(admin_session, test_records, foreign_person):
    r = admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                            json={"tipo": "attivita", "id": test_records["activity_id"],
                                  "responsabile_id": foreign_person["id"]})
    assert r.status_code == 400, r.text


# ---- Unknown activity id -> 404 ----
def test_unknown_id_404(admin_session, qa_person):
    r = admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                            json={"tipo": "attivita", "id": "nope_" + uuid.uuid4().hex,
                                  "responsabile_id": qa_person["id"]})
    assert r.status_code == 404


# ---- Non-admin without edit perm -> 403 ----
def test_non_admin_no_edit_403(qa_person, test_records):
    # ensure membership exists and permissions are empty
    m = db.memberships.find_one({"user_id": NON_ADMIN_USER_ID, "org_id": QA_ORG_ID}, {"_id": 0})
    if not m:
        pytest.skip(f"Membership for {NON_ADMIN_USER_ID} in {QA_ORG_ID} not found")
    original_perms = m.get("permissions")
    db.memberships.update_one({"user_id": NON_ADMIN_USER_ID, "org_id": QA_ORG_ID},
                              {"$set": {"permissions": {"sections": {"attivita": [], "followup": [], "pipeline": []},
                                                         "events": "all", "teams": {"scope": "all", "ids": []}}}})
    try:
        u = db.users.find_one({"user_id": NON_ADMIN_USER_ID}, {"_id": 0, "email": 1})
        token = mint_token(NON_ADMIN_USER_ID, u["email"])
        headers = {"Authorization": f"Bearer {token}", "X-Org-Id": QA_ORG_ID}
        r = requests.post(f"{BASE_URL}/api/my/todo/assign", headers=headers,
                           json={"tipo": "attivita", "id": test_records["activity_id"],
                                 "responsabile_id": qa_person["id"]})
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    finally:
        if original_perms is None:
            db.memberships.update_one({"user_id": NON_ADMIN_USER_ID, "org_id": QA_ORG_ID},
                                       {"$unset": {"permissions": ""}})
        else:
            db.memberships.update_one({"user_id": NON_ADMIN_USER_ID, "org_id": QA_ORG_ID},
                                       {"$set": {"permissions": original_perms}})


# ---- Pipeline task assign + restore ----
def test_pipeline_assign_and_restore(admin_session, qa_person):
    task = db.pipeline_tasks.find_one({"org_id": QA_ORG_ID, "stato": {"$ne": "completata"}}, {"_id": 0})
    if not task:
        pytest.skip("No pipeline task in QA org to test")
    original_resp = task.get("responsabile_id")
    tid = task["id"]
    try:
        r = admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                                json={"tipo": "pipeline", "id": tid, "responsabile_id": qa_person["id"]})
        assert r.status_code == 200, r.text
        after = db.pipeline_tasks.find_one({"id": tid}, {"_id": 0})
        assert after["responsabile_id"] == qa_person["id"]
        # unchanged fields
        for k in ("stato", "priorita", "scadenza", "event_id"):
            assert task.get(k) == after.get(k), f"{k} changed"
    finally:
        # restore via API
        admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                           json={"tipo": "pipeline", "id": tid, "responsabile_id": original_resp})


# ---- GET /api/activities returns responsabile_id ----
def test_activities_list_includes_responsabile_id(admin_session, test_records, qa_person):
    # ensure assigned
    admin_session.post(f"{BASE_URL}/api/my/todo/assign",
                        json={"tipo": "attivita", "id": test_records["activity_id"],
                              "responsabile_id": qa_person["id"]})
    r = admin_session.get(f"{BASE_URL}/api/activities")
    assert r.status_code == 200
    rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    row = next((x for x in rows if x["id"] == test_records["activity_id"]), None)
    assert row is not None
    assert row.get("responsabile_id") == qa_person["id"]
