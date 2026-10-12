"""Test simulato sincronizzazione abbonamenti → Brevo (nessuna chiamata reale)."""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

import brevo_funnel  # noqa: E402
import brevo_subscriptions as BS  # noqa: E402
import subscriptions as S  # noqa: E402

calls = []


async def fake_request(method, path, json=None, params=None):
    calls.append((method, path, json))
    if path == "/v3/contacts/attributes":
        return 200, {"attributes": [{"name": "NOME"}, {"name": "CRM_PIANO"}]}, None
    return 201, None, None


def _iso(d):
    return d.isoformat()


async def _scenario():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:6]
    uid, email = f"TEST_u_{tag}", f"test_bs_{tag}@example.com"
    o1, o2 = f"TEST_o1_{tag}", f"TEST_o2_{tag}"
    saas_active = {"plan": "silver", "billing_cycle": "semester", "stripe_status": "active", "cancel_at_period_end": True,
                   "current_period_end": _iso(now + timedelta(days=20)), "activated_at": _iso(now - timedelta(days=160)), "trial_end": _iso(now - timedelta(days=200))}
    saas_auto = {**saas_active, "plan": "gold", "billing_cycle": "yearly", "cancel_at_period_end": False, "current_period_end": _iso(now + timedelta(days=200))}
    await db.users.insert_one({"user_id": uid, "email": email, "name": "Test"})
    await db.organizations.insert_many([{"id": o1, "nome": "TEST_Org1", "type": "cliente", "saas": saas_active},
                                        {"id": o2, "nome": "TEST_Org2", "type": "cliente", "saas": saas_auto}])
    await db.memberships.insert_many([{"user_id": uid, "org_id": o1, "role": "admin_org", "active": True},
                                      {"user_id": uid, "org_id": o2, "role": "admin_org", "active": True},
                                      {"user_id": "TEST_member", "org_id": o1, "role": "user", "active": True}])
    cfg = S.DEFAULT_CONFIG

    async def state_for(oid):
        return S.org_state(await db.organizations.find_one({"id": oid}, {"_id": 0}), cfg)

    b = BS.build(db, {"state_for": state_for, "require_superadmin": lambda: None, "record_audit": None})
    try:
        r1 = await b["sync_org"](o1)
        ups = [c[2] for c in calls if c[1] == "/v3/contacts"]
        created = [c[1].rsplit("/", 1)[1] for c in calls if "/attributes/normal/" in c[1]]
        doc = await db.saas_brevo_sync.find_one({"org_id": o1}, {"_id": 0})
        # rinnovo: la scadenza di Org1 si sposta → il contatto passa alla scadenza più vicina (Org2 è più lontana) ma resta Org1 aggiornata
        await db.organizations.update_one({"id": o1}, {"$set": {"saas.current_period_end": _iso(now + timedelta(days=380)), "saas.cancel_at_period_end": False}})
        calls.clear()
        d = await b["daily"]()
        ups2 = [c[2] for c in calls if c[1] == "/v3/contacts"]
        calls.clear()
        d2 = await b["daily"]()
        return r1, ups, created, doc, ups2, d, d2
    finally:
        await db.users.delete_one({"user_id": uid})
        await db.organizations.delete_many({"id": {"$in": [o1, o2]}})
        await db.memberships.delete_many({"org_id": {"$in": [o1, o2]}})
        await db.saas_brevo_sync.delete_many({"org_id": {"$in": [o1, o2]}})


def test_subscription_sync():
    brevo_funnel._request = fake_request
    brevo_funnel.is_configured = lambda: True
    r1, ups, created, doc, ups2, d, d2 = asyncio.run(_scenario())
    assert r1["ok"] and r1["recipients"] == 1
    assert "CRM_PIANO" not in created and set(created) == set(BS.ATTRS) - {"CRM_PIANO"}
    a = ups[0]["attributes"]
    assert ups[0]["updateEnabled"] is True and "listIds" not in ups[0]
    assert a["CRM_ORG_ID"].startswith("TEST_o1_") and a["CRM_STATO"] == "In scadenza" and a["CRM_PIANO"] == "SILVER"
    assert a["CRM_DURATA"] == 6 and a["CRM_RINNOVO_AUTO"] is False and len(a["CRM_SCADENZA"]) == 10
    assert doc["status"] == "ok"
    # dopo il rinnovo: contatto unico aggiornato, scadenza più vicina = Org2 (200 gg) rispetto a Org1 (380 gg)
    assert ups2 and all(u["attributes"]["CRM_ORG_ID"].startswith("TEST_o2_") for u in ups2 if u["email"].startswith("test_bs_"))
    assert any(u["email"].startswith("test_bs_") for u in ups2)
    assert d["synced"] >= 1 and d2["synced"] == 0
