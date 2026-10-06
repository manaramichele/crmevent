"""Backend E2E tests for the organizer onboarding/tutorial feature.

Covers:
- GET /api/onboarding/status for org admin (new vs existing),
  with and without event_id, event_id-dependent counters,
  superadmin no-op, main_done progression, next_step shape.
- POST /api/onboarding/state: seen/started/later/card_hidden/completed,
  skip/unskip, idempotency, no-op for superadmin.
- End-to-end: create event -> staff -> team -> shifts -> activities -> briefing
  flipping completed[] in the expected order (no artificial completion).
- Sponsor + Hospitality optional flows (skip -> unskip -> real data -> completed).
- Multi-event isolation (event A vs event B).
"""
import os
import time
import uuid
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

SUPERADMIN = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
EXISTING_ADMIN = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}


# ---------- helpers ----------
def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(s, email, password):
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()


def _register_new_org(s):
    rand = uuid.uuid4().hex[:8]
    email = f"TEST_ob_{rand}@crmeventtest.it"
    body = {
        "nome": "QA",
        "cognome": "Onboarding",
        "email": email,
        "password": "OnboardTest2026!",
        "org_name": f"TEST OB Org {rand}",
        "telefono": "+393331112233",
        "accept_terms": True,
    }
    r = s.post(f"{API}/auth/register-organization", json=body, timeout=20)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return email, r.json()


def _status(s, event_id=None):
    params = {"event_id": event_id} if event_id else {}
    r = s.get(f"{API}/onboarding/status", params=params, timeout=20)
    assert r.status_code == 200, f"status failed: {r.status_code} {r.text}"
    return r.json()


def _step(status, key):
    for s in status.get("steps", []) + status.get("optional", []):
        if s["key"] == key:
            return s
    return None


def _create_event(s, name="TEST_OB_Event", activate=True):
    # Give the event a future date so activation isn't blocked by "past event".
    r = s.post(f"{API}/events", json={"nome": name, "stato": "pianificato",
                                      "data_inizio": "2026-12-01", "data_fine": "2026-12-02"}, timeout=20)
    assert r.status_code == 200, f"event create failed: {r.status_code} {r.text}"
    ev = r.json()
    if activate:
        ra = s.post(f"{API}/events/{ev['id']}/activate", timeout=20)
        # 200 = activated, 402 = no credits (treated as a hard skip signal in that test),
        # anything else is an unexpected failure.
        if ra.status_code not in (200, 402):
            raise AssertionError(f"activate failed: {ra.status_code} {ra.text}")
        ev["_activated"] = (ra.status_code == 200)
    return ev


def _create_person(s, nome="Mario", cognome="Rossi"):
    r = s.post(f"{API}/persons", json={"nome": nome, "cognome": cognome,
                                       "email": f"TEST_p_{uuid.uuid4().hex[:6]}@x.it"}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- 1. Super Admin no-op ----------
def test_superadmin_onboarding_is_noop():
    s = _sess()
    _login(s, **SUPERADMIN)
    st = _status(s)
    assert st.get("superadmin") is True
    assert st.get("show") is False
    assert st.get("steps") == []

    # state endpoint must also be a no-op (no users.onboarding written)
    r = s.post(f"{API}/onboarding/state", json={"started": True, "seen": True}, timeout=20)
    assert r.status_code == 200
    assert r.json().get("superadmin") is True


# ---------- 2. New org admin: welcome + first step = event ----------
def test_new_org_first_step_is_event_and_welcome_eligible():
    s = _sess()
    _register_new_org(s)
    st = _status(s)
    assert st["superadmin"] is False
    assert st["show"] is True
    assert st["event_id"] is None
    assert st["main_done"] == 0
    assert st["main_total"] == 6
    assert st["returning_user"] is False
    assert st["state"]["seen"] is False
    assert st["state"]["completed"] is False
    nxt = st["next_step"]
    assert nxt and nxt["key"] == "event"
    assert nxt["route"] == "/eventi"
    # all other main steps are not completed and not skipped
    for key in ["event", "people", "team", "shifts", "activities", "briefing"]:
        step = _step(st, key)
        assert step is not None, key
        assert step["completed"] is False
        assert step["skipped"] is False


# ---------- 3. State transitions: seen / later / card_hidden ----------
def test_state_seen_later_card_hidden_persist():
    s = _sess()
    _register_new_org(s)

    # seen
    r = s.post(f"{API}/onboarding/state", json={"seen": True}, timeout=20)
    assert r.status_code == 200
    assert r.json()["onboarding"]["seen"] is True
    st = _status(s)
    assert st["state"]["seen"] is True

    # later
    s.post(f"{API}/onboarding/state", json={"later": True}, timeout=20)
    st = _status(s)
    assert st["state"]["later"] is True

    # card_hidden
    s.post(f"{API}/onboarding/state", json={"card_hidden": True}, timeout=20)
    st = _status(s)
    assert st["state"]["card_hidden"] is True


# ---------- 4. Full sequential completion of 6 main steps ----------
def test_sequential_main_steps_flip_to_completed():
    s = _sess()
    _register_new_org(s)

    # before any event
    st = _status(s)
    assert st["main_done"] == 0

    # 1) create event
    ev = _create_event(s, "TEST_OB_A")
    st = _status(s)
    assert _step(st, "event")["completed"] is True
    assert st["main_done"] == 1
    assert st["event_id"] == ev["id"]
    assert st["next_step"]["key"] == "people"

    # Must also work when explicitly filtered by event_id
    st2 = _status(s, event_id=ev["id"])
    assert st2["event_id"] == ev["id"]
    assert _step(st2, "event")["completed"] is True

    # 2) staff/people (needs a person first)
    p = _create_person(s)
    r = s.post(f"{API}/staff", json={"persona_id": p["id"], "evento_id": ev["id"],
                                     "categoria": "staff", "ruolo": "Operativo"}, timeout=20)
    assert r.status_code == 200, r.text
    st = _status(s, event_id=ev["id"])
    assert _step(st, "people")["completed"] is True
    assert st["main_done"] == 2
    assert st["next_step"]["key"] == "team"

    # 3) team
    r = s.post(f"{API}/teams", json={"nome": "Team Alpha", "evento_id": ev["id"]}, timeout=20)
    assert r.status_code == 200, r.text
    st = _status(s, event_id=ev["id"])
    assert _step(st, "team")["completed"] is True
    assert st["main_done"] == 3
    assert st["next_step"]["key"] == "shifts"

    # 4) shift
    r = s.post(f"{API}/shifts", json={"evento_id": ev["id"], "persona_id": p["id"],
                                      "data": "2026-06-01", "ora_inizio": "09:00",
                                      "ora_fine": "12:00", "ruolo": "Operativo"}, timeout=20)
    assert r.status_code == 200, r.text
    st = _status(s, event_id=ev["id"])
    assert _step(st, "shifts")["completed"] is True
    assert st["main_done"] == 4
    assert st["next_step"]["key"] == "activities"

    # 5) activity
    r = s.post(f"{API}/activities", json={"titolo": "TEST OB Attività", "evento_id": ev["id"],
                                          "tipo": "generica"}, timeout=20)
    assert r.status_code == 200, r.text
    st = _status(s, event_id=ev["id"])
    assert _step(st, "activities")["completed"] is True
    assert st["main_done"] == 5
    assert st["next_step"]["key"] == "briefing"

    # 6) briefing version
    r = s.post(f"{API}/events/{ev['id']}/briefing-versions",
               json={"titolo": "V1"}, timeout=30)
    assert r.status_code == 200, r.text
    st = _status(s, event_id=ev["id"])
    assert _step(st, "briefing")["completed"] is True
    assert st["main_done"] == 6
    assert st["main_total"] == 6
    assert st["all_main_completed"] is True
    assert st["next_step"] is None

    # Server flags completed=true once all main done (even without POST)
    assert st["state"]["completed"] is True


# ---------- 5. Multi-event isolation ----------
def test_multi_event_isolation():
    s = _sess()
    _register_new_org(s)
    # Event A with data
    ev_a = _create_event(s, "TEST_OB_MultiA")
    p = _create_person(s)
    s.post(f"{API}/staff", json={"persona_id": p["id"], "evento_id": ev_a["id"],
                                 "categoria": "staff"}, timeout=20).raise_for_status()
    s.post(f"{API}/teams", json={"nome": "Team A", "evento_id": ev_a["id"]}, timeout=20).raise_for_status()

    # Event B empty — must be created AFTER A so default/most-recent = B
    time.sleep(0.2)
    ev_b = _create_event(s, "TEST_OB_MultiB")

    # Explicit filter by A: people + team completed, main_done >= 3 (event+people+team)
    st_a = _status(s, event_id=ev_a["id"])
    assert st_a["event_id"] == ev_a["id"]
    assert _step(st_a, "people")["completed"] is True
    assert _step(st_a, "team")["completed"] is True
    assert st_a["main_done"] >= 3

    # Explicit filter by B: only "event" completed; people/team must be false
    st_b = _status(s, event_id=ev_b["id"])
    assert st_b["event_id"] == ev_b["id"]
    assert _step(st_b, "event")["completed"] is True
    assert _step(st_b, "people")["completed"] is False
    assert _step(st_b, "team")["completed"] is False
    assert st_b["main_done"] == 1
    assert st_b["next_step"]["key"] == "people"

    # Default (no event_id): backend picks most recent -> should match ev_b
    st_def = _status(s)
    assert st_def["event_id"] == ev_b["id"]
    assert _step(st_def, "people")["completed"] is False


# ---------- 6. Sponsor optional: skip/unskip/complete; doesn't affect main_total ----------
def test_sponsor_skip_unskip_and_complete():
    s = _sess()
    _register_new_org(s)
    ev = _create_event(s, "TEST_OB_Sponsor")

    st = _status(s, event_id=ev["id"])
    sp = _step(st, "sponsor")
    assert sp and sp["optional"] is True
    assert sp["completed"] is False
    assert sp["skipped"] is False
    assert st["main_total"] == 6  # sponsor must NOT affect main total

    # skip
    r = s.post(f"{API}/onboarding/state", json={"skip": "sponsor"}, timeout=20)
    assert r.status_code == 200
    st = _status(s, event_id=ev["id"])
    assert _step(st, "sponsor")["skipped"] is True
    assert st["state"]["skipped"].get("sponsor") is True
    assert st["main_total"] == 6

    # unskip
    r = s.post(f"{API}/onboarding/state", json={"unskip": "sponsor"}, timeout=20)
    assert r.status_code == 200
    st = _status(s, event_id=ev["id"])
    assert _step(st, "sponsor")["skipped"] is False

    # create real sponsor deal (needs company + deal)
    rc = s.post(f"{API}/companies", json={"nome": "TEST OB Sponsor Co"}, timeout=20)
    assert rc.status_code == 200, rc.text
    company = rc.json()
    rd = s.post(f"{API}/deals", json={"azienda_id": company["id"], "evento_id": ev["id"],
                                      "tipo": "sponsor", "fase": "prospect"}, timeout=20)
    assert rd.status_code == 200, rd.text
    st = _status(s, event_id=ev["id"])
    assert _step(st, "sponsor")["completed"] is True
    # Sponsor is optional; main_done still reflects only "event"
    assert st["main_done"] == 1


# ---------- 7. Hospitality optional: skip/unskip/complete ----------
def test_hospitality_skip_unskip_and_complete():
    s = _sess()
    _register_new_org(s)
    ev = _create_event(s, "TEST_OB_Hospitality")
    p = _create_person(s)

    # skip
    s.post(f"{API}/onboarding/state", json={"skip": "hospitality"}, timeout=20).raise_for_status()
    st = _status(s, event_id=ev["id"])
    assert _step(st, "hospitality")["skipped"] is True

    # unskip
    s.post(f"{API}/onboarding/state", json={"unskip": "hospitality"}, timeout=20).raise_for_status()
    st = _status(s, event_id=ev["id"])
    assert _step(st, "hospitality")["skipped"] is False

    # Create real lodging -> hospitality completed
    r = s.post(f"{API}/lodgings", json={"evento_id": ev["id"], "persona_id": p["id"],
                                        "tipo_struttura": "hotel"}, timeout=20)
    assert r.status_code == 200, r.text
    st = _status(s, event_id=ev["id"])
    assert _step(st, "hospitality")["completed"] is True
    # main_total still 6 (hospitality is optional and doesn't move main_done)
    assert st["main_total"] == 6


# ---------- 8. Returning user vs new user flag ----------
def test_returning_user_flag_after_event_exists_and_no_state():
    s = _sess()
    _register_new_org(s)
    # Nothing seen/started yet, no events -> returning_user=False
    st = _status(s)
    assert st["returning_user"] is False
    # Create event; still haven't posted seen/started
    _create_event(s, "TEST_OB_Returning")
    st = _status(s)
    # len(events)>0 and seen/started not set => returning_user True
    assert st["returning_user"] is True

    # After setting seen, returning_user should become False
    s.post(f"{API}/onboarding/state", json={"seen": True}, timeout=20).raise_for_status()
    st = _status(s)
    assert st["returning_user"] is False


# ---------- 9. Existing admin: endpoint reachable (regression) ----------
def test_existing_admin_status_shape():
    s = _sess()
    try:
        _login(s, **EXISTING_ADMIN)
    except AssertionError:
        import pytest
        pytest.skip("Existing QA admin credentials not valid in this env")
    st = _status(s)
    # Must return the expected shape (regression guard)
    assert "superadmin" in st
    assert st["superadmin"] is False
    assert "steps" in st and isinstance(st["steps"], list)
    assert st.get("main_total") == 6
    assert "optional" in st and isinstance(st["optional"], list)
    opt_keys = sorted([o["key"] for o in st["optional"]])
    assert opt_keys == ["hospitality", "sponsor"]
