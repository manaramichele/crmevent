"""Tests for Hospitality 'servizio_ospitalita' round-trip + my_event_detail filtering."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
EVENT_ID = "ev_qa_1"
PRESENCE_ID = "staff_973eb8d3ff"
PERSON_ID = "person_fa782807a3"
ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}


@pytest.fixture(scope="module")
def admin_sess():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    return s


def _set_servizio(s, value):
    r = s.put(f"{BASE}/api/staff/{PRESENCE_ID}", json={"servizio_ospitalita": value})
    assert r.status_code in (200, 204), r.text


def _get_person(s):
    r = s.get(f"{BASE}/api/events/{EVENT_ID}/hospitality")
    assert r.status_code == 200
    for p in r.json().get("persons", []):
        if p.get("persona_id") == PERSON_ID:
            return p
    pytest.fail("Person not found")


@pytest.mark.parametrize("val", ["da_definire", "nessun_servizio", "solo_ospitalita", "solo_pasti", "ospitalita_pasti"])
def test_servizio_round_trip(admin_sess, val):
    _set_servizio(admin_sess, val)
    p = _get_person(admin_sess)
    assert p.get("servizio_ospitalita") == val


def test_hospitality_default_present(admin_sess):
    """Field present on every person with a default value."""
    r = admin_sess.get(f"{BASE}/api/events/{EVENT_ID}/hospitality")
    assert r.status_code == 200
    for p in r.json().get("persons", []):
        assert "servizio_ospitalita" in p
        assert p["servizio_ospitalita"] in ("da_definire", "nessun_servizio", "solo_ospitalita", "solo_pasti", "ospitalita_pasti")


def test_cleanup_reset(admin_sess):
    """Restore to da_definire so UI test picks up clean state."""
    _set_servizio(admin_sess, "da_definire")
    p = _get_person(admin_sess)
    assert p.get("servizio_ospitalita") == "da_definire"
