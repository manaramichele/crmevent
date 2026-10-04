"""Backend tests for Briefing Evento feature (iteration 10)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "manara.michele.pro@gmail.com"
ADMIN_PASSWORD = "CrmEvent2026!"
KNOWN_EVENT_ID = "d6f6296a0f1a406fb13c4dacbccea885"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ---------- Auth gating ----------
def test_briefing_live_unauthenticated(anon_session):
    r = anon_session.get(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-live", timeout=10)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


def test_briefing_live_404(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/events/does-not-exist-xyz/briefing-live", timeout=10)
    assert r.status_code == 404


# ---------- Live briefing structure ----------
def test_briefing_live_structure(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-live", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("event", "sections", "stats", "completeness", "generated_at",
              "live_hash", "latest_version", "is_stale"):
        assert k in data, f"missing key {k}"
    for sec in ("teams", "staff", "shifts", "hospitality", "maps", "sponsors", "timeline"):
        assert sec in data["sections"], f"missing section {sec}"
    comp = data["completeness"]
    assert "percent" in comp and "checks" in comp
    assert isinstance(comp["checks"], list) and len(comp["checks"]) > 0
    for c in comp["checks"]:
        assert c["status"] in ("ok", "warning")


def test_briefing_live_hospitality_no_cost_fields(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-live", timeout=15)
    assert r.status_code == 200
    hosp = r.json()["sections"]["hospitality"]
    forbidden = {"costo", "costo_totale", "prezzo", "prezzo_unitario", "importo"}
    for person in hosp:
        for item in person.get("lodgings", []) + person.get("meals", []):
            assert not (set(item.keys()) & forbidden), f"cost field leaked: {item.keys()}"


# ---------- Versions CRUD ----------
def test_publish_list_get_delete_version(admin_session):
    # publish
    r = admin_session.post(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-versions",
                           json={"titolo": "TEST_snapshot", "note": "test"}, timeout=15)
    assert r.status_code == 200, r.text
    pub = r.json()
    assert "id" in pub and "versione" in pub
    vid = pub["id"]

    # list metadata only (no content)
    r = admin_session.get(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-versions", timeout=10)
    assert r.status_code == 200
    versions = r.json()
    assert any(v["id"] == vid for v in versions)
    for v in versions:
        assert "content" not in v, "list must not include content"

    # get full snapshot
    r = admin_session.get(f"{BASE_URL}/api/briefing-versions/{vid}", timeout=10)
    assert r.status_code == 200
    full = r.json()
    assert "content" in full and "content_hash" in full
    assert full["content"]["sections"]["teams"] is not None

    # delete
    r = admin_session.delete(f"{BASE_URL}/api/briefing-versions/{vid}", timeout=10)
    assert r.status_code == 200

    # verify gone
    r = admin_session.get(f"{BASE_URL}/api/briefing-versions/{vid}", timeout=10)
    assert r.status_code == 404


def test_version_increments(admin_session):
    r1 = admin_session.post(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-versions",
                            json={"titolo": "TEST_v1"}, timeout=15).json()
    r2 = admin_session.post(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-versions",
                            json={"titolo": "TEST_v2"}, timeout=15).json()
    assert r2["versione"] == r1["versione"] + 1
    # cleanup
    admin_session.delete(f"{BASE_URL}/api/briefing-versions/{r1['id']}", timeout=10)
    admin_session.delete(f"{BASE_URL}/api/briefing-versions/{r2['id']}", timeout=10)


# ---------- Stale detection & completeness ----------
def test_stale_detection_and_completeness_changes(admin_session):
    # publish fresh snapshot -> is_stale false
    pub = admin_session.post(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-versions",
                             json={"titolo": "TEST_stale"}, timeout=15).json()
    vid = pub["id"]
    live = admin_session.get(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-live", timeout=15).json()
    assert live["is_stale"] is False, "should not be stale immediately after publish"
    assert live["latest_version"]["id"] == vid
    percent_before = live["completeness"]["percent"]

    # mutate: add a map
    m = admin_session.post(f"{BASE_URL}/api/maps",
                           json={"evento_id": KNOWN_EVENT_ID, "nome": "TEST_map",
                                 "tipologia": "Mappa", "url": "https://example.com/x.pdf"},
                           timeout=10)
    assert m.status_code in (200, 201), m.text
    map_id = m.json().get("id")

    time.sleep(0.5)
    live2 = admin_session.get(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-live", timeout=15).json()
    assert live2["is_stale"] is True, "should be stale after adding a map"

    # completeness may change (map check flips to ok if it wasn't)
    # Just ensure percent recomputed and within bounds
    assert 0 <= live2["completeness"]["percent"] <= 100

    # cleanup
    if map_id:
        admin_session.delete(f"{BASE_URL}/api/maps/{map_id}", timeout=10)
    admin_session.delete(f"{BASE_URL}/api/briefing-versions/{vid}", timeout=10)


def test_no_duplication_live_reads_live_data(admin_session):
    # Live briefing shift count must match /api/shifts count for same event
    live = admin_session.get(f"{BASE_URL}/api/events/{KNOWN_EVENT_ID}/briefing-live", timeout=15).json()
    shifts_live = live["sections"]["shifts"]
    r = admin_session.get(f"{BASE_URL}/api/shifts?evento_id={KNOWN_EVENT_ID}", timeout=10)
    assert r.status_code == 200
    assert len(shifts_live) == len(r.json()), "live briefing shifts count must match /api/shifts"
