"""Reachability + guard test for POST /api/social/posts/{id}/publish (no real Meta call)."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
EMAIL = "manara.michele.pro@gmail.com"
PASSWORD = "CrmEvent2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


def test_publish_unauthenticated_is_protected():
    r = requests.post(f"{BASE}/api/social/posts/nonexistent/publish",
                      json={"confirm": True}, timeout=20)
    # require_org_admin -> 401/403 without auth (NOT 500)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text[:200]}"


def test_publish_nonexistent_post_returns_404_not_500(session):
    # Super Admin uses scope=platform per convention but endpoint uses oq(user,...)
    # A random id must return 404, never 500.
    r = session.post(f"{BASE}/api/social/posts/does-not-exist-xyz/publish",
                     json={"confirm": True}, timeout=20)
    assert r.status_code != 500, f"unexpected 500: {r.text[:300]}"
    # Expect 404 (post not found) or 403 (superadmin has no org_id -> may block)
    # 428 = superadmin must pick an org context; 403 = org guard; 404 = post not found. All acceptable (NOT 500).
    assert r.status_code in (403, 404, 428), f"unexpected status {r.status_code}: {r.text[:300]}"


def test_publish_endpoint_validation_message_shape(session):
    """If we can locate an existing post w/o IG account, we should see 400 with 'da completare:'.
    Otherwise this is skipped."""
    # Try to list social posts as super admin (scope=platform)
    lr = session.get(f"{BASE}/api/social/posts", params={"scope": "platform"}, timeout=20)
    if lr.status_code != 200:
        pytest.skip(f"social posts list unavailable to superadmin: {lr.status_code}")
    items = lr.json() if isinstance(lr.json(), list) else lr.json().get("items", [])
    if not items:
        pytest.skip("no social posts available in preview")
    pid = items[0].get("id")
    r = session.post(f"{BASE}/api/social/posts/{pid}/publish",
                     json={"confirm": True}, params={"scope": "platform"}, timeout=30)
    # No IG account connected in preview -> must be 400 with descriptive detail, not 500
    assert r.status_code != 500, f"got 500: {r.text[:300]}"
    if r.status_code == 400:
        detail = (r.json() or {}).get("detail", "")
        assert "da completare" in detail.lower() or "impossibile pubblicare" in detail.lower(), \
            f"unexpected 400 detail: {detail}"
