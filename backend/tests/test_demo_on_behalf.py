# Super Admin books demo on behalf of org users (support mode + /piattaforma/demo) — regression tests
import pytest

from demo_onbehalf_helpers import BASE_URL, SA_EMAIL, SA_PW, PW, login, open_config, setup_org, cleanup, mdb

S = {}


@pytest.fixture(scope="module", autouse=True)
def env():
    sa = login(SA_EMAIL, SA_PW)
    open_config(sa)
    ctx = setup_org("B")
    S.update(ctx=ctx, sa=sa)
    yield
    cleanup(ctx)
    mdb().demo_slot_config.delete_many({"id": "config"})


def slots(sess):
    r = sess.get(f"{BASE_URL}/api/demo/slots")
    assert r.status_code == 200, r.text
    return [s["slot_key"] for s in r.json()["slots"]]


# Flow A: normal user request (unchanged flow)
def test_flow_a_normal_request():
    m2 = login(S["ctx"]["m2"]["email"], PW)
    S["m2"] = m2
    ks = slots(m2)
    assert len(ks) > 100
    S["slot_a"] = ks[30]
    r = m2.post(f"{BASE_URL}/api/demo/requests", json={"slot_key": S["slot_a"], "nome": "Membro2 TestB"})
    assert r.status_code == 200, r.text
    db = mdb()
    req = db.demo_requests.find_one({"id": r.json()["id"]})
    assert req["status"] == "nuova" and req["org_id"] == S["ctx"]["org_id"]
    lead = db.leads.find_one({"demo_request_id": req["id"]})
    assert lead["demo_status"] == "da_confermare" and not lead.get("demo_booked_by_admin")
    mine = m2.get(f"{BASE_URL}/api/demo/mine").json()["demos"]
    assert [d["demo_slot"] for d in mine] == [S["slot_a"]]


# Permissions: non-support org users cannot book on behalf
def test_permissions_org_user_forbidden():
    owner = login(S["ctx"]["owner"]["email"], PW)
    S["owner"] = owner
    for sess in (owner, S["m2"]):
        assert sess.get(f"{BASE_URL}/api/demo/on-behalf/context").status_code == 403
        r = sess.post(f"{BASE_URL}/api/demo/on-behalf", json={"user_id": S["ctx"]["m3"]["user_id"], "slot_key": "2030-01-01T10:00"})
        assert r.status_code == 403


# Flow B: support session on member3 -> prefilled -> confirmed booking
def test_flow_b_support_booking():
    sup = login(SA_EMAIL, SA_PW)
    r = sup.post(f"{BASE_URL}/api/platform/impersonate", json={"user_id": S["ctx"]["m3"]["user_id"]})
    assert r.status_code == 200, r.text
    S["sup"] = sup
    me = sup.get(f"{BASE_URL}/api/auth/me").json()
    assert me.get("support"), me
    c = sup.get(f"{BASE_URL}/api/demo/on-behalf/context")
    assert c.status_code == 200, c.text
    ctx = c.json()
    assert ctx["org"]["id"] == S["ctx"]["org_id"]
    assert ctx["default_user_id"] == S["ctx"]["m3"]["user_id"]
    ids = {m["user_id"] for m in ctx["members"]}
    assert ids == {S["ctx"]["owner"]["user_id"], S["ctx"]["m2"]["user_id"], S["ctx"]["m3"]["user_id"]}
    m2 = next(m for m in ctx["members"] if m["user_id"] == S["ctx"]["m2"]["user_id"])
    assert m2["active_demo"] and m2["active_demo"]["demo_slot"] == S["slot_a"]
    S["slot_b"] = [k for k in (x["slot_key"] for x in ctx["slots"]) if k != S["slot_a"]][40]
    r = sup.post(f"{BASE_URL}/api/demo/on-behalf", json={"user_id": S["ctx"]["m3"]["user_id"], "slot_key": S["slot_b"]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["demo_status"] == "confermata" and b["demo_booked_by_admin"] is True
    assert b["demo_booked_by"]["via"] == "assistenza" and b["demo_booked_by"]["email"] == SA_EMAIL
    assert b["demo_meet_link"] and b["demo_meet_simulated"]
    assert b["org_id"] == S["ctx"]["org_id"] and b["user_id"] == S["ctx"]["m3"]["user_id"]
    req = mdb().demo_requests.find_one({"id": b["demo_request_id"]})
    assert req["status"] == "confermata" and req["booked_by_admin"] is True
    assert mdb().demo_slot_locks.find_one({"slot": S["slot_b"]})["lead_id"] == b["id"]
    S["lead_b"] = b["id"]


# Duplicate: user with active future demo -> 409
def test_duplicate_409():
    r = S["sup"].post(f"{BASE_URL}/api/demo/on-behalf", json={"user_id": S["ctx"]["m3"]["user_id"], "slot_key": slots(S["m2"])[50]})
    assert r.status_code == 409, r.text
    r = S["sup"].post(f"{BASE_URL}/api/demo/on-behalf", json={"user_id": S["ctx"]["m2"]["user_id"], "slot_key": slots(S["m2"])[50]})
    assert r.status_code == 409, r.text


# Overlap: slot already booked is no longer offered and is rejected
def test_overlap_409():
    assert S["slot_b"] not in slots(S["m2"])
    r = S["sa"].post(f"{BASE_URL}/api/demo/on-behalf", json={"org_id": S["ctx"]["org_id"], "user_id": S["ctx"]["owner"]["user_id"], "slot_key": S["slot_b"]})
    assert r.status_code == 409, r.text


# Cross-org: user not in org -> 400; SA direct without org -> 400
def test_validation():
    r = S["sa"].post(f"{BASE_URL}/api/demo/on-behalf", json={"org_id": S["ctx"]["org_id"], "user_id": "user_nonexistent", "slot_key": S["slot_a"]})
    assert r.status_code == 400
    assert S["sa"].get(f"{BASE_URL}/api/demo/on-behalf/context").status_code == 400


# Flow C: SA direct (prenotazioni_demo) books for owner
def test_flow_c_platform_booking():
    c = S["sa"].get(f"{BASE_URL}/api/demo/on-behalf/context", params={"org_id": S["ctx"]["org_id"]})
    assert c.status_code == 200, c.text
    assert S["slot_b"] not in [x["slot_key"] for x in c.json()["slots"]]
    S["slot_c"] = c.json()["slots"][60]["slot_key"]
    r = S["sa"].post(f"{BASE_URL}/api/demo/on-behalf", json={"org_id": S["ctx"]["org_id"], "user_id": S["ctx"]["owner"]["user_id"], "slot_key": S["slot_c"], "note": "TEST note"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["demo_status"] == "confermata" and b["demo_booked_by"]["via"] == "prenotazioni_demo" and b["demo_meet_link"]
    S["lead_c"] = b["id"]


# demo/mine scoping: member sees own, org admin sees all org demos
def test_my_demos_scoping():
    m2 = S["m2"].get(f"{BASE_URL}/api/demo/mine").json()["demos"]
    assert len(m2) == 1 and m2[0]["email"] == S["ctx"]["m2"]["email"]
    m3 = login(S["ctx"]["m3"]["email"], PW).get(f"{BASE_URL}/api/demo/mine").json()["demos"]
    assert len(m3) == 1 and m3[0]["demo_booked_by_admin"] is True and m3[0]["demo_meet_link"]
    own = S["owner"].get(f"{BASE_URL}/api/demo/mine").json()["demos"]
    assert len(own) == 3


# Platform bookings + audit log
def test_platform_bookings_and_audit():
    rows = S["sa"].get(f"{BASE_URL}/api/platform/demo/bookings").json()["bookings"]
    mine = {r["user_id"]: r for r in rows if r.get("org_id") == S["ctx"]["org_id"]}
    assert set(mine) == {S["ctx"]["owner"]["user_id"], S["ctx"]["m2"]["user_id"], S["ctx"]["m3"]["user_id"]}
    assert mine[S["ctx"]["m3"]["user_id"]]["demo_booked_by_admin"] and mine[S["ctx"]["owner"]["user_id"]]["demo_booked_by_admin"]
    logs = list(mdb().audit_logs.find({"action": "demo_booked_on_behalf", "org_id": S["ctx"]["org_id"]}))
    assert len(logs) == 2


# Known gap check: Flow A pending request slot is NOT locked -> still offered to others (overlap risk)
def test_pending_request_slot_still_offered():
    offered = S["slot_a"] in slots(S["m2"])
    print(f"Flow A pending slot still offered: {offered}")
    assert not offered, "Pending (da_confermare) request slot is still offered -> on-behalf can overlap it"
