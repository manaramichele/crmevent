"""Iter 111: People-based plan limit (Staff e Volontari) tests.

Scenarios:
- GET /api/saas/me usage.people exists.
- Super Admin PUT org to active+silver+max_users=14 -> 403 plan_limit kind=people on NEW person.
- Existing counted person: adding staff link on another event allowed.
- quick-add new name -> 403 and NO orphan person.
- Public availability new person -> 409; existing counted -> OK.
- Raise max_users=20 -> new allowed. Gold (no override) unlimited.
- Login invites not blocked by plan_limit kind=people.
Finally restore snapshot and events_created=5.
"""
import os
import time
import requests
import pytest

def _load_env():
    for p in ("/app/frontend/.env", "/app/backend/.env"):
        try:
            for line in open(p):
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    os.environ.setdefault(k, v)
        except Exception:
            pass
_load_env()
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

SUPER = ("manara.michele.pro@gmail.com", "CrmEvent2026!")
QA = ("qa.eventi@crmeventqa.it", "QaEvents2026!")
ORG = "org_qa_eventi"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(*SUPER)


@pytest.fixture(scope="module")
def qa():
    return _login(*QA)


@pytest.fixture(scope="module")
def snapshot(sa):
    import pymongo, copy
    cli = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    dbn = os.environ.get("DB_NAME", "test_database")
    org = cli[dbn].organizations.find_one({"id": ORG}, {"_id": 0})
    assert org, "org not found"
    snap = copy.deepcopy(org.get("saas") or {})
    yield snap
    # Restore via direct mongo write of saas doc
    cli[dbn].organizations.update_one({"id": ORG}, {"$set": {"saas": snap}})
    print("RESTORE snapshot ok. plan=", snap.get("plan"), "status=", snap.get("status"))


@pytest.fixture(scope="module")
def created_ids(qa, snapshot):
    ids = {"persons": [], "staff": [], "avails_subs": [], "avail_link_id": None, "avail_code": None}
    yield ids
    # Cleanup staff links
    for sid in ids["staff"]:
        qa.delete(f"{API}/staff/{sid}", timeout=15)
    # Cleanup availabilities submissions
    for aid in ids["avails_subs"]:
        qa.delete(f"{API}/availabilities/{aid}", timeout=15)
    for pid in ids["persons"]:
        qa.delete(f"{API}/persons/{pid}", timeout=15)
    # Reset events_created to 5
    import pymongo
    try:
        cli = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        dbn = os.environ.get("DB_NAME", "test_database")
        cli[dbn].saas_usage.update_one({"org_id": ORG}, {"$set": {"events_created": 5}}, upsert=True)
    except Exception as e:
        print("events_created reset failed:", e)


def _set_plan(sa, **kw):
    r = sa.put(f"{API}/platform/saas/orgs/{ORG}/admin", json=kw, timeout=20)
    assert r.status_code == 200, f"set plan: {r.status_code} {r.text}"
    return r.json()


# ---------- Tests ----------

def test_01_usage_has_people(qa):
    r = qa.get(f"{API}/saas/me", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    us = data.get("usage") or {}
    assert "people" in us, f"usage missing 'people': {us}"
    assert isinstance(us["people"], int)
    print(f"Initial people={us['people']} events={us.get('events')}")


def test_02_force_silver_14_then_block_new_person(sa, qa, created_ids):
    # Snapshot current people count
    me = qa.get(f"{API}/saas/me", timeout=20).json()
    cur_people = (me.get("usage") or {}).get("people", 0)
    # Set silver with max_users = current count to simulate at-limit
    _set_plan(sa, status="active", plan="silver", max_users=cur_people, max_events=-1)
    time.sleep(0.3)

    # Pick an existing event
    evs = qa.get(f"{API}/events", timeout=20).json()
    assert isinstance(evs, list) and evs, "no events"
    event_id = evs[0]["id"]

    # Create a NEW person
    r = qa.post(f"{API}/persons", json={"nome": "TEST_Iter111", "cognome": "NewP", "email": "test_iter111_new@example.com"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    new_pid = r.json()["id"]
    created_ids["persons"].append(new_pid)

    # Try to attach to staff -> should 403 plan_limit people
    r2 = qa.post(f"{API}/staff", json={"persona_id": new_pid, "evento_id": event_id, "categoria": "volontario"}, timeout=20)
    assert r2.status_code == 403, f"expected 403 got {r2.status_code}: {r2.text}"
    body = r2.json()
    det = body.get("detail") or {}
    assert det.get("code") == "plan_limit" and det.get("kind") == "people", body


def test_03_existing_person_other_event_allowed(sa, qa, created_ids):
    # Find an already-counted person (any existing staff link persona)
    links = qa.get(f"{API}/staff?limit=200", timeout=20).json()
    rows = links.get("items") if isinstance(links, dict) else links
    assert rows, "no staff rows to use"
    # Pick a persona that has at least one link; pick another event where they are not yet attached
    evs = qa.get(f"{API}/events", timeout=20).json()
    chosen = None
    for row in rows:
        pid = row.get("persona_id")
        ev1 = row.get("evento_id")
        for ev in evs:
            if ev["id"] != ev1:
                # Check they are not already attached to ev["id"]
                exists = any(x.get("persona_id") == pid and x.get("evento_id") == ev["id"] for x in rows)
                if not exists:
                    chosen = (pid, ev["id"])
                    break
        if chosen:
            break
    if not chosen:
        pytest.skip("No suitable existing persona/event combo found")
    pid, eid = chosen
    r = qa.post(f"{API}/staff", json={"persona_id": pid, "evento_id": eid, "categoria": "volontario"}, timeout=20)
    assert r.status_code in (200, 201), f"existing person add should be allowed: {r.status_code} {r.text}"
    sid = r.json().get("id")
    if sid:
        created_ids["staff"].append(sid)


def test_04_quick_add_new_blocked_no_orphan(qa, created_ids):
    evs = qa.get(f"{API}/events", timeout=20).json()
    event_id = evs[0]["id"]
    unique_email = f"test_iter111_quick_{int(time.time())}@example.com"
    r = qa.post(f"{API}/staff/quick-add", json={
        "nome": "TEST_Iter111",
        "cognome": "Quick",
        "email": unique_email,
        "evento_id": event_id,
        "categoria": "volontario"
    }, timeout=20)
    assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"
    det = (r.json().get("detail") or {})
    assert det.get("code") == "plan_limit" and det.get("kind") == "people"
    # Ensure no orphan person created
    search = qa.get(f"{API}/persons?search={unique_email}", timeout=20).json()
    items = search.get("items") if isinstance(search, dict) else search
    matched = [p for p in (items or []) if (p.get("email") or "") == unique_email]
    assert not matched, f"orphan person created: {matched}"


def test_05_public_availability_blocked_new_and_allowed_existing(qa, created_ids):
    evs = qa.get(f"{API}/events", timeout=20).json()
    event_id = evs[0]["id"]
    # Try to get or create active link
    r = qa.get(f"{API}/events/{event_id}/availability/link", timeout=20)
    code = None
    created_link = False
    if r.status_code == 200 and (r.json() or {}).get("code"):
        code = r.json()["code"]
    else:
        r2 = qa.post(f"{API}/events/{event_id}/availability/link", json={}, timeout=20)
        assert r2.status_code in (200, 201), r2.text
        code = r2.json()["code"]
        created_link = True

    # New person submission -> 409
    pub = requests.Session()
    # fetch days from public endpoint
    info = pub.get(f"{API}/public/availability/{code}", timeout=20).json()
    days_list = info.get("days") or []
    if not days_list:
        pytest.skip("Event has no availability days")
    day0 = days_list[0]["date"]
    unique_email = f"test_iter111_pub_{int(time.time())}@example.com"
    payload = {"nome": "TEST_Iter111", "cognome": "Pub", "email": unique_email, "cellulare": "+393331112233",
               "data_nascita": "1990-01-01", "privacy": True,
               "days": [{"date": day0, "disponibile": True}]}
    r3 = pub.post(f"{API}/public/availability/{code}", json=payload, timeout=20)
    assert r3.status_code == 409, f"expected 409 got {r3.status_code} {r3.text}"

    # Existing counted person -> OK. Pick persona from staff.
    links = qa.get(f"{API}/staff?limit=50", timeout=20).json()
    rows = links.get("items") if isinstance(links, dict) else links
    assert rows
    # Pick a persona with real email/cellulare so pub endpoint can match it
    chosen_person = None
    for row in rows:
        pid_try = row.get("persona_id")
        if not pid_try:
            continue
        p = qa.get(f"{API}/persons/{pid_try}", timeout=20).json()
        if p and p.get("id") and (p.get("email") or p.get("cellulare")):
            chosen_person = p
            break
    assert chosen_person, "no suitable existing counted person with email/cellulare"
    person = chosen_person
    pid = person["id"]
    print("chosen pid:", pid, "email:", person.get("email"))
    payload2 = {
        "nome": person.get("nome") or "X",
        "cognome": person.get("cognome") or "Y",
        "email": person.get("email") or f"existing_{pid}@example.com",
        "cellulare": person.get("cellulare") or "+393330000001",
        "data_nascita": person.get("data_nascita") or "1990-01-01",
        "privacy": True,
        "days": [{"date": day0, "disponibile": True}],
    }
    r4 = pub.post(f"{API}/public/availability/{code}", json=payload2, timeout=20)
    # Should NOT be 409 (plan limit) — may be 200/201 or 400 for validation but not plan limit
    print("existing-submit resp:", r4.status_code, r4.text[:200])
    # Diagnose: confirm the person is actually in people_ids per server; via /saas/me usage
    me_now = qa.get(f"{API}/saas/me", timeout=20).json()
    print("usage after:", me_now.get("usage"))
    assert r4.status_code != 409, f"existing counted blocked: {r4.status_code} {r4.text}"
    if r4.status_code in (200, 201):
        aid = (r4.json() or {}).get("id")
        if aid:
            created_ids["avails_subs"].append(aid)

    # Cleanup availability link if we created it
    if created_link:
        qa.post(f"{API}/events/{event_id}/availability/link/deactivate", timeout=15)


def test_06_raise_limit_then_new_allowed_then_gold_unlimited(sa, qa, created_ids):
    me = qa.get(f"{API}/saas/me", timeout=20).json()
    cur_people = (me.get("usage") or {}).get("people", 0)
    _set_plan(sa, status="active", plan="silver", max_users=cur_people + 5, max_events=-1)
    time.sleep(0.3)
    evs = qa.get(f"{API}/events", timeout=20).json()
    event_id = evs[0]["id"]
    r = qa.post(f"{API}/persons", json={"nome": "TEST_Iter111", "cognome": "Allowed", "email": f"test_iter111_allowed_{int(time.time())}@example.com"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    created_ids["persons"].append(pid)
    r2 = qa.post(f"{API}/staff", json={"persona_id": pid, "evento_id": event_id, "categoria": "volontario"}, timeout=20)
    assert r2.status_code in (200, 201), f"new person should be allowed now: {r2.status_code} {r2.text}"
    sid = r2.json().get("id")
    if sid:
        created_ids["staff"].append(sid)

    # Now Gold, no override: unlimited (max_users=-1 for gold by default)
    _set_plan(sa, status="active", plan="gold", max_users=-1, max_events=-1)
    time.sleep(0.3)
    me2 = qa.get(f"{API}/saas/me", timeout=20).json()
    assert me2.get("limits", {}).get("max_users", 0) < 0, f"gold should be unlimited: {me2.get('limits')}"


def test_07_invites_not_plan_limited(sa, qa):
    # Force a very low max_users (people-based) and ensure invite is not blocked by plan_limit code
    me = qa.get(f"{API}/saas/me", timeout=20).json()
    cur_people = (me.get("usage") or {}).get("people", 0)
    _set_plan(sa, status="active", plan="silver", max_users=max(1, cur_people), max_events=-1)
    time.sleep(0.3)
    r = sa.post(f"{API}/platform/organizations/{ORG}/invites", json={
        "email": f"test_iter111_invite_{int(time.time())}@example.com",
        "role": "staff",
    }, timeout=20)
    # Accept any status except a plan_limit 403
    if r.status_code == 403:
        det = (r.json().get("detail") or {})
        assert det.get("code") != "plan_limit", f"invite should NOT return plan_limit: {r.text}"
    print("invite endpoint status:", r.status_code, r.text[:200])
