# Iteration 137: tickets for every org role (user/collaboratore) + SA close + isolation; availability event-day rule w/ optional preference
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
USER = ("test_iter137_user@crmeventqa.it", "TestPass2026!")
COLLAB = ("test_iter137_collab@crmeventqa.it", "TestPass2026!")
QA_ORG = "org_qa_eventi"
mdb = MongoClient(os.environ.get("MONGO_URL"))[os.environ.get("DB_NAME")]
ST = {}


def login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd})
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code}")
    return s


@pytest.fixture(scope="module")
def sa():
    return login(*SA)


@pytest.fixture(scope="module")
def org2():
    email = f"test_iter137_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={
        "nome": "TEST", "cognome": "Iso", "email": email, "password": "TestPass2026!",
        "org_name": f"TEST_Iso137_{uuid.uuid4().hex[:6]}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    s = login(email, "TestPass2026!")
    yield s
    u = mdb.users.find_one({"email": email})
    if u:
        oid = u.get("org_id")
        mdb.users.delete_many({"email": email})
        mdb.memberships.delete_many({"user_id": u["user_id"]})
        if oid:
            mdb.organizations.delete_many({"id": oid})
            mdb.settings.delete_many({"id": oid})


# --- Tickets: user and collaboratore can create and list
@pytest.mark.parametrize("who", ["user", "collab"])
def test_member_create_ticket(who, sa):
    s = login(*(USER if who == "user" else COLLAB))
    before = sa.get(f"{BASE_URL}/api/platform/tickets/count").json()["pending"]
    meta = s.get(f"{BASE_URL}/api/tickets/meta")
    assert meta.status_code == 200, meta.text
    cat = list(meta.json()["categories"].keys())[0] if isinstance(meta.json()["categories"], dict) else meta.json()["categories"][0]["id"]
    r = s.post(f"{BASE_URL}/api/tickets", data={"category": cat, "subject": f"TEST_ {who} ticket", "description": "desc"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["status"] == "aperta" and t["org_id"] == QA_ORG and t["created_by"]["email"] == (USER if who == "user" else COLLAB)[0]
    assert t["created_at"]
    ST[who] = t["id"]
    assert any(x["id"] == t["id"] for x in s.get(f"{BASE_URL}/api/tickets").json())
    assert sa.get(f"{BASE_URL}/api/platform/tickets/count").json()["pending"] == before + 1


# --- org members of same org see each other's tickets (org-scoped list)
def test_admin_sees_member_tickets():
    s = login(*QA)
    ids = {x["id"] for x in s.get(f"{BASE_URL}/api/tickets").json()}
    assert ST["user"] in ids and ST["collab"] in ids


# --- SA closes with final message; org sees chiusa + closed_at
def test_sa_close_and_org_sees(sa):
    before = sa.get(f"{BASE_URL}/api/platform/tickets/count").json()["pending"]
    r = sa.post(f"{BASE_URL}/api/platform/tickets/{ST['collab']}/status", json={"status": "chiusa", "message": "TEST final msg"})
    assert r.status_code == 200, r.text
    assert sa.get(f"{BASE_URL}/api/platform/tickets/count").json()["pending"] == before - 1
    s = login(*COLLAB)
    d = s.get(f"{BASE_URL}/api/tickets/{ST['collab']}").json()
    assert d["status"] == "chiusa" and d["closed_at"]
    assert any(m.get("text") == "TEST final msg" for m in d["messages"])


# --- Cross-org isolation
def test_cross_org_isolation(org2):
    assert org2.get(f"{BASE_URL}/api/tickets").json() == []
    for tid in (ST["user"], ST["collab"]):
        assert org2.get(f"{BASE_URL}/api/tickets/{tid}").status_code == 404
        assert org2.post(f"{BASE_URL}/api/tickets/{tid}/messages", data={"text": "x"}).status_code == 404


# ---------------- Availability ----------------
def _xff():
    return {"X-Forwarded-For": f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"}


@pytest.fixture(scope="module")
def av():
    s = login(*QA)
    s.headers.update({"X-Org-Id": QA_ORG})
    r = s.post(f"{BASE_URL}/api/events", json={"nome": "TEST_Avail137", "data_inizio_allestimento": "2026-11-08", "data_inizio": "2026-11-10",
                                               "data_fine": "2026-11-11", "data_fine_disallestimento": "2026-11-13", "localita": "Milano"})
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    code = s.post(f"{BASE_URL}/api/events/{eid}/availability/link").json()["code"]
    yield {"eid": eid, "code": code}
    mdb.availabilities.delete_many({"evento_id": eid})
    mdb.avail_links.delete_many({"evento_id": eid})
    mdb.persons.delete_many({"org_id": QA_ORG, "email": {"$regex": "^test_avail137_"}})
    mdb.events.delete_many({"id": eid})


def _body(days, **kw):
    b = {"nome": "TEST_Mario", "cognome": "Rossi", "cellulare": f"+39333{uuid.uuid4().int % 10**7:07d}",
         "email": f"test_avail137_{uuid.uuid4().hex[:8]}@example.com", "data_nascita": "1990-01-01",
         "days": [{"date": d, "disponibile": True} for d in days], "privacy": True}
    b.update(kw)
    return b


@pytest.mark.parametrize("days", [["2026-11-08"], ["2026-11-12"], ["2026-11-08", "2026-11-09", "2026-11-12", "2026-11-13"]])
def test_setup_teardown_only_rejected(av, days):
    r = requests.post(f"{BASE_URL}/api/public/availability/{av['code']}", json=_body(days), headers=_xff())
    assert r.status_code == 400, r.text
    assert "giorno dell'evento" in r.json()["detail"]


def test_no_days_rejected(av):
    r = requests.post(f"{BASE_URL}/api/public/availability/{av['code']}", json=_body([]), headers=_xff())
    assert r.status_code == 400


def test_event_day_without_pref_ok(av):
    b = _body(["2026-11-10"])
    r = requests.post(f"{BASE_URL}/api/public/availability/{av['code']}", json=b, headers=_xff())
    assert r.status_code == 200, r.text
    a = mdb.availabilities.find_one({"evento_id": av["eid"], "email": b["email"]})
    assert a and a.get("preferenza_attivita") in (None, "")


def test_altro_without_text_ok(av):
    b = _body(["2026-11-11", "2026-11-12"], preferenza_attivita="Altro", preferenza_altro="")
    r = requests.post(f"{BASE_URL}/api/public/availability/{av['code']}", json=b, headers=_xff())
    assert r.status_code == 200, r.text


def test_invalid_event_date_ignored(av):
    r = requests.post(f"{BASE_URL}/api/public/availability/{av['code']}", json=_body(["2030-01-01"]), headers=_xff())
    assert r.status_code == 400
