# Moduli e Attivazioni (iteration 173): SA modules hub, toggles, CR grant/revoke, org /org/modules auth & tenant isolation
import os, uuid, time
import pytest, requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
API = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api"
SA_EMAIL, SA_PWD = "manara.michele.pro@gmail.com", "CrmEvent2026!"
ORG = "4343e7742dd04ff8ad9d9157b34176ac"
EV = "87d6098128cc4feda081e8a7de01b32f"
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
STATE = {}


def _login(email, pwd, org=None):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {s.cookies.get('access_token')}"
    if org:
        s.headers["X-Org-Id"] = org
    return s


def _register(tag):
    email = f"test_mh_{tag}_{uuid.uuid4().hex[:6]}@crmevent-test.it"
    r = requests.post(f"{API}/auth/register-organization", json={"nome": "TEST", "cognome": tag, "email": email, "password": "TestMH2026!",
                                                                 "org_name": f"TEST_MH Org {tag}", "telefono": "+393331234567", "accept_terms": True})
    assert r.status_code == 200, r.text
    u = mdb.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "org_id": 1})
    return email, u["user_id"], u["org_id"]


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PWD, ORG)


@pytest.fixture(scope="module")
def orgs():
    a = _register("a"); b = _register("b")
    # staff member of org A = the org-B admin added as staff membership in org A (created test data)
    mdb.memberships.insert_one({"id": uuid.uuid4().hex, "user_id": b[1], "org_id": a[2], "role": "staff", "active": True})
    STATE.update(a=a, b=b)
    yield {"a": a, "b": b}
    for _, uid, oid in (a, b):
        mdb.memberships.delete_many({"user_id": uid}); mdb.users.delete_one({"user_id": uid}); mdb.organizations.delete_one({"id": oid})
        mdb.subscriptions.delete_many({"org_id": oid})


class TestSuperAdmin:
    def test_list_modules(self, sa):
        r = sa.get(f"{API}/platform/orgs/{ORG}/modules")
        assert r.status_code == 200
        d = r.json()
        assert [m["key"] for m in d["modules"]] == ["planner", "eventmap", "controlroom"]
        assert isinstance(d["history"], list)
        for m in d["modules"]:
            assert "_id" not in m and "active" in m and "disabled" in m

    def test_cr_grant_status_revoke(self, sa):
        r = sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/grant", json={"event_ids": [EV], "note": "TEST_grant"})
        assert r.status_code == 200 and r.json()["created"] == 1, r.text
        st = sa.get(f"{API}/controlroom/events/{EV}/status").json()
        assert st["active"] is True
        assert sa.get(f"{API}/org/modules/access").json()["controlroom"] is True
        # double grant idempotent
        assert sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/grant", json={"event_ids": [EV]}).json()["created"] == 0
        mods = sa.get(f"{API}/platform/orgs/{ORG}/modules").json()
        cr = next(m for m in mods["modules"] if m["key"] == "controlroom")
        pid = next(e["purchase_id"] for e in cr["events"] if e["id"] == EV)
        assert any(h["action"] == "controlroom_granted" for h in mods["history"])
        rv = sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/{pid}/revoke")
        assert rv.status_code == 200
        assert sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/{pid}/revoke").status_code == 400
        assert sa.get(f"{API}/controlroom/events/{EV}/status").json()["active"] is False

    def test_grant_foreign_event_404(self, sa):
        r = sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/grant", json={"event_ids": ["nonexistent"]})
        assert r.status_code == 404

    def test_unknown_module_404(self, sa):
        assert sa.post(f"{API}/platform/orgs/{ORG}/modules/foo/state", json={"enabled": False}).status_code == 404

    def test_toggle_controlroom(self, sa):
        r = sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/grant", json={"event_ids": [EV], "note": "TEST_toggle"})
        assert r.status_code == 200
        try:
            assert sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/state", json={"enabled": False}).status_code == 200
            assert sa.get(f"{API}/controlroom/events/{EV}/status").json()["active"] is False
            assert sa.get(f"{API}/org/modules/access").json()["controlroom"] is False
            ck = sa.post(f"{API}/controlroom/events/{EV}/checkout", json={"origin_url": "https://example.com"})
            assert ck.status_code in (403, 409), ck.text  # 409 means is_active check precedes? should be 403
            STATE["checkout_disabled"] = ck.status_code
            mods = sa.get(f"{API}/platform/orgs/{ORG}/modules").json()["modules"]
            cr = next(m for m in mods if m["key"] == "controlroom")
            assert cr["disabled"] is True and cr["active"] is False
            # data kept: purchase still active in DB
            assert mdb.controlroom_purchases.find_one({"org_id": ORG, "event_id": EV, "status": "active"})
        finally:
            assert sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/state", json={"enabled": True}).status_code == 200
        assert sa.get(f"{API}/controlroom/events/{EV}/status").json()["active"] is True
        cr = next(m for m in sa.get(f"{API}/platform/orgs/{ORG}/modules").json()["modules"] if m["key"] == "controlroom")
        for e in cr["events"]:
            if e["source"] == "superadmin":
                assert sa.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/{e['purchase_id']}/revoke").status_code == 200

    def test_toggle_planner(self, sa):
        before = sa.get(f"{API}/org/modules/access").json()
        try:
            assert sa.post(f"{API}/platform/orgs/{ORG}/modules/planner/state", json={"enabled": False}).status_code == 200
            assert sa.get(f"{API}/org/modules/access").json()["planner"] is False
            org = mdb.organizations.find_one({"id": ORG}, {"_id": 0, "modules_disabled": 1})
            assert "planner" in org["modules_disabled"]
            h = sa.get(f"{API}/platform/orgs/{ORG}/modules").json()["history"]
            assert h[0]["action"] == "module_disabled"
        finally:
            sa.post(f"{API}/platform/orgs/{ORG}/modules/planner/state", json={"enabled": True})
        assert sa.get(f"{API}/org/modules/access").json()["planner"] == before["planner"]
        assert (mdb.organizations.find_one({"id": ORG}, {"_id": 0, "modules_disabled": 1}).get("modules_disabled") or []) == []


class TestAuthz:
    def test_org_admin_sees_own_modules(self, orgs):
        a = _login(orgs["a"][0], "TestMH2026!")
        r = a.get(f"{API}/org/modules")
        assert r.status_code == 200
        assert all("grants" not in m for m in r.json()["modules"])
        assert a.get(f"{API}/org/modules/access").status_code == 200

    def test_org_admin_forbidden_platform(self, orgs):
        a = _login(orgs["a"][0], "TestMH2026!")
        assert a.get(f"{API}/platform/orgs/{ORG}/modules").status_code == 403
        assert a.post(f"{API}/platform/orgs/{ORG}/modules/planner/state", json={"enabled": False}).status_code == 403
        assert a.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/grant", json={"event_ids": [EV]}).status_code == 403
        assert a.post(f"{API}/platform/orgs/{ORG}/modules/controlroom/x/revoke").status_code == 403
        assert a.get(f"{API}/platform/orgs/{orgs['a'][2]}/modules").status_code == 403

    def test_spoof_other_org(self, orgs):
        a = _login(orgs["a"][0], "TestMH2026!", orgs["b"][2])
        assert a.get(f"{API}/org/modules").status_code == 403
        a2 = _login(orgs["a"][0], "TestMH2026!", ORG)
        assert a2.get(f"{API}/org/modules").status_code == 403

    def test_staff_member_forbidden(self, orgs):
        s = _login(orgs["b"][0], "TestMH2026!", orgs["a"][2])
        r = s.get(f"{API}/org/modules")
        assert r.status_code == 403, r.text
        # access endpoint is allowed for members (sidebar locks)
        assert s.get(f"{API}/org/modules/access").status_code == 200

    def test_unauth(self):
        assert requests.get(f"{API}/org/modules").status_code == 401
        assert requests.get(f"{API}/platform/orgs/{ORG}/modules").status_code == 401
