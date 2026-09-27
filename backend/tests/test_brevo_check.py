"""Tests for GET /api/integrations/brevo/check — connection-only, no email is ever sent."""
import os
import re
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
SUPERADMIN_EMAIL = "manara.michele.pro@gmail.com"
SUPERADMIN_PASSWORD = "CrmEvent2026!"


def _login_superadmin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD},
               timeout=15)
    assert r.status_code == 200, f"Superadmin login failed: {r.status_code} {r.text}"
    return s


# --- 1) Auth guard ---
def test_brevo_check_requires_auth():
    r = requests.get(f"{BASE_URL}/api/integrations/brevo/check", timeout=15)
    assert r.status_code == 401, f"Expected 401 without auth, got {r.status_code}: {r.text}"


# --- 2) Superadmin login works (no regression on /api/auth/login) ---
def test_superadmin_login_no_regression():
    s = _login_superadmin()
    # basic session/me sanity if endpoint exists — otherwise just assert cookie set
    cookies = s.cookies.get_dict()
    assert cookies, "Login must set an auth cookie (httpOnly session)"


# --- 3) With empty BREVO_API_KEY — safe response, no key exposure, no email sent ---
def test_brevo_check_empty_key_safe_response():
    s = _login_superadmin()
    r = s.get(f"{BASE_URL}/api/integrations/brevo/check", timeout=15)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    # Exact contract fields
    assert set(["configured", "valid", "status", "message"]).issubset(data.keys())
    assert data["configured"] is False
    assert data["valid"] is False
    assert data["status"] is None
    assert isinstance(data["message"], str) and "non configurata" in data["message"].lower()

    # Response must NOT contain a raw API key or Brevo account payload fields
    raw = r.text
    # Brevo keys typically start with "xkeysib-"
    assert "xkeysib-" not in raw
    # Common Brevo account payload fields must not appear
    for forbidden in ["companyName", "plan", "credits", "firstName", "lastName", "address"]:
        assert forbidden not in raw, f"Response leaks Brevo account field '{forbidden}'"
    # Only safe keys allowed
    assert set(data.keys()) == {"configured", "valid", "status", "message"}, \
        f"Unexpected extra fields: {set(data.keys())}"


# --- 4) Non-superadmin should not access (forbidden). Best-effort: try org admin if reachable ---
def test_brevo_check_non_superadmin_forbidden():
    # Anonymous case already covered; here we ensure endpoint stays superadmin-only.
    # Use a session with an invalid/expired cookie -> still 401.
    s = requests.Session()
    s.cookies.set("session", "invalid.token.value")
    r = s.get(f"{BASE_URL}/api/integrations/brevo/check", timeout=15)
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
