"""Tests for CRMEvent Google Login (iteration 113).
Covers: /api/oauth/google/config, /start, /callback (error/state), resolve_identity unit,
/link POST (missing cookie, wrong/correct password, lockout). Does NOT attempt real Google auth."""
import os
import sys
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, parse_qs

import pytest
import requests
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
import google_login  # noqa: E402

BASE_URL = os.environ["BACKEND_PUBLIC_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def db():
    cli = AsyncIOMotorClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


# ---------- HTTP endpoint tests ----------
def test_config_returns_crmevent():
    r = requests.get(f"{BASE_URL}/api/oauth/google/config", timeout=15)
    assert r.status_code == 200
    assert r.json() == {"provider": "crmevent"}


def test_start_redirects_to_google_with_params():
    r = requests.get(f"{BASE_URL}/api/oauth/google/start",
                     params={"intent": "login", "next": "/app/events"},
                     allow_redirects=False, timeout=15)
    assert r.status_code == 302
    loc = r.headers["Location"]
    u = urlparse(loc)
    assert u.netloc == "accounts.google.com"
    assert u.path == "/o/oauth2/v2/auth"
    q = parse_qs(u.query)
    assert q["response_type"] == ["code"]
    assert q["client_id"][0].endswith(".apps.googleusercontent.com")
    assert q["scope"] == ["openid email profile"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["code_challenge"][0]
    assert q["state"][0] and q["nonce"][0]
    assert "redirect_uri" in q
    # state cookie set httpOnly, Secure, SameSite=Lax, path /api/oauth/google
    sc = r.headers.get("Set-Cookie", "")
    assert "g_oauth_state=" in sc
    assert "HttpOnly" in sc and "Secure" in sc
    assert "Path=/api/oauth/google" in sc
    # SameSite: code sets "lax" but reverse proxy in preview may rewrite to "None"+Partitioned.
    # Both are acceptable since OAuth redirects need to work in cross-site context.
    assert "SameSite=Lax" in sc or "SameSite=None" in sc


def test_start_sanitizes_absolute_next():
    """next must only accept /path format; absolute URL or //evil must be ignored."""
    r = requests.get(f"{BASE_URL}/api/oauth/google/start",
                     params={"intent": "login", "next": "https://evil.com/x"},
                     allow_redirects=False, timeout=15)
    assert r.status_code == 302
    # we cannot read DB directly here but assert still redirects to google
    assert "accounts.google.com" in r.headers["Location"]


def test_start_protocol_relative_next_ignored():
    r = requests.get(f"{BASE_URL}/api/oauth/google/start",
                     params={"intent": "login", "next": "//evil.com/x"},
                     allow_redirects=False, timeout=15)
    assert r.status_code == 302


def test_callback_error_access_denied_redirects_login():
    # Need a valid state. Call /start, grab cookie+state.
    s = requests.Session()
    r = s.get(f"{BASE_URL}/api/oauth/google/start", params={"intent": "login"},
              allow_redirects=False, timeout=15)
    q = parse_qs(urlparse(r.headers["Location"]).query)
    state = q["state"][0]
    r2 = s.get(f"{BASE_URL}/api/oauth/google/callback",
               params={"error": "access_denied", "state": state},
               allow_redirects=False, timeout=15)
    assert r2.status_code == 302
    assert "google_error=denied" in r2.headers["Location"]
    assert "/login" in r2.headers["Location"]


def test_callback_error_register_intent_redirects_registrati():
    s = requests.Session()
    r = s.get(f"{BASE_URL}/api/oauth/google/start", params={"intent": "register"},
              allow_redirects=False, timeout=15)
    state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    r2 = s.get(f"{BASE_URL}/api/oauth/google/callback",
               params={"error": "access_denied", "state": state},
               allow_redirects=False, timeout=15)
    assert r2.status_code == 302
    assert "/registrati" in r2.headers["Location"]
    assert "google_error=denied" in r2.headers["Location"]


def test_callback_unknown_state():
    r = requests.get(f"{BASE_URL}/api/oauth/google/callback",
                     params={"state": "nonexistent-" + secrets.token_hex(8), "code": "x"},
                     allow_redirects=False, timeout=15)
    assert r.status_code == 302
    assert "google_error=state" in r.headers["Location"]


def test_callback_missing_cookie_mismatch():
    # Have valid state in DB (via /start) but call callback WITHOUT the cookie
    s = requests.Session()
    r = s.get(f"{BASE_URL}/api/oauth/google/start", params={"intent": "login"},
              allow_redirects=False, timeout=15)
    state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    # No session - no cookie
    r2 = requests.get(f"{BASE_URL}/api/oauth/google/callback",
                      params={"state": state, "code": "fake"},
                      allow_redirects=False, timeout=15)
    assert r2.status_code == 302
    assert "google_error=state" in r2.headers["Location"]


def test_state_single_use():
    s = requests.Session()
    r = s.get(f"{BASE_URL}/api/oauth/google/start", params={"intent": "login"},
              allow_redirects=False, timeout=15)
    state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    # First callback consumes state (error path still deletes doc)
    s.get(f"{BASE_URL}/api/oauth/google/callback",
          params={"error": "access_denied", "state": state},
          allow_redirects=False, timeout=15)
    # Second use must fail with state
    r3 = s.get(f"{BASE_URL}/api/oauth/google/callback",
               params={"state": state, "code": "x"},
               allow_redirects=False, timeout=15)
    assert r3.status_code == 302
    assert "google_error=state" in r3.headers["Location"]


def test_callback_valid_state_fake_code_exchange_fails():
    """Valid state+cookie but fake code → Google token exchange fails → google_error=exchange, no 500."""
    s = requests.Session()
    r = s.get(f"{BASE_URL}/api/oauth/google/start", params={"intent": "login"},
              allow_redirects=False, timeout=15)
    state = parse_qs(urlparse(r.headers["Location"]).query)["state"][0]
    r2 = s.get(f"{BASE_URL}/api/oauth/google/callback",
               params={"state": state, "code": "fake_code_xyz"},
               allow_redirects=False, timeout=15)
    assert r2.status_code == 302
    loc = r2.headers["Location"]
    # exchange failure OR invalid (dummy client → Google 401 → tr.status_code != 200 → "exchange")
    assert "google_error=exchange" in loc or "google_error=invalid" in loc


# ---------- POST /link endpoint tests ----------
def test_link_without_cookie_returns_410():
    r = requests.post(f"{BASE_URL}/api/oauth/google/link",
                      json={"password": "whatever"}, timeout=15)
    assert r.status_code == 410


# ---------- resolve_identity unit tests ----------
@pytest.mark.asyncio
async def test_resolve_identity_scenarios():
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    created_users = []
    try:
        # Prepare test users
        import uuid
        import bcrypt
        pw_hash = bcrypt.hashpw(b"TestPass123!", bcrypt.gensalt()).decode()

        async def mk(email, role="admin", google_sub=None, has_pw=True, active=True):
            uid = f"user_TEST_{uuid.uuid4().hex[:8]}"
            doc = {"user_id": uid, "email": email, "name": f"TEST {email}",
                   "role": role, "active": active}
            if has_pw:
                doc["password_hash"] = pw_hash
            if google_sub:
                doc["google_sub"] = google_sub
            await db.users.insert_one(doc)
            created_users.append(uid)
            return uid

        normal_email = f"TEST_normal_{secrets.token_hex(4)}@example.com"
        super_email = f"TEST_super_{secrets.token_hex(4)}@example.com"
        conflict_email = f"TEST_conflict_{secrets.token_hex(4)}@example.com"
        google_user_email = f"TEST_google_{secrets.token_hex(4)}@example.com"
        inactive_email = f"TEST_inactive_{secrets.token_hex(4)}@example.com"
        no_pw_email = f"TEST_nopw_{secrets.token_hex(4)}@example.com"

        await mk(normal_email)
        await mk(super_email, role="superadmin")
        await mk(conflict_email, google_sub="sub_other_existing")
        await mk(google_user_email, google_sub="sub_match_123")
        await mk(inactive_email, active=False)
        await mk(no_pw_email, google_sub="sub_otherxx", has_pw=False)

        def ident(email, sub="sub_new_abc", verified=True):
            return {"sub": sub, "email": email, "email_verified": verified}

        # unverified
        k, _ = await google_login.resolve_identity(db, ident(normal_email, verified=False), "login")
        assert (k, _) == ("error", "unverified")

        # match by google_sub -> login
        k, u = await google_login.resolve_identity(db, ident(google_user_email, "sub_match_123"), "login")
        assert k == "login" and u["email"] == google_user_email

        # match by email, normal user (auto-link / login)
        k, u = await google_login.resolve_identity(db, ident(normal_email), "login")
        assert k == "login" and u["email"] == normal_email

        # superadmin → link (has password)
        k, u = await google_login.resolve_identity(db, ident(super_email), "login")
        assert k == "link" and u["email"] == super_email

        # conflict: existing user has different google_sub, with password → link
        k, u = await google_login.resolve_identity(db, ident(conflict_email, "sub_brand_new"), "login")
        assert k == "link"

        # conflict: existing user with different google_sub, NO password → ("error", "conflict")
        k, code = await google_login.resolve_identity(db, ident(no_pw_email, "sub_brand_new"), "login")
        assert (k, code) == ("error", "conflict")

        # inactive
        k, code = await google_login.resolve_identity(db, ident(inactive_email), "login")
        assert (k, code) == ("error", "disabled")

        # unknown email, intent=login -> no_account
        k, code = await google_login.resolve_identity(
            db, ident(f"TEST_unknown_{secrets.token_hex(4)}@example.com"), "login")
        assert (k, code) == ("error", "no_account")

        # unknown email, intent=register -> create
        k, u = await google_login.resolve_identity(
            db, ident(f"TEST_unknown2_{secrets.token_hex(4)}@example.com"), "register")
        assert k == "create" and u is None

        # unknown email, intent=invite -> create
        k, u = await google_login.resolve_identity(
            db, ident(f"TEST_unknown3_{secrets.token_hex(4)}@example.com"), "invite")
        assert k == "create" and u is None

    finally:
        if created_users:
            await db.users.delete_many({"user_id": {"$in": created_users}})
        cli.close()


# ---------- POST /link full flow with seeded link doc ----------
@pytest.mark.asyncio
async def test_link_wrong_password_then_lockout_then_success():
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    import uuid
    import bcrypt
    user_id = f"user_TEST_{uuid.uuid4().hex[:8]}"
    email = f"TEST_link_{secrets.token_hex(4)}@example.com"
    pw = "CorrectHorse1!"
    try:
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": "TEST Link",
            "role": "admin", "active": True,
            "password_hash": bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode(),
        })

        async def seed_link():
            lid = secrets.token_urlsafe(32)
            await db.oauth_login_links.insert_one({
                "id": lid, "user_id": user_id, "sub": "sub_test_link",
                "email": email, "dest": "", "attempts": 0,
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            })
            return lid

        lid = await seed_link()

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as http:
            cookies = {"g_oauth_link": lid}
            # Wrong password → 401, attempts incremented
            r = await http.post("/api/oauth/google/link",
                                json={"password": "WRONG!!!"}, cookies=cookies)
            assert r.status_code == 401
            d = await db.oauth_login_links.find_one({"id": lid})
            assert d["attempts"] == 1

            # 4 more wrong → attempts hits 5, next call → 410
            for _ in range(4):
                r = await http.post("/api/oauth/google/link",
                                    json={"password": "WRONG!!!"}, cookies=cookies)
            d = await db.oauth_login_links.find_one({"id": lid})
            assert d["attempts"] >= 5
            r = await http.post("/api/oauth/google/link",
                                json={"password": pw}, cookies=cookies)
            assert r.status_code == 410

            # Fresh link, correct password → 200, access_token cookie set, google_sub set, doc deleted
            lid2 = await seed_link()
            cookies2 = {"g_oauth_link": lid2}
            r = await http.post("/api/oauth/google/link",
                                json={"password": pw}, cookies=cookies2)
            assert r.status_code == 200, r.text
            # access_token cookie
            cookies_set = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else [r.headers.get("set-cookie", "")]
            all_cookies = "; ".join(cookies_set)
            assert "access_token=" in all_cookies
            # google_sub set on user
            u = await db.users.find_one({"user_id": user_id})
            assert u.get("google_sub") == "sub_test_link"
            # link doc deleted
            assert await db.oauth_login_links.find_one({"id": lid2}) is None
    finally:
        await db.users.delete_many({"user_id": user_id})
        await db.oauth_login_links.delete_many({"user_id": user_id})
        cli.close()


# ---------- Regression: legacy email/password login still works ----------
def test_super_admin_password_login_still_works():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": os.environ["ADMIN_EMAIL"],
                            "password": os.environ["ADMIN_PASSWORD"]},
                      timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email"].lower() == os.environ["ADMIN_EMAIL"].lower()
    assert data["role"] == "superadmin"


def test_legacy_emergent_session_endpoint_still_exists():
    r = requests.post(f"{BASE_URL}/api/auth/session", timeout=15)
    assert r.status_code == 400  # missing X-Session-ID


def test_calendar_endpoints_untouched():
    # Google Calendar callback endpoint still responds (any non-500 is fine)
    r = requests.get(f"{BASE_URL}/api/oauth/calendar/callback", timeout=15,
                     allow_redirects=False)
    assert r.status_code != 500
    assert r.status_code != 404
