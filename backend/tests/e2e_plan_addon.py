"""E2E (Stripe TEST) per il modulo annuale aggiunto al piano. Crea e poi rimuove tutto ciò che crea."""
import asyncio
import os
import sys
import time
from datetime import datetime, timezone

import requests
import stripe
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0] + "/api"
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
import server  # noqa: E402  (stessa chiave Stripe dell'app)
stripe.api_key = server.stripe_sdk.api_key
assert server.STRIPE_MODE == "test"


async def main():
    s = requests.Session()
    email = f"test_addon_{int(time.time())}@example.com"
    r = s.post(f"{API}/auth/register-organization", json={"nome": "Test", "cognome": "Addon", "email": email, "password": "TestPass123!",
                                                           "org_name": "TEST_Addon Org", "telefono": "+39 333 123 4567", "accept_terms": True})
    oid = r.json()["org_id"]
    price = (await db.saas_stripe_prices.find_one({"kind": "price", "plan": "gold", "cycle": "yearly", "mode": "test"}))["price_id"]
    clock = stripe.test_helpers.TestClock.create(frozen_time=int(time.time()))
    cust = stripe.Customer.create(email=email, name="TEST Addon", test_clock=clock.id)
    pm = stripe.PaymentMethod.attach("pm_card_visa", customer=cust.id)
    stripe.Customer.modify(cust.id, invoice_settings={"default_payment_method": pm.id})
    sub = stripe.Subscription.create(customer=cust.id, items=[{"price": price}], metadata={"kind": "saas", "org_id": oid, "plan": "gold", "cycle": "yearly"})
    stripe.test_helpers.TestClock.advance(clock.id, frozen_time=int(time.time()) + 182 * 86400)
    for _ in range(40):
        if stripe.test_helpers.TestClock.retrieve(clock.id).status == "ready":
            break
        time.sleep(2)
    sub = stripe.Subscription.retrieve(sub.id)
    it = sub["items"]["data"][0]
    cps, cpe = it["current_period_start"], it["current_period_end"]
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()  # noqa: E731
    await db.organizations.update_one({"id": oid}, {"$set": {
        "subscription.stripe_customer_id": cust.id, "saas.plan": "gold", "saas.billing_cycle": "yearly", "saas.stripe_status": "active",
        "saas.stripe_subscription_id": sub.id, "saas.current_period_start": iso(cps), "saas.current_period_end": iso(cpe),
        "billing": {"tipo": "azienda", "paese": "IT", "ragione_sociale": "TEST Srl", "partita_iva": "01234567890", "indirizzo": "Via Roma 1", "cap": "00100",
                    "citta": "Roma", "provincia": "RM", "codice_sdi": "0000000", "email": email}}})
    svc_before = await db.marketplace_services.find_one({"key": "gestione-societa"}, {"_id": 0, "purchasable": 1, "status": 1})
    try:
        q0 = s.get(f"{API}/marketplace/plan-addon/quote").json()
        print("quote (acquisto spento):", q0.get("purchasable"), q0.get("days_left"), q0.get("amount"), q0.get("blocked"))
        print("purchase spento:", s.post(f"{API}/marketplace/plan-addon/purchase", json={"confirm_amount": 0}).status_code)
        await db.marketplace_services.update_one({"key": "gestione-societa"}, {"$set": {"purchasable": True, "status": "available"}})
        q = s.get(f"{API}/marketplace/plan-addon/quote").json()
        print("quote:", q["days_left"], q["period_days"], q["amount"], "stripe:", q.get("amount_due"), q.get("amount_net"))
        print("wrong amount:", s.post(f"{API}/marketplace/plan-addon/purchase", json={"confirm_amount": 1.23}).status_code)
        bad = stripe.PaymentMethod.attach("pm_card_chargeCustomerFail", customer=cust.id)
        stripe.Customer.modify(cust.id, invoice_settings={"default_payment_method": bad.id})
        f = s.post(f"{API}/marketplace/plan-addon/purchase", json={"confirm_amount": q["amount_due"]})
        print("failed payment:", f.status_code, f.json().get("detail"), "items:", len(stripe.Subscription.retrieve(sub.id)["items"]["data"]),
              "purchases:", await db.marketplace_purchases.count_documents({"org_id": oid}))
        stripe.Customer.modify(cust.id, invoice_settings={"default_payment_method": pm.id})
        b = s.post(f"{API}/marketplace/plan-addon/purchase", json={"confirm_amount": q["amount_due"]})
        print("purchase:", b.status_code, (b.json().get("purchase") or b.json()).get("current_period_end") if b.ok else b.text)
        print("double purchase:", s.post(f"{API}/marketplace/plan-addon/purchase", json={"confirm_amount": q["amount_due"]}).status_code)
        sub2 = stripe.Subscription.retrieve(sub.id)
        print("items in plan sub:", len(sub2["items"]["data"]), "same period end:", sub2["items"]["data"][-1]["current_period_end"] == cpe)
        invs = stripe.Invoice.list(subscription=sub.id, limit=5)
        print("invoices:", [(i["billing_reason"], i["amount_paid"]) for i in invs["data"]])
        print("semester change blocked:", s.post(f"{API}/saas/change", json={"plan": "gold", "cycle": "semester"}).json().get("detail"))
        print("renewal off:", s.post(f"{API}/marketplace/plan-addon/renewal", params={"renew": "false"}).json())
        sub3 = stripe.Subscription.retrieve(sub.id)
        print("items after off:", len(sub3["items"]["data"]))
        print("quote after off:", s.get(f"{API}/marketplace/plan-addon/quote").json()["purchase"]["status"])
        print("renewal on:", s.post(f"{API}/marketplace/plan-addon/renewal", params={"renew": "true"}).json(), len(stripe.Subscription.retrieve(sub.id)["items"]["data"]))
        print("upcoming renewal lines:", [(ln["description"], ln["amount"]) for ln in stripe.Invoice.create_preview(customer=cust.id, subscription=sub.id)["lines"]["data"]])
        stripe.Subscription.cancel(sub.id)
        import plan_addons
        await server.PLAN_ADDONS["sync_from_event"]("customer.subscription.deleted", stripe.Subscription.retrieve(sub.id))
        p = await db.marketplace_purchases.find_one({"org_id": oid, "source": "plan_addon"}, {"_id": 0, "status": 1})
        print("after plan cancel:", p)
    finally:
        await db.marketplace_services.update_one({"key": "gestione-societa"}, {"$set": svc_before})
        for c in await db.list_collection_names():
            await db[c].delete_many({"org_id": oid})
        await db.organizations.delete_one({"id": oid})
        await db.users.delete_many({"email": email})
        try:
            stripe.test_helpers.TestClock.delete(clock.id)
        except Exception:
            pass
        print("cleanup ok", await db.marketplace_services.find_one({"key": "gestione-societa"}, {"_id": 0, "purchasable": 1, "status": 1}))


asyncio.run(main())
