"""Iteration 6: verify per-event role assignment on Persons (no anagrafica duplication)
and quick smoke of related APIs. Non-destructive."""
import os
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PW = "CrmEvent2026!"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    return sess


def test_login_ok(s):
    r = s.get(f"{API}/auth/me")
    assert r.status_code == 200
    assert r.json().get("email") == ADMIN_EMAIL


def test_events_list(s):
    r = s.get(f"{API}/events")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_persons_list(s):
    r = s.get(f"{API}/persons")
    assert r.status_code == 200


def test_person_event_role_assignment_no_duplicate(s):
    events = s.get(f"{API}/events").json()
    if len(events) < 2:
        pytest.skip("need >= 2 events")
    ev_a, ev_b = events[0]["id"], events[1]["id"]

    tag = f"TEST_{uuid.uuid4().hex[:6]}"
    # create person
    r = s.post(f"{API}/persons", json={"nome": tag, "cognome": "Roles", "email": f"{tag}@t.io"})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]

    try:
        # associate A as volontario
        r1 = s.post(f"{API}/staff", json={"persona_id": pid, "evento_id": ev_a, "categoria": "volontario", "ruolo": "Runner"})
        assert r1.status_code in (200, 201), r1.text
        pres_a_id = r1.json()["id"]
        # associate B as staff
        r2 = s.post(f"{API}/staff", json={"persona_id": pid, "evento_id": ev_b, "categoria": "staff", "ruolo": "Coord"})
        assert r2.status_code in (200, 201), r2.text
        pres_b_id = r2.json()["id"]

        # verify: exactly 1 person record with that email
        allp = s.get(f"{API}/persons").json()
        matches = [p for p in allp if p.get("email") == f"{tag}@t.io"]
        assert len(matches) == 1, f"anagrafica duplicated: {len(matches)}"

        # detail should list both events with correct categorie
        detail = s.get(f"{API}/persons/{pid}/detail").json()
        cats = sorted([e["presence"]["categoria"] for e in detail.get("events", [])])
        assert "staff" in cats and "volontario" in cats, f"cats={cats}"

        # modify: update role B to 'team'
        upd = s.put(f"{API}/staff/{pres_b_id}", json={"persona_id": pid, "evento_id": ev_b, "categoria": "team", "ruolo": "Coord"})
        assert upd.status_code in (200, 201), upd.text
        detail2 = s.get(f"{API}/persons/{pid}/detail").json()
        cats2 = sorted([e["presence"]["categoria"] for e in detail2.get("events", [])])
        assert "team" in cats2 and "volontario" in cats2, f"cats2={cats2}"

        # remove B
        d = s.delete(f"{API}/staff/{pres_b_id}")
        assert d.status_code in (200, 204)
        detail3 = s.get(f"{API}/persons/{pid}/detail").json()
        cats3 = [e["presence"]["categoria"] for e in detail3.get("events", [])]
        assert cats3 == ["volontario"], f"cats3={cats3}"
    finally:
        # cleanup: presences + person
        for _pid in [pid]:
            try:
                s.delete(f"{API}/staff/{pres_a_id}")
            except Exception:
                pass
            s.delete(f"{API}/persons/{_pid}")


def test_deals_endpoint_for_sponsor_modal(s):
    r = s.get(f"{API}/deals")
    assert r.status_code == 200
