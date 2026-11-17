"""AI traffic attribution: public visit endpoint, super-admin report, registration attribution storage."""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
DEMO = {"email": "demo.crmevent@gmail.com", "password": "DemoCrm#2026pv"}


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


@pytest.fixture(scope="module")
def db():
    c = MongoClient(_env("MONGO_URL"))
    d = c[_env("DB_NAME")]
    yield d
    d.web_visits.delete_many({"visitor_id": {"$regex": "^TEST"}})


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    tok = r.json().get("token") or r.json().get("session_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


def _cleanup(db, email):
    u = db.users.find_one({"email": email})
    if not u:
        return
    oid = u.get("org_id")
    if oid:
        for c in db.list_collection_names():
            db[c].delete_many({"org_id": oid})
        db.organizations.delete_one({"id": oid})
    db.memberships.delete_many({"user_id": u["user_id"]})
    db.users.delete_one({"user_id": u["user_id"]})


# Public visit
class TestVisit:
    def test_visit_ok(self, db):
        vid = "TEST-" + uuid.uuid4().hex[:12]
        r = requests.post(f"{BASE_URL}/api/public/visit", json={"visitor_id": vid, "ai": "chatgpt", "source": "chatgpt", "referrer_host": "chatgpt.com", "landing": "/faq"})
        assert r.status_code == 200 and r.json() == {"ok": True}
        doc = db.web_visits.find_one({"visitor_id": vid})
        assert doc and doc["ai"] == "chatgpt" and doc["landing"] == "/faq"

    def test_visit_unknown_ai_blanked(self, db):
        vid = "TEST-" + uuid.uuid4().hex[:12]
        r = requests.post(f"{BASE_URL}/api/public/visit", json={"visitor_id": vid, "ai": "evilbot"})
        assert r.status_code == 200
        assert db.web_visits.find_one({"visitor_id": vid})["ai"] == ""

    def test_visit_bad_id(self):
        r = requests.post(f"{BASE_URL}/api/public/visit", json={"visitor_id": "TEST$$$$$$$$"})
        assert r.json() == {"ok": False}
        r = requests.post(f"{BASE_URL}/api/public/visit", json={"visitor_id": "short"})
        assert r.status_code == 422


# Super admin report
class TestReport:
    def test_unauth(self):
        r = requests.get(f"{BASE_URL}/api/platform/ai-traffic?days=90")
        assert r.status_code in (401, 403)

    def test_org_admin_forbidden(self):
        s = _login(DEMO)
        r = s.get(f"{BASE_URL}/api/platform/ai-traffic?days=90")
        assert r.status_code in (401, 403)

    def test_superadmin_report(self):
        s = _login(SA)
        r = s.get(f"{BASE_URL}/api/platform/ai-traffic?days=90")
        assert r.status_code == 200
        d = r.json()
        assert [x["ai"] for x in d["rows"]] == ["chatgpt", "perplexity", "gemini", "copilot", "claude"]
        for x in d["rows"]:
            for f in ("visits", "visitors", "registrations", "trials", "subscriptions"):
                assert isinstance(x[f], int)
        assert d["rows"][0]["visits"] >= 1
        assert set(d["total_ai"]) == {"visits", "visitors", "registrations", "trials", "subscriptions"}
        assert "visits" in d["other"]

    def test_days_validation(self):
        s = _login(SA)
        assert s.get(f"{BASE_URL}/api/platform/ai-traffic?days=0").status_code == 422
        assert s.get(f"{BASE_URL}/api/platform/ai-traffic?days=9999").status_code == 422


# Registration attribution
class TestRegisterAttribution:
    def test_register_stores_clean_attr(self, db):
        email = f"test_ai_{uuid.uuid4().hex[:8]}@example.com"
        before = _login(SA).get(f"{BASE_URL}/api/platform/ai-traffic?days=30").json()["rows"][4]["registrations"]
        r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={
            "nome": "Test", "cognome": "Ai", "email": email, "password": "TestPass123!", "org_name": "TEST_AiOrg",
            "telefono": "+393331234567", "accept_terms": True,
            "attribution": {"ai": "claude", "source": "claude", "referrer_host": "claude.ai", "landing": "/faq", "evil": "x" * 500, "utm_source": "y" * 300}})
        try:
            assert r.status_code == 200, r.text
            u = db.users.find_one({"email": email})
            org = db.organizations.find_one({"id": u["org_id"]})
            a = org["attribution"]
            assert a["ai"] == "claude" and a["referrer_host"] == "claude.ai"
            assert "evil" not in a and len(a["utm_source"]) == 120
            after = _login(SA).get(f"{BASE_URL}/api/platform/ai-traffic?days=30").json()["rows"][4]
            assert after["registrations"] == before + 1
            assert after["trials"] >= 1
        finally:
            _cleanup(db, email)

    def test_register_invalid_ai_blanked(self, db):
        email = f"test_ai_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={
            "nome": "Test", "cognome": "Ai", "email": email, "password": "TestPass123!", "org_name": "TEST_AiOrg2",
            "telefono": "+393331234567", "accept_terms": True, "attribution": {"ai": "hacker", "source": "google"}})
        try:
            assert r.status_code == 200, r.text
            u = db.users.find_one({"email": email})
            org = db.organizations.find_one({"id": u["org_id"]})
            assert org["attribution"]["ai"] == "" and org["attribution"]["source"] == "google"
        finally:
            _cleanup(db, email)

    def test_register_without_attribution(self, db):
        email = f"test_ai_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register-organization", json={
            "nome": "Test", "cognome": "Ai", "email": email, "password": "TestPass123!", "org_name": "TEST_AiOrg3", "telefono": "+393331234567", "accept_terms": True})
        try:
            assert r.status_code == 200, r.text
            u = db.users.find_one({"email": email})
            assert "attribution" not in db.organizations.find_one({"id": u["org_id"]})
        finally:
            _cleanup(db, email)
