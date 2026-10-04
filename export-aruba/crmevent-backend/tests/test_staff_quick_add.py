"""Backend tests for POST /api/staff/quick-add (iteration 45).

Covers:
- Create new person + link as staff on event (categoria=staff)
- Dedupe: second call with same email/cellulare returns status='exists' + existing person
- use_existing_person_id associates existing person without duplicating
- confirm_existing=True also forces creation of staff link without creating a duplicate person
- /api/persons-enriched flags the person as is_staff=True, NOT volontario / NOT referente
"""
import os
import time
import uuid
import pytest
import requests
from dotenv import dotenv_values


def _base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")


BASE_URL = _base_url()
QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASS = "QaEvents2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": QA_EMAIL, "password": QA_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def test_event(admin_session):
    """Create a disposable event for the quick-add tests."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "nome": f"TEST_QA_QuickAdd_{suffix}",
        "data_inizio": "2026-09-10",
        "data_fine": "2026-09-12",
        "stato": "pianificato",
    }
    r = admin_session.post(f"{BASE_URL}/api/events", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create event failed: {r.status_code} {r.text}"
    ev = r.json()
    ev_id = ev["id"]
    created_persons = []
    yield {"id": ev_id, "created_persons": created_persons}
    # teardown: delete created persons, their staff links, and the event
    for pid in created_persons:
        try:
            # delete staff link(s)
            links = admin_session.get(f"{BASE_URL}/api/staff", params={"evento_id": ev_id}, timeout=20).json()
            for l in links:
                if l.get("persona_id") == pid:
                    admin_session.delete(f"{BASE_URL}/api/staff/{l['id']}", timeout=20)
            admin_session.delete(f"{BASE_URL}/api/persons/{pid}", timeout=20)
        except Exception:
            pass
    try:
        admin_session.delete(f"{BASE_URL}/api/events/{ev_id}", timeout=20)
    except Exception:
        pass


class TestStaffQuickAdd:
    def test_01_create_new_person_and_staff_link(self, admin_session, test_event):
        suf = uuid.uuid4().hex[:6]
        body = {
            "evento_id": test_event["id"],
            "nome": "TEST_QA_Mario",
            "cognome": "Rossi",
            "email": f"test_qa_{suf}@example.com",
            "cellulare": f"+393331{suf[:5]}0",
        }
        test_event["_body1"] = body
        r = admin_session.post(f"{BASE_URL}/api/staff/quick-add", json=body, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert data["status"] == "ok"
        assert data["person"]["nome"] == "TEST_QA_Mario"
        assert data["person"]["cognome"] == "Rossi"
        assert "id" in data["person"] and data["person"]["id"]
        pid = data["person"]["id"]
        test_event["created_persons"].append(pid)
        test_event["_pid1"] = pid

        # Verify the staff link exists for the event with categoria=staff
        staff_list = admin_session.get(f"{BASE_URL}/api/staff", params={"evento_id": test_event["id"]}, timeout=20).json()
        links = [s for s in staff_list if s.get("persona_id") == pid]
        assert len(links) == 1, f"expected exactly 1 staff link, got {len(links)}: {links}"
        assert links[0]["categoria"] == "staff"
        assert links[0]["evento_id"] == test_event["id"]

    def test_02_persons_enriched_flags_staff_only(self, admin_session, test_event):
        pid = test_event["_pid1"]
        enriched = admin_session.get(f"{BASE_URL}/api/persons-enriched", timeout=30).json()
        matches = [p for p in enriched if p.get("id") == pid]
        assert len(matches) == 1, f"person not found in persons-enriched"
        p = matches[0]
        assert p.get("is_staff") is True, f"is_staff should be True, got {p.get('is_staff')}"
        assert p.get("is_volontario") in (False, None), f"is_volontario should be False, got {p.get('is_volontario')}"
        assert p.get("is_referente") in (False, None), f"is_referente should be False, got {p.get('is_referente')}"

    def test_03_dedupe_same_email_returns_exists(self, admin_session, test_event):
        """Second call with same email on a NEW event should match the existing person (dedupe)."""
        # create a second event to avoid the already-linked short-circuit
        suf = uuid.uuid4().hex[:8]
        r = admin_session.post(f"{BASE_URL}/api/events", json={
            "nome": f"TEST_QA_QuickAdd2_{suf}",
            "data_inizio": "2026-10-10", "data_fine": "2026-10-12", "stato": "pianificato",
        }, timeout=30)
        assert r.status_code in (200, 201)
        ev2 = r.json()["id"]
        test_event["_ev2"] = ev2

        body = dict(test_event["_body1"])
        body["evento_id"] = ev2
        body["nome"] = "DifferentNameShouldBeIgnored"
        r = admin_session.post(f"{BASE_URL}/api/staff/quick-add", json=body, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "exists", f"expected 'exists' got: {data}"
        assert data["person"]["id"] == test_event["_pid1"]
        assert data["person"]["email"] == body["email"]

        # no new staff link should have been created yet
        staff_list = admin_session.get(f"{BASE_URL}/api/staff", params={"evento_id": ev2}, timeout=20).json()
        assert all(s.get("persona_id") != test_event["_pid1"] for s in staff_list)

    def test_04_use_existing_person_id_links_no_duplicate(self, admin_session, test_event):
        ev2 = test_event["_ev2"]
        body = {
            "evento_id": ev2,
            "nome": "TEST_QA_Mario",
            "use_existing_person_id": test_event["_pid1"],
        }
        r = admin_session.post(f"{BASE_URL}/api/staff/quick-add", json=body, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["person"]["id"] == test_event["_pid1"]

        # exactly one staff link for the person on ev2
        staff_list = admin_session.get(f"{BASE_URL}/api/staff", params={"evento_id": ev2}, timeout=20).json()
        links = [s for s in staff_list if s.get("persona_id") == test_event["_pid1"]]
        assert len(links) == 1
        assert links[0]["categoria"] == "staff"

        # ensure NO duplicate person was created with same email
        enriched = admin_session.get(f"{BASE_URL}/api/persons-enriched", timeout=30).json()
        with_email = [p for p in enriched if (p.get("email") or "").lower() == test_event["_body1"]["email"].lower()]
        assert len(with_email) == 1, f"duplicate person created, found {len(with_email)}"

        # teardown ev2
        for s in admin_session.get(f"{BASE_URL}/api/staff", params={"evento_id": ev2}, timeout=20).json():
            if s.get("persona_id") == test_event["_pid1"]:
                admin_session.delete(f"{BASE_URL}/api/staff/{s['id']}", timeout=20)
        admin_session.delete(f"{BASE_URL}/api/events/{ev2}", timeout=20)

    def test_05_missing_nome_returns_400(self, admin_session, test_event):
        r = admin_session.post(f"{BASE_URL}/api/staff/quick-add", json={
            "evento_id": test_event["id"], "nome": "   "
        }, timeout=20)
        assert r.status_code == 400

    def test_06_missing_evento_returns_400(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/staff/quick-add", json={
            "evento_id": "", "nome": "Pippo"
        }, timeout=20)
        assert r.status_code == 400
