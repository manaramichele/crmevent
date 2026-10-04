"""Backend tests for CRMEvent AI support assistant (iteration 4)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to reading frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PASSWORD = "CrmEvent2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# -------- KB seeded + chat KB-answered --------
def test_kb_seeded_and_published(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/support-kb")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 1
    pub = [k for k in data if k.get("stato") == "pubblicato"]
    assert len(pub) >= 1


def test_chat_known_question_answers_from_kb(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/chat",
                           json={"question": "Come inserisco uno sponsor?"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("answered") is True
    assert "answer" in data and len(data["answer"]) > 5
    assert "message_id" in data and "conversation_id" in data


def test_chat_offtopic_answered_false(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/chat",
                           json={"question": "Qual è la capitale della Francia?"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("answered") is False


def test_chat_feature_request_flag(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/chat",
                           json={"question": "Posso inviare un WhatsApp automatico agli sponsor?"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("is_feature_request") is True
    fr = admin_session.get(f"{BASE_URL}/api/support-feature-requests")
    assert fr.status_code == 200
    assert isinstance(fr.json(), list) and len(fr.json()) >= 1


# -------- feedback --------
def test_feedback_persist(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/chat",
                           json={"question": "Come inserisco uno sponsor?"})
    mid = r.json()["message_id"]
    fb = admin_session.post(f"{BASE_URL}/api/support/feedback",
                            json={"message_id": mid, "value": "up"})
    assert fb.status_code == 200


# -------- ticket --------
def test_create_ticket(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/chat",
                           json={"question": "Qual è la capitale della Francia?"})
    cid = r.json()["conversation_id"]
    t = admin_session.post(f"{BASE_URL}/api/support/ticket",
                           json={"conversation_id": cid, "oggetto": "TEST_ticket"})
    assert t.status_code == 200, t.text
    assert "id" in t.json()


# -------- admin-only endpoints --------
def test_admin_can_list_conversations(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/support/conversations")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_insights(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/support/insights")
    assert r.status_code == 200
    data = r.json()
    # Loose shape check
    assert isinstance(data, dict)


def test_faq_generate(admin_session):
    r = admin_session.post(f"{BASE_URL}/api/support/faq/generate",
                           json={"question": "Come creo un evento?"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


# -------- KB CRUD with comma-separated parole_chiave --------
def test_kb_create_with_comma_string_parole_chiave(admin_session):
    payload = {
        "titolo": "TEST_KB_iter4",
        "categoria": "Test",
        "domanda": "TEST domanda",
        "risposta": "TEST risposta",
        "parole_chiave": "alfa, beta , gamma",
        "stato": "bozza",
    }
    r = admin_session.post(f"{BASE_URL}/api/support-kb", json=payload)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created.get("id")
    # cleanup
    admin_session.delete(f"{BASE_URL}/api/support-kb/{created['id']}")


# -------- unauthenticated blocked --------
def test_unauth_conversations_blocked(anon_session):
    r = anon_session.get(f"{BASE_URL}/api/support/conversations")
    assert r.status_code in (401, 403)


def test_unauth_insights_blocked(anon_session):
    r = anon_session.get(f"{BASE_URL}/api/support/insights")
    assert r.status_code in (401, 403)


def test_my_conversations_admin(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/support/my-conversations")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
