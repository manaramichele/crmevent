"""Backend tests for mandatory E.164 phone across all signup/activation paths.

Covers:
- GET /api/auth/me needs_phone flag (superadmin, admin w/wo phone)
- POST /api/auth/complete-profile validation + persistence + no org/credit side-effects
- POST /api/invites/{token}/register requires phone when invite has none
"""
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

SUPER_EMAIL = "manara.michele.pro@gmail.com"
SUPER_PASS = "CrmEvent2026!"
QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASS = "QaEvents2026!"


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s, r.json()


# ---------- /auth/me (via login response payload, same shape as user_payload) ----------
class TestNeedsPhone:
    def test_superadmin_never_needs_phone(self):
        _, data = _login(SUPER_EMAIL, SUPER_PASS)
        assert data.get("role") == "superadmin"
        assert data.get("needs_phone") is False

    def test_qa_admin_without_phone_needs_phone(self, mongo):
        # Ensure phone is empty on qa account
        mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": "", "cellulare": ""}})
        s, data = _login(QA_EMAIL, QA_PASS)
        assert data.get("needs_phone") is True
        # /auth/me endpoint
        r = s.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json().get("needs_phone") is True

    def test_qa_admin_with_phone_does_not_need(self, mongo):
        mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": "+393331234567"}})
        try:
            s, data = _login(QA_EMAIL, QA_PASS)
            assert data.get("needs_phone") is False
            r = s.get(f"{API}/auth/me")
            assert r.json().get("needs_phone") is False
        finally:
            mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": ""}})


# ---------- /auth/complete-profile ----------
class TestCompleteProfile:
    def test_rejects_empty_phone(self, mongo):
        mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": ""}})
        s, _ = _login(QA_EMAIL, QA_PASS)
        r = s.post(f"{API}/auth/complete-profile", json={"telefono": ""})
        assert r.status_code == 400, r.text

    def test_rejects_invalid_phone(self, mongo):
        mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": ""}})
        s, _ = _login(QA_EMAIL, QA_PASS)
        r = s.post(f"{API}/auth/complete-profile", json={"telefono": "123"})
        assert r.status_code == 400, r.text

    def test_rejects_without_country_code(self, mongo):
        mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": ""}})
        s, _ = _login(QA_EMAIL, QA_PASS)
        r = s.post(f"{API}/auth/complete-profile", json={"telefono": "3331234567"})
        # should be rejected (requires + prefix / E.164)
        assert r.status_code == 400, r.text

    def test_accepts_valid_e164_and_persists(self, mongo):
        mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": ""}})
        before = mongo.users.find_one({"email": QA_EMAIL})
        s, _ = _login(QA_EMAIL, QA_PASS)
        r = s.post(f"{API}/auth/complete-profile", json={"telefono": "+393331234567"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("needs_phone") is False
        # org and role unchanged
        assert body.get("org_id") == before.get("org_id")
        after = mongo.users.find_one({"email": QA_EMAIL})
        assert after.get("telefono") == "+393331234567"
        assert after.get("role") == before.get("role")
        assert after.get("org_id") == before.get("org_id")
        # No new org created
        assert mongo.organizations.count_documents({}) == mongo.organizations.count_documents({})
        # Cleanup
        mongo.users.update_one({"email": QA_EMAIL}, {"$set": {"telefono": ""}})

    def test_complete_profile_requires_auth(self):
        r = requests.post(f"{API}/auth/complete-profile", json={"telefono": "+393331234567"})
        assert r.status_code in (401, 403)


# ---------- Invite register requires phone when invite has no phone ----------
class TestInviteRegisterPhone:
    def test_invite_register_without_phone_fails(self, mongo):
        # Seed an org + invite with no phone, unique email
        org = mongo.organizations.find_one({"id": "org_qa_eventi"})
        assert org, "org_qa_eventi must exist for QA"
        token = f"TEST_tok_{uuid.uuid4().hex[:10]}"
        email = f"TEST_invite_{uuid.uuid4().hex[:8]}@crmeventqa.it"
        invite_doc = {
            "id": f"TEST_inv_{uuid.uuid4().hex[:10]}",
            "token": token,
            "org_id": "org_qa_eventi",
            "email": email,
            "role": "member",
            "status": "pending",
            "nome": "Test",
            "cognome": "Invite",
            "telefono": None,
            "created_at": "2026-01-01T00:00:00+00:00",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        mongo.org_invites.insert_one(invite_doc)
        try:
            r = requests.post(
                f"{API}/invites/{token}/register",
                json={"password": "Password12345!", "name": "Test Invite"},
            )
            assert r.status_code == 400, f"Expected 400 phone required, got {r.status_code}: {r.text}"
            # Verify no user was created
            assert mongo.users.find_one({"email": email}) is None

            # Now retry with valid phone -> should succeed
            r2 = requests.post(
                f"{API}/invites/{token}/register",
                json={"password": "Password12345!", "name": "Test Invite", "telefono": "+393334445566"},
            )
            print("r2:", r2.status_code, r2.text[:400])
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert body.get("needs_phone") is False
            u = mongo.users.find_one({"email": email.lower()})
            assert u and u.get("telefono") == "+393334445566"
        finally:
            # Cleanup
            mongo.org_invites.delete_many({"token": token})
            mongo.users.delete_many({"email": email.lower()})
            mongo.persons.delete_many({"email": email.lower()})
