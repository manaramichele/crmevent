"""Iter130 — Unified Super Admin 'Prenotazioni demo' + 'Richieste demo' + booking-counts."""
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
BASE = BASE.rstrip("/")
API = f"{BASE}/api"

SA = {"email": "manara.michele.pro@gmail.com", "password": "CrmEvent2026!"}
MEMBER = {"email": "qa.eventi@crmeventqa.it", "password": "QaEvents2026!"}
ROME = ZoneInfo("Europe/Rome")

# ---------- Mongo helpers ----------
MONGO_URL = None
DB_NAME = None
for line in open("/app/backend/.env"):
    if line.startswith("MONGO_URL="):
        MONGO_URL = line.split("=", 1)[1].strip().strip('"')
    if line.startswith("DB_NAME="):
        DB_NAME = line.split("=", 1)[1].strip().strip('"')
_mc = MongoClient(MONGO_URL)
db = _mc[DB_NAME]


# ---------- sessions ----------
@pytest.fixture(scope="module")
def sa_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SA, timeout=20)
    assert r.status_code == 200, r.text
    yield s


@pytest.fixture(scope="module")
def member_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=MEMBER, timeout=20)
    assert r.status_code == 200, r.text
    yield s


# ---------- availability config ----------
ORIG_CFG = {}
ORIG_WELCOME = None
CREATED_REQ_IDS = []
CREATED_LEAD_IDS = []


@pytest.fixture(scope="module", autouse=True)
def setup_and_cleanup(sa_session):
    global ORIG_CFG, ORIG_WELCOME
    r = sa_session.get(f"{API}/platform/demo/config")
    assert r.status_code == 200
    orig = r.json()
    ORIG_CFG = {"weekly": orig.get("weekly", []), "closed_dates": orig.get("closed_dates", []),
                "min_notice_hours": orig.get("min_notice_hours", 12), "horizon_days": orig.get("horizon_days", 30)}
    # Set wide windows
    weekly = [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)]
    cfg = {"weekly": weekly, "closed_dates": [], "min_notice_hours": 0, "horizon_days": 30}
    r = sa_session.put(f"{API}/platform/demo/config", json=cfg)
    assert r.status_code == 200, r.text

    # Save welcome_demo of QA user
    u = db.users.find_one({"email": MEMBER["email"]}, {"welcome_demo": 1}) or {}
    ORIG_WELCOME = u.get("welcome_demo")

    yield

    # restore config
    sa_session.put(f"{API}/platform/demo/config", json=ORIG_CFG)
    # restore welcome_demo
    db.users.update_one({"email": MEMBER["email"]}, {"$set": {"welcome_demo": ORIG_WELCOME}})
    # cleanup created test data
    for rid in CREATED_REQ_IDS:
        db.demo_requests.delete_many({"id": rid})
    emails = set()
    for rid in CREATED_REQ_IDS:
        emails.add(MEMBER["email"].lower())
    if emails:
        leads = list(db.leads.find({"email": {"$in": list(emails)}, "demo_request_id": {"$in": CREATED_REQ_IDS}}, {"id": 1}))
        for lead in leads:
            db.demo_slot_locks.delete_many({"lead_id": lead["id"]})
            db.leads.delete_one({"id": lead["id"]})
    for lid in CREATED_LEAD_IDS:
        db.demo_slot_locks.delete_many({"lead_id": lid})
        db.leads.delete_one({"id": lid})


# ---------- helpers ----------
def _pick_slot(member_session, exclude=None):
    r = member_session.get(f"{API}/demo/slots")
    assert r.status_code == 200, r.text
    slots = r.json().get("slots", [])
    assert slots, "No slots available"
    if exclude:
        slots = [s for s in slots if s["slot_key"] != exclude]
    return slots[0]["slot_key"]


def _create_request(member_session, slot_key):
    body = {"slot_key": slot_key, "nome": "QA Tester", "telefono": "3331112233", "organizzazione": "TEST_QA Org"}
    r = member_session.post(f"{API}/demo/requests", json=body)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    CREATED_REQ_IDS.append(rid)
    return rid


# ---------- Tests ----------
class TestDemoUnified:

    def test_01_counts_endpoint_shape(self, sa_session):
        r = sa_session.get(f"{API}/platform/booking-counts")
        assert r.status_code == 200
        j = r.json()
        assert "demo" in j and "assistenza" in j
        assert isinstance(j["demo"], int) and isinstance(j["assistenza"], int)

    def test_02_counts_requires_superadmin(self, member_session):
        r = member_session.get(f"{API}/platform/booking-counts")
        assert r.status_code == 403, r.text

    def test_03_bookings_requires_superadmin(self, member_session):
        r = member_session.get(f"{API}/platform/demo/bookings")
        assert r.status_code == 403

    def test_04_confirm_request_creates_booking_with_meet(self, sa_session, member_session):
        before_counts = sa_session.get(f"{API}/platform/booking-counts").json()["demo"]
        slot_key = _pick_slot(member_session)
        rid = _create_request(member_session, slot_key)

        # Confirm
        r = sa_session.patch(f"{API}/platform/demo/requests/{rid}", json={"status": "confermata"})
        assert r.status_code == 200, r.text
        j = r.json()
        b = j.get("booking")
        assert b is not None, "no booking returned"
        assert b["demo_status"] == "confermata"
        assert b["demo_slot"] == slot_key
        assert b.get("demo_meet_link"), f"meet link missing: {b}"
        assert "meet.google.com" in b["demo_meet_link"]
        assert b.get("demo_meet_status") == "ok"

        # list bookings future
        rr = sa_session.get(f"{API}/platform/demo/bookings?when=future")
        assert rr.status_code == 200
        rows = rr.json()["bookings"]
        matching = [x for x in rows if x["id"] == b["id"]]
        assert len(matching) == 1, f"expected 1 booking got {len(matching)}"

        # count
        after_counts = sa_session.get(f"{API}/platform/booking-counts").json()["demo"]
        assert after_counts == before_counts + 1, f"counts {before_counts} -> {after_counts}"

        # idempotency: repeat PATCH confermata
        r = sa_session.patch(f"{API}/platform/demo/requests/{rid}", json={"status": "confermata"})
        assert r.status_code == 200
        # repeat sync booking
        r = sa_session.post(f"{API}/platform/demo/requests/{rid}/booking")
        assert r.status_code == 200
        # Verify at most 1 lead with that demo_request_id
        lead_count = db.leads.count_documents({"demo_request_id": rid})
        assert lead_count == 1, f"duplicates: {lead_count}"
        lock_count = db.demo_slot_locks.count_documents({"lead_id": b["id"]})
        assert lock_count == 1

    def test_05_reschedule_booking(self, sa_session, member_session):
        # find lead from prior test
        rid = CREATED_REQ_IDS[-1]
        lead = db.leads.find_one({"demo_request_id": rid}, {"id": 1, "demo_slot": 1})
        assert lead
        lead_id = lead["id"]
        cur_slot = lead["demo_slot"]

        # get a different slot
        r = sa_session.get(f"{API}/platform/demo/slots", params={"exclude": lead_id})
        assert r.status_code == 200
        slots = r.json()["slots"]
        new_slot = next((s["slot_key"] for s in slots if s["slot_key"] != cur_slot), None)
        assert new_slot

        r = sa_session.post(f"{API}/platform/demo/bookings/{lead_id}/action",
                            json={"action": "reschedule", "slot_key": new_slot})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["demo_status"] == "riprogrammata"
        assert b["demo_slot"] == new_slot

        # lock moved
        locks = list(db.demo_slot_locks.find({"lead_id": lead_id}))
        assert len(locks) == 1
        assert locks[0]["slot"] == new_slot

        # invalid slot -> 409
        r = sa_session.post(f"{API}/platform/demo/bookings/{lead_id}/action",
                            json={"action": "reschedule", "slot_key": "1999-01-01T09:00"})
        assert r.status_code == 409

    def test_06_note_persists(self, sa_session):
        rid = CREATED_REQ_IDS[-1]
        lead = db.leads.find_one({"demo_request_id": rid}, {"id": 1})
        lead_id = lead["id"]
        r = sa_session.put(f"{API}/platform/demo/bookings/{lead_id}/note", json={"admin_note": "TEST nota interna"})
        assert r.status_code == 200
        got = db.leads.find_one({"id": lead_id}, {"demo_admin_note": 1})
        assert got["demo_admin_note"] == "TEST nota interna"

    def test_07_cancel_booking(self, sa_session):
        rid = CREATED_REQ_IDS[-1]
        lead = db.leads.find_one({"demo_request_id": rid}, {"id": 1})
        lead_id = lead["id"]
        before = sa_session.get(f"{API}/platform/booking-counts").json()["demo"]
        r = sa_session.post(f"{API}/platform/demo/bookings/{lead_id}/action", json={"action": "cancel"})
        assert r.status_code == 200
        b = r.json()
        assert b["demo_status"] == "annullata"
        assert db.demo_slot_locks.count_documents({"lead_id": lead_id}) == 0
        req = db.demo_requests.find_one({"id": rid}, {"status": 1})
        assert req["status"] == "annullata"
        after = sa_session.get(f"{API}/platform/booking-counts").json()["demo"]
        assert after == before - 1

    def test_08_lead_demo_action_regression(self, sa_session, member_session):
        # create a NEW request + lead directly, then confirm via /api/leads/{id}/demo
        # Need to first reset lead state (QA user lead was cancelled)
        slot_key = _pick_slot(member_session)
        rid = _create_request(member_session, slot_key)
        lead = db.leads.find_one({"demo_request_id": rid}, {"id": 1})
        lead_id = lead["id"]

        r = sa_session.post(f"{API}/leads/{lead_id}/demo", json={"action": "confirm"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["demo_status"] == "confermata"
        assert j.get("demo_meet_link")
        assert j.get("demo_meet_status") == "ok"
        # cleanup: cancel this one too
        sa_session.post(f"{API}/platform/demo/bookings/{lead_id}/action", json={"action": "cancel"})

    def test_09_video_support_regression(self, sa_session):
        r = sa_session.get(f"{API}/platform/video-support/bookings")
        assert r.status_code == 200
        assert "bookings" in r.json()
        r = sa_session.get(f"{API}/platform/video-support/config")
        assert r.status_code == 200

    def test_10_meet_error_rendering_seed(self, sa_session):
        """Seed a TEST lead with demo_meet_status='errore' to allow frontend to render error UI."""
        import uuid
        now_rome = datetime.now(ROME)
        future = (now_rome + timedelta(days=2)).strftime("%Y-%m-%dT10:00")
        lid = uuid.uuid4().hex
        doc = {
            "id": lid, "nome": "TEST_ERR", "cognome": "Meet", "email": f"test_err_{lid[:6]}@crmeventqa.it",
            "telefono": "", "organizzazione": "TEST_ERR Org", "stato": "nuovo", "source": "test",
            "demo_slot": future, "demo_status": "confermata", "demo_meet_link": None,
            "demo_meet_status": "errore", "demo_meet_error": "TEST error for UI rendering",
            "demo_source": "test", "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        db.leads.insert_one(doc)
        CREATED_LEAD_IDS.append(lid)
        r = sa_session.get(f"{API}/platform/demo/bookings?when=future")
        assert r.status_code == 200
        rows = r.json()["bookings"]
        row = next((x for x in rows if x["id"] == lid), None)
        assert row is not None
        assert row.get("demo_meet_status") == "errore"
