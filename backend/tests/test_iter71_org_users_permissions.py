"""Iter71 - OrgUsers/Permissions moved under Profilo & Account. Backend coverage.

Covers:
 - /api/org/permissions GET (roles, persons, members include persona_id)
 - /api/org/permissions/{uid} PUT (persona_id + teams flags, audit written)
 - /api/org/permissions/audit GET returns permissions_changed entries
 - /api/platform/organizations/{org}/invites POST includes permissions+persona_id and persists on invite
 - _allowed_team_ids via membership.persona_id → Team Leader scope
 - staff PUT 403 when lacking manage_staff/manage_volunteers for team change
 - Super Admin with X-Org-Id can read /api/org/permissions; other org admin forbidden
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ORG = "org_TEST_tl"
UID_ADMIN = "user_TEST_tl_admin"
UID_LEADER = "user_TEST_tl_leader"
UID_RESP = "user_TEST_tl_resp"
EV = "ev_TEST_tl"
TEAM_START = "tm_TEST_start"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login("test_tl_admin@crmeventqa.it", "TestTl2026!")


@pytest.fixture(scope="module")
def resp_sess():
    return _login("test_tl_resp@crmeventqa.it", "TestTl2026!")


@pytest.fixture(scope="module")
def super_sess():
    return _login("manara.michele.pro@gmail.com", "CrmEvent2026!")


@pytest.fixture(scope="module")
def qa_admin_sess():
    return _login("qa.eventi@crmeventqa.it", "QaEvents2026!")


# ---- GET /api/org/permissions ----
def test_org_permissions_list_contains_members(admin_sess):
    r = admin_sess.get(f"{BASE}/api/org/permissions", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "members" in d and "persons" in d and "teams" in d and "roles" in d
    uids = {m["user_id"] for m in d["members"]}
    assert UID_ADMIN in uids and UID_LEADER in uids and UID_RESP in uids
    resp = next(m for m in d["members"] if m["user_id"] == UID_RESP)
    assert resp.get("persona_id") == "pe_TEST_leader"
    me = next(m for m in d["members"] if m["user_id"] == UID_ADMIN)
    assert me.get("is_self") is True


# ---- PUT /api/org/permissions/{uid} with persona_id + audit ----
def test_update_permissions_changes_and_audit(admin_sess):
    # change leader: give persona_id + sections.staff view
    payload = {
        "role": "collaboratore",
        "persona_id": "pe_TEST_leader",
        "sections": {"staff": ["view"], "dashboard": ["view"]},
        "events": "all",
        "teams": {"scope": "leader", "ids": [], "manage_staff": False, "manage_volunteers": False},
    }
    r = admin_sess.put(f"{BASE}/api/org/permissions/{UID_LEADER}", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    # audit log should include permissions_changed
    r2 = admin_sess.get(f"{BASE}/api/org/permissions/audit", timeout=20)
    assert r2.status_code == 200
    items = r2.json().get("items", [])
    assert any(it.get("action") == "permissions_changed" and it.get("target_email", "").lower() == "test_tl_leader@crmeventqa.it" for it in items), items[:3]


def test_update_self_forbidden(admin_sess):
    r = admin_sess.put(f"{BASE}/api/org/permissions/{UID_ADMIN}", json={"role": "collaboratore"}, timeout=20)
    assert r.status_code == 400


# ---- Invite with permissions + persona_id persisted on invite row ----
def test_create_invite_persists_permissions_and_persona(admin_sess):
    body = {
        "email": "test_tl_invited@crmeventqa.it",
        "role": "collaboratore",
        "nome": "Invited",
        "cognome": "TEST",
        "telefono": "+393331234567",
        "permissions": {"sections": {"staff": ["view", "edit"]}, "events": "all",
                        "teams": {"scope": "selected", "ids": [TEAM_START], "manage_staff": True, "manage_volunteers": False}},
        "persona_id": "pe_TEST_leader",
    }
    r = admin_sess.post(f"{BASE}/api/platform/organizations/{ORG}/invites", json=body, timeout=20)
    assert r.status_code == 200, r.text
    inv_id = r.json().get("id")
    assert inv_id
    # verify via DB (direct) that permissions+persona_id stored
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _check():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        inv = await db.org_invites.find_one({"id": inv_id}, {"_id": 0})
        return inv
    inv = asyncio.run(_check())
    assert inv["persona_id"] == "pe_TEST_leader"
    assert inv["permissions"]["sections"]["staff"] == ["view", "edit"] or set(inv["permissions"]["sections"]["staff"]) == {"view", "edit"}
    assert inv["permissions"]["teams"]["ids"] == [TEAM_START]
    assert inv["permissions"]["teams"]["manage_staff"] is True


# ---- Team-leader scoping via persona_id in membership ----
def test_resp_sees_only_leader_team_staff(resp_sess):
    # resp has teams.scope=leader, persona_id=pe_TEST_leader (leader of tm_TEST_start only)
    r = resp_sess.get(f"{BASE}/api/staff?evento_id={EV}", timeout=20)
    assert r.status_code == 200, r.text
    items = r.json()
    teams = {s.get("team_id") for s in items}
    assert teams.issubset({TEAM_START, None, ""}), f"saw teams: {teams}"
    assert any(s.get("team_id") == TEAM_START for s in items)


def test_resp_without_staff_edit_cannot_update(resp_sess):
    # resp currently has only staff:['view']  → PUT must 403
    r = resp_sess.get(f"{BASE}/api/staff?evento_id={EV}", timeout=20)
    staff_items = r.json()
    volontario = next((s for s in staff_items if s.get("categoria") == "volontario" and s.get("team_id") == TEAM_START), None)
    assert volontario, "need a volontario on start team"
    r2 = resp_sess.put(f"{BASE}/api/staff/{volontario['id']}", json={"stato": "confermato"}, timeout=20)
    assert r2.status_code == 403, r2.status_code


def test_resp_with_edit_can_update_volontario_but_not_staff(admin_sess, resp_sess):
    # Grant staff: view+edit, keep manage_staff=False, manage_volunteers=True
    payload = {
        "role": "collaboratore",
        "sections": {"staff": ["view", "edit"], "dashboard": ["view"], "anagrafiche": ["view"]},
        "events": "all",
        "teams": {"scope": "leader", "ids": [], "manage_staff": False, "manage_volunteers": True},
    }
    r = admin_sess.put(f"{BASE}/api/org/permissions/{UID_RESP}", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    # Create two staff records WITHOUT a team (admin), both anagrafica fresh,
    # then as resp move them INTO tm_TEST_start (the leader team).
    import asyncio, uuid
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _seed():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        pid_v = f"pe_TEST_tl_vfree_{uuid.uuid4().hex[:6]}"
        pid_s = f"pe_TEST_tl_sfree_{uuid.uuid4().hex[:6]}"
        sid_v = f"sl_TEST_tl_vfree_{uuid.uuid4().hex[:6]}"
        sid_s = f"sl_TEST_tl_sfree_{uuid.uuid4().hex[:6]}"
        await db.persons.insert_many([
            {"id": pid_v, "org_id": ORG, "nome": "VolFree", "cognome": "TEST", "created_at": "2026-01-01T00:00:00Z"},
            {"id": pid_s, "org_id": ORG, "nome": "StfFree", "cognome": "TEST", "created_at": "2026-01-01T00:00:00Z"},
        ])
        await db.staff.insert_many([
            {"id": sid_v, "org_id": ORG, "evento_id": EV, "persona_id": pid_v, "categoria": "volontario", "stato": "confermato", "created_at": "2026-01-01T00:00:00Z"},
            {"id": sid_s, "org_id": ORG, "evento_id": EV, "persona_id": pid_s, "categoria": "staff", "stato": "confermato", "created_at": "2026-01-01T00:00:00Z"},
        ])
        return sid_v, sid_s
    sid_v, sid_s = asyncio.run(_seed())
    # Volunteer -> assign to tm_TEST_start: allowed
    rv = resp_sess.put(f"{BASE}/api/staff/{sid_v}", json={"team_id": TEAM_START}, timeout=20)
    assert rv.status_code == 200, f"volunteer move expected 200, got {rv.status_code} {rv.text}"
    # Staff -> assign to tm_TEST_start: forbidden by manage_staff=False
    rs = resp_sess.put(f"{BASE}/api/staff/{sid_s}", json={"team_id": TEAM_START}, timeout=20)
    assert rs.status_code == 403, f"staff move expected 403, got {rs.status_code} {rs.text}"
    assert "staff" in rs.json().get("detail", "").lower()


# ---- Super Admin with X-Org-Id can access /api/org/permissions; other admin cannot ----
def test_superadmin_can_access_org_permissions(super_sess):
    r = super_sess.get(f"{BASE}/api/org/permissions", headers={"X-Org-Id": ORG}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    uids = {m["user_id"] for m in d["members"]}
    assert UID_ADMIN in uids


def test_other_org_admin_cannot_access(qa_admin_sess):
    r = qa_admin_sess.get(f"{BASE}/api/org/permissions", headers={"X-Org-Id": ORG}, timeout=20)
    assert r.status_code == 403, r.status_code
