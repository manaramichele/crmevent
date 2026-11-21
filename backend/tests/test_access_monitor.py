# Accessi e utilizzo (Super Admin): login tracking, heartbeat, overview, config, simulation, reminder engine, unsubscribe.
# Run serially: pytest tests/test_access_monitor.py -n 0
import os
import hmac
import hashlib
import time
import uuid
from datetime import datetime, timezone, timedelta

import bcrypt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
RUN = uuid.uuid4().hex[:6]
ORG_ID = f"TEST_org_{RUN}"
ADMIN_PW = "TestPass123!"
CREATED = {"users": [], "orgs": [ORG_ID]}


def now():
    return datetime.now(timezone.utc)


def ago(days=0, minutes=0):
    return (now() - timedelta(days=days, minutes=minutes)).isoformat()


def mk_user(tag, *, last_login_days=None, created_days=30, active=True, role_mem="admin_org", pw=True,
            marketing=False, org=ORG_ID, user_role="admin"):
    uid = f"TEST_{RUN}_{tag}"
    email = f"test_{RUN}_{tag}@example.com".lower()
    db.users.insert_one({"user_id": uid, "email": email, "name": f"TEST_ {tag}", "role": user_role, "org_id": org,
                         "auth_provider": "password", "active": active, "created_at": ago(created_days),
                         "password_hash": bcrypt.hashpw(ADMIN_PW.encode(), bcrypt.gensalt()).decode() if pw else None,
                         "marketing_consent": marketing})
    db.memberships.insert_one({"id": f"TEST_m_{uid}", "user_id": uid, "org_id": org, "role": role_mem, "active": True,
                               "created_at": ago(created_days)})
    if last_login_days is not None:
        ll = ago(last_login_days)
        db.access_users.insert_one({"user_id": uid, "last_login_at": ll, "first_login_at": ll, "login_count": 1, "total_seconds": 0})
    CREATED["users"].append(uid)
    return uid, email


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module", autouse=True)
def setup_cleanup():
    db.organizations.insert_one({"id": ORG_ID, "nome": f"TEST_Org {RUN}", "created_at": ago()})
    yield
    db.access_sessions.delete_many({"client_id": "sa-test"})
    if os.environ.get("KEEP_ACCESS_TEST_DATA") == "1":  # used to inspect data in the UI; cleanup with cleanup_access_test.py
        import json
        json.dump(CREATED, open("/tmp/access_test_created.json", "w"))
        return
    cleanup(CREATED)


def cleanup(created):
    uids = created["users"]
    emails = [u["email"] for u in db.users.find({"user_id": {"$in": uids}}, {"email": 1})]
    db.audit_logs.delete_many({"$or": [{"target_email": {"$in": emails}}, {"org_id": {"$in": created["orgs"]}}]})
    for c in ("access_users", "access_logins", "access_sessions", "access_reminders"):
        db[c].delete_many({"user_id": {"$in": uids}})
    db.memberships.delete_many({"user_id": {"$in": uids}})
    db.users.delete_many({"user_id": {"$in": uids}})
    db.organizations.delete_many({"id": {"$in": created["orgs"]}})
    s = login(SA["email"], SA["password"])
    s.post(f"{BASE_URL}/api/platform/access/deactivate")
    s.put(f"{BASE_URL}/api/platform/access/config", json={"enabled": False, "orgs_include": [],
          "templates": {k: None for k in ("inactive_1", "inactive_2", "never_1", "never_2")}})


@pytest.fixture(scope="module")
def sa():
    return login(SA["email"], SA["password"])


@pytest.fixture(scope="module")
def org_admin():
    uid, email = mk_user("orgadm", last_login_days=None, created_days=1)
    return uid, email, login(email, ADMIN_PW)


# ---------- Login tracking ----------
def test_sa_login_tracks(sa):
    me = sa.get(f"{BASE_URL}/api/auth/me").json()
    uid = me["user_id"]
    before = (db.access_users.find_one({"user_id": uid}) or {}).get("login_count", 0)
    login(SA["email"], SA["password"])
    after = db.access_users.find_one({"user_id": uid})
    assert after["login_count"] == before + 1
    assert db.access_logins.find_one({"user_id": uid}, sort=[("at", -1)])["method"] == "password"


# ---------- Auth gating ----------
@pytest.mark.parametrize("path,method", [("/api/platform/access/overview", "get"), ("/api/platform/access/config", "get"),
                                         ("/api/platform/access/simulate", "post"), ("/api/platform/access/run-now", "post"),
                                         ("/api/platform/access/reminders", "get"), ("/api/platform/access/activate", "post"),
                                         ("/api/platform/access/templates", "get")])
def test_gating(org_admin, path, method):
    r = getattr(org_admin[2], method)(f"{BASE_URL}{path}", json={"confirm": True})
    assert r.status_code == 403, (path, r.status_code)
    r2 = getattr(requests, method)(f"{BASE_URL}{path}", json={"confirm": True})
    assert r2.status_code == 401, (path, r2.status_code)


# ---------- Heartbeat ----------
def test_heartbeat_flow(org_admin):
    uid, _, s = org_admin
    assert db.access_users.find_one({"user_id": uid})["login_count"] == 1
    r = s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "c1", "interacted": False})
    assert r.json()["counted"] is False
    assert not db.access_users.find_one({"user_id": uid}).get("last_activity_at")
    assert s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "c1", "interacted": True}).json()["counted"]
    s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "c2", "interacted": True})
    t0 = db.access_users.find_one({"user_id": uid})["total_seconds"]
    time.sleep(4)
    s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "c1", "interacted": True})
    s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "c2", "interacted": True})
    t1 = db.access_users.find_one({"user_id": uid})["total_seconds"]
    assert 3 <= t1 - t0 <= 6, f"two tabs doubled total: {t1 - t0}"
    # 60s cap: backdate last_counted & session by 3 min (within 5 min timeout)
    db.access_users.update_one({"user_id": uid}, {"$set": {"last_counted_at": ago(minutes=3)}})
    db.access_sessions.update_one({"user_id": uid, "client_id": "c1", "ended_at": None}, {"$set": {"last_activity_at": ago(minutes=3)}})
    sess_before = db.access_sessions.find_one({"user_id": uid, "client_id": "c1", "ended_at": None})["active_seconds"]
    s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "c1", "interacted": True})
    t2 = db.access_users.find_one({"user_id": uid})["total_seconds"]
    assert t2 - t1 == 60
    assert db.access_sessions.find_one({"user_id": uid, "client_id": "c1", "ended_at": None})["active_seconds"] - sess_before == 60
    # timeout: backdate 10 min -> previous session closed with timeout and new one opened
    old = db.access_sessions.find_one({"user_id": uid, "client_id": "c1", "ended_at": None})
    db.access_sessions.update_one({"id": old["id"]}, {"$set": {"last_activity_at": ago(minutes=10)}})
    s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "c1", "interacted": True})
    closed = db.access_sessions.find_one({"id": old["id"]})
    assert closed["end_reason"] == "timeout" and closed["ended_at"]
    assert db.access_sessions.count_documents({"user_id": uid, "client_id": "c1", "ended_at": None}) == 1
    # logout end
    s.post(f"{BASE_URL}/api/access/end", json={"client_id": "c1", "reason": "logout"})
    assert db.access_sessions.count_documents({"user_id": uid, "client_id": "c1", "ended_at": None}) == 0
    assert db.access_sessions.find_one({"user_id": uid, "client_id": "c1"}, sort=[("started_at", -1)])["end_reason"] == "logout"


# ---------- Overview ----------
def test_overview(sa, org_admin):
    s = sa
    s.post(f"{BASE_URL}/api/access/heartbeat", json={"client_id": "sa-test", "interacted": True})
    r = s.get(f"{BASE_URL}/api/platform/access/overview")
    assert r.status_code == 200
    d = r.json()
    k, rows = d["kpis"], d["users"]
    assert k["users"] == len(rows)
    assert k["never"] == sum(1 for x in rows if x["status"] == "never")
    assert k["logged"] + k["never"] == k["users"]
    assert k["active_7"] + k["inactive_7"] == k["logged"]
    me = s.get(f"{BASE_URL}/api/auth/me").json()["user_id"]
    row = next(x for x in rows if x["user_id"] == me)
    assert row["status"] == "online" and row["last_login_at"] and row["first_login_at"]
    # scope active
    r = s.get(f"{BASE_URL}/api/platform/access/overview?scope=active", headers={"X-Org-Id": ORG_ID})
    assert r.status_code == 200
    assert {x["user_id"] for x in r.json()["users"]} <= set(CREATED["users"])
    assert org_admin[0] in {x["user_id"] for x in r.json()["users"]}
    assert s.get(f"{BASE_URL}/api/platform/access/overview?scope=active").status_code == 400
    assert s.get(f"{BASE_URL}/api/platform/access/overview?scope=active", headers={"X-Org-Id": "nope"}).status_code == 400
    det = s.get(f"{BASE_URL}/api/platform/access/users/{org_admin[0]}").json()
    assert det["user"]["login_count"] == 1 and len(det["sessions"]) >= 2 and "reminders" in det
    assert s.get(f"{BASE_URL}/api/platform/access/users/nonexistent").status_code == 404


# ---------- Config ----------
def test_config_validation(sa):
    c = sa.get(f"{BASE_URL}/api/platform/access/config").json()
    assert c["fake_send"] is True and c["mode"] in ("simulation", "live")
    assert sa.put(f"{BASE_URL}/api/platform/access/config", json={"never_first_days": 14, "never_second_days": 10}).status_code == 400
    assert sa.put(f"{BASE_URL}/api/platform/access/config", json={"inactivity_timeout_min": 0}).status_code == 400
    assert sa.put(f"{BASE_URL}/api/platform/access/config", json={"run_hour": 24}).status_code == 400
    assert sa.put(f"{BASE_URL}/api/platform/access/config", json={"never_start_from": "foo"}).status_code == 400
    r = sa.put(f"{BASE_URL}/api/platform/access/config", json={"inactivity_timeout_min": 6})
    assert r.status_code == 200 and r.json()["inactivity_timeout_min"] == 6
    r = sa.put(f"{BASE_URL}/api/platform/access/config", json={"inactivity_timeout_min": 5, "kinds": {"never_1": "bogus"}})
    assert r.json()["kinds"]["never_1"] == "service"


def test_activate_refuses_without_templates(sa):
    sa.put(f"{BASE_URL}/api/platform/access/config", json={"templates": {"inactive_1": None, "inactive_2": None, "never_1": None, "never_2": None}})
    r = sa.post(f"{BASE_URL}/api/platform/access/activate", json={"confirm": True})
    assert r.status_code == 400 and "template" in r.json()["detail"].lower()
    assert sa.post(f"{BASE_URL}/api/platform/access/run-now").status_code == 400


# ---------- Reminder engine ----------
def recs(uid):
    return list(db.access_reminders.find({"user_id": uid}, {"_id": 0}))


def test_reminder_engine(sa):
    A, _ = mk_user("inact8", last_login_days=8)
    B, _ = mk_user("never8", created_days=8)
    C, _ = mk_user("disabled", last_login_days=8, active=False)
    D, _ = mk_user("roleuser", last_login_days=8, role_mem="user", user_role="staff")
    E, _ = mk_user("optout", last_login_days=8)
    F, _ = mk_user("noact", created_days=8, pw=False)
    G, _ = mk_user("relogin", last_login_days=8)
    H, _ = mk_user("neverlogin", created_days=8)
    # unsubscribe
    assert requests.get(f"{BASE_URL}/api/access/unsubscribe", params={"u": E, "t": "wrong"}).status_code == 400
    tok = hmac.new(os.environ["JWT_SECRET"].encode(), f"acc-unsub:{E}".encode(), hashlib.sha256).hexdigest()[:32]
    assert requests.get(f"{BASE_URL}/api/access/unsubscribe", params={"u": E, "t": tok}).status_code == 200
    assert db.users.find_one({"user_id": E})["reminders_opt_out"] is True

    r = sa.put(f"{BASE_URL}/api/platform/access/config", json={"orgs_include": [ORG_ID], "templates": {
        "inactive_1": 101, "inactive_2": 102, "never_1": 103, "never_2": "104"}})
    assert r.json()["templates"] == {"inactive_1": 101, "inactive_2": 102, "never_1": 103, "never_2": 104}
    n_before = db.access_reminders.count_documents({})
    sim = sa.post(f"{BASE_URL}/api/platform/access/simulate").json()
    assert db.access_reminders.count_documents({}) == n_before
    items = {i["user_id"]: i for i in sim["items"]}
    assert items[A]["step"] == "inactive_1" and items[A]["excluded"] is None and items[A]["template_id"] == 101
    assert items[B]["step"] == "never_1" and items[B]["excluded"] is None
    assert items[C]["excluded"] == "Account disabilitato"
    assert items[D]["excluded"] == "Ruolo non incluso"
    assert items[E]["excluded"] == "Ha disattivato i promemoria"
    assert items[F]["excluded"] == "Account non ancora attivato"

    assert sa.post(f"{BASE_URL}/api/platform/access/activate", json={"confirm": False}).status_code == 400
    r = sa.post(f"{BASE_URL}/api/platform/access/activate", json={"confirm": True})
    assert r.status_code == 200 and r.json()["mode"] == "live"
    st = sa.post(f"{BASE_URL}/api/platform/access/run-now").json()
    assert st["sent"] >= 4, st
    for u in (A, B, G, H):
        rr = recs(u)
        assert len(rr) == 1 and rr[0]["status"] == "test_sent" and rr[0]["brevo_message_id"].startswith("<test-"), (u, rr)
    for u in (C, D, E, F):
        assert recs(u) == []
    # no duplicates
    sa.post(f"{BASE_URL}/api/platform/access/run-now")
    for u in (A, B, G, H):
        assert len(recs(u)) == 1

    # time travel: A last login 15d, inactive_1 sent 8d ago (cycle id follows the reference login)
    ll = (now() - timedelta(days=15)).isoformat()
    db.access_users.update_one({"user_id": A}, {"$set": {"last_login_at": ll}})
    db.access_reminders.update_one({"user_id": A, "step": "inactive_1"}, {"$set": {"cycle_id": f"inactive:{A}:{ll}", "sent_at": ago(8)}})
    # G logs in again now
    db.access_users.update_one({"user_id": G}, {"$set": {"last_login_at": ago()}, "$inc": {"login_count": 1}})
    db.access_logins.insert_one({"id": uuid.uuid4().hex, "user_id": G, "at": ago(), "method": "password"})
    # B never-logged 15d, never_1 sent 8d ago; H logs in
    db.users.update_one({"user_id": B}, {"$set": {"created_at": ago(15)}})
    db.access_reminders.update_one({"user_id": B, "step": "never_1"}, {"$set": {"sent_at": ago(8)}})
    db.users.update_one({"user_id": H}, {"$set": {"created_at": ago(15)}})
    db.access_reminders.update_one({"user_id": H, "step": "never_1"}, {"$set": {"sent_at": ago(8)}})
    db.access_users.insert_one({"user_id": H, "last_login_at": ago(), "first_login_at": ago(), "login_count": 1, "total_seconds": 0})
    db.access_logins.insert_one({"id": uuid.uuid4().hex, "user_id": H, "at": ago(), "method": "password"})

    sim = {i["user_id"]: i for i in sa.post(f"{BASE_URL}/api/platform/access/simulate").json()["items"]}
    assert sim[A]["step"] == "inactive_2" and "consenso marketing" in (sim[A]["excluded"] or "")
    assert sim[B]["step"] == "never_2" and "consenso marketing" in (sim[B]["excluded"] or "")
    sa.post(f"{BASE_URL}/api/platform/access/run-now")
    assert len(recs(A)) == 1 and len(recs(B)) == 1
    db.users.update_many({"user_id": {"$in": [A, B]}}, {"$set": {"marketing_consent": True}})
    sa.post(f"{BASE_URL}/api/platform/access/run-now")
    assert sorted(x["step"] for x in recs(A)) == ["inactive_1", "inactive_2"]
    assert sorted(x["step"] for x in recs(B)) == ["never_1", "never_2"]
    assert len(recs(G)) == 1 and len(recs(H)) == 1
    # G: 8 days after new login -> new cycle inactive_1
    db.access_users.update_one({"user_id": G}, {"$set": {"last_login_at": ago(8)}})
    sa.post(f"{BASE_URL}/api/platform/access/run-now")
    g = recs(G)
    assert len(g) == 2 and len({x["cycle_id"] for x in g}) == 2 and all(x["step"] == "inactive_1" for x in g)
    # log views
    log = sa.get(f"{BASE_URL}/api/platform/access/reminders").json()
    gl = [x for x in log if x["user_id"] == G]
    assert any(x["next_login_at"] for x in gl)
    assert all(x.get("step_label") for x in gl)
    aud = db.audit_logs if "audit_logs" in db.list_collection_names() else None
    if aud is not None:
        assert aud.count_documents({"action": "access_reminder_sent", "target_email": {"$regex": f"test_{RUN}"}}) >= 7
    # deactivate
    assert sa.post(f"{BASE_URL}/api/platform/access/deactivate").json()["mode"] == "simulation"
    assert sa.post(f"{BASE_URL}/api/platform/access/run-now").status_code == 400


def test_cron_requires_secret():
    assert requests.post(f"{BASE_URL}/api/cron/access-reminders-tick").status_code == 401
    assert requests.post(f"{BASE_URL}/api/cron/access-reminders-tick", headers={"Authorization": "Bearer x"}).status_code == 401
