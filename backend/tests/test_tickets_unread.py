# Tickets: creator in-app unread notifications (creator_unread, /tickets/unread-count, /tickets/{id}/read)
import os
import uuid
import asyncio

import bcrypt
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
ORG_ID = "org_qa_eventi"
MEM_EMAIL = f"test_unread_{uuid.uuid4().hex[:6]}@crmeventqa.it"
MEM_PW = "TestMember2026!"
MEM_UID = "user_TEST_" + uuid.uuid4().hex[:10]
S = {}


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.new_event_loop().run_until_complete(coro)


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module", autouse=True)
def setup_member():
    async def mk():
        db = _db()
        now = "2026-01-01T00:00:00+00:00"
        await db.users.insert_one({"user_id": MEM_UID, "email": MEM_EMAIL, "name": "TEST Member", "role": "member",
                                   "auth_provider": "password", "org_id": ORG_ID, "active": True, "picture": "",
                                   "password_hash": bcrypt.hashpw(MEM_PW.encode(), bcrypt.gensalt()).decode(),
                                   "accepted_terms_at": now, "created_at": now})
        await db.memberships.insert_one({"id": "mem_TEST_" + uuid.uuid4().hex[:8], "user_id": MEM_UID, "org_id": ORG_ID,
                                         "role": "user", "active": True, "permissions": {}, "added_by": "user_qaeventi",
                                         "created_at": now, "updated_at": now})
    run(mk())
    yield


@pytest.fixture(scope="module")
def qa():
    return _login(*QA)


@pytest.fixture(scope="module")
def sa():
    return _login(*SA)


@pytest.fixture(scope="module")
def mem():
    return _login(MEM_EMAIL, MEM_PW)


@pytest.fixture(scope="module")
def other_org():
    email = f"test_unr_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": "Unread", "email": email, "password": "TestPass2026!",
        "org_name": f"TEST_UnreadOrg_{uuid.uuid4().hex[:6]}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    S["other_email"] = email
    return _login(email, "TestPass2026!")


def cnt(s):
    r = s.get(f"{BASE_URL}/api/tickets/unread-count")
    assert r.status_code == 200, r.text
    return r.json()["unread"]


def _creator_unread(tid):
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]].tickets.find_one({"id": tid}, {"_id": 0, "creator_unread": 1}).get("creator_unread")


def test_create_tickets_initial_zero(qa, mem):
    a = qa.post(f"{BASE_URL}/api/tickets", data={"category": "problema_tecnico", "subject": "TEST_unread A", "description": "a"})
    assert a.status_code == 200, a.text
    b = mem.post(f"{BASE_URL}/api/tickets", data={"category": "problema_tecnico", "subject": "TEST_unread B", "description": "b"})
    assert b.status_code == 200, b.text
    S["A"], S["B"] = a.json(), b.json()
    assert cnt(qa) == 0 and cnt(mem) == 0


def test_internal_note_no_unread(qa, sa):
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{S['A']['id']}/messages", data={"text": "TEST internal", "internal": "true"})
    assert r.status_code == 200
    assert cnt(qa) == 0


def test_public_reply_sets_unread_for_creator_only(qa, sa, mem):
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{S['A']['id']}/messages", data={"text": "TEST reply", "internal": "false"})
    assert r.status_code == 200
    assert cnt(qa) == 1 and cnt(mem) == 0
    lst = qa.get(f"{BASE_URL}/api/tickets").json()
    assert lst[0]["id"] == S["A"]["id"] and lst[0]["unread"] is True
    assert "creator_unread" not in lst[0]
    ml = mem.get(f"{BASE_URL}/api/tickets").json()
    a = next(x for x in ml if x["id"] == S["A"]["id"])
    assert a["unread"] is False


def test_sa_get_and_other_member_do_not_mark(qa, sa, mem):
    tid = S["A"]["id"]
    assert sa.get(f"{BASE_URL}/api/platform/tickets/{tid}").status_code == 200
    assert _creator_unread(tid) is True
    r = mem.post(f"{BASE_URL}/api/tickets/{tid}/read")
    assert r.status_code == 200 and r.json()["marked"] is False
    assert cnt(qa) == 1
    d = mem.get(f"{BASE_URL}/api/tickets/{tid}").json()
    assert d["unread"] is False and d["is_creator"] is False


def test_creator_get_alone_does_not_mark_then_read(qa):
    tid = S["A"]["id"]
    d = qa.get(f"{BASE_URL}/api/tickets/{tid}").json()
    assert d["unread"] is True and d["is_creator"] is True
    assert cnt(qa) == 1
    r = qa.post(f"{BASE_URL}/api/tickets/{tid}/read")
    assert r.status_code == 200 and r.json()["marked"] is True
    assert cnt(qa) == 0
    assert qa.post(f"{BASE_URL}/api/tickets/{tid}/read").json()["marked"] is False


def test_close_reopen_reply(qa, sa):
    tid = S["A"]["id"]
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": "chiusa", "message": "TEST final"})
    assert r.status_code == 200, r.text
    assert cnt(qa) == 1
    d = qa.get(f"{BASE_URL}/api/tickets/{tid}").json()
    assert d["status"] == "chiusa" and d["closed_at"]
    assert any(m.get("text") == "TEST final" for m in d["messages"])
    assert qa.post(f"{BASE_URL}/api/tickets/{tid}/read").json()["marked"] is True
    assert cnt(qa) == 0
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": "in_lavorazione"})
    assert r.status_code == 200
    assert cnt(qa) == 1
    sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/messages", data={"text": "TEST reply 2", "internal": "false"})
    assert cnt(qa) == 1


def test_member_ticket_B_unread(qa, sa, mem):
    tid = S["B"]["id"]
    sa.post(f"{BASE_URL}/api/platform/tickets/{tid}/status", json={"status": "in_lavorazione"})
    assert cnt(mem) == 1 and cnt(qa) == 1
    assert qa.post(f"{BASE_URL}/api/tickets/{tid}/read").json()["marked"] is False
    assert cnt(mem) == 1


def test_cross_org(other_org):
    tid = S["A"]["id"]
    assert other_org.get(f"{BASE_URL}/api/tickets/{tid}").status_code == 404
    r = other_org.post(f"{BASE_URL}/api/tickets/{tid}/read")
    assert r.status_code in (404, 200)
    if r.status_code == 200:
        assert r.json()["marked"] is False
    S["cross_read_status"] = r.status_code
    assert _creator_unread(tid) is True
    assert cnt(other_org) == 0
