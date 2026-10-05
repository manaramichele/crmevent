"""Backend tests for Super Admin platform messages reads tracking.
Covers: list recipients/read, stats detail (recipients/read/unread/users rows), idempotent read,
superadmin preview non-counting, delete purges reads.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

SUPER_EMAIL = "manara.michele.pro@gmail.com"
SUPER_PW = "CrmEvent2026!"


def _login(session, email, password):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


@pytest.fixture(scope="module")
def super_session():
    s = requests.Session()
    r = _login(s, SUPER_EMAIL, SUPER_PW)
    assert r.status_code == 200, f"Superadmin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("role") in ("superadmin",) or data.get("user", {}).get("role") == "superadmin", f"unexpected role: {data}"
    return s


@pytest.fixture(scope="module")
def org_admin_session():
    """Register a brand-new organization and return its logged session + user_id."""
    s = requests.Session()
    suffix = uuid.uuid4().hex[:8]
    email = f"TEST_orgadmin_{suffix}@crmeventtest.it"
    pw = "TestPwd2026!"
    body = {
        "nome": "Test",
        "cognome": "Admin",
        "email": email,
        "password": pw,
        "org_name": f"TEST Org {suffix}",
        "telefono": "+393331112233",
        "accept_terms": True,
    }
    r = s.post(f"{BASE_URL}/api/auth/register-organization", json=body, timeout=30)
    assert r.status_code in (200, 201), f"register-organization failed: {r.status_code} {r.text}"
    # Make sure session is active (login explicitly)
    r2 = _login(s, email, pw)
    assert r2.status_code == 200, f"org admin login failed: {r2.status_code} {r2.text}"
    data = r2.json()
    user_id = data.get("user_id") or data.get("user", {}).get("user_id") or data.get("id")
    org_id = data.get("org_id") or data.get("user", {}).get("org_id")
    return {"session": s, "email": email, "user_id": user_id, "org_id": org_id}


@pytest.fixture
def created_message(super_session):
    mid = None
    try:
        body = {
            "titolo": f"TEST Msg {uuid.uuid4().hex[:6]}",
            "messaggio": "Automated test message",
            "tipologia": "informazione",
            "recipients_mode": "all",
            "org_ids": [],
            "status": "attivo",
        }
        r = super_session.post(f"{BASE_URL}/api/platform/messages", json=body, timeout=30)
        assert r.status_code == 200, f"create message failed: {r.status_code} {r.text}"
        mid = r.json()["id"]
        yield mid
    finally:
        if mid:
            super_session.delete(f"{BASE_URL}/api/platform/messages/{mid}", timeout=30)


class TestPlatformMessagesList:
    def test_list_returns_recipients_and_read(self, super_session, created_message):
        r = super_session.get(f"{BASE_URL}/api/platform/messages", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        row = next((x for x in rows if x["id"] == created_message), None)
        assert row is not None, "created message not in list"
        assert isinstance(row.get("recipients"), int) and row["recipients"] > 0, f"recipients>0 expected, got {row}"
        assert row.get("read") == 0, f"initial read must be 0, got {row['read']}"
        assert row.get("unread") == row["recipients"]
        assert row.get("orgs_reached", 0) > 0


class TestPlatformMessagesStats:
    def test_stats_shape_and_initial_state(self, super_session, created_message):
        r = super_session.get(f"{BASE_URL}/api/platform/messages/{created_message}/stats", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert set(["recipients", "read", "unread", "users", "orgs"]).issubset(data.keys())
        assert data["read"] == 0
        assert data["recipients"] == data["unread"]
        assert isinstance(data["users"], list) and len(data["users"]) == data["recipients"]
        for u in data["users"][:3]:
            assert set(["org_id", "org_name", "user_id", "name", "email", "read", "read_at"]).issubset(u.keys())
            assert u["read"] is False
            assert u["read_at"] is None


class TestReadFlow:
    def test_read_increments_and_idempotent(self, super_session, org_admin_session, created_message):
        # The brand-new org is automatically a recipient of recipients_mode=all messages.
        org_s = org_admin_session["session"]
        uid = org_admin_session["user_id"]

        # Baseline list counts
        r0 = super_session.get(f"{BASE_URL}/api/platform/messages", timeout=30)
        row0 = next(x for x in r0.json() if x["id"] == created_message)
        base_read = row0["read"]
        recipients = row0["recipients"]

        # Org admin marks as read
        rr = org_s.post(f"{BASE_URL}/api/my/messages/{created_message}/read", timeout=30)
        assert rr.status_code == 200, f"my/read failed: {rr.status_code} {rr.text}"

        # List should increment by 1
        time.sleep(0.3)
        r1 = super_session.get(f"{BASE_URL}/api/platform/messages", timeout=30)
        row1 = next(x for x in r1.json() if x["id"] == created_message)
        assert row1["read"] == base_read + 1, f"expected read={base_read+1}, got {row1['read']}"
        assert row1["recipients"] == recipients

        # Stats should show that user as read=True
        s1 = super_session.get(f"{BASE_URL}/api/platform/messages/{created_message}/stats", timeout=30).json()
        assert s1["read"] == base_read + 1
        urow = next((u for u in s1["users"] if u["user_id"] == uid), None)
        assert urow is not None, "org admin user not in users rows"
        assert urow["read"] is True and urow["read_at"], f"user row not marked read: {urow}"

        # Idempotency: reading again doesn't bump count
        rr2 = org_s.post(f"{BASE_URL}/api/my/messages/{created_message}/read", timeout=30)
        assert rr2.status_code == 200
        r2 = super_session.get(f"{BASE_URL}/api/platform/messages", timeout=30)
        row2 = next(x for x in r2.json() if x["id"] == created_message)
        assert row2["read"] == base_read + 1, f"idempotency violated: {row2['read']}"

    def test_superadmin_preview_does_not_count(self, super_session, org_admin_session):
        """Superadmin hitting /my/messages/*/read must NOT create a read doc."""
        # Create a fresh message so counts are deterministic
        body = {"titolo": f"TEST Preview {uuid.uuid4().hex[:6]}", "messaggio": "x",
                "tipologia": "informazione", "recipients_mode": "all", "org_ids": [], "status": "attivo"}
        mid = super_session.post(f"{BASE_URL}/api/platform/messages", json=body, timeout=30).json()["id"]
        try:
            # Superadmin "preview" read attempt (must pass X-Org-Id header to adopt an org context)
            headers = {"X-Org-Id": org_admin_session["org_id"]}
            rr = super_session.post(f"{BASE_URL}/api/my/messages/{mid}/read", headers=headers, timeout=30)
            assert rr.status_code == 200, f"preview read: {rr.status_code} {rr.text}"
            assert rr.json().get("preview") is True
            # Count must still be 0
            rows = super_session.get(f"{BASE_URL}/api/platform/messages", timeout=30).json()
            row = next(x for x in rows if x["id"] == mid)
            assert row["read"] == 0, f"superadmin preview counted as read: {row}"
            stats = super_session.get(f"{BASE_URL}/api/platform/messages/{mid}/stats", timeout=30).json()
            assert stats["read"] == 0
        finally:
            super_session.delete(f"{BASE_URL}/api/platform/messages/{mid}", timeout=30)


class TestDeletePurgesReads:
    def test_delete_purges_reads(self, super_session, org_admin_session):
        body = {"titolo": f"TEST Delete {uuid.uuid4().hex[:6]}", "messaggio": "x",
                "tipologia": "informazione", "recipients_mode": "all", "org_ids": [], "status": "attivo"}
        mid = super_session.post(f"{BASE_URL}/api/platform/messages", json=body, timeout=30).json()["id"]
        org_s = org_admin_session["session"]
        org_s.post(f"{BASE_URL}/api/my/messages/{mid}/read", timeout=30)
        # Delete
        d = super_session.delete(f"{BASE_URL}/api/platform/messages/{mid}", timeout=30)
        assert d.status_code == 200
        # Re-create same id? no; just verify list no longer contains and stats 404
        rows = super_session.get(f"{BASE_URL}/api/platform/messages", timeout=30).json()
        assert not any(x["id"] == mid for x in rows)
        s = super_session.get(f"{BASE_URL}/api/platform/messages/{mid}/stats", timeout=30)
        assert s.status_code == 404
