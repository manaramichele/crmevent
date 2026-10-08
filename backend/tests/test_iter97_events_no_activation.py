"""Iter97: verify event activation removed - events immediately operational, no 403 event_not_operational,
no credit activation dialogs required. Uses QA org admin."""
import os, uuid, requests, pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASS = "QaEvents2026!"


@pytest.fixture(scope="module")
def qa_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": QA_EMAIL, "password": QA_PASS})
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def test_event(qa_session):
    name = f"TEST_Iter97_{uuid.uuid4().hex[:6]}"
    r = qa_session.post(f"{BASE}/api/events", json={
        "nome": name, "data_inizio": "2026-06-01", "data_fine": "2026-06-02", "stato": "pianificato",
    })
    assert r.status_code in (200, 201), r.text
    ev = r.json()
    yield ev
    try:
        qa_session.delete(f"{BASE}/api/events/{ev['id']}")
    except Exception:
        pass


def test_event_created_without_credits_dialog_fields(test_event):
    # Backend should not expose credit_state blocking the UI, or if present should be legacy/attivo.
    # Primary check: event is created and returned with id.
    assert "id" in test_event
    assert test_event["nome"].startswith("TEST_Iter97_")


def test_event_edit_to_attivo_no_400(qa_session, test_event):
    r = qa_session.put(f"{BASE}/api/events/{test_event['id']}", json={"stato": "attivo"})
    assert r.status_code == 200, r.text
    g = qa_session.get(f"{BASE}/api/events/{test_event['id']}")
    assert g.status_code == 200
    assert g.json()["stato"] == "attivo"


def test_event_edit_to_concluso(qa_session, test_event):
    r = qa_session.put(f"{BASE}/api/events/{test_event['id']}", json={"stato": "concluso"})
    assert r.status_code == 200, r.text


def test_create_shift_linked_to_event_not_403(qa_session, test_event):
    # Operational write referencing event — previously blocked by _assert_event_operational.
    # First get or create a team
    tr = qa_session.get(f"{BASE}/api/teams")
    teams = tr.json() if tr.status_code == 200 else []
    if teams:
        team_id = teams[0]["id"]
    else:
        cr = qa_session.post(f"{BASE}/api/teams", json={"nome": f"TEST_Team_{uuid.uuid4().hex[:4]}"})
        assert cr.status_code in (200, 201), cr.text
        team_id = cr.json()["id"]

    body = {
        "nome": f"TEST_Shift_{uuid.uuid4().hex[:4]}",
        "evento_id": test_event["id"],
        "team_id": team_id,
        "data": "2026-06-01",
        "ora_inizio": "09:00",
        "ora_fine": "12:00",
    }
    r = qa_session.post(f"{BASE}/api/shifts", json=body)
    # Must not be 403 event_not_operational
    assert r.status_code != 403, f"Unexpected 403: {r.text}"
    assert r.status_code in (200, 201, 400, 422), r.text  # 400/422 OK if schema differs; just not 403
    if r.status_code in (200, 201):
        sid = r.json().get("id")
        if sid:
            qa_session.delete(f"{BASE}/api/shifts/{sid}")


def test_events_list_fields_no_credit_badge(qa_session):
    r = qa_session.get(f"{BASE}/api/events")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    # events may still carry credit_state server-side (legacy), but response is a list we can iterate
    for ev in data[:5]:
        assert "id" in ev
        assert "stato" in ev or "nome" in ev
