# Iteration 184: AI assistant disabled for staff/volunteer + event-branded staff emails (preview & invite)
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ORG = "cb4f315678b24a72b20e18ba254456fa"
EVENT = "6b93e13cc3f24d51823ebdf70491995a"
ADMIN = ("test_ai_1795001031@example.com", "TestPass123!")
VOL = ("test_ai_volunteer@example.com", "TestPass123!")
STAFF = ("test_ai_staff@example.com", "TestPass123!")
LUCA_ID = "21554b30b24843078539971bf058653c"


def _env():
    d = {}
    for line in open("/app/backend/.env"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            d[k] = v.strip('"')
    return d


_E = _env()
mdb = MongoClient(_E["MONGO_URL"])[_E["DB_NAME"]]


def login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": creds[0], "password": creds[1]})
    if r.status_code != 200:
        pytest.skip(f"login failed {creds[0]}: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def admin():
    return login(ADMIN)


# --- Feature A: AI denied for staff/volunteer ---
class TestAIDeny:
    @pytest.mark.parametrize("creds", [VOL, STAFF])
    def test_chat_403(self, creds):
        s = login(creds)
        r = s.post(f"{BASE_URL}/api/support/chat", json={"question": "ciao"})
        assert r.status_code == 403, r.text
        assert "Assistente AI non disponibile" in r.json().get("detail", "")

    @pytest.mark.parametrize("creds", [VOL, STAFF])
    def test_feedback_403(self, creds):
        s = login(creds)
        r = s.post(f"{BASE_URL}/api/support/feedback", json={"message_id": "x", "value": "up"})
        assert r.status_code == 403, r.text

    def test_admin_feedback_not_403(self, admin):
        r = admin.post(f"{BASE_URL}/api/support/feedback", json={"message_id": "nonexistent", "value": "up"})
        assert r.status_code != 403, r.text


# --- Feature B: staff email preview ---
class TestPreview:
    @pytest.mark.parametrize("kind,role,subj", [
        ("nuovo", "staff", "Maratona di Pisa – Attiva il tuo account Staff e Volontari"),
        ("nuovo", "volunteer", "Maratona di Pisa – Attiva il tuo account Staff e Volontari"),
        ("esistente", "staff", "Maratona di Pisa – Sei stato associato all'evento"),
        ("disponibilita", "volunteer", "Maratona di Pisa – Abbiamo ricevuto la tua disponibilità"),
    ])
    def test_preview_ok(self, admin, kind, role, subj):
        r = admin.get(f"{BASE_URL}/api/events/{EVENT}/staff-email-preview", params={"kind": kind, "role": role})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["subject"] == subj
        assert d["from_name"] == "Maratona di Pisa | CRMEvent"
        h = d["html"]
        assert "Maratona di Pisa" in h and "14/03/2027" in h
        assert "Gestione Staff e Volontari tramite CRMEvent" in h and "crmevent.it" in h
        assert ">MP<" in h  # initials header (no logo)
        if kind == "nuovo":
            assert "/attiva?token=ANTEPRIMA" in h
            assert ("Volontario" if role == "volunteer" else "Staff") in h
        elif kind == "esistente":
            assert "/login" in h and "/attiva" not in h
        else:
            assert "/attiva" not in h

    def test_preview_invalid_kind(self, admin):
        r = admin.get(f"{BASE_URL}/api/events/{EVENT}/staff-email-preview", params={"kind": "bogus"})
        assert r.status_code == 400

    def test_preview_invalid_role(self, admin):
        r = admin.get(f"{BASE_URL}/api/events/{EVENT}/staff-email-preview", params={"kind": "nuovo", "role": "admin"})
        assert r.status_code == 400

    def test_preview_other_org_404(self, admin):
        other = mdb.events.find_one({"org_id": {"$ne": ORG}}, {"_id": 0, "id": 1})
        r = admin.get(f"{BASE_URL}/api/events/{other['id']}/staff-email-preview", params={"kind": "nuovo"})
        assert r.status_code == 404

    def test_preview_volunteer_forbidden(self):
        s = login(VOL)
        r = s.get(f"{BASE_URL}/api/events/{EVENT}/staff-email-preview", params={"kind": "nuovo"})
        assert r.status_code in (401, 403)


# --- Feature B: invite existing vs new account ---
class TestInvite:
    def test_invite_existing_account(self, admin):
        before = mdb.users.count_documents({"email": VOL[0]})
        r = admin.post(f"{BASE_URL}/api/persons/{LUCA_ID}/invite", json={"evento_id": EVENT, "force": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["existing_account"] is True
        u = mdb.users.find_one({"email": VOL[0]})
        assert u.get("activation_token") in (None, "")
        assert mdb.users.count_documents({"email": VOL[0]}) == before == 1
        # volunteer can still log in with same password
        login(VOL)

    def test_invite_new_person(self, admin):
        email = f"test_ai_new_{uuid.uuid4().hex[:6]}@example.com"
        r = admin.post(f"{BASE_URL}/api/staff/quick-add", json={"evento_id": EVENT, "nome": "TEST_Nuovo", "cognome": "Invito",
                                                               "email": email, "categoria": "volontario"})
        assert r.status_code == 200, r.text
        pid = r.json()["person"]["id"]
        try:
            r = admin.post(f"{BASE_URL}/api/persons/{pid}/invite", json={"evento_id": EVENT, "role": "volunteer"})
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["existing_account"] is False
            users = list(mdb.users.find({"email": email}))
            assert len(users) == 1
            assert users[0].get("activation_token")
            assert users[0]["role"] == "volunteer" and users[0]["org_id"] == ORG
        finally:
            mdb.staff.delete_many({"org_id": ORG, "persona_id": pid})
            mdb.persons.delete_one({"org_id": ORG, "id": pid})
            mdb.users.delete_one({"email": email})
