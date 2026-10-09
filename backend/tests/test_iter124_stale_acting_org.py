"""Iter124 - Stale acting_org_id cookie / X-Org-Id tests.

Covers:
- /auth/me returns 200 when session_token cookie is garbage but access_token is valid
- Non-member X-Org-Id still returns 403 on scoped endpoints
- Password login still works for QA + SA
- JWT-minted "Google-like" users with no org are forced to /completa-organizzazione (no org = 403 on /events)
- Super Admin acting_org selection works
"""
import os
import uuid
import time
import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

# JWT secret from backend .env
JWT_SECRET = None
with open("/app/backend/.env") as fh:
    for line in fh:
        if line.startswith("JWT_SECRET="):
            JWT_SECRET = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
assert JWT_SECRET, "JWT_SECRET missing"

MONGO_URL = None
DB_NAME = None
with open("/app/backend/.env") as fh:
    for line in fh:
        if line.startswith("MONGO_URL="):
            MONGO_URL = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("DB_NAME="):
            DB_NAME = line.split("=", 1)[1].strip().strip('"')

QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASS = "QaEvents2026!"
SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"


def _mint(uid, email):
    return pyjwt.encode({"sub": uid, "email": email, "type": "access",
                         "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                        JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="module")
def db():
    cli = MongoClient(MONGO_URL)
    return cli[DB_NAME]


@pytest.fixture(scope="module")
def qa_cookies():
    r = requests.post(f"{API}/auth/login", json={"email": QA_EMAIL, "password": QA_PASS})
    assert r.status_code == 200, r.text
    return r.cookies


@pytest.fixture(scope="module")
def sa_cookies():
    r = requests.post(f"{API}/auth/login", json={"email": SA_EMAIL, "password": SA_PASS})
    assert r.status_code == 200, r.text
    return r.cookies


# ---- auth basics ----
def test_qa_login_me(qa_cookies):
    r = requests.get(f"{API}/auth/me", cookies=qa_cookies)
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == QA_EMAIL


def test_sa_login_me(sa_cookies):
    r = requests.get(f"{API}/auth/me", cookies=sa_cookies)
    assert r.status_code == 200
    assert r.json().get("role") == "superadmin"


# ---- Backend fix: stale session_token must not shadow valid access_token ----
def test_stale_session_token_with_valid_access_token(qa_cookies):
    access = qa_cookies.get("access_token")
    assert access, f"no access_token cookie, got {dict(qa_cookies)}"
    jar = requests.cookies.RequestsCookieJar()
    jar.set("session_token", "garbage-expired-xxxxx", domain=BASE_URL.replace("https://", ""), path="/")
    jar.set("access_token", access, domain=BASE_URL.replace("https://", ""), path="/")
    r = requests.get(f"{API}/auth/me", cookies=jar)
    assert r.status_code == 200, f"expected 200 with stale session + valid access, got {r.status_code} {r.text}"
    assert r.json()["email"] == QA_EMAIL


# ---- Security: non-member X-Org-Id returns 403 (not relaxed) ----
def test_non_member_x_org_id_returns_403(qa_cookies):
    r = requests.get(f"{API}/events", cookies=qa_cookies,
                     headers={"X-Org-Id": "stale-nonexistent-org-xyz"})
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"


def test_qa_events_no_header_ok(qa_cookies):
    r = requests.get(f"{API}/events", cookies=qa_cookies)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


# ---- Scenario A: Google-like user without any membership ----
@pytest.fixture
def google_noorg_user(db):
    uid = f"TEST_google_noorg_{uuid.uuid4().hex[:8]}"
    email = f"TEST_{uuid.uuid4().hex[:6]}@test-google.local"
    db.users.insert_one({
        "user_id": uid, "email": email, "name": "TEST Google NoOrg",
        "role": "admin", "auth_provider": "google",
        "google_sub": f"google-sub-{uid}", "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield uid, email
    db.users.delete_one({"user_id": uid})
    db.memberships.delete_many({"user_id": uid})


def test_scenarioA_google_noorg_me_ok(google_noorg_user):
    uid, email = google_noorg_user
    tok = _mint(uid, email)
    r = requests.get(f"{API}/auth/me", cookies={"access_token": tok})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["email"] == email
    # organizations list must be empty => frontend will redirect to /completa-organizzazione
    assert data.get("organizations", []) == [] or data.get("org_id") in (None, "")


def test_scenarioA_google_noorg_events_403(google_noorg_user):
    uid, email = google_noorg_user
    tok = _mint(uid, email)
    r = requests.get(f"{API}/events", cookies={"access_token": tok})
    # No membership -> 403 "Nessuna organizzazione associata"
    assert r.status_code == 403, f"got {r.status_code} {r.text[:200]}"


def test_scenarioA_google_noorg_stale_x_org_403(google_noorg_user):
    """Spec: stale acting_org_id as X-Org-Id must 403 (not relaxed). Frontend clears it."""
    uid, email = google_noorg_user
    tok = _mint(uid, email)
    r = requests.get(f"{API}/events", cookies={"access_token": tok},
                     headers={"X-Org-Id": "stale_org_123"})
    assert r.status_code == 403


# ---- Scenario B: existing org user with stale X-Org-Id still 403, but no header works ----
def test_scenarioB_existing_user_stale_header_403_no_header_ok(qa_cookies):
    bad = requests.get(f"{API}/events", cookies=qa_cookies, headers={"X-Org-Id": "nope-xyz"})
    assert bad.status_code == 403
    ok = requests.get(f"{API}/events", cookies=qa_cookies)
    assert ok.status_code == 200


# ---- Scenario F: SA acting org selection ----
def test_scenarioF_sa_requires_x_org_id(sa_cookies):
    r = requests.get(f"{API}/events", cookies=sa_cookies)
    # SA without X-Org-Id => 428 "Seleziona un'organizzazione attiva"
    assert r.status_code == 428, f"got {r.status_code} {r.text[:200]}"


def test_scenarioF_sa_valid_org_works(sa_cookies):
    # pick an existing org via platform listing
    r = requests.get(f"{API}/platform/organizations", cookies=sa_cookies)
    assert r.status_code == 200
    orgs = r.json()
    assert isinstance(orgs, list) and orgs, "no orgs listed"
    org_id = orgs[0]["id"]
    r2 = requests.get(f"{API}/events", cookies=sa_cookies, headers={"X-Org-Id": org_id})
    assert r2.status_code == 200, f"SA acting {org_id} got {r2.status_code} {r2.text[:200]}"
