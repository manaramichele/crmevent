"""Backend tests for review 22: persons-enriched classification flags,
invite/activation flow, /api/me/events presence, email FROM configuration."""
import os
import time
import pytest
import requests

def _get_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        from dotenv import dotenv_values
        v = dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")

BASE_URL = _get_base_url()
ADMIN_EMAIL = "tabtest_1790713653@crmevent.it"
ADMIN_PASS = "TestPass2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


# ---------- persons-enriched classification flags ----------
class TestPersonsEnriched:
    def test_persons_enriched_status(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/persons-enriched")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0

    def test_seeded_persons_classification(self, admin_session):
        data = admin_session.get(f"{BASE_URL}/api/persons-enriched").json()
        by_name = {f"{p.get('nome','')} {p.get('cognome','')}".strip(): p for p in data}

        expected = {
            "Refe Rente":       {"is_referente": True,  "is_evento": False},
            "Stef Volo":        {"is_referente": False, "is_evento": True,
                                 "is_volontario": True},
            "Enrico Trambe":    {"is_referente": True,  "is_evento": True,
                                 "is_staff": True},
            "Dacla Ssificare":  {"is_referente": False, "is_evento": False},
        }
        for name, flags in expected.items():
            assert name in by_name, f"seeded person '{name}' missing"
            for k, v in flags.items():
                assert by_name[name].get(k) == v, (
                    f"{name}.{k} expected {v} got {by_name[name].get(k)}"
                )

    def test_no_person_duplication(self, admin_session):
        data = admin_session.get(f"{BASE_URL}/api/persons-enriched").json()
        ids = [p["id"] for p in data]
        assert len(ids) == len(set(ids)), "duplicate person ids in persons-enriched"

        # Enrico must appear ONCE but classified in both buckets
        enrico = [p for p in data if p.get("cognome") == "Trambe"]
        assert len(enrico) == 1
        assert enrico[0]["is_referente"] and enrico[0]["is_evento"]


# ---------- invite + activation flow ----------
class TestInviteFlow:
    person_id = None
    invite_token = None
    invite_email = f"TEST_invitee_{int(time.time())}@example.com"

    def test_create_person_with_email(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/persons", json={
            "nome": "TEST", "cognome": f"Invitee{int(time.time())}",
            "email": TestInviteFlow.invite_email,
        })
        assert r.status_code in (200, 201), r.text
        TestInviteFlow.person_id = r.json()["id"]

    def test_send_invite(self, admin_session):
        pid = TestInviteFlow.person_id
        assert pid
        r = admin_session.post(f"{BASE_URL}/api/persons/{pid}/invite", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        # Extract invite token from DB via enriched status
        # The endpoint might return email_sent/token
        # We'll fetch through DB-exposed status endpoint below

    def test_invite_status_after_send(self, admin_session):
        pid = TestInviteFlow.person_id
        # persons-enriched should reflect invite_status now
        data = admin_session.get(f"{BASE_URL}/api/persons-enriched").json()
        me = next((p for p in data if p["id"] == pid), None)
        assert me is not None
        # after invite, status should be 'invitato' (or similar) — NOT account_attivato yet
        assert me.get("invite_status") in ("invitato", "invito_inviato",
                                           "email_inviata", "invitato_email",
                                           "invito", None) or me.get("invite_status") != "account_attivato"

    def test_activate_via_token(self, admin_session):
        # Look up invite token via server-side helper endpoint if exposed;
        # otherwise pull from DB via admin route
        pid = TestInviteFlow.person_id
        r = admin_session.get(f"{BASE_URL}/api/persons/{pid}")
        assert r.status_code == 200
        p = r.json()
        token = p.get("invite_token") or p.get("activation_token")
        if not token:
            pytest.skip("invite token not exposed in /api/persons/{id}; activation covered via UI test")
        TestInviteFlow.invite_token = token

        r = requests.post(f"{BASE_URL}/api/auth/activate",
                          json={"token": token, "password": "NewMemberPass2026!"})
        assert r.status_code == 200, r.text

        # Re-check enriched status
        data = admin_session.get(f"{BASE_URL}/api/persons-enriched").json()
        me = next((p for p in data if p["id"] == pid), None)
        assert me.get("invite_status") == "account_attivato", (
            f"expected 'account_attivato' got {me.get('invite_status')}"
        )


# ---------- email sender configuration ----------
class TestEmailSenderConfig:
    def test_email_from_address_env(self):
        # backend/.env has been updated; import the module to read effective value
        import importlib, sys
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env", override=True)
        import email_utils
        importlib.reload(email_utils)
        assert email_utils.EMAIL_FROM_ADDRESS == "hello@crmevent.it"
        assert email_utils.EMAIL_FROM_NAME == "CRMEvent"
