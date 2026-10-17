"""Verifica Brevo Tracker con Brevo simulato (nessuna chiamata reale). Uso: python tests/check_brevo_tracker.py <email_test>"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import brevo_funnel  # noqa: E402
import brevo_tracker  # noqa: E402

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
SENT = []


async def fake_request(method, path, json=None, params=None):
    SENT.append((method, path, json))
    return 204, None, None


async def main(email):
    print("log reali:", [(d["event"], d["status"]) async for d in db.brevo_tracker_log.find({"email": email})])
    u = await db.users.find_one({"email": email}, {"_id": 0})
    org = await db.organizations.find_one({"id": u["org_id"]}, {"_id": 0})
    brevo_funnel.is_configured = lambda: True
    brevo_funnel._request = fake_request

    async def state_for(oid):
        return {"enabled": True, "org_type": "cliente", "sub_status": "trial", "plan_label": "GOLD", "expires_at": "2026-10-31"}
    async def _dep():
        return {}
    t = brevo_tracker.build(db, {"state_for": state_for, "get_current_user": _dep, "require_superadmin": _dep})
    await db.brevo_tracker_once.delete_many({"org_id": org["id"]})
    t["track"]("login_completed", u["user_id"], org["id"], {"method": "password"})
    inv = {"id": "in_TEST_BRT_1", "total": 1990, "currency": "eur"}
    await t["on_payment"](org, inv, "silver", "monthly", True)
    await t["on_payment"](org, inv, "silver", "monthly", True)  # duplicato webhook
    await asyncio.sleep(1)
    await db.invoices.insert_one({"org_id": org["id"], "kind": "saas_subscription", "payment_status": "paid", "stripe_invoice_id": "in_TEST_BRT_1"})
    await t["on_payment"](org, {"id": "in_TEST_BRT_2", "total": 1990, "currency": "eur"}, "silver", "monthly", True)
    await asyncio.sleep(1)
    names = [b["event_name"] for _, p, b in SENT if p == "/v3/events"]
    print("eventi inviati (mock):", names)
    assert names.count("subscription_started") == 1 and names.count("subscription_renewed") == 1 and "login_completed" in names
    b = SENT[0][2]
    print("payload esempio:", {k: b[k] for k in ("event_name", "identifiers", "contact_properties", "event_properties")})
    assert b["identifiers"] == {"email_id": email}
    await db.invoices.delete_many({"stripe_invoice_id": {"$in": ["in_TEST_BRT_1"]}})
    print("OK")


asyncio.run(main(sys.argv[1]))
