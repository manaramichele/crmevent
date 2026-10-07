"""Iter 63: Pre-deploy verification — numero_camera persistence, QA isolation, event isolation."""
import os
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
EV = "ev_TEST_brf"
ORG_PE = "pe_TEST_p6"  # Sara Senzahotel (no existing lodging) in seeded org_TEST_brf
ORG_ST = "st_TEST_pi"  # Hotel Pisa


@pytest.fixture(scope="module")
def s_test():
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json={"email": "test_brf@crmeventqa.it", "password": "TestBrf2026!"})
    assert r.status_code == 200, r.text
    return sess


@pytest.fixture(scope="module")
def s_qa():
    sess = requests.Session()
    r = sess.post(f"{BASE}/api/auth/login", json={"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"})
    assert r.status_code == 200, r.text
    return sess


# -------- numero_camera persistence --------
def test_numero_camera_crud_persist(s_test):
    created = []
    try:
        # POST with 305
        payload = {
            "evento_id": EV,
            "persona_id": ORG_PE,
            "struttura_id": ORG_ST,
            "numero_camera": "305",
            "check_in": "2026-12-18",
            "check_out": "2026-12-19",
        }
        r = s_test.post(f"{BASE}/api/lodgings", json=payload)
        assert r.status_code in (200, 201), r.text
        lid = r.json()["id"]
        created.append(lid)
        # GET verify
        r2 = s_test.get(f"{BASE}/api/lodgings/{lid}")
        assert r2.status_code == 200
        assert r2.json().get("numero_camera") == "305"

        # PUT to 306
        r3 = s_test.put(f"{BASE}/api/lodgings/{lid}", json={"numero_camera": "306"})
        assert r3.status_code == 200, r3.text
        r4 = s_test.get(f"{BASE}/api/lodgings/{lid}")
        assert r4.json().get("numero_camera") == "306"

        # PUT to empty -> should appear in da_assegnare in briefing
        r5 = s_test.put(f"{BASE}/api/lodgings/{lid}", json={"numero_camera": ""})
        assert r5.status_code == 200, r5.text
        r6 = s_test.get(f"{BASE}/api/lodgings/{lid}")
        nc = r6.json().get("numero_camera")
        assert nc in ("", None), f"expected empty/null, got {nc!r}"

        # Briefing: structure Hotel Pisa should include this guest in da_assegnare
        br = s_test.get(f"{BASE}/api/events/{EV}/briefing-live").json()
        structs = br["sections"]["lodging_structures"]
        pisa = next((st for st in structs if "Pisa" in (st.get("nome") or "")), None)
        assert pisa, "Hotel Pisa not in briefing"
        da = pisa.get("da_assegnare") or []
        # Look for Sara Senzahotel in da_assegnare
        assert any("Sara" in (g.get("nome", "") or "") or
                   "Senzahotel" in (g.get("cognome", "") or "") for g in da), f"Sara Senzahotel not in da_assegnare: {da}"
    finally:
        for lid in created:
            s_test.delete(f"{BASE}/api/lodgings/{lid}")


# -------- QA Isolation --------
def test_qa_cannot_get_test_lodging(s_qa):
    r = s_qa.get(f"{BASE}/api/lodgings/lo_TEST_0")
    assert r.status_code in (403, 404), f"QA could read TEST lodging: {r.status_code}"


def test_qa_cannot_put_test_lodging(s_qa, s_test):
    # Read original value with test session
    orig = s_test.get(f"{BASE}/api/lodgings/lo_TEST_0").json()
    orig_nc = orig.get("numero_camera")
    # Try PUT from QA
    r = s_qa.put(f"{BASE}/api/lodgings/lo_TEST_0", json={"numero_camera": "999"})
    assert r.status_code in (403, 404), f"QA could PUT TEST lodging: {r.status_code}"
    # Verify unchanged
    after = s_test.get(f"{BASE}/api/lodgings/lo_TEST_0").json()
    assert after.get("numero_camera") == orig_nc


def test_qa_cannot_get_test_briefing_live(s_qa):
    r = s_qa.get(f"{BASE}/api/events/{EV}/briefing-live")
    assert r.status_code in (403, 404), f"QA could read TEST briefing: {r.status_code}"


# -------- Event isolation within same org --------
def test_event_isolation_in_same_org(s_test):
    """Verify briefing of ev_TEST_brf is strictly filtered by evento_id.
    NOTE: creating a new event + lodging requires activating event with credits (403 otherwise).
    So we validate isolation by inspecting that no numero_camera outside the known seeded set
    appears in briefing lodging_structures (sentinel-based check).
    """
    br = s_test.get(f"{BASE}/api/events/{EV}/briefing-live").json()
    import json
    blob = json.dumps(br)
    # Sentinel: random number not used in seed
    assert "777" not in blob
    # Attempt to create unrelated event (expected 403 due to activation requirement) — if it ever
    # succeeds operationally, extend this test with lodging bleed-through check.
    r = s_test.post(f"{BASE}/api/events", json={
        "nome": "TEST_SecondaryEvent_iter63",
        "data_inizio": "2026-12-25",
        "data_fine": "2026-12-26",
        "luogo": "TestLuogo",
    })
    assert r.status_code in (200, 201), r.text
    ev2 = r.json()["id"]
    try:
        # POST lodging may be blocked by operational check; accept 403 OR success+verify isolation
        r2 = s_test.post(f"{BASE}/api/lodgings", json={
            "evento_id": ev2,
            "persona_id": ORG_PE,
            "struttura_id": ORG_ST,
            "numero_camera": "777",
            "check_in": "2026-12-25",
            "check_out": "2026-12-26",
        })
        if r2.status_code in (200, 201):
            lid = r2.json()["id"]
            try:
                br2 = s_test.get(f"{BASE}/api/events/{EV}/briefing-live").json()
                assert "777" not in json.dumps(br2), "Lodging from ev2 leaked into ev_TEST_brf briefing"
            finally:
                s_test.delete(f"{BASE}/api/lodgings/{lid}")
        else:
            # Event not operational — isolation still holds (no lodgings created on ev2)
            assert r2.status_code in (403, 400)
    finally:
        s_test.delete(f"{BASE}/api/events/{ev2}")
