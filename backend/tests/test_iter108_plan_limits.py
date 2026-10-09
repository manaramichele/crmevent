"""iter108 - SILVER plan limits (5 events, 30 users), events counter never decreases, invite seats."""
import os, time, pytest, requests
from pymongo import MongoClient

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO = MongoClient(os.environ["MONGO_URL"])
DB = MONGO[os.environ["DB_NAME"]]

SUPER = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
QA = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
QA_ORG = "org_qa_eventi"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SUPER)


@pytest.fixture(scope="module")
def qa():
    return _login(QA)


# ---------- Snapshot/restore ----------
@pytest.fixture(scope="module", autouse=True)
def snapshot():
    org = DB.organizations.find_one({"id": QA_ORG}, {"_id": 0, "saas": 1, "type": 1})
    usage = DB.saas_usage.find_one({"org_id": QA_ORG}, {"_id": 0}) or {}
    pre_events = set(DB.events.find({"org_id": QA_ORG}, {"id": 1, "_id": 0}).distinct("id"))
    pre_invites = set(DB.org_invites.find({"org_id": QA_ORG, "status": "pending"}).distinct("id"))
    yield
    # cleanup TEST_ events + invites
    DB.events.delete_many({"org_id": QA_ORG, "id": {"$nin": list(pre_events)}})
    DB.org_invites.delete_many({"org_id": QA_ORG, "id": {"$nin": list(pre_invites), "$ne": None}})
    # restore saas doc
    if org:
        DB.organizations.update_one({"id": QA_ORG}, {"$set": {"saas": org.get("saas") or {}, "type": org.get("type") or "cliente"}})
    # restore saas_usage counter to original (if existed), else delete
    if usage:
        DB.saas_usage.update_one({"org_id": QA_ORG}, {"$set": usage}, upsert=True)
    else:
        DB.saas_usage.delete_one({"org_id": QA_ORG})


# ---------- Public plans config ----------
def test_plans_public_silver_limits():
    r = requests.get(f"{BASE}/api/saas/plans-public", timeout=10)
    assert r.status_code == 200
    plans = {p["key"]: p for p in r.json()["plans"]}
    s = plans["silver"]
    assert s["max_events"] == 5
    assert s["max_users"] == 30
    assert s["video_quota"] == 3
    assert s["monthly"] == 49.0
    assert round(s["yearly"], 2) == 470.40
    assert plans["bronze"]["max_events"] == 1 and plans["bronze"]["max_users"] == 10
    assert plans["gold"]["max_events"] == -1 and plans["gold"]["max_users"] == -1


# ---------- Admin helper ----------
def _set_admin(sa, status="active", plan="silver", **extra):
    body = {"status": status, "plan": plan, "comp": True, **extra}
    r = sa.put(f"{BASE}/api/platform/saas/orgs/{QA_ORG}/admin", json=body, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _seed_counter(value):
    DB.saas_usage.update_one({"org_id": QA_ORG}, {"$set": {"org_id": QA_ORG, "events_created": value}}, upsert=True)


# ---------- Events limit ----------
def test_events_limit_silver_blocks_sixth(sa, qa):
    _set_admin(sa, plan="silver", max_events=None, max_users=None)
    _seed_counter(5)  # already at limit
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_blocked"}, timeout=15)
    assert r.status_code == 403, r.text
    d = r.json().get("detail") or {}
    assert d.get("code") == "plan_limit"
    assert d.get("kind") == "events"
    assert d.get("limit") == 5


def test_deleted_events_still_count(sa, qa):
    _set_admin(sa, plan="silver")
    _seed_counter(5)
    # Even with 0 current events, counter 5 blocks
    DB.events.delete_many({"org_id": QA_ORG, "nome": "TEST_deleted_probe"})
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_deleted_probe"}, timeout=15)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "plan_limit"


def test_gold_unlimited_events(sa, qa):
    _set_admin(sa, plan="gold")
    _seed_counter(100)
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_gold_ev"}, timeout=15)
    assert r.status_code == 200, r.text
    DB.events.delete_one({"id": r.json()["id"]})


def test_bronze_blocks_second(sa, qa):
    _set_admin(sa, plan="bronze")
    _seed_counter(1)
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_bronze"}, timeout=15)
    assert r.status_code == 403
    d = r.json()["detail"]
    assert d["kind"] == "events" and d["limit"] == 1


def test_super_admin_exception_max_events(sa, qa):
    _set_admin(sa, plan="silver", max_events=10)
    _seed_counter(5)  # under override limit of 10
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_override_ev"}, timeout=15)
    assert r.status_code == 200, r.text
    ev_id = r.json()["id"]
    # Reset: set to 10 -> blocked
    _seed_counter(10)
    r2 = qa.post(f"{BASE}/api/events", json={"nome": "TEST_override_blocked"}, timeout=15)
    assert r2.status_code == 403
    assert r2.json()["detail"]["limit"] == 10
    DB.events.delete_one({"id": ev_id})


def test_trial_without_override_unlimited(sa, qa):
    # Reset to pure trial: no admin plan
    DB.organizations.update_one({"id": QA_ORG}, {"$set": {
        "saas.admin": {}, "saas.trial_end": "2099-12-31T00:00:00+00:00",
        "saas.trial_status": "active", "saas.plan": None}})
    _seed_counter(200)
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_trial_free"}, timeout=15)
    assert r.status_code == 200, r.text
    DB.events.delete_one({"id": r.json()["id"]})


def test_trial_with_override_blocks(sa, qa):
    # trial + super admin override max_events=1 should block beyond 1
    _set_admin(sa, status="trial", plan=None, max_events=1)
    # status=trial requires plan None allowed; but body validation: status=active needs plan. Set manually.
    DB.organizations.update_one({"id": QA_ORG}, {"$set": {
        "saas.admin": {"status": "auto", "max_events": 1, "comp": True},
        "saas.trial_end": "2099-12-31T00:00:00+00:00", "saas.trial_status": "active", "saas.plan": None}})
    _seed_counter(1)
    r = qa.post(f"{BASE}/api/events", json={"nome": "TEST_trial_cap"}, timeout=15)
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["kind"] == "events"


# ---------- /saas/me usage ----------
def test_saas_me_usage(qa):
    r = qa.get(f"{BASE}/api/saas/me", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "usage" in j
    u = j["usage"]
    for k in ("events", "events_current", "users", "pending_invites"):
        assert k in u


def test_auth_me_saas_usage(qa):
    r = qa.get(f"{BASE}/api/auth/me", timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert "saas_usage" in j
    if j.get("saas_usage"):
        assert "events" in j["saas_usage"]


# ---------- Users limit via invite ----------
def test_users_limit_blocks_invite(sa, qa):
    _set_admin(sa, plan="silver", max_events=None, max_users=1)
    # Find a staff person without account to invite
    person = DB.persons.find_one({"org_id": QA_ORG, "email": {"$exists": True, "$ne": None}}, {"_id": 0, "id": 1, "email": 1})
    if not person:
        pytest.skip("No staff person with email to invite")
    r = qa.post(f"{BASE}/api/platform/organizations/{QA_ORG}/invites",
                json={"persona_id": person["id"], "role": "staff", "email": person["email"]}, timeout=15)
    # Expect 403 plan_limit (1 user already = admin)
    assert r.status_code == 403, f"Expected 403 got {r.status_code}: {r.text}"
    d = r.json().get("detail") or {}
    assert d.get("code") == "plan_limit"
    assert d.get("kind") == "users"


# ---------- SaasAdmin table includes usage ----------
def test_admin_orgs_includes_usage(sa):
    r = sa.get(f"{BASE}/api/platform/saas/organizations", timeout=20)
    assert r.status_code == 200
    rows = r.json()
    qa_row = next((x for x in rows if x["id"] == QA_ORG), None)
    assert qa_row is not None
    assert "users_count" in qa_row
    assert "events_count" in qa_row
    assert "limits" in qa_row or qa_row.get("model") == "crediti"
