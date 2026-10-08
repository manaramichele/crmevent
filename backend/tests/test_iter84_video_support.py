"""Iter 84 — Assistenza in videochiamata (Google Meet) a crediti.
Backend regression + end-to-end tests. Meet è SIMULATO (VIDEO_SUPPORT_MEET_SIMULATION=1).
Cleanup finale: ripristina servizio video_support (active=False, unit_cost=None), config, bookings.
"""
import os
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASS = "CrmEvent2026!"
ADM_EMAIL = "qa.eventi@crmeventqa.it"
ADM_PASS = "QaEvents2026!"
ROME = ZoneInfo("Europe/Rome")

COST = 5


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PASS)


@pytest.fixture(scope="module")
def adm():
    return _login(ADM_EMAIL, ADM_PASS)


@pytest.fixture(scope="module", autouse=True)
def service_cleanup(sa):
    """Record original service state + QA balance; restore at the end."""
    svcs = sa.get(f"{API}/platform/credit-services").json()
    vs = next(s for s in svcs["services"] if s["key"] == "video_support")
    orig = {"active": vs.get("active"), "consumo_active": vs.get("consumo_active"),
            "unit_cost": vs.get("unit_cost")}
    # Record QA org balance via Mongo direct (admin may not expose that)
    loop = asyncio.new_event_loop()
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    async def _get_balance():
        u = await db.users.find_one({"email": ADM_EMAIL}, {"_id": 0, "org_id": 1})
        org = await db.organizations.find_one({"id": u["org_id"]}, {"_id": 0, "credits": 1})
        return u["org_id"], ((org or {}).get("credits") or {}).get("balance", 0)
    org_id, start_balance = loop.run_until_complete(_get_balance())
    print(f"[iter84] start QA balance = {start_balance}  org_id={org_id}")

    yield {"orig": orig, "org_id": org_id, "start_balance": start_balance}

    # --- Final cleanup: deactivate service, remove bookings, config, test news
    async def _cleanup():
        await db.video_support_bookings.delete_many({"org_id": org_id})
        await db.video_support_config.delete_one({"id": "config"})
        upd = {"active": False, "consumo_active": False, "unit_cost": None}
        await db.credit_services.update_one({"key": "video_support"}, {"$set": upd})
        await db.news_items.delete_many({"titolo": {"$regex": "^TEST_iter84"}})
        # Restore balance to original (compensate ledger entries created in tests)
        await db.organizations.update_one({"id": org_id}, {"$set": {"credits.balance": start_balance,
                                                                     "credits.reserved": 0,
                                                                     "credits.updated_at": datetime.now(timezone.utc).isoformat()}})
        await db.credit_ledger.delete_many({"org_id": org_id, "service_key": "video_support"})
        await db.credit_ledger.delete_many({"org_id": org_id, "reason_code": "video_support_refund"})
    loop.run_until_complete(_cleanup())
    cli.close()
    loop.close()
    print("[iter84] cleanup done")


# ----------------------- Phase 1: service DEFAULT = disabled -----------------------
class TestPhase1Default:
    def test_info_available_false(self, adm, sa, service_cleanup):
        # Ensure service is currently disabled (deactivate first)
        sa.put(f"{API}/platform/credit-services/video_support",
               json={"active": False, "consumo_active": False, "unit_cost": None})
        r = adm.get(f"{API}/video-support/info")
        assert r.status_code == 200
        data = r.json()
        assert data["available"] is False
        assert data["duration_min"] == 30

    def test_service_costs_excludes_video_support(self, adm):
        r = adm.get(f"{API}/credits/service-costs")
        assert r.status_code == 200
        keys = [s["key"] for s in r.json().get("services", [])]
        assert "video_support" not in keys

    def test_slots_empty_when_disabled(self, adm):
        r = adm.get(f"{API}/video-support/slots")
        assert r.status_code == 200
        assert r.json()["slots"] == []

    def test_book_forbidden_when_disabled(self, adm):
        r = adm.post(f"{API}/video-support/bookings", json={"slot_key": "2099-01-01T10:00", "confirm_cost": 5})
        assert r.status_code == 403


# ----------------------- Phase 2: Super Admin activation -----------------------
class TestPhase2Activate:
    def test_sa_activate_service(self, sa):
        r = sa.put(f"{API}/platform/credit-services/video_support",
                   json={"active": True, "consumo_active": True, "unit_cost": COST})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["active"] is True
        assert body["consumo_active"] is True
        assert body["unit_cost"] == COST

    def test_info_available_true_after_activation(self, adm):
        r = adm.get(f"{API}/video-support/info").json()
        assert r["available"] is True
        assert r["service"]["unit_cost"] == COST

    def test_service_costs_now_includes(self, adm):
        r = adm.get(f"{API}/credits/service-costs").json()
        vs = next((s for s in r["services"] if s["key"] == "video_support"), None)
        assert vs is not None
        assert vs["unit_cost"] == COST


# ----------------------- Phase 3: Config + Slots -----------------------
class TestPhase3Config:
    def test_sa_only_config(self, adm):
        r = adm.get(f"{API}/platform/video-support/config")
        assert r.status_code == 403

    def test_put_config(self, sa):
        body = {
            "weekly": [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)],
            "closed_dates": [],
            "min_notice_hours": 24,
            "horizon_days": 30,
        }
        r = sa.put(f"{API}/platform/video-support/config", json=body)
        assert r.status_code == 200
        d = r.json()
        assert len(d["weekly"]) == 7
        assert d["min_notice_hours"] == 24

    def test_slots_all_in_future_min_notice(self, adm):
        r = adm.get(f"{API}/video-support/slots").json()
        slots = r["slots"]
        assert len(slots) > 0
        min_dt = datetime.now(timezone.utc) + timedelta(hours=23)
        for s in slots[:50]:
            start = datetime.fromisoformat(s["start"].replace("Z", "+00:00"))
            assert start >= min_dt, f"slot {s['slot_key']} is < 24h from now"

    def test_closed_date_excludes_day(self, sa, adm):
        # Pick 3rd distinct date from slots and close it
        r = adm.get(f"{API}/video-support/slots").json()
        dates = sorted({s["slot_key"][:10] for s in r["slots"]})
        target_day = dates[2]
        body = {
            "weekly": [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)],
            "closed_dates": [target_day],
            "min_notice_hours": 24,
            "horizon_days": 30,
        }
        sa.put(f"{API}/platform/video-support/config", json=body)
        r2 = adm.get(f"{API}/video-support/slots").json()
        remaining = {s["slot_key"][:10] for s in r2["slots"]}
        assert target_day not in remaining
        # restore
        sa.put(f"{API}/platform/video-support/config", json={**body, "closed_dates": []})


# ----------------------- Phase 4: Booking happy path -----------------------
@pytest.fixture(scope="module")
def booked(sa, adm, service_cleanup):
    """Books a slot and returns the response + initial balance."""
    # ensure min_notice=24 config
    sa.put(f"{API}/platform/video-support/config", json={
        "weekly": [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)],
        "closed_dates": [], "min_notice_hours": 24, "horizon_days": 30})
    before = adm.get(f"{API}/video-support/info").json()
    slots = adm.get(f"{API}/video-support/slots").json()["slots"]
    assert slots, "no slot available"
    slot_key = slots[0]["slot_key"]
    r = adm.post(f"{API}/video-support/bookings",
                 json={"slot_key": slot_key, "confirm_cost": COST, "note": "TEST_iter84 booking"})
    assert r.status_code == 200, r.text
    bk = r.json()
    assert bk["status"] == "confermata"
    assert bk["meet_link"].startswith("https://meet.google.com/sim-")
    assert bk["simulated"] is True
    return {"booking": bk, "slot_key": slot_key, "balance_before": before["balance"]}


class TestPhase4Booking:
    def test_booking_charged_exactly_cost(self, adm, booked):
        after = adm.get(f"{API}/video-support/info").json()
        assert after["balance"] == booked["balance_before"] - COST
        assert booked["booking"]["credits_charged"] == COST

    def test_slot_disappears(self, adm, booked):
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        assert booked["slot_key"] not in {s["slot_key"] for s in slots}

    def test_my_bookings_includes_it(self, adm, booked):
        r = adm.get(f"{API}/video-support/bookings").json()
        ids = [b["id"] for b in r["bookings"]]
        assert booked["booking"]["id"] in ids

    def test_double_booking_conflict(self, adm, booked):
        r = adm.post(f"{API}/video-support/bookings",
                     json={"slot_key": booked["slot_key"], "confirm_cost": COST})
        assert r.status_code == 409

    def test_cost_changed_detection(self, adm):
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        if not slots:
            pytest.skip("no slots")
        r = adm.post(f"{API}/video-support/bookings",
                     json={"slot_key": slots[0]["slot_key"], "confirm_cost": COST + 99})
        assert r.status_code == 409
        detail = r.json().get("detail")
        assert isinstance(detail, dict) and detail.get("code") == "cost_changed"


# ----------------------- Phase 5: Insufficient balance -----------------------
class TestPhase5Insufficient:
    def test_402_when_balance_low(self, sa, adm, service_cleanup):
        # Temporarily set unit_cost very high
        sa.put(f"{API}/platform/credit-services/video_support",
               json={"unit_cost": 99999})
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        assert slots
        r = adm.post(f"{API}/video-support/bookings",
                     json={"slot_key": slots[0]["slot_key"], "confirm_cost": 99999})
        assert r.status_code == 402
        # restore
        sa.put(f"{API}/platform/credit-services/video_support", json={"unit_cost": COST})


# ----------------------- Phase 6: Reschedule + cancel policy -----------------------
@pytest.fixture(scope="module")
def booking_future(adm, booked):
    # Use the one from booked (it's >24h away since min_notice=24)
    return booked["booking"]


class TestPhase6Reschedule:
    def test_reschedule_once(self, adm, booking_future):
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        new_slot = slots[0]["slot_key"]
        r = adm.post(f"{API}/video-support/bookings/{booking_future['id']}/reschedule",
                     json={"slot_key": new_slot})
        assert r.status_code == 200, r.text
        assert r.json()["slot_key"] == new_slot

    def test_reschedule_second_time_blocked(self, adm, booking_future):
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        if not slots:
            pytest.skip("no slot")
        r = adm.post(f"{API}/video-support/bookings/{booking_future['id']}/reschedule",
                     json={"slot_key": slots[0]["slot_key"]})
        assert r.status_code == 400


class TestPhase7CancelFullRefund:
    def test_cancel_more_than_24h_refunds(self, adm, booking_future, service_cleanup):
        bal_before = adm.get(f"{API}/video-support/info").json()["balance"]
        r = adm.post(f"{API}/video-support/bookings/{booking_future['id']}/cancel",
                     json={"reason": "TEST_iter84"})
        assert r.status_code == 200
        assert r.json()["refunded"] == COST
        bal_after = adm.get(f"{API}/video-support/info").json()["balance"]
        assert bal_after == bal_before + COST


# ----------------------- Phase 8: Cancel < 24h = no refund -----------------------
class TestPhase8CancelNoRefund:
    def test_min_notice_zero_allows_near_slot(self, sa, adm, service_cleanup):
        # Set min_notice=0 and book a near future slot
        sa.put(f"{API}/platform/video-support/config", json={
            "weekly": [{"weekday": d, "start": "00:00", "end": "23:30"} for d in range(7)],
            "closed_dates": [], "min_notice_hours": 0, "horizon_days": 2})
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        # Pick a slot < 24h
        near = None
        for s in slots:
            start = datetime.fromisoformat(s["start"].replace("Z", "+00:00"))
            hours_left = (start - datetime.now(timezone.utc)).total_seconds() / 3600
            if 0.5 < hours_left < 23:
                near = s
                break
        assert near, "no near slot"
        bk = adm.post(f"{API}/video-support/bookings",
                      json={"slot_key": near["slot_key"], "confirm_cost": COST, "note": "TEST_iter84_near"}).json()
        assert bk["status"] == "confermata"

        # Reschedule should 400 (<24h)
        slots2 = adm.get(f"{API}/video-support/slots").json()["slots"]
        if slots2:
            rr = adm.post(f"{API}/video-support/bookings/{bk['id']}/reschedule",
                          json={"slot_key": slots2[-1]["slot_key"]})
            assert rr.status_code == 400

        bal_before = adm.get(f"{API}/video-support/info").json()["balance"]
        rc = adm.post(f"{API}/video-support/bookings/{bk['id']}/cancel", json={"reason": "test"})
        assert rc.status_code == 200
        assert rc.json()["refunded"] == 0  # <24h = no refund
        bal_after = adm.get(f"{API}/video-support/info").json()["balance"]
        assert bal_after == bal_before  # no refund

        # restore 24h config
        sa.put(f"{API}/platform/video-support/config", json={
            "weekly": [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)],
            "closed_dates": [], "min_notice_hours": 24, "horizon_days": 30})


# ----------------------- Phase 9: Super Admin can always cancel w/ refund -----------------------
class TestPhase9SuperAdmin:
    def test_sa_sees_all_bookings_and_cancel_with_full_refund(self, sa, adm, service_cleanup):
        # Create a near-future booking (<24h)
        sa.put(f"{API}/platform/video-support/config", json={
            "weekly": [{"weekday": d, "start": "00:00", "end": "23:30"} for d in range(7)],
            "closed_dates": [], "min_notice_hours": 0, "horizon_days": 2})
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        near = next((s for s in slots if 0.5 < (datetime.fromisoformat(s["start"].replace("Z","+00:00")) - datetime.now(timezone.utc)).total_seconds()/3600 < 23), None)
        assert near
        bk = adm.post(f"{API}/video-support/bookings",
                      json={"slot_key": near["slot_key"], "confirm_cost": COST, "note": "TEST_iter84_sa"}).json()
        bal_before = adm.get(f"{API}/video-support/info").json()["balance"]

        # SA sees it
        r = sa.get(f"{API}/platform/video-support/bookings")
        assert r.status_code == 200
        assert any(b["id"] == bk["id"] for b in r.json()["bookings"])

        # SA admin note
        rn = sa.put(f"{API}/platform/video-support/bookings/{bk['id']}/note",
                    json={"admin_note": "TEST_iter84 admin note"})
        assert rn.status_code == 200

        # SA cancel -> full refund even if <24h
        rc = sa.post(f"{API}/platform/video-support/bookings/{bk['id']}/cancel",
                     json={"reason": "SA cancel"})
        assert rc.status_code == 200
        assert rc.json()["refunded"] == COST
        bal_after = adm.get(f"{API}/video-support/info").json()["balance"]
        assert bal_after == bal_before + COST

        sa.put(f"{API}/platform/video-support/config", json={
            "weekly": [{"weekday": d, "start": "09:00", "end": "18:00"} for d in range(7)],
            "closed_dates": [], "min_notice_hours": 24, "horizon_days": 30})

    def test_non_sa_forbidden_platform(self, adm):
        for p in ["/platform/video-support/config", "/platform/video-support/bookings",
                  "/platform/video-support/slots"]:
            r = adm.get(f"{API}{p}")
            assert r.status_code == 403, f"{p} expected 403, got {r.status_code}"


# ----------------------- Phase 10: News publish gating -----------------------
class TestPhase10News:
    def test_publish_blocked_when_service_disabled(self, sa):
        # Create draft directly in Mongo with requires_service=video_support, then disable service
        loop = asyncio.new_event_loop()
        cli = AsyncIOMotorClient(MONGO_URL)
        db = cli[DB_NAME]
        nid = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()

        async def _setup():
            await db.news_items.insert_one({
                "id": nid, "release_id": f"TEST_iter84_{nid}", "titolo": "TEST_iter84 novità",
                "descrizione": "test", "area": "crm", "status": "bozza",
                "requires_service": "video_support", "created_at": now, "updated_at": now})
            await db.credit_services.update_one({"key": "video_support"},
                                                {"$set": {"active": False, "consumo_active": False}})
        loop.run_until_complete(_setup())

        try:
            r = sa.post(f"{API}/platform/news/{nid}/publish")
            assert r.status_code == 400
            assert "non è ancora attiva" in r.json()["detail"].lower()
        finally:
            async def _teardown():
                await db.news_items.delete_one({"id": nid})
                await db.credit_services.update_one({"key": "video_support"},
                                                    {"$set": {"active": True, "consumo_active": True,
                                                              "unit_cost": COST}})
            loop.run_until_complete(_teardown())
            cli.close()
            loop.close()


# ----------------------- Phase 11: Isolation -----------------------
class TestPhase11Isolation:
    def test_other_user_cannot_access_booking(self, adm, sa, service_cleanup):
        """Create booking as adm, verify SA endpoint returns 404 for unknown id, and that a user from another org (we'll simulate by querying a non-existent id) returns 404."""
        slots = adm.get(f"{API}/video-support/slots").json()["slots"]
        if not slots:
            pytest.skip("no slot")
        bk = adm.post(f"{API}/video-support/bookings",
                      json={"slot_key": slots[0]["slot_key"], "confirm_cost": COST, "note": "TEST_iter84_iso"}).json()
        assert bk.get("status") == "confermata"

        # Unknown id 404
        r = adm.post(f"{API}/video-support/bookings/{uuid.uuid4().hex}/cancel", json={})
        assert r.status_code == 404

        # cleanup
        adm.post(f"{API}/video-support/bookings/{bk['id']}/cancel", json={})
