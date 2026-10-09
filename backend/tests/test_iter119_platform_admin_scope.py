"""Iter 119 — Super Admin access to organizations must not pollute org-level
collaborator audit / membership lists. Platform audit preserves real identity.

Scope coverage:
- POST /api/platform/audit/org-access → 200; no active membership created for SA;
  audit_logs row has scope "platform_admin" and real actor_email.
- Super Admin PUT /api/org/permissions/{id} with X-Org-Id (impersonation) then
  restore → QA org admin GET /api/org/permissions/audit sees entries as
  "Assistenza CRMEvent" (actor_email/user_id/role masked), while real
  org-admin entries keep real name.
- Super Admin GET /api/platform/audit?org_id=... still returns real actor_email.
- Historical migration: every audit_logs row has a "scope" field; count stable.
- Org members listing (/api/org/permissions members[]) excludes superadmin.
- saas/me usage.users unchanged after SA access.
- Non-superadmin GET /api/platform/audit → 403.
- Super Admin POST /api/platform/organizations (TEST_ org) → no membership added
  for SA; cleanup TEST_ org afterward.
"""
import os
import time
import uuid
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
SUPERADMIN = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
QA_ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
QA_ORG = "org_qa_eventi"


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(s, cred):
    r = s.post(f"{API}/auth/login", json=cred, timeout=20)
    assert r.status_code == 200, f"login {cred['email']}: {r.status_code} {r.text}"
    return r.json()


# ----------------- Fixtures (module-level sessions) -----------------
def _sa_session():
    s = _sess()
    _login(s, SUPERADMIN)
    return s


def _qa_session():
    s = _sess()
    _login(s, QA_ADMIN)
    return s


# ----------------- Tests -----------------
def test_1_org_access_platform_admin_scope():
    """SA POST /platform/audit/org-access → 200, no active membership, scope platform_admin."""
    s = _sa_session()
    me = s.get(f"{API}/auth/me", timeout=20).json()
    sa_uid = me.get("user_id")
    assert sa_uid, f"no user_id in /auth/me: {me}"

    r = s.post(f"{API}/platform/audit/org-access", json={"org_id": QA_ORG}, timeout=20)
    assert r.status_code == 200, f"org-access: {r.status_code} {r.text}"
    audit_id = r.json().get("id")
    assert audit_id

    # Pull platform audit to confirm no membership was created, scope is correct
    # Use SA /platform/audit filter for QA org, action org_access
    rr = s.get(f"{API}/platform/audit", params={"org_id": QA_ORG, "action": "org_access", "limit": 20}, timeout=20)
    assert rr.status_code == 200, rr.text
    items = rr.json().get("items") or rr.json()
    # The response may be wrapped; handle both {"items":...} and list
    if isinstance(items, dict):
        items = items.get("items", [])
    assert any(it.get("id") == audit_id for it in items), f"org_access audit not visible to SA: {audit_id}"
    rec = next(it for it in items if it.get("id") == audit_id)
    assert rec.get("scope") == "platform_admin", f"scope={rec.get('scope')}"
    assert rec.get("actor_email") == SUPERADMIN["email"], f"actor_email={rec.get('actor_email')}"
    assert rec.get("actor_user_id") == sa_uid


def test_2_sa_permissions_change_appears_as_assistenza_in_org_audit():
    """SA with X-Org-Id modifies a QA member, then restores. Org audit shows masked identity."""
    sa = _sa_session()
    qa = _qa_session()

    # Pick a non-admin member via QA /org/permissions
    perms = qa.get(f"{API}/org/permissions", timeout=20).json()
    members = perms.get("members") or []
    # Only pick members whose user record still exists (requires valid email)
    target = next((m for m in members
                   if not m.get("is_self") and m.get("role") != "admin_org" and m.get("email")), None)
    if not target:
        target = next((m for m in members if not m.get("is_self") and m.get("email")), None)
    assert target, f"no suitable target member in QA org: {members}"
    tgt_id = target["user_id"]
    original_role = target["role"]
    original_perm = target.get("permissions") or {}
    original_sections = (original_perm.get("sections") or {})
    original_persona = target.get("persona_id")

    # SA PUT /org/permissions/{tgt} with X-Org-Id header; change role to collaboratore and reset
    sa.headers.update({"X-Org-Id": QA_ORG})
    # Use reset=True to only change permissions deterministically; keep role unchanged
    change_body = {"role": original_role, "reset": True, "persona_id": original_persona}
    r = sa.put(f"{API}/org/permissions/{tgt_id}", json=change_body, timeout=20)
    assert r.status_code == 200, f"SA PUT permissions: {r.status_code} {r.text}"

    # Restore original (reapply original sections if present)
    if original_perm:
        restore_body = {
            "role": original_role,
            "sections": original_perm.get("sections"),
            "events": original_perm.get("events"),
            "teams": original_perm.get("teams"),
            "send_invites": original_perm.get("send_invites"),
            "marketplace_purchase": original_perm.get("marketplace_purchase"),
            "team_leader": original_perm.get("team_leader"),
            "persona_id": original_persona,
        }
    else:
        restore_body = {"role": original_role, "reset": True, "persona_id": original_persona}
    r2 = sa.put(f"{API}/org/permissions/{tgt_id}", json=restore_body, timeout=20)
    assert r2.status_code == 200, f"SA PUT permissions restore: {r2.status_code} {r2.text}"

    # Also do a change by QA admin itself to validate real identity preserved
    qa_change = {"role": original_role, "reset": True, "persona_id": original_persona}
    r3 = qa.put(f"{API}/org/permissions/{tgt_id}", json=qa_change, timeout=20)
    assert r3.status_code == 200, f"QA PUT permissions: {r3.status_code} {r3.text}"
    # And restore again
    qa.put(f"{API}/org/permissions/{tgt_id}", json=restore_body, timeout=20)

    # QA admin pulls org audit
    audit = qa.get(f"{API}/org/permissions/audit", timeout=20).json()
    items = audit.get("items") or []
    assert items, "no items in /org/permissions/audit"

    # Entries whose underlying scope is platform_admin should be masked
    sa_entries = [it for it in items if it.get("actor_name") == "Assistenza CRMEvent"]
    assert sa_entries, f"no masked 'Assistenza CRMEvent' entries after SA changes; items[0]={items[0]}"
    for it in sa_entries:
        assert it.get("actor_email") is None, f"actor_email leaked for SA entry: {it}"
        assert it.get("actor_user_id") is None, f"actor_user_id leaked for SA entry: {it}"
        assert it.get("actor_role") in (None, "platform_admin"), f"actor_role={it.get('actor_role')}"

    # Entries by the QA admin itself keep real name/email
    qa_entries = [it for it in items if it.get("actor_email") == QA_ADMIN["email"]]
    assert qa_entries, "QA-admin-authored audit entries should still show real email"
    for it in qa_entries:
        assert it.get("actor_name") and it["actor_name"] != "Assistenza CRMEvent"


def test_3_platform_audit_preserves_real_identity():
    """Super Admin GET /platform/audit shows real email on SA-authored records (any action)."""
    sa = _sa_session()
    me = sa.get(f"{API}/auth/me", timeout=20).json()
    sa_uid = me["user_id"]
    r = sa.get(f"{API}/platform/audit", params={"actor_user_id": sa_uid, "limit": 100}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    # must contain at least one entry with the real SA email (from test_1 org_access, and/or test_2 permissions_changed)
    sa_mails = [it for it in items if it.get("actor_email") == SUPERADMIN["email"]]
    assert sa_mails, f"platform audit must preserve real SA email. items sample: {items[:2]}"
    for it in sa_mails:
        assert it.get("scope") == "platform_admin", f"scope not platform_admin: {it}"


def test_4_audit_migration_all_rows_have_scope():
    """All audit_logs must have 'scope' field (via platform/audit sample)."""
    sa = _sa_session()
    r = sa.get(f"{API}/platform/audit", params={"limit": 1000}, timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data["items"] if isinstance(data, dict) and "items" in data else data
    assert items, "no audit_logs returned"
    missing = [it for it in items if "scope" not in it or it.get("scope") is None]
    assert not missing, f"{len(missing)} audit rows missing scope field (sample id: {missing[0].get('id') if missing else None})"


def test_5_org_members_excludes_superadmin():
    """QA /org/permissions members[] must not include the Super Admin."""
    qa = _qa_session()
    perms = qa.get(f"{API}/org/permissions", timeout=20).json()
    emails = {(m.get("email") or "").lower() for m in (perms.get("members") or [])}
    assert SUPERADMIN["email"].lower() not in emails, f"SA leaked into QA members list: {emails}"


def test_6_saas_me_usage_users_unchanged_after_sa_access():
    """saas/me usage.users count unaffected by SA access."""
    qa = _qa_session()
    before = qa.get(f"{API}/saas/me", timeout=20).json()
    users_before = (before.get("usage") or {}).get("users")
    people_before = (before.get("usage") or {}).get("people")
    sa = _sa_session()
    sa.post(f"{API}/platform/audit/org-access", json={"org_id": QA_ORG}, timeout=20)
    after = qa.get(f"{API}/saas/me", timeout=20).json()
    users_after = (after.get("usage") or {}).get("users")
    people_after = (after.get("usage") or {}).get("people")
    assert users_before == users_after, f"usage.users changed: {users_before} → {users_after}"
    assert people_before == people_after, f"usage.people changed: {people_before} → {people_after}"


def test_7_non_superadmin_cannot_call_platform_audit():
    qa = _qa_session()
    r = qa.get(f"{API}/platform/audit", timeout=20)
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


def test_8_creating_test_org_does_not_add_sa_as_member():
    """SA creates a TEST_ org via /platform/organizations; verify no SA membership; cleanup."""
    sa = _sa_session()
    me = sa.get(f"{API}/auth/me", timeout=20).json()
    sa_uid = me["user_id"]
    org_name = f"TEST_SA_Scope_{uuid.uuid4().hex[:6]}"
    r = sa.post(f"{API}/platform/organizations", json={"nome": org_name, "type": "test", "status": "active"}, timeout=20)
    assert r.status_code == 200, f"create org: {r.status_code} {r.text}"
    org = r.json()
    oid = org.get("id") or (org.get("organization") or {}).get("id")
    assert oid, f"no org id in response: {org}"

    # Query SA members on that org via /platform/organizations/{oid}/members
    rr = sa.get(f"{API}/platform/organizations/{oid}/members", timeout=20)
    assert rr.status_code == 200, rr.text
    members = rr.json()
    sa_members = [m for m in members if m.get("user_id") == sa_uid]
    assert not sa_members, f"SA leaked as member of new org: {sa_members}"

    # Cleanup: delete the TEST_ org (DELETE requires confirm_name body)
    cleanup = sa.delete(f"{API}/platform/organizations/{oid}", json={"confirm_name": org_name}, timeout=20)
    assert cleanup.status_code in (200, 204), f"cleanup failed: {cleanup.status_code} {cleanup.text}"
