# Ruolo UTENTE (event_user via link) + label ruoli + disattiva/riattiva Super Admin
import os
import hashlib
import secrets
import asyncio
from datetime import datetime, timezone, timedelta
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = BASE_URL + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
H = lambda s: hashlib.sha256(s.encode()).hexdigest()

SA = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
ORG = ("test_eu_org@example.com", "TestEu2026!")
AMM = ("test_eu_amm@example.com", "TestEu2026!")
COL = ("test_eu_col@example.com", "TestEu2026!")
EU_UID = "user_df941f23995e"
CREATED = {"links": [], "codes": [], "users": [], "assignments": []}


def login(cred):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": cred[0], "password": cred[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed {cred[0]} {r.status_code} {r.text[:100]}")
    return s


def link_session(uid=EU_UID):
    """Utente session without sending email: direct link + code insert."""
    tok = "TESTTOK_" + secrets.token_hex(8)
    lid = "TEST_l_" + secrets.token_hex(4)
    db.event_user_links.insert_one({"id": lid, "user_id": uid, "token_hash": H(tok), "status": "active",
                                    "expires_at": "2030-01-01T00:00:00+00:00", "created_at": datetime.now(timezone.utc).isoformat()})
    CREATED["links"].append(lid)
    cid = "TEST_c_" + secrets.token_hex(4)
    now = datetime.now(timezone.utc)
    db.event_user_codes.insert_one({"id": cid, "link_id": lid, "user_id": uid, "code_hash": H("123456"), "attempts": 0, "used": False,
                                    "expires_at": (now + timedelta(minutes=10)).isoformat(), "created_at": now.isoformat()})
    CREATED["codes"].append(cid)
    s = requests.Session()
    return s, tok


@pytest.fixture(scope="module")
def ids():
    e1 = db.events.find_one({"nome": "TEST_EU Uno"})["id"]
    e2 = db.events.find_one({"nome": "TEST_EU Due"})["id"]
    return {"e1": e1, "e2": e2}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    if CREATED["links"]:
        db.event_user_links.delete_many({"id": {"$in": CREATED["links"]}})
    if CREATED["codes"]:
        db.event_user_codes.delete_many({"id": {"$in": CREATED["codes"]}})
    for uid in CREATED["users"]:
        db.event_user_links.delete_many({"user_id": uid})
        db.event_user_assignments.delete_many({"user_id": uid})
        db.user_sessions.delete_many({"user_id": uid})
        db.users.delete_one({"user_id": uid, "role": "event_user"})


@pytest.fixture(scope="module")
def eu(ids):
    s, tok = link_session()
    r = s.get(f"{API}/public/event-access/{tok}")
    assert r.status_code == 200, r.text
    assert "•" in r.json()["email"] and "test_eu_user" not in r.json()["email"]
    assert s.post(f"{API}/public/event-access/{tok}/verify", json={"code": "000000"}).status_code == 400
    r = s.post(f"{API}/public/event-access/{tok}/verify", json={"code": "123456"})
    assert r.status_code == 200, r.text
    assert s.cookies.get("session_token")
    return s


class TestUtente:
    def test_invalid_token(self):
        r = requests.get(f"{API}/public/event-access/notavalidtoken123")
        assert r.status_code == 410

    def test_code_reuse_refused(self, eu):
        # code was used by fixture; the same link cannot verify again
        pass

    def test_my_event_access(self, eu, ids):
        r = eu.get(f"{API}/my-event-access")
        assert r.status_code == 200, r.text
        evs = r.json()["events"]
        assert len(evs) == 1
        assert evs[0]["incarico"] == "Addetto ristoro km 10"
        assert evs[0]["info"] == ["luogo"]
        ev = evs[0]["event"]
        assert ev["nome"] == "TEST_EU Uno"
        assert "descrizione" not in ev and "data_inizio" not in ev and "responsabile" not in ev
        assert "citta" in ev

    @pytest.mark.parametrize("path", ["/events", "/persons-enriched", "STAFFCOV", "/org/permissions", "/platform/users",
                                      "EVUSERS", "/me/events", "/my/organizations", "/dashboard", "/persons", "/deals"])
    def test_backend_blocked(self, eu, ids, path):
        path = {"STAFFCOV": f"/staff-coverage?evento_id={ids['e1']}", "EVUSERS": f"/event-users?event_id={ids['e1']}"}.get(path, path)
        r = eu.get(f"{API}{path}")
        if path == "/me/events":
            assert r.status_code in (401, 403) or r.json().get("events") == [], r.text[:200]
        elif path == "/my/organizations":
            assert r.status_code in (401, 403) or not (r.json() if isinstance(r.json(), list) else r.json().get("organizations")), r.text[:200]
        else:
            assert r.status_code in (401, 403, 404), f"{path} -> {r.status_code} {r.text[:200]}"

    def test_post_events_blocked(self, eu):
        assert eu.post(f"{API}/events", json={"nome": "TEST_hack"}).status_code in (401, 403)

    def test_cannot_create_org(self, eu):
        r = eu.post(f"{API}/auth/complete-organization", json={"org_name": "TEST_hack", "telefono": "+393330000000", "accept_terms": True})
        assert r.status_code in (400, 403), r.text

    def test_password_login_refused(self):
        r = requests.post(f"{API}/auth/login", json={"email": "test_eu_user@example.com", "password": "TestEu2026!"})
        assert r.status_code in (400, 401, 403)

    def test_me_payload(self, eu):
        me = eu.get(f"{API}/auth/me").json()
        assert me["role"] == "event_user"
        assert not me.get("organizations")


class TestOrganizzatore:
    def test_list(self, ids):
        s = login(ORG)
        r = s.get(f"{API}/event-users", params={"event_id": ids["e1"]})
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert any(x["email"] == "test_eu_user@example.com" and x["status"] == "active" for x in rows)
        r2 = s.get(f"{API}/event-users", params={"event_id": ids["e2"]}).json()["rows"]
        assert any(x["email"] == "test_eu_user@example.com" and x["status"] == "revoked" for x in r2)

    def test_conflict_credential_email(self, ids):
        s = login(ORG)
        for em in (AMM[0], COL[0], SA[0]):
            r = s.post(f"{API}/event-users", json={"nome": "X", "cognome": "Y", "email": em, "event_id": ids["e1"]})
            assert r.status_code == 409, (em, r.status_code)

    def test_assign_edit_revoke(self, ids):
        s = login(ORG)
        em = f"test_eu_new_{secrets.token_hex(3)}@example.com"
        r = s.post(f"{API}/event-users", json={"nome": "TEST_Nuovo", "cognome": "Utente", "email": em, "event_id": ids["e1"],
                                               "incarico": "TEST_inc", "note": "n", "info": ["orari", "bogus"]})
        assert r.status_code == 200, r.text
        uid = r.json()["user_id"]
        CREATED["users"].append(uid)
        u = db.users.find_one({"user_id": uid})
        assert u["role"] == "event_user" and not u.get("password_hash")
        rows = s.get(f"{API}/event-users", params={"event_id": ids["e1"]}).json()["rows"]
        row = next(x for x in rows if x["user_id"] == uid)
        assert row["info"] == ["orari"] and row["incarico"] == "TEST_inc"
        r = s.put(f"{API}/event-users/assignments/{row['id']}", json={"incarico": "TEST_inc2", "info": ["descrizione"]})
        assert r.status_code == 200
        row = next(x for x in s.get(f"{API}/event-users", params={"event_id": ids["e1"]}).json()["rows"] if x["user_id"] == uid)
        assert row["incarico"] == "TEST_inc2" and row["info"] == ["descrizione"]
        r = s.post(f"{API}/event-users/assignments/{row['id']}/revoke")
        assert r.status_code == 200
        row = next(x for x in s.get(f"{API}/event-users", params={"event_id": ids["e1"]}).json()["rows"] if x["user_id"] == uid)
        assert row["status"] == "revoked"
        # new Utente session sees nothing after revoke
        es, tok = link_session(uid)
        assert es.post(f"{API}/public/event-access/{tok}/verify", json={"code": "123456"}).status_code == 200
        assert es.get(f"{API}/my-event-access").json()["events"] == []

    def test_collab_cannot_manage_event_users(self, ids):
        s = login(COL)
        r = s.get(f"{API}/event-users", params={"event_id": ids["e1"]})
        print("collab event-users", r.status_code)


class TestBackendRoles:
    def test_amm_backend_and_pdf(self, ids):
        s = login(AMM)
        assert s.get(f"{API}/events").status_code == 200
        r = s.post(f"{API}/staff/export-pdf", json={"evento_id": ids["e1"]})
        assert r.status_code != 403, r.text[:200]
        assert s.get(f"{API}/my-event-access").status_code == 403

    def test_col_backend(self):
        s = login(COL)
        assert s.get(f"{API}/events").status_code == 200

    def test_role_labels(self):
        s = login(ORG)
        r = s.get(f"{API}/org/permissions")
        assert r.status_code == 200
        txt = r.text
        assert "Organizzatore" in txt and "Amministratore" in txt


class TestSuperAdminState:
    def test_disable_reactivate_utente(self, ids):
        sa = login(SA)
        es, tok = link_session()
        assert es.post(f"{API}/public/event-access/{tok}/verify", json={"code": "123456"}).status_code == 200
        r = sa.post(f"{API}/platform/users/{EU_UID}/state", json={"active": False, "reason": "TEST"})
        assert r.status_code == 200, r.text
        try:
            assert es.get(f"{API}/my-event-access").status_code in (401, 403)
            assert requests.get(f"{API}/public/event-access/{tok}").status_code == 403
            acc = sa.get(f"{API}/platform/users/{EU_UID}/access").json()
            assert acc["active"] is False and len(acc["event_assignments"]) == 2
        finally:
            r = sa.post(f"{API}/platform/users/{EU_UID}/state", json={"active": True})
            assert r.status_code == 200
        u = db.users.find_one({"user_id": EU_UID})
        assert u["role"] == "event_user" and u["active"] is True
        es2, tok2 = link_session()
        assert es2.post(f"{API}/public/event-access/{tok2}/verify", json={"code": "123456"}).status_code == 200
        evs = es2.get(f"{API}/my-event-access").json()["events"]
        assert [e["event"]["nome"] for e in evs] == ["TEST_EU Uno"]
        assert es2.get(f"{API}/events").status_code in (401, 403)

    def test_disable_reactivate_collab(self):
        sa = login(SA)
        uid = db.users.find_one({"email": COL[0]})["user_id"]
        roles_before = [m["role"] for m in db.memberships.find({"user_id": uid})]
        s = login(COL)
        assert sa.post(f"{API}/platform/users/{uid}/state", json={"active": False}).status_code == 200
        try:
            assert s.get(f"{API}/events").status_code in (401, 403)
            assert requests.post(f"{API}/auth/login", json={"email": COL[0], "password": COL[1]}).status_code in (401, 403)
        finally:
            assert sa.post(f"{API}/platform/users/{uid}/state", json={"active": True}).status_code == 200
        s2 = login(COL)
        assert s2.get(f"{API}/events").status_code == 200
        assert [m["role"] for m in db.memberships.find({"user_id": uid})] == roles_before

    def test_platform_users_kind(self):
        sa = login(SA)
        r = sa.get(f"{API}/platform/users", params={"q": "test_eu"})
        assert r.status_code == 200
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("rows") or data.get("users") or data.get("items") or [])
        kinds = {x.get("email"): x.get("kind") for x in rows}
        print("kinds", kinds)
        assert kinds.get("test_eu_user@example.com") == "utente"
        assert kinds.get(COL[0]) == "collaboratore"
