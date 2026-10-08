"""Iter 87 — Prenotazione Demo + Brevo Lead list sync + funnel gating.

Covers:
- POST /api/leads validation (privacy required, demo_slot/status, brevo_sync status in preview = non_configurato)
- Marketing consent sets marketing_consent_at; funnel not activated in preview (no double enrollment)
- Invalid demo date/time -> 400
- SA /leads/{id}/demo confirm/reschedule/cancel; 400 w/o slot; QA admin -> 403
- SA /leads/{id}/brevo-sync increments attempts
- demo_booking.tick: retry errored sync + reminder single-fire
"""
import os
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://manage-events-12.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SA_EMAIL = "manara.michele.pro@gmail.com"
SA_PASSWORD = "CrmEvent2026!"
QA_EMAIL = "qa.eventi@crmeventqa.it"
QA_PASSWORD = "QaEvents2026!"

TOMORROW = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
IN_3_DAYS = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")
TEST_PREFIX = "TEST_iter87_"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def sa():
    return _login(SA_EMAIL, SA_PASSWORD)


@pytest.fixture(scope="module")
def qa():
    return _login(QA_EMAIL, QA_PASSWORD)


@pytest.fixture(scope="module")
def created_lead_ids():
    ids = []
    yield ids
    # Cleanup via Mongo
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        import sys; sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]

        async def _cleanup():
            cli = AsyncIOMotorClient(mongo_url)
            db = cli[db_name]
            await db.leads.delete_many({"email": {"$regex": f"^{TEST_PREFIX}"}})
            await db.funnel_enrollments.delete_many({"email": {"$regex": f"^{TEST_PREFIX}"}})
            await db.audit_logs.delete_many({"target_email": {"$regex": f"^{TEST_PREFIX}"}})
            cli.close()

        asyncio.run(_cleanup())
    except Exception as e:
        print(f"cleanup warn: {e}")


# --- POST /api/leads ---
class TestCreateLead:
    def test_privacy_required(self):
        r = requests.post(f"{API}/leads", json={
            "nome": "Mario", "email": f"{TEST_PREFIX}noprivacy@example.com", "privacy": False
        }, timeout=30)
        assert r.status_code == 400
        assert "privacy" in r.text.lower()

    def test_create_with_demo_slot_no_marketing(self, created_lead_ids, sa):
        email = f"{TEST_PREFIX}demo1@example.com"
        r = requests.post(f"{API}/leads", json={
            "nome": "Luca", "cognome": "Rossi", "email": email, "telefono": "+39333",
            "privacy": True, "marketing_consent": False,
            "demo_data": TOMORROW, "demo_ora": "10:30",
            "source": "test",
        }, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        lead_id = data["id"]
        created_lead_ids.append(lead_id)

        # Fetch via SA
        r2 = sa.get(f"{API}/leads/{lead_id}", timeout=30)
        assert r2.status_code == 200, r2.text
        lead = r2.json()["lead"]
        assert lead["demo_slot"] == f"{TOMORROW}T10:30"
        assert lead["demo_status"] == "da_confermare"
        assert lead["marketing_consent"] is False
        assert lead.get("marketing_consent_at") in (None, "")
        bs = lead.get("brevo_sync") or {}
        assert bs.get("status") == "non_configurato", f"expected non_configurato, got {bs}"
        assert bs.get("attempts") == 1

    def test_create_with_marketing_consent(self, created_lead_ids, sa):
        email = f"{TEST_PREFIX}mkt@example.com"
        r = requests.post(f"{API}/leads", json={
            "nome": "Giulia", "email": email, "privacy": True, "marketing_consent": True,
            "demo_data": TOMORROW, "demo_ora": "11:00",
        }, timeout=30)
        assert r.status_code == 200, r.text
        lead_id = r.json()["id"]
        created_lead_ids.append(lead_id)
        lead = sa.get(f"{API}/leads/{lead_id}", timeout=30).json()["lead"]
        assert lead["marketing_consent"] is True
        assert lead.get("marketing_consent_at")
        # idempotency: second POST with same email should not fail even if funnel inactive
        r2 = requests.post(f"{API}/leads", json={
            "nome": "Giulia2", "email": email, "privacy": True, "marketing_consent": True,
            "demo_data": IN_3_DAYS, "demo_ora": "12:00",
        }, timeout=30)
        assert r2.status_code == 200, r2.text
        created_lead_ids.append(r2.json()["id"])

    def test_invalid_demo_datetime(self):
        r = requests.post(f"{API}/leads", json={
            "nome": "X", "email": f"{TEST_PREFIX}bad@example.com", "privacy": True,
            "demo_data": "not-a-date", "demo_ora": "10:00"
        }, timeout=30)
        assert r.status_code == 400
        r2 = requests.post(f"{API}/leads", json={
            "nome": "X", "email": f"{TEST_PREFIX}bad2@example.com", "privacy": True,
            "demo_data": TOMORROW, "demo_ora": "99:99"
        }, timeout=30)
        assert r2.status_code == 400

    def test_create_without_slot(self, created_lead_ids, sa):
        email = f"{TEST_PREFIX}noslot@example.com"
        r = requests.post(f"{API}/leads", json={
            "nome": "No", "email": email, "privacy": True
        }, timeout=30)
        assert r.status_code == 200
        lead_id = r.json()["id"]
        created_lead_ids.append(lead_id)
        lead = sa.get(f"{API}/leads/{lead_id}", timeout=30).json()["lead"]
        assert lead.get("demo_slot") in (None, "")
        assert lead.get("demo_status") in (None, "")


# --- SA demo actions ---
class TestDemoActions:
    def test_confirm_reschedule_cancel(self, created_lead_ids, sa, qa):
        assert created_lead_ids, "need a prior lead"
        lead_id = created_lead_ids[0]

        # QA admin forbidden
        rq = qa.post(f"{API}/leads/{lead_id}/demo", json={"action": "confirm"}, timeout=30)
        assert rq.status_code == 403, f"expected 403 for QA admin, got {rq.status_code}"

        # confirm
        r = sa.post(f"{API}/leads/{lead_id}/demo", json={"action": "confirm"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["demo_status"] == "confermata"

        # reschedule
        r = sa.post(f"{API}/leads/{lead_id}/demo", json={
            "action": "reschedule", "demo_data": IN_3_DAYS, "demo_ora": "15:00"
        }, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["demo_status"] == "riprogrammata"
        assert r.json()["demo_slot"] == f"{IN_3_DAYS}T15:00"

        # reschedule without date -> 400
        r = sa.post(f"{API}/leads/{lead_id}/demo", json={"action": "reschedule"}, timeout=30)
        assert r.status_code == 400

        # cancel
        r = sa.post(f"{API}/leads/{lead_id}/demo", json={"action": "cancel"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["demo_status"] == "annullata"

    def test_confirm_without_slot_400(self, created_lead_ids, sa):
        # Find the no-slot lead (last in list likely)
        no_slot_id = None
        for lid in created_lead_ids:
            lead = sa.get(f"{API}/leads/{lid}", timeout=30).json()["lead"]
            if not lead.get("demo_slot"):
                no_slot_id = lid
                break
        assert no_slot_id, "need a no-slot lead"
        r = sa.post(f"{API}/leads/{no_slot_id}/demo", json={"action": "confirm"}, timeout=30)
        assert r.status_code == 400

    def test_brevo_sync_increments_attempts(self, created_lead_ids, sa):
        lead_id = created_lead_ids[0]
        before = sa.get(f"{API}/leads/{lead_id}", timeout=30).json()["lead"]
        before_attempts = (before.get("brevo_sync") or {}).get("attempts", 0)
        r = sa.post(f"{API}/leads/{lead_id}/brevo-sync", json={}, timeout=30)
        assert r.status_code == 200, r.text
        state = r.json()
        assert state["attempts"] == before_attempts + 1
        assert state["status"] == "non_configurato"


# --- Cron / demo_booking.tick ---
class TestDemoBookingTick:
    def test_tick_retries_errored_and_reminder_once(self):
        """Seed TEST_ lead with errore+1h ago, run tick, verify attempts incremented.
        Also seed a confermata lead with slot in 23h and verify demo_reminder_sent_for set once."""
        import sys
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        from motor.motor_asyncio import AsyncIOMotorClient
        import demo_booking as db_mod
        from zoneinfo import ZoneInfo

        mongo_url = os.environ["MONGO_URL"]
        db_name = os.environ["DB_NAME"]

        async def _run():
            cli = AsyncIOMotorClient(mongo_url)
            db = cli[db_name]
            now = datetime.now(timezone.utc)
            two_hours_ago = (now - timedelta(hours=2)).isoformat()
            # Lead with sync error
            err_id = f"{TEST_PREFIX}tick_err"
            err_doc = {
                "id": err_id, "email": f"{TEST_PREFIX}tickerr@example.com", "nome": "Err",
                "privacy": True, "requested_at": now.isoformat(),
                "brevo_sync": {"status": "errore", "attempts": 1, "last_attempt_at": two_hours_ago, "error": "test"},
            }
            await db.leads.delete_one({"id": err_id})
            await db.leads.insert_one(dict(err_doc))

            # Lead confirmed with slot within 24h
            rome = ZoneInfo("Europe/Rome")
            slot_dt = now.astimezone(rome) + timedelta(hours=20)
            slot = slot_dt.strftime("%Y-%m-%dT%H:%M")
            rem_id = f"{TEST_PREFIX}tick_rem"
            rem_doc = {
                "id": rem_id, "email": f"{TEST_PREFIX}tickrem@example.com", "nome": "Rem",
                "privacy": True, "demo_slot": slot, "demo_status": "confermata",
            }
            await db.leads.delete_one({"id": rem_id})
            await db.leads.insert_one(dict(rem_doc))

            # Run tick
            app_url = os.environ.get("APP_URL", "https://manage-events-12.preview.emergentagent.com")
            await db_mod.tick(db, app_url)

            err_after = await db.leads.find_one({"id": err_id})
            rem_after = await db.leads.find_one({"id": rem_id})

            # Second tick -> reminder must NOT be re-sent (field unchanged)
            await db_mod.tick(db, app_url)
            rem_after2 = await db.leads.find_one({"id": rem_id})

            # Cleanup
            await db.leads.delete_many({"id": {"$in": [err_id, rem_id]}})
            cli.close()
            return err_after, rem_after, rem_after2, slot

        err_after, rem_after, rem_after2, slot = asyncio.run(_run())
        assert (err_after.get("brevo_sync") or {}).get("attempts") == 2, err_after.get("brevo_sync")
        assert rem_after.get("demo_reminder_sent_for") == slot, rem_after
        # Second tick should not change the marker (still equal to slot, single-fire by design)
        assert rem_after2.get("demo_reminder_sent_for") == slot


# --- Cron endpoint auth ---
class TestCronEndpoint:
    def test_cron_unauthorized(self):
        r = requests.post(f"{API}/cron/brevo-funnel-tick", timeout=30)
        assert r.status_code == 401

    def test_cron_with_secret(self):
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
        assert secret
        r = requests.post(f"{API}/cron/brevo-funnel-tick",
                          headers={"Authorization": f"Bearer {secret}"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("accepted") is True
