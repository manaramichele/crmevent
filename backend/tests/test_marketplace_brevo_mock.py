"""Mock Brevo: verifica attributi per servizio, payload contatto (nessuna lista), verify/resync. Nessuna chiamata reale."""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
import sys  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import brevo_funnel  # noqa: E402
import marketplace  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

calls, attrs = [], {"NOME": "text", "COGNOME": "text", "ORGANIZZAZIONE": "text"}


async def fake(method, path, *, json=None, params=None):
    calls.append((method, path, json))
    if method == "GET" and path == "/v3/contacts/attributes":
        return 200, {"attributes": [{"name": k, "type": v, "category": "normal"} for k, v in attrs.items()]}, None
    if method == "POST" and path.startswith("/v3/contacts/attributes/normal/"):
        attrs[path.rsplit("/", 1)[1]] = json["type"]
        return 201, None, None
    if method == "POST" and path == "/v3/contacts":
        return 204, None, None
    return 404, None, "nf"


async def main():
    brevo_funnel._request = fake
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    async def dep():
        return {}

    async def audit(*a, **k):
        pass

    r = marketplace.build(db, {k: dep for k in ("require_admin", "require_superadmin", "ensure_customer", "billing_missing", "record_invoice", "emit_invoice")}
                          | {"record_audit": audit, "stripe_mode": "test"})
    ep = {x.path: x.endpoint for x in r["router"].routes}
    await ep["/api/marketplace/services"](user={"org_id": "TEST_org", "user_id": "TEST_u"})  # seed
    svcs = {s["key"]: s for s in await db.marketplace_services.find({"key": {"$in": ["survey", "gestione-societa"]}}, {"_id": 0}).to_list(5)}
    await db.users.insert_one({"user_id": "TEST_u", "nome": "Mario", "cognome": "Rossi", "email": "test_mkt@example.com"})
    user = {"org_id": "TEST_org", "user_id": "TEST_u", "name": "Mario Rossi", "email": "test_mkt@example.com"}
    try:
        for k in ("survey", "gestione-societa"):
            assert (await ep["/api/marketplace/services/{sid}/notify"](sid=svcs[k]["id"], user=user)) == {"notify_me": True}
        await asyncio.sleep(0.5)
        posts = [c[2] for c in calls if c[1] == "/v3/contacts"]
        assert len(posts) == 2, posts
        assert all("listIds" not in p and p["updateEnabled"] is True and p["email"] == "test_mkt@example.com" for p in posts)
        assert posts[0]["attributes"]["MKT_SURVEY"] is True and posts[0]["attributes"]["NOME"] == "Mario" and posts[0]["attributes"]["COGNOME"] == "Rossi"
        assert posts[1]["attributes"]["MKT_GESTIONE_SOCIETA"] is True and "MKT_SURVEY" not in posts[1]["attributes"]  # interessi precedenti conservati
        assert attrs["MKT_SURVEY"] == "boolean" and attrs["MKT_ULTIMA_RICHIESTA"] == "date"
        its = await db.marketplace_interests.find({"org_id": "TEST_org"}, {"_id": 0}).to_list(5)
        assert all(i["brevo_status"] == "sincronizzato" and i["created_at"] and i["org_id"] == "TEST_org" for i in its), its
        rep = await ep["/api/platform/marketplace/brevo/verify"](admin={})
        assert rep["all_ok"], rep
        await db.marketplace_interests.update_many({"org_id": "TEST_org"}, {"$set": {"brevo_status": "errore"}})
        assert (await ep["/api/platform/marketplace/brevo/resync"](admin={})) == {"synced": 2, "failed": 0}
        print("OK", [a["attribute"] for a in rep["attributes"]])
    finally:
        await db.marketplace_interests.delete_many({"org_id": "TEST_org"})
        await db.users.delete_one({"user_id": "TEST_u"})


asyncio.run(main())
